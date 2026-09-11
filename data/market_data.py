#반드시 market_data 이해해야함.
import yfinance as yf
import pandas as pd
import logging
from api.kis_broker import check_current_price

logger = logging.getLogger(__name__)

def fetch_historical_data(ticker, period="1y", interval ="1d"):
    """
    yfinance에서 과거 데이터 받아서 받은 순대로 처리후
    단일 인덱스 dataframe으로 반환
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)

        if df.empty:
            logger.error(f"[{ticker}] The data from yfinance is empty.")
            return None
 
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df. columns.get_level_values(0)

        return df
    except Exception as e:
        logger.error(f"[{ticker}]  Error downloading data from yfinance")
        return None

def merge_current_price_to_df(df, current_price):
    """
    yfinance 데이터프레임의 오늘 가격에 KIS 실시간 현재가를 반영합니다.
    """
    if df is None or df.empty:
        return df

    last_idx = df.index[-1]

    df.loc[last_idx, 'Close'] = current_price

    #High 값 Low 값 반영.
    if current_price > df.loc[last_idx, 'High']:
        df.loc[last_idx, 'High'] = current_price

    if current_price < df.loc[last_idx, 'Low']:
        df.loc[last_idx, 'Low'] = current_price

    return df

def get_prepared_data(token, app_key, app_secret, ticker, excd):
    """
    [메인 데이터 가공]
    1. yf 과거 데이터 호출
    2. KIS 실시간 현재가 호출
    3. 두 데이터를 합쳐서 반환
    """
    df = fetch_historical_data(ticker)
    if df is None:
        return None, 0.0

    success, current_price = check_current_price(token, app_key, app_secret, ticker, excd)

    if not success or current_price <= 0:
        logger.warning(f"[{ticker}] 실시간 현재가 확보 실패. 지표 계산을 건너뜁니다.")
        return None, 0.0

    merged_df = merge_current_price_to_df(df, current_price)

    return merged_df, current_price

