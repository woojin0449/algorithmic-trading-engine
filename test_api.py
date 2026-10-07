import os
# import requests
import json
# from dotenv import load_dotenv
from api.kis_broker import *
from generate_universe import update_universe
from config import *
# 환경 변수 세팅


BASE_URL = "https://openapivts.koreainvestment.com:29443"

def get_new_token():
    """테스트용 토큰을 즉시 새로 발급받습니다."""
    print("🔑 새로운 KIS 토큰을 발급받는 중...")
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(url, headers=headers, json=body)
    token = res.json().get("access_token")
    if token:
        print("✅ 토큰 발급 성공!\n")
        return token
    else:
        print(f"❌ 토큰 발급 실패: {res.text}")
        return None

def check_overseas_balance(token):
    """해외주식 잔고 및 예수금 조회"""
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-balance"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTS3012R",
        "custtype": "P"
    }
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    res = requests.get(url, headers=headers, params=params)
    print("================ [해외주식 잔고 조회] ================")
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

def check_unexecuted_orders(token):
    """해외주식 미체결 내역 조회"""
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-nccs"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTS3018R",
        "custtype": "P"
    }
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "SORT_SQN": "DS",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    res = requests.get(url, headers=headers, params=params)
    print("\n================ [해외주식 미체결 조회] ================")
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

def check_orderable_amount(token):
    """해외주식 매수 가능 예수금(달러) 조회"""
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/inquire-psamount"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTS3007R",  # [모의] 해외주식 매수가능금액 조회
        "custtype": "P"
    }
    # 이 API는 단가와 종목코드를 빈칸으로 넘기면 전체 예수금을 알려줍니다.
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "OVRS_ORD_UNPR": "0",      # 빈칸 대신 "0" 달러
        "ITEM_CD": "AAPL"          # 빈칸 대신 "AAPL" (임의의 종목)
    }
    res = requests.get(url, headers=headers, params=params)
    print("\n================ [해외주식 매수 가능 예수금 조회] ================")
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

def check_current_price(token, ticker="AAPL", excd="NAS"):
    """KIS 해외주식 현재체결가 조회"""
    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS00000300",  # [모의/실전 동일] 해외주식 현재가
        "custtype": "P"
    }
    params = {
        "AUTH": "",         # Null 값 설정
        "EXCD": excd,       # 나스닥: NAS, 뉴욕: NYS, 아멕스: AMS
        "SYMB": ticker      # 티커
    }
    
    res = requests.get(url, headers=headers, params=params)
    print(f"\n================ [{ticker}] 현재체결가 조회 ================")
    
    data = res.json()
    if data.get("rt_cd") == "0":
        last_price = data.get("output", {}).get("last")
        sign = data.get("output", {}).get("sign") # 1:상한, 2:상승, 3:보합, 4:하한, 5:하락
        print(f"✅ {ticker} 현재가: ${last_price} (대비기호: {sign})")
    else:
        print(f"❌ 조회 실패: {data.get('msg1')}")
    
    print(json.dumps(data, indent=2, ensure_ascii=False))

def send_us_order(token, app_key, app_secret, cano, ticker, is_buy, qty, price, exchange="NASD",slippage_factor=SLIPPAGE_FACTOR):
    if qty <= 0:
        return False, None
    
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
            #success
            if data.get('rt_cd') == '0':
                action_str = "BUY" if is_buy else "SELL"
                logger.info(f"{ticker} Open Order: {action_str} {qty} shares @ ${order_price}")
                #주문 번호 리턴?
                order_number = data.get('output', {}).get('ODNO')
                return True, order_number
            
            else:
                logger.error(f"{ticker} Order FAILED (Attempt {attempt+1}/{MAX_RETRIES}): {data.get('msg1')} | Payload: {body}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        
        except Exception as e:
            logger.error(f"[{ticker}] Order API communication error (Attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return False, None

def created_universe(token, excd="NAS"):
    """KIS 해외주식 조건 검색"""
    url = f"{BASE_URL}/uapi/overseas-price/v1/quotations/inquire-search"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS76410000",  # [모의/실전 동일] 해외주식 현재가
        "custtype": "P"
    }
    params = {
        "AUTH": "",
        "EXCD": "NAS",

        # 시가총액 조건 사용
        "CO_YN_VALX": "1",

        # 범위는 일단 넓게
        "CO_ST_VALX": "0",
        "CO_EN_VALX": "999999999999",

        "KEYB": "",
    }
    
    res = requests.get(url, headers=headers, params=params)
    print(f"\n================ 해외주식 조건 검색 ================")
    
    data = res.json()
    if data.get("rt_cd") == "0":
        for item in data.get("output2", []):
            print(
                item.get("rank"),
                item.get("symb"),
                item.get("name"),
                item.get("valx"),
                item.get("excd"),
                item.get("rsym"),
            )

    else:
        print(f"❌ 조회 실패: {data.get('msg1')}")
    
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # print(f"📡 테스트 계좌번호: {CANO}-{ACNT_PRDT_CD} 통신 시작...")
    
    # 1. 토큰 발급
    # fresh_token = get_new_token()
    token = get_access_token(APP_KEY, APP_SECRET)
    update_universe(token, APP_KEY, APP_SECRET, "NAS", 100)
    # if fresh_token:
    #     # 2. 잔고 & 미체결 조회
    #     check_overseas_balance(fresh_token)
    #     check_orderable_amount(fresh_token)
    #     check_current_price(fresh_token, ticker="AAPL", excd="NAS")
    #     check_current_price(fresh_token, ticker="TSM", excd="NYS")
    # get_access_token(APP_KEY, APP_SECRET)
    # saved_token = load_json("kis_token.json")
    # created_universe(fresh_token)