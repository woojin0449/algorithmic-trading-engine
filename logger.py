import csv
import os
from datetime import datetime

LOG_FILE = "trade_history.csv"

def log_trade(ticker, action, qty, price, units, atr):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['datetime', 'ticker', 'action', 'qty', 'price', 'units', 'atr'])
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ticker, action, qty, f"{price:.2f}", units, f"{atr:.4f}"
        ])
