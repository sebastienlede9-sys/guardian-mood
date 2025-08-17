import os, json, pathlib, requests, datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TZ = ZoneInfo("Europe/Helsinki")

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONVO_FILE = ROOT / "state" / "convo_state.json"

QUESTIONS = [
    "Depuis combien d’heures ça dure ?",
    "Pour quelle raison ?",
    "Quelles sont les pensées qui te traversent l’esprit ?",
    "Qu’est-ce que tu as envie de faire ?",
    "Quelle solution tu choisis ? (Balade Katajanokka / Sauna / Baignade / Pompes/Gainage)",
]

def load_convo():
    try:
        return json.loads(CONVO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_convo(state):
    CONVO_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONVO_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

def main():
    state = load_convo()
    convo = state.get(CHAT_ID)
    if not convo or not convo.get("active"):
        return  # rien à faire

    step = convo.get("step", 0)
    # Nous utilisons un champ 'last_question_sent_step' pour éviter de renvoyer la même question en boucle
    last_sent = convo.get("last_question_sent_step", -1)

    # Si la conversation vient de démarrer (créée par poll_replies après un "non")
    if step == 0 and last_sent < 0:
        send(
            "Tu as répondu non. Voici 4 solutions possibles :\n"
            "- Balade à Katajanokka\n- Sauna\n- Baignade\n- Pompes / Gainage"
        )

    # Envoyer la question correspondante au step courant si pas encore envoyée
    if step < len(QUESTIONS) and last_sent < step:
        send(QUESTIONS[step])
        convo["last_question_sent_step"] = step
        state[CHAT_ID] = convo
        save_convo(state)

if __name__ == "__main__":
    main()
