import exchange_calendars as ecals
import pandas as pd

XNYS = ecals.get_calendar("XNYS")
def is_market_open():
    now = pd.Timestamp.now(tz="America/New_York")

    today = now.normalize()

    if not XNYS.is_session(today):
        return False
    market_open = XNYS.session_open(today)
    market_close = XNYS.session_close(today)
    
    return market_open <= now < market_close
