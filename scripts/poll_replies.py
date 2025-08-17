import os
import csv
import json
import requests
import datetime
import pathlib
from zoneinfo import ZoneInfo

# =========================
# Config & chemins
# =========================
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]  # str attendu (on cast plus bas au besoin)
TZ = ZoneInfo("Europe/Helsinki")

ACTIONS = ["Balade Katajanokka", "Sauna", "Baignade", "Pompes/Gainage"]

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG_FILE = pathlib.Path(os.environ.get("LOG_FILE", str(ROOT / "data" / "mood_log.csv")))
DETAILS_FILE = ROOT / "data" / "mood_details.csv"
FOLLOWUPS_FILE = ROOT / "state" / "followups.json"
CONVO_FILE = ROOT / "state" / "convo_state.json"
STATE_FILE = pathlib.Path(os.environ.get("STATE_FILE", str(ROOT / "state" / "last_update_id.txt")))
FOLLOWUPS_LOG = ROOT / "data" / "mood_followups.csv"

# =========================
# Utils fichiers
# =========================
def ensure_parents(p: pathlib.Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def read_json(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def write_json(path: pathlib.Path, data):
    ensure_parents(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_csv_header(path: pathlib.Path, header: list[str]):
    ensure_parents(path)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def ensure_all_headers():
    ensure_csv_header(LOG_FILE, ["date","slot","answer","telegram_message_ts","action_suggested"])
    ensure_csv_header(DETAILS_FILE, ["date","slot","origin_ts","duration_h","reason","thoughts","desire","choice"])
    ensure_csv_header(FOLLOWUPS_LOG, ["date","slot","origin_ts","followup_sent_ts","followup_response_ts","response","response_text"])

# =========================
# Telegram helpers (écriture minime)
# =========================
def send_message(text: str):
    """Utilisé uniquement pour des petits accusés (ex: merci pour le suivi)."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

# =========================
# Offset (anti-doublon)
# =========================
def load_last_update_id() -> int:
    if STATE_FILE.exists():
        t = STATE_FILE.read_text().strip()
        return int(t) if t else 0
    return 0

def save_last_update_id(uid: int):
    ensure_parents(STATE_FILE)
    STATE_FILE.write_text(str(uid))

# =========================
# Parsing & logging
# =========================
def parse_slot_answer(text: str):
    """
    Retourne (slot, is_yes) pour '9 oui' / '21 non' / '9h oui' / '21:00 non' etc.
    Sinon (None, None).
    """
    t = text.strip().lower().replace(":", " ").replace("h", " ")
    parts = [p for p in t.split() if p]
    if len(parts) < 2:
        return None, None
    slot_token, ans = parts[0], parts[1]
    if slot_token not in {"9","09","15","21"}:
        return None, None
    slot = {"9":"09:00","09":"09:00","15":"15:00","21":"21:00"}[slot_token]
    if ans not in {"oui","non"}:
        return None, None
    return slot, (ans == "oui")

def log_main(date_str, slot, is_yes, ts_str, action):
    ensure_csv_header(LOG_FILE, ["date","slot","answer","telegram_message_ts","action_suggested"])
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([date_str, slot, "1" if is_yes else "0", ts_str, action or ""])

def log_details(date_str, slot, origin_ts, dur, reason, thoughts, desire, choice):
    ensure_csv_header(DETAILS_FILE, ["date","slot","origin_ts","duration_h","reason","thoughts","desire","choice"])
    with DETAILS_FILE.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([date_str, slot, origin_ts, dur, reason, thoughts, desire, choice or ""])

def log_followup(date_str, slot, origin_ts, sent_ts, resp_ts, resp_bool, resp_text):
    ensure_csv_header(FOLLOWUPS_LOG, ["date","slot","origin_ts","followup_sent_ts","followup_response_ts","response","response_text"])
    with FOLLOWUPS_LOG.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            date_str, slot, origin_ts, sent_ts or "", resp_ts or "",
            "" if resp_bool is None else ("1" if resp_bool else "0"),
            resp_text or ""
        ])

# =========================
# État conversation & suivis
# =========================
QUESTIONS = [
    "Depuis combien d’heures ça dure ?",
    "Pour quelle raison ?",
    "Quelles sont les pensées qui te traversent l’esprit ?",
    "Qu’est-ce que tu as envie de faire ?",
    "Quelle solution tu choisis ? (Balade Katajanokka / Sauna / Baignade / Pompes/Gainage)",
]

def convo_get():
    state = read_json(CONVO_FILE, {})
    return state.get(str(CHAT_ID)) or state.get(CHAT_ID)  # compat str/int

def convo_set(obj):
    state = read_json(CONVO_FILE, {})
    key = str(CHAT_ID)
    if obj is None:
        state.pop(key, None)
    else:
        state[key] = obj
    write_json(CONVO_FILE, state)

def followups_read():
    return read_json(FOLLOWUPS_FILE, {"pending": [], "sent": []})

def followups_write(data):
    write_json(FOLLOWUPS_FILE, data)

def followups_add(entry):
    data = followups_read()
    data["pending"].append(entry)
    followups_write(data)

def handle_convo_step(incoming_text: str, msg_dt_local: datetime.datetime) -> bool:
    """
    Si une conversation est active :
      - enregistre la réponse pour la question courante,
      - incrémente `step`,
      - si terminé (step == len(QUESTIONS)), log details et planifie un follow-up,
      - ne pas envoyer la question suivante (c'est le rôle de ask_questions.py).
    Retourne True si le message a été consommé par la conversation.
    """
    convo = convo_get()
    if not convo or not convo.get("active"):
        return False

    step = convo.get("step", 0)
    key_order = ["duration_h","reason","thoughts","desire","choice"]
    if step < len(key_order):
        key = key_order[step]
        convo["answers"][key] = incoming_text.strip()
        convo["step"] = step + 1

    if convo["step"] < len(QUESTIONS):
        # Sauvegarder l'avancement, ask_questions.py enverra la prochaine question
        convo_set(convo)
    else:
        # Questionnaire terminé -> log details + planifier suivi + close convo
        date_str = convo["date"]
        slot = convo["slot"]
        origin_ts = convo["origin_ts"]
        ans = convo["answers"]
        log_details(date_str, slot, origin_ts, ans["duration_h"], ans["reason"], ans["thoughts"], ans["desire"], ans["choice"])

        # planifier follow-up à +1h (UTC en stockage)
        due_dt_local = msg_dt_local + datetime.timedelta(hours=1)
        due_utc = due_dt_local.astimezone(datetime.timezone.utc).isoformat()
        entry = {
            "chat_id": str(CHAT_ID),
            "date": date_str,
            "slot": slot,
            "origin_ts": origin_ts,
            "due_ts_utc": due_utc,
            "sent": False,
            "awaiting_response": False,
            "followup_sent_ts": None
        }
        followups_add(entry)
        # clôture
        convo_set(None)

    return True

def try_capture_followup_response(incoming_text: str, msg_dt_local: datetime.datetime) -> bool:
    """
    Si un suivi est 'en attente', capte 'oui'/'non', logge, clôture l'attente.
    """
    t = incoming_text.strip().lower()
    if t not in {"oui","non"}:
        return False

    data = followups_read()
    updated = False
    for item in data.get("pending", []):
        if str(item.get("chat_id")) != str(CHAT_ID):
            continue
        if item.get("sent") and item.get("awaiting_response"):
            resp_bool = (t == "oui")
            sent_ts = item.get("followup_sent_ts")
            resp_ts = msg_dt_local.isoformat()
            log_followup(item["date"], item["slot"], item["origin_ts"], sent_ts, resp_ts, resp_bool, t)
            item["awaiting_response"] = False
            updated = True
            # petit accusé
            try:
                send_message("Merci pour ton retour.")
            except Exception:
                pass
            break

    if updated:
        followups_write(data)
        return True
    return False

# =========================
# Main
# =========================
def main():
    ensure_all_headers()

    last_id = load_last_update_id()
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"offset": last_id + 1, "timeout": 0}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    updates = r.json().get("result", [])

    max_id = last_id

    for u in updates:
        upd_id = u.get("update_id", 0)
        if upd_id > max_id:
            max_id = upd_id

        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue

        chat = msg.get("chat", {})
        if str(chat.get("id")) != str(CHAT_ID):
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue

        # horodatage local (Helsinki) du message
        dt_local = datetime.datetime.fromtimestamp(msg["date"], tz=datetime.timezone.utc).astimezone(TZ)
        date_str = dt_local.strftime("%Y-%m-%d")
        ts_str = dt_local.isoformat()

        # 0) priorité : réponse à un SUVI 'oui/non' ?
        if try_capture_followup_response(text, dt_local):
            continue

        # 1) une conversation (questionnaire) est-elle en cours ?
        #    si oui, consommer la réponse et avancer le step (sans envoyer la prochaine question ici)
        if handle_convo_step(text, dt_local):
            continue

        # 2) sinon, est-ce une réponse de slot '9/15/21 oui|non' ?
        slot, is_yes = parse_slot_answer(text)
        if slot is None:
            # message libre ignoré
            continue

        # Log principal
        action = None
        if not is_yes:
            # On ne propose rien ici (c'est ask_questions.py qui enverra),
            # mais on note les actions proposées dans le CSV principal.
            action = " | ".join(ACTIONS)
            # Créer l'état de conversation (step=0, rien encore envoyé)
            convo = {
                "active": True,
                "slot": slot,
                "date": date_str,
                "origin_ts": ts_str,
                "step": 0,
                "last_question_sent_step": -1,
                "answers": {"duration_h":"", "reason":"", "thoughts":"", "desire":"", "choice":""}
            }
            convo_set(convo)

        log_main(date_str, slot, is_yes, ts_str, action)

    if max_id != last_id:
        save_last_update_id(max_id)

if __name__ == "__main__":
    main()
