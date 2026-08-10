# api/kis_broker.py
import requests
import json
import os
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("TurtleBot")

URL_BASE = "https://openapivts.koreainvestment.com:29443"
ACNT_PRDT_CD = "01"
MAX_RETRIES = 3
RETRY_DELAY = 2
SLIPPAGE_FACTOR = 0.003

def get_access_token(app_key, app_secret):
    token_file = "kis_token.json"
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                saved_token = json.load(f)
                token_time = datetime.strptime(saved_token['timestamp'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() - token_time < timedelta(hours=20):
                    return saved_token['token']
        except Exception:
            pass

    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
    
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(body), timeout=15)
            data = res.json()
            if "access_token" in data:
                token = data["access_token"]
                # safe_save_json을 임포트하지 않고 직접 처리하여 의존성 분리
                tmp_file = token_file + ".tmp"
                with open(tmp_file, "w") as f:
                    json.dump({"token": token, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, indent=4)
                os.replace(tmp_file, token_file)
                
                logger.info("새로운 API 토큰 발급 및 저장 성공!")
                return token
            else:
                logger.error(f"토큰 발급 거부됨: {data}")
                return None
        except Exception as e:
            logger.error(f"접속 토큰 발급 통신 에러 (시도 {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return None

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
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if data.get('rt_cd') == '0':
            summary = data.get('output2', {})
            total_buy = float(summary.get('frcr_buy_amt_smtl1', 0))
            total_pnl = float(summary.get('tot_evlu_pfls_amt', 0))
            total_equity = total_buy + total_pnl
            cash = 0
            return total_equity, cash
        else:
            logger.error(f"잔고 조회 실패: {data.get('msg1')}")
            return 0, 0
    except Exception as e:
        logger.error(f"잔고 조회 API 에러: {e}")
        return 0, 0

def send_us_order(token, app_key, app_secret, cano, ticker, is_buy, qty, price, slippage_factor=SLIPPAGE_FACTOR):
    if qty <= 0:
        return False
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"

    if is_buy:
        tr_id = "VTTT1002U"
        order_price = price * (1 + slippage_factor)
    else:
        tr_id = "VTTT1001U"
        order_price = price * (1 - slippage_factor)

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
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                logger.info(f"[{ticker}] 주문 성공: {'매수' if is_buy else '매도'} {qty}주 @ ${order_price:.2f}")
                return True
            else:
                logger.error(f"[{ticker}] 주문 실패 (시도 {attempt+1}/{MAX_RETRIES}): {data.get('msg1')} | 주문내역: {body}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"[{ticker}] 주문 API 통신 에러 (시도 {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return False
