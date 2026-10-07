from generate_universe import update_universe
from config import *
from api.kis_broker import get_access_token

if __name__ == "__main__":
    token = get_access_token(APP_KEY, APP_SECRET)
    update_universe(token, APP_KEY, APP_SECRET, "NAS", 100)