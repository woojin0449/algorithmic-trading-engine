import requests
import json
import os
import time
import logging
from datetime import datetime, timedelta

# To be loaded from config.py or environment variables later
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
def get_account_balance(token, app_key, app_secret, cano):
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "VTTS3012R",
    }
    body = {
        "CANO": cano,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD"
    }

    try:
        #post -> get
        res = requests.get(url, headers=headers, params=body, timeout=10)
        data = res.json()

        if data.get('rt_cd') == '0':
            summary = data.get('output2', {})
            total_buy = float(summary.get('frcr_buy_amt_smtl1',0))
            total_pnl = float(summary.get('tot_evlu_pfls_amt', 0))
            total_equity = total_buy + total_pnl
            #현재 재화를 출력하려면 전체 잔고가 다 출력되는 극단적 단점이 존재함
            cash = 0 # To be extracted later if needed
            return total_equity, cash
        else:
            logger.error(f"Failed to fetch balance: {data.get('msg1')}")
            return 0,0

    except Exception as e:
        logger.error(f"Balance API error: {e}")
        return 0, 0

# Send a US stock buy/sell order to KIS API
def send_us_order(token, app_key, app_secret, cano, ticker, is_buy, qty, price, slippage_factor=SLIPPAGE_FACTOR):
    if qty <= 0:
        return False
    
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"
    # VTTT1002U: Buy, VTTT1001U: Sell
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
        "OVRS_EXCG_CD": "NASD",
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
            #success
            if data.get('rt_cd') == '0':
                action_str = "BUY" if is_buy else "SELL"
                logger.info(f"{ticker} Order SUCCESS: {action_str} {qty} shares @ ${order_price}")
                return True
            
            else:
                logger.error(f"{ticker} Order FAILED (Attempt {attempt+1}/{MAX_RETRIES}): {data.get('msg1')} | Payload: {body}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        
        except Exception as e:
            logger.error(f"[{ticker}] Order API communication error (Attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return False

