import exchange_calendars as ecals
import pandas as pd

XNYS = ecals.get_calendar("XNYS")
def is_market_open():
    now = pd.Timestamp.now(tz="America/New_York")

    today_str = now.strftime('%Y-%m-%d')

    if not XNYS.is_session(today_str):
        return False
    market_open = XNYS.session_open(today_str)
    market_close = XNYS.session_close(today_str)
    
    return market_open <= now < market_close
