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
from core.execution import update_balance_and_positions, handle_entry, handle_exit

# 4. Load .env file (apply environment variables)
load_dotenv()
APP_KEY = os.getenv("APP_KEY")
APP_SECRET = os.getenv("APP_SECRET")
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

def check_telegram_commands(is_paused, state):
    commands = get_new_commands()
    for cmd in commands:
        if cmd == "/pause":
            is_paused = True
            send_message("The system has been paused. (Liquidation only)")
        elif cmd == "/resume":
            is_paused = False
            send_message("The system is resuming trading.")
        elif cmd == "/status":
            bal_data = load_json(BALANCE_FILE) or {}
            msg = f"[System Status]\nRunning: {not is_paused}\nTotal Equity: ${bal_data.get('total_equity', 0):,.2f}\nCash: ${bal_data.get('usd_balance', 0):,.2f}"
            send_message(msg)
    return is_paused

def run_cycle(last_report_hour, is_paused):
    logger.info("Start a new scan cycle")

    if not is_market_open() and not is_paused:
        logger.info("The Nasdaq is currently closed for trading. I am skipping the trading update and standing by.")
        return last_report_hour, is_paused

    token = get_access_token(APP_KEY, APP_SECRET)
    if not token:
        logger.error("Skipping the cycle due to token issuance failure.")
        return last_report_hour, is_paused

    state = load_json(STATE_FILE) or {}

    now_kst = datetime.now(KST)
    current_hour = now_kst.hour
    if current_hour != last_report_hour:
        bal_data = load_json(BALANCE_FILE) or {}
        send_message(f" [Periodic Report] Operating Normally Total Assets: ${bal_data.get('total_equity', 0):,.2f}\n가용 현금: ${bal_data.get('usd_balance', 0):,.2f}")
        last_report_hour = current_hour

    is_paused = check_telegram_commands(is_paused, state)

    tickers = load_tickers()
    count = 0

    if is_paused:
        logger.info("Trading is suspended. Only data updates and liquidation checks are being performed.")

    for ticker in tickers:
        try:
            df = yf.download(ticker, period="1y",interval="1d",progress=False)
            indicators = calculate_turtle_indicators(df)

            if indicators is None:
                logger.warning(f"[{ticker}] Skipped due to insufficient data or delisting.")
                continue

            curr = indicators['current_price']

            if ticker in state and state[ticker].get('units', 0) > 0:
                state[ticker]['current_price'] = curr

            handle_exit(token, ticker, state, indicators)

            if not is_paused:
                bal_data = load_json(BALANCE_FILE) or {}
                total_equity = bal_data.get("total_equity", 20000.0)
                handle_entry(token, ticker, state, indicators,total_equity)
            
            count += 1
            if count %10 == 0:
                logger.info(f"Progress: {count}/{len(tickers)} completed")
            

        except Exception as e:
            logger.exception(f"[{ticker}] Exception occurred during processing: {e}")

        time.sleep(0.6)
    # Cycle end
    update_balance_and_positions(state)
    safe_save_json(state, STATE_FILE)

    logger.info("Scanning of all categories complete. Standing by for 5 minutes...")
    gc.collect()

    return last_report_hour, is_paused

# [Implementation Unit]
if __name__ == "__main__":
    start_msg = "Algorithmic trading engine v2.0 launched."
    logger.info(start_msg)
    send_message(start_msg)

    last_reported_hour = -1
    is_paused =False

    try:
        while True:
            try:
                last_reported_hour, is_paused = run_cycle(last_reported_hour, is_paused)
                time.sleep(300)
            except Exception as e:
                logger.error(f"System fatal exception occurred: {e}")
                send_message(f"System exception occurred. Retrying in 1 minute: {e}")
                time.sleep(60)

    except KeyboardInterrupt:
        logger.info("The system has been safely shut down by the user.")
        send_message("The system has been safely shut down manually.")
            

