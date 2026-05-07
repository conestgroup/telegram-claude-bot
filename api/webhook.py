from http.server import BaseHTTPRequestHandler
import json, os, urllib.request

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

def ask_claude(user_message):
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": user_message}]
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01"
    })
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return result["content"][0]["text"]

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            message = body.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            if chat_id and text:
                if text == "/start":
                    reply = "Привет! Я Claude AI. Пиши мне что угодно — отвечу!"
                else:
                    reply = ask_claude(text)
                send_message(chat_id, reply)
        except Exception as e:
            print(f"Error: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Telegram Claude Bot is running!")

    def log_message(self, format, *args):
        pass
