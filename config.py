 # 1. Trading parameters
 
RISK_PER_UNIT = 0.01      # 1 유닛 당 총자산의 1% 리스크
STOP_N = 2.0              # 손절 폭
PYRAMID_N = 0.5           # 피라미딩 간격 
MAX_UNITS = 3             # 단일 종목 최대 진입 유닛
MAX_HOLDINGS = 4          # 포트폴리오 내 최대 동시 보유 종목 수

 # 2. System and API Communication settings
 
SLIPPAGE_FACTOR = 0.003   # 예상 슬리피지 비율 보정용
MAX_RETRIES = 3           # API 통신 실패 시 재시도 횟수
RETRY_DELAY = 2           # 재시도 대기 시간 (초)

 # 3. Date and Status management file paths
 
STATE_FILE = "turtle_state.json"
LAST_LIQUIDATION_FILE = "last_liquidation.json"
BALANCE_FILE = "balance.json"
TICKERS_FILE = "data/tickers.csv"
