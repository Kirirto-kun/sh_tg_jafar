from flask import Flask, request, jsonify
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_sqlalchemy import SQLAlchemy
import shodan
import asyncio
from telegram import Bot

# Flask приложение
app = Flask(__name__)

# Telegram настройки
TOKEN = "8023166814:AAEjAAjDdyK_mFcCoPWQomvAD2zGNHfbRQg"
bot = Bot(TOKEN)
SERVER_URL = "http://20.64.237.199:4000/user/telegram"
# SMTP настройки
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "kosov.m0517@gmail.com"
SMTP_PASSWORD = "trrcnvlleybstithbnkz"

# Shodan API
SHODAN_API_KEY = 'BWiX3u3WpLDBnuQvglTI3bOiC88x8PKQ'
shodan_api = shodan.Shodan(SHODAN_API_KEY)

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vulnerabilities.db'
db = SQLAlchemy(app)


# Модели данных
class Vulnerability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cve_id = db.Column(db.String(50), unique=True)
    description = db.Column(db.Text)
    published_date = db.Column(db.String(50))
    source = db.Column(db.String(100))
    exploit_available = db.Column(db.Boolean, default=False)



async def delete_webhook():
    """
    Удаляем webhook, чтобы переключиться на polling.
    """
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook удален.")
    except Exception as e:
        print(f"Ошибка при удалении webhook: {e}")


async def send_login_request(telegram_id, email):
    """
    Отправляет запрос на сервер.
    """
    
    try:
        response = requests.post(
            SERVER_URL,
            json={"telegramId": int(telegram_id), "email": email},
        )
        response.raise_for_status()
        return True, "✅ Регистрация прошла успешно!"
    except requests.exceptions.RequestException as e:
        print(e)
        print(telegram_id, email)
        return False, f"❌ Ошибка: {e}"

def send_message(chat_id, text):
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке сообщения: {e}")
        return {"ok": False, "error": str(e)}
    
# Создание базы данных
with app.app_context():
    db.create_all()


# Функция отправки Email
def send_email(to_email, subject, content):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"Email отправлен на {to_email}")
        return True
    except Exception as e:
        print(f"Ошибка при отправке Email: {e}")
        return False


# Эндпоинты
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    if not data or "message" not in data:
        return jsonify({"error": "Invalid request"}), 400

    message = data.get("message")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if text.startswith("/login"):
        parts = text.split()
        if len(parts) == 3:
            telegram_id, email = parts[1], parts[2]
            try:
                response = requests.post(
                    "http://20.64.237.199:4000/user/telegram",
                    json={"telegramId": telegram_id, "email": email},
                )
                response.raise_for_status()
                send_message(chat_id, "✅ Регистрация успешна!")
            except requests.exceptions.RequestException as e:
                send_message(chat_id, f"❌ Ошибка подключения: {e}")
        else:
            send_message(chat_id, "❌ Неправильный формат. Используйте: /login <telegramId> <email>")
    else:
        send_message(chat_id, "❌ Неизвестная команда.")

    return jsonify({"status": "ok"}), 200


@app.route('/scan', methods=['POST'])
def scan():
    data = request.json
    ip_address = data.get('ip')
    if not ip_address:
        return jsonify({'error': 'IP address is required'}), 400

    try:
        host_info = shodan_api.host(ip_address)
        results = [
            {'port': service['port'], 'service': service.get('product', 'Unknown'), 'version': service.get('version', 'Unknown')}
            for service in host_info['data']
        ]
        return jsonify({'ip': ip_address, 'services': results})
    except shodan.APIError as e:
        return jsonify({'error': str(e)}), 500


@app.route('/vulnerabilities', methods=['GET'])
def get_vulnerabilities():
    vulnerabilities = Vulnerability.query.all()
    return jsonify([
        {
            'cve_id': v.cve_id,
            'description': v.description,
            'published_date': v.published_date,
            'source': v.source,
            'exploit_available': v.exploit_available
        } for v in vulnerabilities
    ])


@app.route('/update_vulnerabilities', methods=['POST'])
def update_vulnerabilities():
    nvd_url = "https://services.nvd.nist.gov/rest/json/cves/1.0"
    response = requests.get(nvd_url, params={'resultsPerPage': 10})
    if response.status_code == 200:
        data = response.json()
        for item in data.get('result', {}).get('CVE_Items', []):
            cve_id = item['cve']['CVE_data_meta']['ID']
            description = item['cve']['description']['description_data'][0]['value']
            published_date = item['publishedDate']
            vuln = Vulnerability.query.filter_by(cve_id=cve_id).first()
            if not vuln:
                db.session.add(Vulnerability(
                    cve_id=cve_id,
                    description=description,
                    published_date=published_date,
                    source="NVD"
                ))
        db.session.commit()
        return jsonify({'message': 'Vulnerabilities updated successfully'}), 200
    return jsonify({'error': 'Failed to fetch data from NVD'}), 500


# Асинхронный polling для Telegram
async def process_updates():
    print("Запущен polling Telegram.")
    last_update_id = None

    while True:
        try:
            updates = await bot.get_updates(offset=last_update_id, timeout=5)
            for update in updates:
                if update.message:
                    chat_id = update.message.chat.id
                    text = update.message.text

                    if text.startswith("/login"):
                        parts = text.split()
                        if len(parts) == 3:
                            telegram_id, email = parts[1], parts[2]
                            response_message = await send_login_request(telegram_id, email)
                            await bot.send_message(chat_id, response_message)
                        else:
                            await bot.send_message(chat_id, "❌ Неправильный формат. Используйте: /login <telegramId> <email>")

                    last_update_id = update.update_id + 1
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Ошибка: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    app.run(debug=True)
    asyncio.run(process_updates())
