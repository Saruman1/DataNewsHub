from flask import Flask, render_template, jsonify, request
import requests
import psycopg2
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import matplotlib
matplotlib.use('Agg')  # Використовуємо бекенд без графічного інтерфейсу
import matplotlib.pyplot as plt
import pdfkit
from datetime import datetime, timedelta
import base64
import io
import asyncio
import aiohttp

app = Flask(__name__)

# Створюємо конфігурацію для pdfkit
config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")

API_KEY = "09cbf1a103604d7e919c59b8783df2fb"
DB_CONFIG = {
    "dbname": "newsdb",
    "user": "postgres",
    "password": "abrakadabra",
    "host": "localhost"
}

yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

categories = ["business", "entertainment", "general", "health", "science", "sports", "technology"]


def db_connect():
    return psycopg2.connect(**DB_CONFIG)

def save_news(title, description, url, source, published_at, category):
    """Saves the news to the database, avoiding duplicates."""
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO news (title, description, url, source, published_at, category)
               VALUES (%s, %s, %s, %s, %s, %s) 
               ON CONFLICT (url) DO NOTHING""",
            (title, description, url, source, published_at, category)
        )
        conn.commit()
    except Exception as e:
        print("Error saving the news:", e)
    finally:
        cursor.close()
        conn.close()

def news_exists_for(category, date):
    """Checks if there are any news with this category for the specified date."""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM news WHERE category = %s AND DATE(published_at) = %s LIMIT 1",
        (category, date)
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None

async def fetch_news_for_category_date(session, category, date):
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
    asyncio.run(async_fetch_and_store_news())


def generate_chart(date):
    try:
        # Перевірка формату дати
        datetime.strptime(date, "%Y-%m-%d")

        conn = db_connect()
        if conn is None:
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT category, COUNT(*) FROM news WHERE DATE(published_at) = %s GROUP BY category", (date,))
        result = cursor.fetchall()
        conn.close()

        if not result:
            return None

        categories, counts = zip(*result)
        plt.figure(figsize=(10, 5))
        plt.bar(categories, counts, color='purple')
        plt.xlabel('Categories')
        plt.ylabel('Number of news items')
        plt.title(f'News for {date}')
        plt.xticks(rotation=45)

        img_stream = io.BytesIO()
        plt.savefig(img_stream, format='png')
        plt.close()  # Avoiding memory leaks
        img_stream.seek(0)

        return img_stream
    except Exception as e:
        print(f"Error in generate_chart: {e}")
        return None

def get_news_by_date(date):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT title, url FROM news WHERE DATE(published_at) = %s", (date,))
    news = cursor.fetchall()
    conn.close()
    return news

def generate_pdf(date, news, config):
    chart_stream = generate_chart(date)  # Generate a graph
    if chart_stream is None:
        return None  # If there is no data, no PDF is created

    # Convert a graph to base64 for embedding in HTML
    chart_base64 = base64.b64encode(chart_stream.getvalue()).decode("utf-8")

    news_html = "".join(f"<li><a href='{n[1]}'>{n[0]}</a></li>" for n in news)

    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Звіт за {date}</title>
    </head>
    <body>
        <h1>Report for {date}</h1>
        <h2>News distribution graph</h2>
        <img src="data:image/png;base64,{chart_base64}" alt="Graph" style="width:80%; height:auto;">
        <h2>List of news</h2>
        <ul>{news_html}</ul>
    </body>
    </html>
    """

    pdf_path = f"reports/report_{date}.pdf"
    pdfkit.from_string(html_content, pdf_path, configuration=config)

    return pdf_path

def send_email(recipient, pdf_path):
    sender_email = "georgekeron39@gmail.com"
    sender_password = "xapx qgaj mkju nrbf"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = "Report for the selected date"

    with open(pdf_path, "rb") as f:
        attach = MIMEBase("application", "octet-stream")
        attach.set_payload(f.read())
        encoders.encode_base64(attach)
        attach.add_header("Content-Disposition", f"attachment; filename={pdf_path}")
        msg.attach(attach)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, recipient, msg.as_string())
    server.quit()


@app.route("/")
def index():
    fetch_and_store_news()
    return render_template("index.html")

@app.route("/send-report", methods=["POST"])
def send_report():
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
        print("✅ Email sent!")

        return jsonify({"message": "Звіт надіслано!"})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/news-by-date")
def news_by_date():
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE DATE(published_at) = %s ORDER BY published_at DESC",
        (date,))
    news = cursor.fetchall()
    conn.close()
    return jsonify([{
        "title": n[0],
        "description": n[1],
        "url": n[2],
        "source": n[3],
        "published_at": n[4]
    } for n in news])


@app.route("/news-by-category")
def news_by_category():
    category = request.args.get("category")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT title, description, url, source, published_at FROM news WHERE category = %s ORDER BY published_at DESC LIMIT 20", (category,))
    news = cursor.fetchall()
    conn.close()
    return jsonify([{"title": n[0], "description": n[1], "url": n[2], "source": n[3], "published_at": n[4]} for n in news])

@app.route("/news-by-category-and-date")
def news_by_category_and_date():
    category = request.args.get("category")
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE category = %s AND DATE(published_at) = %s ORDER BY published_at DESC",
        (category, date))
    news = cursor.fetchall()
    conn.close()
    return jsonify([{
        "title": n[0],
        "description": n[1],
        "url": n[2],
        "source": n[3],
        "published_at": n[4]
    } for n in news])


@app.route("/weekly-data")
def weekly_data():
    conn = db_connect()
    cursor = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT DATE(published_at), COUNT(*) 
        FROM news 
        WHERE DATE(published_at) >= %s 
        GROUP BY DATE(published_at)
        ORDER BY DATE(published_at)
    """, (week_ago,))
    result = cursor.fetchall()
    conn.close()
    return jsonify({str(r[0]): r[1] for r in result})

@app.route("/daily-data")
def daily_data():
    date = request.args.get("date")
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT category, COUNT(*) FROM news WHERE DATE(published_at) = %s GROUP BY category", (date,))
    result = dict(cursor.fetchall())
    conn.close()
    return jsonify({cat: result.get(cat, 0) for cat in categories})



if __name__ == "__main__":
    app.run(debug=True)
