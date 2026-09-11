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

from utils.file_io import load_json, safe_save_json
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
    config = {
        "APP_KEY": APP_KEY,
        "APP_SECRET": APP_SECRET,
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "URL_BASE": URL_BASE
    }
    if not is_market_open() and not is_paused:
        logger.info("The Nasdaq is currently closed for trading. I am skipping the trading update and standing by.")
        return last_report_hour, is_paused

    token = get_access_token(config["APP_KEY"], config["APP_SECRET"])
    if not token:
        logger.error("Skipping the cycle due to token issuance failure.")
        return last_report_hour, is_paused

    state = load_json(STATE_FILE) or {}
    is_paused = check_telegram_commands(is_paused, state)
    if is_paused:
        logger.info("Trading is suspended. Only data updates and liquidation checks are being performed.")

    #미체결 관리 및 잔고 업데이트
    
    resolve_pending_orders(token, config, state)
    state = update_account_balance(token, config, state)

    safe_save_json(state, STATE_FILE)

    current_cash = state.get("cash_balance", 0.0)
    total_equity = state.get("total_equity", 20000.0)
    logger.info(f"Synchronization complete. Currently available cash: ${current_cash:,.2f}")

    now_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
    current_hour = now_utc.hour
    if current_hour != last_report_hour:
        send_message(f" [Periodic Report] Operating Normally Total Assets: ${total_equity:,.2f}\n가용 현금: ${current_cash:,.2f}")
        last_report_hour = current_hour
    #abandon code
    # tickers = load_tickers()
    count = 0

    universe_data = load_json(UNIVERSE_FILE)or {}
    universe_stocks = universe_data.get("stocks", {})

    local_positions = state.get("positions", {})
    target_tickers = list(set(universe_stocks.keys()) | set(local_positions.keys()))

    for ticker in target_tickers:
        try:
            ticker_info = universe_stocks.get(ticker, local_positions.get(ticker,{}))

            excd = ticker_info.get('market', 'NAS')
            order_excd = ticker_info.get('order_exchange','NASD')

            df, curr= get_prepared_data(token, config["APP_KEY"], config["APP_SECRET"], ticker, excd)

            if df is None or curr <= 0:
                logger.warning(f"[{ticker}] 데이터 확보 실패로 이번 사이클 건너뜀.")
                continue

            indicators = calculate_turtle_indicators(df)

            if indicators is None:
                logger.warning(f"[{ticker}] Skipped due to insufficient data or delisting.")
                continue
            
            indicators['current_price'] = curr
            indicators['order_exchange'] = order_excd

            is_just_sold = False

            if ticker in local_positions:
                is_just_sold = handle_exit(token, config, state, ticker, indicators)

            if is_just_sold:
                continue

            #pending_orders 기록 주문 번호 추가. @@@

            if not is_paused:
                handle_entry(token, config, state, ticker, indicators,current_cash, total_equity)
            
            count += 1
            if count %10 == 0:
                logger.info(f"Progress: {count}/{len(target_tickers)} completed")
            

        except Exception as e:
            logger.exception(f"[{ticker}] Exception occurred during processing: {e}")

        time.sleep(0.6)
    # Cycle end

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
