import requests
import json
import os
import time
import logging
from datetime import datetime, timedelta
from utils.file_io import load_json, safe_save_json
from utils.logger import logger
from config import URL_BASE, ACNT_PRDT_CD
# To be loaded from config.py or environment variables later
logger = logging.getLogger(__name__)

URL_BASE = "https://openapivts.koreainvestment.com:29443"
ACNT_PRDT_CD = "01"
MAX_RETRIES = 3
RETRY_DELAY = 2
SLIPPAGE_FACTOR = 0.003
TOKEN_FILE = "kis_token.json"

# Retrieve existing valid token from file or issue a new one from KIS API
def get_access_token(app_key, app_secret):
    saved_token = load_json(TOKEN_FILE)
    #토큰이 있을때
    if saved_token and 'timestamp' in saved_token and 'token' in saved_token:
        try:
            token_time = datetime.strptime(saved_token['timestamp'], '%Y-%m-%d %H:%M:%S')
            #Token is valid for 24hours; we use 20 hours as a safe buffer
            if datetime.now() - token_time < timedelta(hours=20):
                return saved_token['token']
        except Exception as e:
            logger.warning(f"Failed to parse saved token timestamp: {e}")
    
    #토큰이 없을때 (여기는 대충 이해만 해도 될거 같음 그냥 토큰 발행 양식에 맞춰 코드 작성)
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}

    for attempt in range(MAX_RETRIES):
        try:
            #json 형태로 넣고 답 안오면 15초 대기
            res = requests.post(url, headers={"content-type": "application/json"}, json=body, timeout=15)
            data = res.json()

            if "access_token" in data:
                token = data["access_token"]
                token_data = {
                    "token": token,
                    #String Format Time
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                safe_save_json(token_data, TOKEN_FILE)
                logger.info("Successfully issued and saved new KIS API token.")
                return token
            else:
                logger.error(f"Token issuance denied: {data}")
                return None
        
        except Exception as e:
            logger.error(f"Token API communication error (Attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES -1:
                time.sleep(RETRY_DELAY)
    return None

# Fetch current account balance and equity from KIS API
def get_account_balance(token, app_key, app_secret, cano, acnt_prdt_cd):
    """
    총 잔고, 구매 가능 금액, kis_position을 리턴합니다. 
    """
    url1 = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-psamount"
    headers1 = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "VTTS3007R",  # 예수금
        "custtype": "P"
    }
    params1 = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": "0", "ITEM_CD": "AAPL" 
    }

    url2 = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance"
    headers2 = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "VTTS3012R",  # 잔고내역
    }
    params2 = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
    }

    try:
        res1 = requests.get(url1, headers=headers1, params=params1, timeout=10)
        data1 = res1.json()
        time.sleep(1.0)
        res2 = requests.get(url2, headers=headers2, params=params2, timeout=10)
        data2 = res2.json()

        if data1.get('rt_cd') == '0' and data2.get('rt_cd') == '0':
            summary1 = data1.get('output', {})
            cash_balance = float(summary1.get("ovrs_ord_psbl_amt", 0))
            
            stock_list = data2.get('output1', [])
            stock_value = 0.0
            kis_positions = {} # ⬅️ 동기화를 위한 KIS 실제 보유 종목 딕셔너리
            
            for item in stock_list:
                eval_amt = float(item.get("ovrs_stck_evlu_amt") or 0.0)
                stock_value += eval_amt
                
                ticker = item.get("ovrs_pdno")
                qty = int(float(item.get("ovrs_cblc_qty", 0)))
                avg_price = float(item.get("pchs_avg_pric", 0))
                now_price = float(item.get("now_pric2", 0))
                
                # 수량이 있는 주식만 파싱해서 딕셔너리에 담기
                if qty > 0 and ticker:
                    kis_positions[ticker] = {
                        "qty": qty,
                        "avg_price": avg_price,
                        "now_price": now_price
                    }
            
            total_equity = stock_value + cash_balance
            return total_equity, cash_balance, kis_positions
            
        else:
            logger.error(f"Failed to fetch balance. Msg1: {data1.get('msg1')}, Msg2: {data2.get('msg1')}")
            return 0.0, 0.0, {}

    except Exception as e:
        logger.error(f"Balance API error: {e}")
        return 0.0, 0.0, {}

def get_order_execution(token, app_key, app_secret, cano, acnt_prdt_cd):
    """
    미체결 및 체결 내역을 조회하여 배열로 리턴합니다.
    (실제 KIS API 스펙에 맞춘 VTTS3018R 등 체결조회 TR_ID 사용)
    """
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-nccs"
    headers = {
        "content-type": "application/json", "authorization": f"Bearer {token}",
        "appkey": app_key, "appsecret": app_secret, "tr_id": "VTTS3018R", "custtype": "P"
    }
    params = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "OVRS_EXCG_CD": "NASD",
        "SORT_SQN": "DS", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0":
            return data.get("output", [])
        return []
    except Exception as e:
        logger.error(f"체결조회 API 에러: {e}")
        return []

def cancel_order(token, app_key, app_secret, cano, acnt_prdt_cd, ticker, odno, exchange):
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order-rvsecncl"
    headers = {
        "content-type": "application/json", "authorization": f"Bearer {token}",
        "appkey": app_key, "appsecret": app_secret, "tr_id": "VTTT1004U"
    }
    body = {
        "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "OVRS_EXCG_CD": exchange,
        "PDNO": ticker, "ORGN_ODNO": odno, "RVSE_CNCL_DVSN_CD": "02",
        "ORD_QTY": "0", "OVRS_ORD_UNPR": "0", "ORD_SVR_DVSN_CD": "0"
    }
    try:
        res = requests.post(url, headers=headers, json=body, timeout=10)
        data = res.json()
        if data.get("rt_cd") == "0":
            logger.info(f"[{ticker}] 미체결 주문 취소 성공 (ODNO: {odno})")
            return True
        logger.error(f"[{ticker}] 주문 취소 실패: {data.get('msg1')}")
        return False
    except Exception as e:
        logger.error(f"[{ticker}] 주문 취소 API 에러: {e}")
        return False

# # Send a US stock buy/sell order to KIS API
# def send_us_order(token, app_key, app_secret, cano, ticker, is_buy, qty, price, slippage_factor=SLIPPAGE_FACTOR):
#     if qty <= 0:
#         return False
    
#     url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"
#     # VTTT1002U: Buy, VTTT1001U: Sell
#     tr_id = "VTTT1002U" if is_buy else "VTTT1001U"
#     order_price = price * (1 + slippage_factor) if is_buy else price * (1 - slippage_factor)

#     headers = {
#         "content-type": "application/json",
#         "authorization": f"Bearer {token}",
#         "appkey": app_key,
#         "appsecret": app_secret,
#         "tr_id": tr_id
#     }

#     body = {
#         "CANO": cano,
#         "ACNT_PRDT_CD": ACNT_PRDT_CD,
#         "OVRS_EXCG_CD": "NASD",
#         "PDNO": ticker,
#         "ORD_QTY": str(int(qty)),
#         "OVRS_ORD_UNPR": f"{order_price:.2f}",
#         "ORD_SVR_DVSN_CD": "0",
#         "ORD_DVSN": "00"
#     }

#     for attempt in range(MAX_RETRIES):
#         try:
#             res = requests.post(url, headers=headers, json=body, timeout=10)
#             data = res.json()
#             #success
#             if data.get('rt_cd') == '0':
#                 action_str = "BUY" if is_buy else "SELL"
#                 logger.info(f"{ticker} Order SUCCESS: {action_str} {qty} shares @ ${order_price}")
#                 return True
            
#             else:
#                 logger.error(f"{ticker} Order FAILED (Attempt {attempt+1}/{MAX_RETRIES}): {data.get('msg1')} | Payload: {body}")
#                 if attempt < MAX_RETRIES - 1:
#                     time.sleep(RETRY_DELAY)
        
#         except Exception as e:
#             logger.error(f"[{ticker}] Order API communication error (Attempt {attempt+1}/{MAX_RETRIES}): {e}")
#             if attempt < MAX_RETRIES - 1:
#                 time.sleep(RETRY_DELAY)

#     return False

def send_us_order(token, app_key, app_secret, cano, ticker, exchange, is_buy, qty, price, slippage_factor=0.0):
    if qty <= 0: return False, None
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"
    tr_id = "VTTT1002U" if is_buy else "VTTT1001U"
    order_price = price * (1 + slippage_factor) if is_buy else price * (1 - slippage_factor)
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key, 
        "appsecret": app_secret,
        "tr_id": tr_id
    }
    body = {
        "CANO": cano, 
        "ACNT_PRDT_CD": ACNT_PRDT_CD, 
        "OVRS_EXCG_CD": exchange,
        "PDNO": ticker, 
        "ORD_QTY": str(int(qty)), 
        "OVRS_ORD_UNPR": f"{order_price:.2f}",
        "ORD_SVR_DVSN_CD": "0", 
        "ORD_DVSN": "00"
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                odno = data.get('output', {}).get("ODNO", "")
                action_str = "BUY" if is_buy else "SELL"
                logger.info(f"[{ticker}] Order SUCCESS: {action_str} {qty} shares @ ${order_price:.2f} (ODNO:{odno})")
                return True, odno
            else:
                logger.error(f"[{ticker}] Order FAILED (Attempt {attempt+1}): {data.get('msg1')}")
                if attempt < MAX_RETRIES - 1: 
                    time.sleep(RETRY_DELAY)

        except requests.exceptions.Timeout:
            logger.error(f"[{ticker}] API 타임아웃. 중복매수 방지를 위해 중단.")
            return False, None
        except Exception as e:
            logger.error(f"[{ticker}] API 에러: {e}")
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY)
    return False, None

def check_current_price(token, app_key, app_secret, ticker, excd):
    """KIS 해외주식 현재체결가 조회"""
    url = f"{URL_BASE}/uapi/overseas-price/v1/quotations/price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "HHDFS00000300",  # [모의/실전 동일] 해외주식 현재가
        "custtype": "P"
    }
    params = {
        "AUTH": "",         # Null 값 설정
        "EXCD": excd,       # 나스닥: NAS, 뉴욕: NYS, 아멕스: AMS
        "SYMB": ticker      # 티커
    }
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get("rt_cd") == "0":
                last_price = float(data.get("output", {}).get("last", 0.0))
                return True, last_price
            else:
                logger.error(f"[{ticker}]현재가 조회 실패: {data.get('msg1')}")
                return False, 0.0
        except requests.exceptions.Timeout:
            logger.error(f"[{ticker}] 현재가 조회 API 타임아웃 (Attempt {attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"[{ticker}]현재가 조회 API 통신 에러: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                
    return False, 0.0