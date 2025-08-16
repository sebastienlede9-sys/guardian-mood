import os, csv, time, requests, random, datetime, pathlib, sys, json

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ACTIONS = ["Balade Katajanokka", "Sauna", "Baignade", "Pompes/Gainage"]

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state" / "last_update_id.txt"
LOG_FILE = ROOT / "data" / "mood_log.csv"

def load_last_update_id():
    if STATE_FILE.exists():
        return int(STATE_FILE.read_text().strip() or "0")
    return 0

def save_last_update_id(uid: int):
    STATE_FILE.write_text(str(uid))

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

def get_updates(offset):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 0}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["result"]

def ensure_log_header():
    if not LOG_FILE.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date","slot","answer","telegram_message_ts","action_suggested"])

def parse_answer(text: str):
    """
    Attend des formats comme:
    '9 oui' / '9 non'
    '15 oui' / '15 non'
    '21 oui' / '21 non'
    Renvoie (slot_str, answer_bool) ou (None, None) si non conforme.
    """
    t = text.strip().lower().replace("h", "").replace(":", " ").split()
    if len(t) < 2:
        return None, None
    slot_token, ans = t[0], t[1]
    if slot_token not in {"9","15","21"}:
        return None, None
    slot = {"9":"09:00","15":"15:00","21":"21:00"}[slot_token]
    if ans not in {"oui","non"}:
        return None, None
    return slot, (ans == "oui")

def log_row(date_str, slot, answer_bool, msg_ts, action):
    ensure_log_header()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        w.writerow([date_str, slot, "1" if answer_bool else "0", msg_ts, action or ""])

def main():
    last_id = load_last_update_id()
    updates = get_updates(last_id + 1)
    max_id = last_id
    for u in updates:
        upd_id = u["update_id"]
        max_id = max(max_id, upd_id)

        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id"))
        if chat_id != CHAT_ID:
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue

        slot, ok = parse_answer(text)
        if slot is None:
            continue  # ignore autres messages

        dt_msg = datetime.datetime.fromtimestamp(msg["date"])
        date_str = dt_msg.strftime("%Y-%m-%d")
        ts_str = dt_msg.isoformat()

        action = None
        if ok:
            action = random.choice(ACTIONS)
            try:
                send_message(f"Noté pour {slot}. Essaie : {action}")
            except Exception as e:
                # On continue même si l'envoi d'action échoue
                pass

        log_row(date_str, slot, ok, ts_str, action)

    if max_id != last_id:
        save_last_update_id(max_id)

if __name__ == "__main__":
    main()
