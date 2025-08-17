import os, json, requests, datetime, pathlib
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ROOT = pathlib.Path(__file__).resolve().parents[1]
FOLLOWUPS_FILE = ROOT / "state" / "followups.json"

def read_json(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def write_json(path: pathlib.Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

def main():
    data = read_json(FOLLOWUPS_FILE, {"pending": [], "sent": []})
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    changed = False
    for item in data.get("pending", []):
        if item.get("chat_id") != CHAT_ID:
            continue
        if item.get("sent"):
            continue
        due = datetime.datetime.fromisoformat(item["due_ts_utc"])
        if now_utc >= due:
            # envoyer le message de suivi
            send_message(f"Il y a ~1h tu as répondu NON pour {item['slot']}. Est-ce que ça va mieux ? (oui/non)")
            item["sent"] = True
            item["awaiting_response"] = True
            item["followup_sent_ts"] = now_utc.isoformat()
            changed = True

    if changed:
        write_json(FOLLOWUPS_FILE, data)

if __name__ == "__main__":
    main()
