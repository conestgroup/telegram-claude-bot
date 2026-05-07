from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

def ask_claude(user_message):
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": user_message}]
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01"
    })
    resp = urllib.request.urlopen(req, timeout=20)
    result = json.loads(resp.read())
    return result["content"][0]["text"]

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        chat_id = None
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
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            print(f"HTTP Error: {e.code} - {err}")
            if chat_id:
                try: send_message(chat_id, f"Ошибка API {e.code}: {err[:150]}")
                except: pass
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
            if chat_id:
                try: send_message(chat_id, f"Ошибка: {str(e)[:150]}")
                except: pass
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        key_status = "SET" if ANTHROPIC_KEY else "MISSING"
        token_status = "SET" if TELEGRAM_TOKEN else "MISSING"
        self.wfile.write(f"Bot OK! KEY:{key_status} TOKEN:{token_status}".encode())

    def log_message(self, format, *args):
        pass
