import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Bot
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Telegram Bot Token
TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(TOKEN)

# Flask app
app = Flask(__name__)

# Server URL for sending data
SERVER_URL = os.getenv("SERVER_URL")

# SMTP settings
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Mock users database
MOCK_USERS = {
    "baner.vk@ya.ru": {"password": "12345", "tgId": 7453733638},
}

async def delete_webhook():
    """
    Deletes the webhook to switch to polling.
    """
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook removed.")
    except Exception as e:
        print(f"Error removing webhook: {e}")

def send_message(chat_id, text):
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
        return {"ok": False, "error": str(e)}

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

        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

async def process_updates():
    """
    Processes Telegram updates.
    """
    print("Bot started and polling...")
    last_update_id = None

    while True:
        try:
            updates = await bot.get_updates(offset=last_update_id, timeout=5)

            for update in updates:
                if update.message:
                    text = update.message.text
                    chat_id = update.message.chat.id

                    if text.startswith("/login"):
                        parts = text.split()
                        if len(parts) == 3:
                            telegram_id, email = parts[1], parts[2]
                            success, response_message = await send_login_request(telegram_id, email)
                            await bot.send_message(chat_id, response_message)
                        else:
                            await bot.send_message(
                                chat_id,
                                "❌ Invalid format. Use: /login <telegramId> <email>",
                            )

                    last_update_id = update.update_id + 1

            await asyncio.sleep(1)

        except Exception as e:
            print(f"Error processing updates: {e}")
            await asyncio.sleep(5)

async def send_login_request(telegram_id, email):
    """
    Sends login request to server.
    """
    try:
        response = requests.post(
            SERVER_URL,
            json={"telegramId": int(telegram_id), "email": email},
        )
        response.raise_for_status()
        return True, "✅ Registration successful!"
    except requests.exceptions.RequestException as e:
        print(e)
        return False, f"❌ Error: {e}"

@app.route("/send", methods=["POST"])
def handle_send():
    data = request.json
    required_fields = ["telegramId", "email", "content", "title"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing fields in query"}), 400

    chat_id = data["telegramId"]
    title = data["title"]
    email = data["email"]
    content = data["content"]

    message_text = f"📧 {title}\n   {content}"
    response = send_message(chat_id, message_text)

    if response.get("ok"):
        email_subject = f"Alert: {title}"
        email_content = f"{content}"
        email_sent = send_email(email, email_subject, email_content)

        if email_sent:
            return jsonify({"status": "Sent to email and Telegram"}), 200
        else:
            return jsonify({"status": "Sent to Telegram but not email"}), 500
    else:
        error_details = response.get("error", "Unknown error")
        return jsonify({"error": "Failed to send message anywhere", "details": error_details}), 500

@app.route("/user/login", methods=["POST"])
def user_login():
    data = request.json
    required_fields = ["email", "password", "tgId"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing fields in request"}), 400

    email = data["email"]
    password = data["password"]
    tg_id = data["tgId"]

    user = MOCK_USERS.get(email)
    if user and user["password"] == password and user["tgId"] == tg_id:
        return jsonify({"status": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid email, password, or tgId"}), 401

def run_flask():
    app.run(debug=True, use_reloader=False)

async def main():
    await delete_webhook()
    threading.Thread(target=run_flask).start()
    await process_updates()

if __name__ == "__main__":
    asyncio.run(main())
