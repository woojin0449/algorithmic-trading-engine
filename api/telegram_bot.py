import requests
from utils.logger import logger
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# Global offset to prevent processing the same message multiple times
LAST_UPDATE_ID = 0

# Send text message to Telegram channel (outbound only)
def send_message(text):
    
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token missing. Cannot send message.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")

# Fetch new commands starting with '/' (no execution)
def get_new_commands():
    global LAST_UPDATE_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_UPDATE_ID}&timeout=5"
    
    commands = []
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("ok") and res.get("result"):
            for item in res["result"]:
                LAST_UPDATE_ID = item["update_id"] + 1
                text = item.get("message", {}).get("text", "")

                if text.startswith("/"):
                    commands.append(text.strip())
    
    except Exception as e:
        logger.error(f"Failed to receive Telegram commands:{e}")

    return commands
