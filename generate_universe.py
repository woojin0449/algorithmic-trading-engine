import requests
import json
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

URL_BASE = "https://openapivts.koreainvestment.com:29443" 
# 사용자님 설계: 조회용 거래소 코드와 주문용 거래소 코드 매핑
ORDER_EXCHANGE = {
    "NAS": "NASD",
    "NYS": "NYSE",
    "AMS": "AMEX"
}

def update_universe(token, app_key, app_secret, excd="NAS", target_rank=100):
    """
    KIS API를 호출하여 시가총액 상위 N개 종목으로 Universe.json을 생성/갱신합니다.
    """
    url = f"{URL_BASE}/uapi/overseas-price/v1/quotations/inquire-search"
    
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "HHDFS76410000",
        "custtype": "P"
    }
    
    params = {
        "AUTH": "",
        "EXCD": excd,
        "CO_YN_VALX": "1",              # 시가총액 조건 켬
        "CO_ST_VALX": "10000000",       # 시작액: 10,000,000 (단위: 천 달러 = 약 100억 달러 이상)
        "CO_EN_VALX": "999999999999",   # 끝액: 999,999,999,999 (무한대에 가깝게)
        "KEYB": ""
    }
    
    logger.info(f"[{excd}] 유니버스 (시총 상위 {target_rank}개) 갱신 요청 중...")
    
    try:
        # [방어 로직] 15초 타임아웃
        res = requests.get(url, headers=headers, params=params, timeout=15)
        data = res.json()
        
        if data.get("rt_cd") != "0":
            logger.error(f"유니버스 조회 실패: {data.get('msg1')}")
            return False
            
        stock_list = data.get("output2", [])
        if not stock_list:
            logger.error("반환된 종목 리스트가 없습니다.")
            return False
            
        # Universe 딕셔너리 조립 (사용자님 설계 포맷 적용)
        universe_data = {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec='seconds'),
            "source": "KIS",
            "criteria": {
                "exchange": excd,
                "market_cap_rank": target_rank
            },
            "stocks": {}
        }
        
        # 반환된 리스트에서 순위대로 파싱 (최대 100개)
        for idx, stock in enumerate(stock_list):
            if idx >= target_rank:
                break
                
            ticker = stock.get("symb")
            market = stock.get("excd", excd)
            
            universe_data["stocks"][ticker] = {
                "market": market,
                "order_exchange": ORDER_EXCHANGE.get(market, "NASD"), # 훗날 주문 시 사용할 코드 미리 매핑
                "rsym": stock.get("rsym"),
                "name": stock.get("name"),
                "rank": idx + 1,
                "market_cap_k": stock.get("valx") # 시총(천 단위) 참고용 저장
            }
            
        # 파일 저장
        with open("Universe.json", "w", encoding="utf-8") as f:
            json.dump(universe_data, f, indent=4, ensure_ascii=False)
            
        logger.info(f"✅ Universe.json 갱신 완료 ({len(universe_data['stocks'])}개 종목 저장됨)")
        return True
        
    except Exception as e:
        logger.error(f"유니버스 API 통신 중 에러 발생: {e}")
        return False

if __name__ == "__main__":
    from api.kis_broker import get_access_token 
    from config import APP_KEY, APP_SECRET 

    print("유니버스 수동 업데이트를 시작합니다...")
    token = get_access_token(APP_KEY, APP_SECRET)
    
    if token:
        update_universe(token, APP_KEY, APP_SECRET, excd="NAS", target_rank=100)
        print("유니버스 업데이트 완료!")
    else:
        print("토큰 발급 실패로 유니버스를 업데이트할 수 없습니다.")