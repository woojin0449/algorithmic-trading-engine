# import json
# import os
# import logging
# import csv
# from datetime import datetime, timezone, timedelta
# KST = timezone(timedelta(hours=9))
# logger = logging.getLogger("TurtleBot")

# def safe_save_json(data, filename):
#     #파일 손상 방지 JSON 생성
#     tmp_file = filename + ".tmp"
#     with open(tmp_file, "w", encoding='utf-8') as f:
#         json.dump(data, f, indent=4, ensure_ascii=False)
#     os.replace(tmp_file, filename)

# def load_json(filepath, default_val = None):
#     if default_val is None:
#         default_val = {}
#     if os.path.exists(filepath):
#         try:
#             with open(filepath, "r", encoding='utf-8') as f:
#                 return json.load(f)
#         except Exception as e:
#             logger.error(f"[{filepath}] json 파일 읽기 실패 및 기본값 복원: {e}")
#             return default_val
#     return default_val

# def get_balance_from_file(balance_file="balance.json"):
#     default_balance = {"usd_balance": 20000.0, "total_equity": 20000.0, "last_update": "없음"}
#     return load_json(balance_file, default_balance)

# def save_closed_trade(ticker, exit_price, qty, cost, revenue, roi_pct, reason, filename = "closed_trades.csv"):
#     file_exists = os.path.exists(filename)
#     with open(filename, 'a', newline='', encoding ="utf-8") as f:
#         # CSV 필드 내 콤마 처리를 위해 csv.writer 사용
#         writer = csv.writer(f)
#         if not file_exists:
#             writer.writerow(["Exit_Date", "Ticker", "Exit_Price", "Qty", "Total_Cost", "Total_Revenue", "ROI_Percent", "Exit_Reason"])
#         #string format time으로 저장
#         exit_date = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
#         writer.writerow([exit_date,ticker, f"{exit_price:.2f}", qty, f"{cost:.2f}", f"{revenue:.2f}", f"{roi_pct:.2f}", reason])
        
# # If the ticker.csv file is missing, the file is automatically generated with default stocks.
# def ensure_tickers_file(filepath="data/tickers.csv"):
#     if not os.path.exists(filepath):
#         directory = os.path.dirname(filepath)
#         if directory:
#             os.makedirs(directory, exist_ok=True)

#         default_tickers = ["AVGO", "INTC", "MU", "AMD", "CRWD", "NVDA"]

#         with open(filepath, "w", encoding="utf-8", newline="") as f:
#             writer = csv.writer(f)
#             writer.writerow(["Ticker"])
#             for ticker in default_tickers:
#                 writer.writerow([ticker])

#         logger.info(
#             f"[{filepath}] 종목 리스트가 없어 기본 유니버스로 자동 생성했습니다.")

import json
import os
import csv
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

def load_json(filepath):
    """JSON 파일을 읽어 딕셔너리로 반환합니다. 파일이 없거나 깨졌으면 빈 딕셔너리를 반환합니다."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"[{filepath}] 파일이 손상되었습니다. 빈 상태로 시작합니다.")
        return {}
    except Exception as e:
        logger.error(f"[{filepath}] 파일 로드 중 에러: {e}")
        return {}

def safe_save_json(data, filepath):
    """
    안전한 저장(Atomic Write)을 수행합니다.
    저장 도중 봇이 강제 종료되어 파일이 0KB로 날아가는 것을 방지하기 위해,
    임시 파일(.tmp)에 먼저 쓰고 원본 파일과 바꿔치기(replace) 합니다.
    """
    tmp_path = f"{filepath}.tmp"
    try:
        # 1. 임시 파일에 예쁘게(indent=4) 쓰기
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        # 2. 원본 파일과 원자적(Atomic)으로 교체
        os.replace(tmp_path, filepath)
    except Exception as e:
        logger.error(f"[{filepath}] 상태 저장 중 치명적 에러 발생: {e}")

def save_closed_trade(ticker, unit, entry_date, exit_date, entry_price, exit_price, qty, cost, revenue, roi_pct, reason, filename="closed_trades.csv"):
    """
    종결된 매매 내역(Unit별)을 CSV에 기록합니다.
    """
    file_exists = os.path.exists(filename)
    
    with open(filename, 'a', newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # 파일이 없으면 헤더 생성 (Unit 컬럼 추가)
        if not file_exists:
            writer.writerow(["Entry_Date", "Exit_Date", "Ticker", "Unit", "Entry_Price", "Exit_Price", "Qty", "Total_Cost", "Total_Revenue", "ROI_Percent", "Exit_Reason"])
        
        writer.writerow([
            entry_date, 
            exit_date, 
            ticker, 
            unit,
            f"{entry_price:.2f}", 
            f"{exit_price:.2f}", 
            qty, 
            f"{cost:.2f}", 
            f"{revenue:.2f}", 
            f"{roi_pct:.2f}%", 
            reason
        ])