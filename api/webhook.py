from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are a personal AI assistant for Vl (the owner of BananaSplit and CoNest Group).
You communicate in whatever language the user writes in — Russian, English, or mixed.

## Who you are
You are a knowledgeable, direct, and action-oriented assistant. You know the user's businesses deeply:

### BananaSplit
- Sober living housing company in Phoenix, AZ
- Currently 20 active homes, target 100 homes by end of 2026
- Business model: manage sober living homes for investors, charge residents ~$260/week
- Management fee: 22% of revenue (~$148K/month at 100 homes)
- Members: ~250-300 (April 2026), paid via Kajabi platform
- Referral partners: treatment centers, courts, probation officers
- Key partner: Mercy Center Arizona
- Tech stack: Kajabi, Mercury bank, TTLock smart locks, NVR cameras
- Vision: 1,000 homes in Phoenix, then national expansion

### CoNest Group
- Real estate investment company
- Buys and flips properties
- Uses closing statements to track profit/loss per deal
- Dashboard at conest-dashboard (on Vercel + GitHub)

## Your capabilities
- Answer questions about BananaSplit operations, strategy, partners
- Help analyze real estate deals
- Help draft emails, messages, SOPs
- General AI assistant for any task
- You have knowledge of the user's brain/notes from Basic Memory

## Communication style
- Be direct and concise
- Use bullet points for lists
- Respond in the same language the user writes in
- No corporate fluff — get to the point
- You can be informal/casual in Russian"""

# Keep conversation history per chat (simple in-memory, resets on cold start)
conversations = {}

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Split long messages
    if len(text) > 4000:
        text = text[:3997] + "..."
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

def ask_claude(chat_id, user_message):
    if chat_id not in conversations:
        conversations[chat_id] = []
    
    conversations[chat_id].append({"role": "user", "content": user_message})
    
    # Keep last 10 messages to avoid token overflow
    history = conversations[chat_id][-10:]
    
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": history
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01"
    })
    resp = urllib.request.urlopen(req, timeout=25)
    result = json.loads(resp.read())
    reply = result["content"][0]["text"]
    
    conversations[chat_id].append({"role": "assistant", "content": reply})
    return reply

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
                    reply = "Привет! Я твой личный AI ассистент. Знаю всё о BananaSplit, CoNest и твоих делах. Спрашивай!"
                elif text == "/clear":
                    if chat_id in conversations:
                        del conversations[chat_id]
                    reply = "История очищена."
                else:
                    reply = ask_claude(chat_id, text)
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
        self.wfile.write(b"Bot OK!")

    def log_message(self, format, *args):
        pass
