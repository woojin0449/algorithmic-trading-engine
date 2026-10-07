import json
from api.kis_broker import get_access_token, get_order_execution
from config import APP_KEY, APP_SECRET, CANO, ACNT_PRDT_CD

def run_test():
    print("1. 토큰 발급 시도 중...")
    token = get_access_token(APP_KEY, APP_SECRET)
    
    if not token:
        print("❌ 토큰 발급 실패")
        return

    print("2. 체결/미체결 API(inquire-ccnl) 호출 중...")
    try:
        # 우리가 수정한 그 함수 호출
        execution_data = get_order_execution(token, APP_KEY, APP_SECRET, CANO, ACNT_PRDT_CD)
        
        print("\n=== 🎯 API 응답 결과 (Raw Data) ===")
        if not execution_data:
            print("응답이 비어있습니다 ([]). 파라미터 문제거나 정말 미체결 내역이 없는 상태입니다.")
        else:
            # 예쁘게 출력
            print(json.dumps(execution_data, indent=4, ensure_ascii=False))
            
            print("\n=== 📋 상태 요약 ===")
            for order in execution_data:
                ticker = order.get("pdno", "알수없음")
                odno = order.get("odno", "번호없음")
                nccs_qty = order.get("nccs_qty", "0")
                print(f"종목: {ticker} | 주문번호: {odno} | 미체결수량: {nccs_qty}주")
                
    except Exception as e:
        print(f"❌ 실행 중 에러 발생: {e}")

if __name__ == "__main__":
    run_test()