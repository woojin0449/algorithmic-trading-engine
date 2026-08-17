import pandas as pd
import math

#Calculates Turtle Trading indicators from a given DataFrame.
def calculate_turtle_indicators(df: pd.DataFrame) -> dict:
    if df is None or df.empty or len(df) < 201:
        #Soft fail for newly listed stocks with insufficient data
        return None

    data = df.copy()

    # Flatten MultiIndex columns if necessary (handling latest yfinance changes)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    #Prevent look-ahead bias by shifting historical data by 1 day.
    data['DC_upper'] = data['High'].rolling(55).max().shift(1)
    data['DC_lower'] = data['Low'].rolling(20).min().shift(1)
    data['MA200'] = data['Close'].rolling(200).mean().shift(1)
    
    #Calculate True Range (TR)
    prev_close = data['Close'].shift(1)
    tr1 = data['High'] - data['Low']
    tr2 = (data['High'] - prev_close).abs()
    tr3 = (data['Low'] - prev_close).abs()

    data['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    #Calculate Average True Range (ATR) based on a 20-day window
    data['ATR'] = data['TR'].rolling(window=20).mean().shift(1)

    #Extract the most recent row
    latest = data.iloc[-1]
    
    curr_price = float(latest['Close'])
    dc_upper = float(latest['DC_upper'])
    dc_lower = float(latest['DC_lower'])
    ma200 = float(latest['MA200'])
    atr_val = float(latest['ATR'])

    #Failsafe: Filter out NaN values and invalid ATR
    indicators = [curr_price, dc_upper, dc_lower, ma200, atr_val]
    if any(math.isnan(x) for x in indicators) or atr_val <= 0:
        return None

    return {
        'current_price': curr_price,
        'dc_upper': dc_upper,
        'dc_lower': dc_lower,
        'ma200': ma200,
        'atr': atr_val
    }
