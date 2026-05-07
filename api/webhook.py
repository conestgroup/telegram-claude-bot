from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error, tempfile

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

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

## Communication style
- Be direct and concise
- Respond in the same language the user writes in
- No corporate fluff — get to the point
- You can be informal/casual in Russian"""

conversations = {}

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:3997] + "..."
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

def get_file_url(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    file_path = result["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

def transcribe_voice(file_id):
    # Download voice file from Telegram
    file_url = get_file_url(file_id)
    req = urllib.request.Request(file_url)
    resp = urllib.request.urlopen(req, timeout=15)
    audio_data = resp.read()
    
    # Send to OpenAI Whisper
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="voice.ogg"\r\n'
        f'Content-Type: audio/ogg\r\n'
        f"\r\n"
    ).encode() + audio_data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n'
        f"\r\n"
        f"whisper-1\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("text", "")

def ask_claude(chat_id, user_message):
    if chat_id not in conversations:
        conversations[chat_id] = []
    conversations[chat_id].append({"role": "user", "content": user_message})
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
            voice = message.get("voice") or message.get("audio")
            
            if chat_id and text:
                if text == "/start":
                    reply = "Привет! Я твой личный AI ассистент. Знаю всё о BananaSplit и CoNest. Пиши или отправляй голосовые!"
                elif text == "/clear":
                    if chat_id in conversations:
                        del conversations[chat_id]
                    reply = "История очищена."
                else:
                    reply = ask_claude(chat_id, text)
                send_message(chat_id, reply)
                
            elif chat_id and voice:
                file_id = voice["file_id"]
                send_message(chat_id, "🎤 Транскрибирую...")
                transcript = transcribe_voice(file_id)
                if transcript:
                    send_message(chat_id, f"🎤 _{transcript}_")
                    reply = ask_claude(chat_id, transcript)
                    send_message(chat_id, reply)
                else:
                    send_message(chat_id, "Не удалось распознать голос. Попробуй ещё раз.")
                    
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            print(f"HTTP Error: {e.code} - {err}")
            if chat_id:
                try: send_message(chat_id, f"Ошибка: {err[:150]}")
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
