from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error, base64, re

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
BRAIN_REPO = "conestgroup/bot-brain"
BRAIN_FILE = "brain.md"

def read_brain():
    try:
        url = f"https://api.github.com/repos/{BRAIN_REPO}/contents/{BRAIN_FILE}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        content = base64.b64decode(data["content"]).decode()
        sha = data["sha"]
        return content, sha
    except:
        return "", ""

def write_brain(new_content, sha):
    try:
        url = f"https://api.github.com/repos/{BRAIN_REPO}/contents/{BRAIN_FILE}"
        encoded = base64.b64encode(new_content.encode()).decode()
        payload = json.dumps({
            "message": "Bot brain update",
            "content": encoded,
            "sha": sha
        }).encode()
        req = urllib.request.Request(url, data=payload, method="PUT", headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json"
        })
        urllib.request.urlopen(req, timeout=10)
        return True
    except:
        return False

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
    file_url = get_file_url(file_id)
    req = urllib.request.Request(file_url)
    resp = urllib.request.urlopen(req, timeout=15)
    audio_data = resp.read()
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

def ask_claude(chat_id, user_message, brain_content, conversations):
    system = f"""You are a personal AI assistant for Vl (owner of BananaSplit and CoNest Group).
Respond in the same language the user writes in. Be direct and concise.

## Your Memory (Brain)
{brain_content}

## Instructions
- Use the brain content to give personalized answers
- If the user says "remember X" or "запомни X" — confirm you will save it
- If the user shares important info, decisions, or tasks — note them
- After responding, if something important was said, add a block at the very end:
  <SAVE>section:Tasks & Follow-ups|content:- Task description here</SAVE>
  Valid sections: Important Decisions, Tasks & Follow-ups, Conversation Memory
"""

    if chat_id not in conversations:
        conversations[chat_id] = []
    conversations[chat_id].append({"role": "user", "content": user_message})
    history = conversations[chat_id][-10:]

    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1024,
        "system": system,
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

def process_save(reply, brain_content, brain_sha):
    """Extract SAVE blocks and update brain"""
    saves = re.findall(r'<SAVE>(.*?)</SAVE>', reply, re.DOTALL)
    if not saves:
        return reply, brain_content, brain_sha
    
    clean_reply = re.sub(r'<SAVE>.*?</SAVE>', '', reply, flags=re.DOTALL).strip()
    
    new_brain = brain_content
    for save_str in saves:
        try:
            # Parse "section:X|content:Y" format
            parts = {}
            for part in save_str.strip().split("|"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    parts[k.strip()] = v.strip()
            section = parts.get("section", "Conversation Memory")
            content = parts.get("content", "")
            if not content:
                continue
            section_header = "## " + section
            marker = "*(auto-updated by bot)*"
            if section_header in new_brain:
                new_brain = new_brain.replace(
                    section_header + "\n" + marker,
                    section_header + "\n" + marker + "\n" + content
                )
        except:
            pass
    
    if new_brain != brain_content:
        success = write_brain(new_brain, brain_sha)
        if success:
            return clean_reply + "\n\n💾 _Сохранено в память_", new_brain, brain_sha
    
    return clean_reply, brain_content, brain_sha

conversations = {}
brain_cache = {"content": "", "sha": "", "loaded": False}

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

            # Load brain
            if not brain_cache["loaded"]:
                brain_cache["content"], brain_cache["sha"] = read_brain()
                brain_cache["loaded"] = True

            if chat_id and text:
                if text == "/start":
                    send_message(chat_id, "Привет! Я твой личный AI ассистент с памятью. Знаю всё о BananaSplit и CoNest. Пиши или отправляй голосовые!")
                elif text == "/clear":
                    if chat_id in conversations:
                        del conversations[chat_id]
                    send_message(chat_id, "История очищена.")
                elif text == "/brain":
                    brain_cache["content"], brain_cache["sha"] = read_brain()
                    brain_cache["loaded"] = True
                    send_message(chat_id, f"🧠 Текущий брейн:\n\n{brain_cache['content'][:2000]}")
                else:
                    reply = ask_claude(chat_id, text, brain_cache["content"], conversations)
                    reply, brain_cache["content"], brain_cache["sha"] = process_save(
                        reply, brain_cache["content"], brain_cache["sha"]
                    )
                    send_message(chat_id, reply)

            elif chat_id and voice:
                file_id = voice["file_id"]
                send_message(chat_id, "🎤 Транскрибирую...")
                transcript = transcribe_voice(file_id)
                if transcript:
                    send_message(chat_id, f"🎤 _{transcript}_")
                    reply = ask_claude(chat_id, transcript, brain_cache["content"], conversations)
                    reply, brain_cache["content"], brain_cache["sha"] = process_save(
                        reply, brain_cache["content"], brain_cache["sha"]
                    )
                    send_message(chat_id, reply)
                else:
                    send_message(chat_id, "Не удалось распознать. Попробуй ещё раз.")

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
