import sys
import exchange_calendars as ecals
import pandas as pd
import subprocess
from utils.logger import logger

def is_market_open():
    XNYS = ecals.get_calendar("XNYS")
    now = pd.Timestamp.now(tz="America/New_York")

    today_str = now.strftime('%Y-%m-%d')

    if not XNYS.is_session(today_str):
        return False
    market_open = XNYS.session_open(today_str)
    market_close = XNYS.session_close(today_str)
    
    return market_open <= now < market_close

def check_holiday_and_shutdown():
    XNYS = ecals.get_calendar("XNYS")
    now = pd.Timestamp.now(tz="America/New_York")

    today_str = now.strftime('%Y-%m-%d')

    if not XNYS.is_session(today_str):
        # 즉시 종료(now)가 아니라 5분 뒤(+5) 종료 예약
        logger.info(f"[{today_str}] 휴장일입니다. 5분 뒤 서버가 자동 종료됩니다.")
        subprocess.run(["sudo", "shutdown", "-h", "+5"])
        sys.exit()