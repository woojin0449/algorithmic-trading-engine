import os
import time
import csv
import json
import gc
import pytz
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

# 1. Global Settings and Utilities
from config import *
from utils.logger import logger
from utils.file_io import load_json, safe_save_json, ensure_tickers_file
from utils.time_checker import is_market_open

# 2. communications network (API)
from api.kis_broker import get_access_token
from api.telegram_bot import send_message, get_new_commands

# 3. Business logic (Core)
from core.strategy import calculate_turtle_indicators
from core.excution import update_balance_and_positions, handle_entry, handle_exit

# 4. Load .env file (apply environment variables)
load_dotenv()
APP_KEY = os.getenv("APP_KEY")
APP_SECRET = os.getenv("APP_SECRECT")
CANO = os.getenv("CANO")

KST = pytz.timezone('Asia/Seoul')

def load_tickers():
    ensure_tickers_file(TICKERS_FILE)
    tickers = []
    try:
        with open(TICKERS_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in  reader:
                if row and row[0].strip():
                    tickers.append(row[0].strip())

    except Exception as e:
        logger.error(f"Failed to read ticker file.: {e}")
    return tickers

def check_telegram_commands(is_pasued, state):
    commands = get_new_commands()
    for cmd in commands:
        if cmd == "/pause":
            is_pasued = True
            send_message("The system has been paused. (Liquidation only)")
        elif cmd == "/resume":
            is_pasued = False
            send_message("The system is resuming trading.")
        elif cmd == "/status":
            bal_data = load_json(BALANCE_FILE) or {}
            msg = f"[System Status]\nRunning: {not is_paused}\nTotal Equity: ${bal_data.get('total_equity', 0):,.2f}\nCash: ${bal_data.get('usd_balance', 0):,.2f}"
            send_message(msg)
    return is_pasued

def run_cycle(last_report_hour, is_paused):
    logger.info("Start a new scan cycle")

    if not is_market_open() and not is_paused:
        logger.info("The Nasdaq is currently closed for trading. I am skipping the trading update and standing by.")
        return last_report_hour, is_paused

    token = get_access_token(APP_KEY, APP_SECRET)
    if not token:
        logger.error("Skipping the cycle due to token issuance failure.")
        return last_report_hour, is_paused
