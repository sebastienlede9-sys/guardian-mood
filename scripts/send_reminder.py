import os, requests, datetime

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SLOT = os.environ.get("SLOT", "09:00")

ACTIONS = ["Balade Katajanokka", "Sauna", "Baignade", "Pompes/Gainage"]

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

def main():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    msg = (
        f"[{today} {SLOT}] Es-tu dans un bon état émotionnel ? Prends ton temps pour répondre \n"
        f"Réponds ici avec le format: 9 oui / 9 non (ou 15 oui/non, 21 oui/non)."
    )
    send_message(msg)

if __name__ == "__main__":
    main()
