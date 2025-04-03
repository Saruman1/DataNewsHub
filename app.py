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
    """Зберігає новину в базу даних, уникаючи дублікатів."""
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
        print("Помилка при збереженні новини:", e)
    finally:
        cursor.close()
        conn.close()


def fetch_and_store_news():
    """Отримує новини через API для кожної категорії та зберігає їх у базу даних."""
    for category in categories:
        url = f"https://newsapi.org/v2/top-headlines?country=us&category={category}&language=en&apiKey={API_KEY}"
        response = requests.get(url)

        if response.status_code != 200:
            print(f"Помилка запиту до API для категорії {category}: {response.status_code}, {response.text}")
            continue

        data = response.json()
        articles = data.get("articles", [])

        for article in articles:
            title = article.get("title")
            description = article.get("description")
            url = article.get("url")
            source = article.get("source", {}).get("name")
            published_at = article.get("publishedAt")

            if title and url and source and published_at:  # Перевірка на відсутність порожніх полів
                save_news(title, description, url, source, published_at, category)


def get_news():
    """Отримує останні 10 новин з БД"""
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, url, source, published_at FROM news WHERE DATE(published_at) = %s ORDER BY published_at DESC LIMIT 10",
        (yesterday,))
    news = cursor.fetchall()
    conn.close()
    return [{"title": n[0], "description": n[1], "url": n[2], "source": n[3], "published_at": n[4]} for n in news]


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
        plt.xlabel('Категорії')
        plt.ylabel('Кількість новин')
        plt.title(f'Новини за {date}')
        plt.xticks(rotation=45)

        img_stream = io.BytesIO()
        plt.savefig(img_stream, format='png')
        plt.close()  # Уникнення витоку пам'яті
        img_stream.seek(0)

        return img_stream
    except Exception as e:
        print(f"Помилка у generate_chart: {e}")
        return None

def get_news_by_date(date):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT title, url FROM news WHERE DATE(published_at) = %s", (date,))
    news = cursor.fetchall()
    conn.close()
    return news

def generate_pdf(date, news, config):
    chart_stream = generate_chart(date)  # Генеруємо графік
    if chart_stream is None:
        return None  # Якщо немає даних, PDF не створюється

    # Конвертуємо графік у base64 для вставки в HTML
    chart_base64 = base64.b64encode(chart_stream.getvalue()).decode("utf-8")

    news_html = "".join(f"<li><a href='{n[1]}'>{n[0]}</a></li>" for n in news)

    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Звіт за {date}</title>
    </head>
    <body>
        <h1>Звіт за {date}</h1>
        <h2>Графік розподілу новин</h2>
        <img src="data:image/png;base64,{chart_base64}" alt="Графік" style="width:80%; height:auto;">
        <h2>Список новин</h2>
        <ul>{news_html}</ul>
    </body>
    </html>
    """

    pdf_path = f"reports/report_{date}.pdf"
    pdfkit.from_string(html_content, pdf_path, configuration=config)

    return pdf_path



def save_chart(data, categories):
    plt.figure(figsize=(10, 5))
    plt.bar(categories, data, color='purple')
    plt.title("Кількість новин за категоріями", fontsize=14, fontweight="bold")
    plt.xlabel("Категорії")
    plt.ylabel("Кількість")

    chart_path = "static/chart.png"  # Шлях до збереження графіка
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()

    return chart_path

def send_email(recipient, pdf_path):
    sender_email = "georgekeron39@gmail.com"
    sender_password = "xapx qgaj mkju nrbf"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = "Звіт за обрану дату"

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
    return render_template("index.html")


@app.route("/data")
def get_data():
    fetch_and_store_news()
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT category, COUNT(*) FROM news WHERE DATE(published_at) = %s GROUP BY category", (yesterday,))
    result = dict(cursor.fetchall())
    conn.close()
    return {cat: result.get(cat, 0) for cat in categories}


@app.route("/send-report", methods=["POST"])
def send_report():
    try:
        date = request.form["date"]
        email = request.form["email"]
        print(f"Дата: {date}, Email: {email}")

        news = get_news_by_date(date)
        print(f"Новини: {news}")

        if not news:
            return jsonify({"message": "Немає даних за цю дату."}), 404

        pdf_path = generate_pdf(date, news, config)
        print(f"PDF створено: {pdf_path}")

        if not pdf_path:
            return jsonify({"message": "Не вдалося створити PDF."}), 500

        send_email(email, pdf_path)
        print("Email надіслано!")

        return jsonify({"message": "Звіт надіслано!"})
    except Exception as e:
        print(f"Помилка: {e}")
        return jsonify({"error": str(e)}), 500



@app.route("/news-data")
def news_data():
    return jsonify(get_news())


if __name__ == "__main__":
    app.run(debug=True)
