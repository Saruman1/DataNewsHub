from flask import Flask, render_template, jsonify, request, session
from flask_cors import CORS
from collections import defaultdict
from jinja2 import Template
import psycopg2
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import matplotlib
from email.mime.text import MIMEText

matplotlib.use("Agg")  # Використовуємо бекенд без графічного інтерфейсу
import matplotlib.pyplot as plt
import pdfkit
from datetime import datetime, timedelta
import base64
import io
import asyncio
import aiohttp
import google.generativeai as genai
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Створюємо конфігурацію для pdfkit
config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

API_KEY = os.getenv("NEWS_API_KEY")
DB_CONFIG = {
    "dbname": "newsdb",
    "user": "postgres",
    "password": os.getenv("BD_PASSWORD"),
    "host": "localhost",
}

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Model initialization
model = genai.GenerativeModel("gemini-1.5-flash")

yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

categories = [
    "business",
    "entertainment",
    "general",
    "health",
    "science",
    "sports",
    "technology",
]

translations = {
    "uk": {
        "report_title": "Звіт за",
        "graph_title": "Графік розподілу новин",
        "news_list": "Список новин",
        "category_label": "Категорія",
        "footer": "Створено автоматично системою NewsAnalyzer™",
        "contents": "Зміст",
        "at": "о",
        "by": "джерело",
        "email_body": "У вкладенні ви знайдете звіт із новинами за обрану дату.",
    },
    "en": {
        "report_title": "Report for",
        "graph_title": "News distribution graph",
        "news_list": "List of news",
        "category_label": "Category",
        "footer": "Generated automatically by NewsAnalyzer™",
        "contents": "Contents",
        "at": "at",
        "by": "source",
        "email_body": "Please find attached the news report for the selected date.",
    },
    "pl": {
        "report_title": "Raport za",
        "graph_title": "Wykres rozkładu wiadomości",
        "news_list": "Lista wiadomości",
        "category_label": "Kategoria",
        "footer": "Wygenerowano automatycznie przez system NewsAnalyzer™",
        "contents": "Spis treści",
        "at": "o",
        "by": "źródło",
        "email_body": "W załączniku znajdziesz raport wiadomości dla wybranej daty.",
    },
}


def db_connect():
    """Establishes and returns a connection to the PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG)


def get_locale():
    lang = request.headers.get("Accept-Language", "en").lower()
    if lang.startswith("uk"):
        return "uk"
    elif lang.startswith("pl"):
        return "pl"
    else:
        return "en"


def save_news(title, description, url, source, published_at, category):
    """Saves a news article to the database, ignoring duplicates based on the URL."""
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO news (title, description, url, source, published_at, category)
               VALUES (%s, %s, %s, %s, %s, %s) 
               ON CONFLICT (url) DO NOTHING""",
            (title, description, url, source, published_at, category),
        )
        conn.commit()
    except Exception as e:
        print("Error saving the news:", e)
    finally:
        cursor.close()
        conn.close()


def news_exists_for(category, date):
    """Checks if any news articles exist in the database for the given category and date.

    Args:
        category (str): The news category.
        date (str): Date in YYYY-MM-DD format.

    Returns:
        bool: True if news exists, False otherwise."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM news WHERE category = %s AND DATE(published_at) = %s LIMIT 1",
        (category, date),
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


async def fetch_news_for_category_date(session, category, date):
    """Fetches news from the API for a specific category and date.

    Args:
        session (aiohttp.ClientSession): The HTTP session.
        category (str): The category of news.
        date (str): Date string in YYYY-MM-DD format.

    Returns:
        list: A list of (article, category) tuples.
    """
    if news_exists_for(category, date):
        print(f"⏭ Skip {category} {date} — already in database")
        return []

    url = f"https://newsapi.org/v2/everything?q={category}&from={date}&to={date}&language=en&apiKey={API_KEY}"
    try:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"❌ API error for {category}, {date}: {response.status}")
                return []
            data = await response.json()
            articles = data.get("articles", [])
            return [(article, category) for article in articles]
    except Exception as e:
        print(f"❌ Request is broken: {e}")
        return []


async def async_fetch_and_store_news():
    """Asynchronously fetches news for each category over the past 7 days
    and stores them in the database.
    """
    tasks = []
    async with aiohttp.ClientSession() as session:
        for day_delta in range(7):
            date = (datetime.now() - timedelta(days=day_delta)).strftime("%Y-%m-%d")
            for category in categories:
                tasks.append(fetch_news_for_category_date(session, category, date))

        results = await asyncio.gather(*tasks)  # run all queries in parallel

        for article_list in results:
            for article, category in article_list:
                title = article.get("title")
                description = article.get("description")
                url = article.get("url")
                source = article.get("source", {}).get("name")
                published_at = article.get("publishedAt")

                if title and url and source and published_at:
                    save_news(title, description, url, source, published_at, category)

    print("✅ News for the last week has been uploaded.")


def fetch_and_store_news():
    """Runs the asynchronous function to fetch and store news in sync context."""
    asyncio.run(async_fetch_and_store_news())


def generate_chart(date):
    """Generates a bar chart of news counts per category for a given date.

    Args:
        date (str): Date in YYYY-MM-DD format.

    Returns:
        BytesIO: In-memory binary stream containing PNG image, or None.
    """
    try:
        # Check data format
        datetime.strptime(date, "%Y-%m-%d")

        conn = db_connect()
        if conn is None:
            return None

        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, COUNT(*) FROM news WHERE DATE(published_at) = %s GROUP BY category",
            (date,),
        )
        result = cursor.fetchall()
        conn.close()

        if not result:
            return None

        categories, counts = zip(*result)
        plt.figure(figsize=(10, 5))
        plt.bar(categories, counts, color="#4f46e5")
        plt.xlabel("Categories")
        plt.ylabel("Number of news items")
        plt.title(f"News for {date}")
        plt.xticks(rotation=45)

        img_stream = io.BytesIO()
        plt.savefig(img_stream, format="png")
        plt.close()  # Avoiding memory leaks
        img_stream.seek(0)

        return img_stream
    except Exception as e:
        print(f"Error in generate_chart: {e}")
        return None


def get_news_by_date(date):
    """Retrieves a list of news (title and url) published on a specific date.

    Args:
        date (str): Date string in YYYY-MM-DD format.

    Returns:
        list: List of tuples containing (title, url).
    """
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, url, category, published_at, source FROM news WHERE DATE(published_at) = %s",
        (date,),
    )
    news = cursor.fetchall()
    conn.close()
    return news


def generate_pdf(date, news, config):
    """Generates a PDF report containing news list and chart.

    Args:
        date (str): The date for which to generate the report.
        news (list): List of news tuples.
        config (pdfkit.configuration): PDF generation configuration.

    Returns:
        str: File path to the generated PDF.
    """
    chart_stream = generate_chart(date)
    if chart_stream is None:
        return None

    chart_base64 = base64.b64encode(chart_stream.getvalue()).decode("utf-8")

    # Detect lenguage
    locale = get_locale()
    t = translations[locale]

    news_by_category = defaultdict(list)
    for title, url, category, published_at, source in news:
        time_str = published_at.strftime("%H:%M")
        news_by_category[category].append(
            {"title": title, "url": url, "time": time_str, "source": source}
        )

    with open("templates/report_template.html", "r", encoding="utf-8") as f:
        template_str = f.read()

    template = Template(template_str)
    rendered_html = template.render(
        date=date,
        chart_base64=chart_base64,
        categories=sorted(news_by_category.keys()),
        news_by_category=dict(sorted(news_by_category.items())),
        t=t,  # pass translations
    )

    pdf_path = f"reports/report_{date}.pdf"
    pdfkit.from_string(rendered_html, pdf_path, configuration=config)
    return pdf_path


def get_news_context(date=None, category=None):
    conn = db_connect()
    cursor = conn.cursor()

    categories = []

    if category and category.lower() != "All categories":
        categories = [category]
    else:
        # Отримуємо всі унікальні категорії з бази
        cursor.execute("SELECT DISTINCT category FROM news")
        categories = [row[0] for row in cursor.fetchall()]

    full_output = []

    for cat in categories:
        query = """
            SELECT title, description
            FROM news
            WHERE title IS NOT NULL AND description IS NOT NULL
              AND title != '' AND description != ''
              AND category = %s
        """
        params = [cat]

        if date:
            query += " AND DATE(published_at) = %s"
            params.append(date)

        query += " ORDER BY published_at DESC"
        cursor.execute(query, tuple(params))
        articles = cursor.fetchall()

        if not articles:
            continue

        # Додаємо заголовок категорії
        full_output.append(f"\n### 🗂 Category: {cat.capitalize()}")

        for i, (title, description) in enumerate(articles, start=1):
            full_output.append(
                f"""📌 {i}.
                **Title:** {title}  
                **Description:** {description}
                """
            )

    cursor.close()
    conn.close()

    return "\n\n".join(full_output)


def send_email(recipient, pdf_path):
    """Sends a report PDF file via email.

    Args:
        recipient (str): The recipient's email address.
        pdf_path (str): Path to the PDF file to send.
    """
    sender_email = "georgekeron39@gmail.com"
    sender_password = "rixg wlno uvhf zupa"  # App Password

    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return

    # Отримуємо дату з назви файлу
    date_str = os.path.basename(pdf_path).replace("report_", "").replace(".pdf", "")
    filename = f"DailyNewsReport_{date_str}.pdf"

    # Визначення мови
    locale = get_locale()
    t = translations.get(locale, translations["en"])

    # Формуємо повідомлення
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = f"{t['report_title']} {date_str}"

    body = f"{t['email_body']}\n\n{t['footer']}"
    msg.attach(MIMEText(body, "plain"))

    # Додаємо PDF
    with open(pdf_path, "rb") as f:
        attach = MIMEBase("application", "octet-stream")
        attach.set_payload(f.read())
        encoders.encode_base64(attach)
        attach.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(attach)

    # Відправка через SMTP з логами
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.set_debuglevel(1)  # 👀 показати SMTP лог
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


@app.route("/")
def index():
    """Root route that fetches and stores the latest news, then renders the homepage."""
    fetch_and_store_news()
    return render_template("index.html")


@app.route("/send-report", methods=["POST"])
def send_report():
    """Receives a date and email from the form, generates a report and sends it via email.

    Returns:
        Response: JSON response with a success or error message.
    """
    try:
        date = request.form["date"]
        email = request.form["email"]

        news = get_news_by_date(date)

        if not news:
            return jsonify({"message": "No data for this date."}), 404

        pdf_path = generate_pdf(date, news, config)

        if not pdf_path:
            return jsonify({"message": "Failed to create PDF."}), 500

        send_email(email, pdf_path)

        return jsonify({"message": "✅ Email sent!"})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/news-by-date")
def news_by_date():
    """Returns JSON of news articles filtered by a specific date.

    Query Params:
        date (str): The date to filter news.

    Returns:
        JSON: List of news articles.
    """
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE DATE(published_at) = %s ORDER BY published_at DESC",
        (date,),
    )
    news = cursor.fetchall()
    conn.close()
    return jsonify(
        [
            {
                "title": n[0],
                "description": n[1],
                "url": n[2],
                "source": n[3],
                "published_at": n[4],
            }
            for n in news
        ]
    )


@app.route("/news-by-category")
def news_by_category():
    """Returns JSON of latest news articles filtered by category.

    Query Params:
        category (str): The category to filter news.

    Returns:
        JSON: List of news articles.
    """
    category = request.args.get("category")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE category = %s ORDER BY published_at DESC LIMIT 20",
        (category,),
    )
    news = cursor.fetchall()
    conn.close()
    return jsonify(
        [
            {
                "title": n[0],
                "description": n[1],
                "url": n[2],
                "source": n[3],
                "published_at": n[4],
            }
            for n in news
        ]
    )


@app.route("/news-by-category-and-date")
def news_by_category_and_date():
    """Returns JSON of news articles filtered by both category and date.

    Query Params:
        category (str): The category.
        date (str): The date.

    Returns:
        JSON: List of news articles.
    """
    category = request.args.get("category")
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE category = %s AND DATE(published_at) = %s ORDER BY published_at DESC",
        (category, date),
    )
    news = cursor.fetchall()
    conn.close()
    return jsonify(
        [
            {
                "title": n[0],
                "description": n[1],
                "url": n[2],
                "source": n[3],
                "published_at": n[4],
            }
            for n in news
        ]
    )


@app.route("/weekly-data")
def weekly_data():
    """Returns JSON of the number of news per day for the past week.

    Returns:
        JSON: Date -> count mapping.
    """
    conn = db_connect()
    cursor = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    cursor.execute(
        """
        SELECT DATE(published_at), COUNT(*) 
        FROM news 
        WHERE DATE(published_at) >= %s 
        GROUP BY DATE(published_at)
        ORDER BY DATE(published_at)
    """,
        (week_ago,),
    )
    result = cursor.fetchall()
    conn.close()
    return jsonify({str(r[0]): r[1] for r in result})


@app.route("/daily-data")
def daily_data():
    """Returns JSON of news count per category for a specific day.

    Query Params:
        date (str): The date.

    Returns:
        JSON: Category -> count mapping.
    """
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT category, COUNT(*) FROM news WHERE DATE(published_at) = %s GROUP BY category",
        (date,),
    )
    result = dict(cursor.fetchall())
    conn.close()
    return jsonify({cat: result.get(cat, 0) for cat in categories})


@app.route("/search")
def search_news():
    query = request.args.get("q", "").strip().lower()
    date = request.args.get("date", "").strip()

    if not query:
        return jsonify([])

    conn = db_connect()
    cursor = conn.cursor()

    base_query = """
        SELECT title, description, url
        FROM news
        WHERE (LOWER(title) LIKE %s OR LOWER(description) LIKE %s)
    """
    params = [f"%{query}%", f"%{query}%"]

    if date:
        base_query += " AND DATE(published_at) = %s"
        params.append(date)

    base_query += " ORDER BY published_at DESC LIMIT 50"

    cursor.execute(base_query, tuple(params))
    results = cursor.fetchall()
    conn.close()

    news_list = []
    for title, description, url in results:
        news_list.append({"title": title, "description": description, "url": url})

    return jsonify(news_list)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message", "")
    date = data.get("date", "")  # YYYY-MM-DD
    category = data.get("category", "")  # optional

    if not msg or not date:
        return jsonify({"error": "Неповні дані"}), 400

    # Читаємо новини з БД за датою і категорією
    conn = db_connect()
    cursor = conn.cursor()
    if category:
        cursor.execute(
            """
            SELECT title, description FROM news
            WHERE DATE(published_at) = %s AND category = %s
            ORDER BY published_at DESC
            LIMIT 50
        """,
            (date, category),
        )
    else:
        cursor.execute(
            """
            SELECT title, description FROM news
            WHERE DATE(published_at) = %s
            ORDER BY published_at DESC
            LIMIT 50
        """,
            (date,),
        )
    articles = cursor.fetchall()
    cursor.close()
    conn.close()

    if not articles:
        return jsonify(
            {"response": "😕 Unfortunately, no news for this date was found."}
        )

    news_context = get_news_context(date=date, category=category)
    if not news_context:
        return jsonify({"response": "😕 No news found for the selected parameters."})

    # Зберігаємо історію чату
    history = session.get("chat_history", "")
    prompt = f"""
    News for {date} {f'in category {category}' if category else ''}:
    {news_context}

    {history}
    User: {msg}
    AI:
    """
    # print(news_context)

    response = model.generate_content(prompt).text.strip()

    # Оновлюємо сесію
    history += f"User: {msg}\nAI: {response}"
    session["chat_history"] = history[-5000:]

    return jsonify({"response": response})


if __name__ == "__main__":
    app.run(debug=True)
