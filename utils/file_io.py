import json
import os
import logging
import csv
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
logger = logging.getLogger("TurtleBot")

def safe_save_json(data, filename):
    #파일 손상 방지 JSON 생성
    tmp_file = filename + ".tmp"
    with open(tmp_file, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp_file, filename)

def load_json(filepath, default_val = None):
    if default_val is None:
        default_val = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[{filepath}] json 파일 읽기 실패 및 기본값 복원: {e}")
            return default_val
    return default_val

def get_balance_from_file(balance_file="balance.json"):
    default_balance = {"usd_balance": 20000.0, "total_equity": 20000.0, "last_update": "없음"}
    return load_json(balance_file, default_balance)

def save_closed_trade(ticker, exit_price, qty, cost, revenue, roi_pct, reason, filename = "closed_trades.csv"):
    file_exists = os.path.exists(filename)
    with open(filename, 'a', newline='', encoding ="utf-8") as f:
        # CSV 필드 내 콤마 처리를 위해 csv.writer 사용
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Exit_Date", "Ticker", "Exit_Price", "Qty", "Total_Cost", "Total_Revenue", "ROI_Percent", "Exit_Reason"])
        #string format time으로 저장
        exit_date = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([exit_date,ticker, f"{exit_price:.2f}", qty, f"{cost:.2f}", f"{revenue:.2f}", f"{roi_pct:.2f}", reason])
