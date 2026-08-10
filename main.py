import requests
import json
import yfinance as yf
import pandas as pd
import math
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
from datetime import time as dt_time  # 이름 충돌을 막기 위한 별명 추가
from logger import log_trade
from dotenv import load_dotenv
import gc
import pytz  # 뉴욕 타임존 계산용


# ========================================================
# [MODULE 1] 환경 설정 및 로깅 (KST 적용)
# ========================================================
load_dotenv()

KST = timezone(timedelta(hours=9))

logger = logging.getLogger("TurtleBot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logging.Formatter.converter = lambda *args: datetime.now(KST).timetuple()

file_handler = RotatingFileHandler('bot_status.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
CANO = os.environ.get("CANO")
ACNT_PRDT_CD = "01"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
URL_BASE = "https://openapivts.koreainvestment.com:29443"

STATE_FILE = "turtle_state.json"
LAST_LIQUIDATION_FILE = "last_liquidation.json"
V2_CORE_UNIVERSE = ["AVGO", "INTC", "MU", "AMD", "CRWD", "NVDA"]
BALANCE_FILE = "balance.json"

RISK_PER_UNIT = 0.01  # 1회 매매당 총자산의 1% 리스크
STOP_N = 2.0          # 손절 폭 (2 * ATR)
PYRAMID_N = 0.5       # 피라미딩 간격 (0.5 * ATR)
MAX_UNITS = 3
MAX_HOLDINGS = 4
SLIPPAGE_FACTOR = 0.003  # 슬리피지 비율 (0.1%)
MAX_RETRIES = 3           # API 재시도 횟수
RETRY_DELAY = 2           # 재시도 대기 시간(초)

LAST_UPDATE_ID = 0
PAUSED = False             # 매매 중지 플래그
last_liquidated = {}       # 청산 기록 저장 (전역)

# ========================================================
# [MODULE 2] 유틸리티 (안전한 파일 저장 등)
# ========================================================
def safe_save_json(data, filename):
    """원자성(Atomicity)을 보장하는 안전한 JSON 저장"""
    tmp_file = filename + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp_file, filename)

def save_closed_trade(ticker, exit_price, qty, cost, revenue, roi_pct, reason):
    file_name = "closed_trades.csv"
    file_exists = os.path.exists(file_name)
    with open(file_name, 'a', encoding='utf-8') as f:
        if not file_exists:
            f.write("Exit_Date,Ticker,Exit_Price,Qty,Total_Cost,Total_Revenue,ROI_Percent,Exit_Reason\n")
        exit_date = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"{exit_date},{ticker},{exit_price},{qty},{cost:.2f},{revenue:.2f},{roi_pct:.2f},{reason}\n")

def load_tickers():
    return V2_CORE_UNIVERSE

def send_telegram_msg(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")

def check_telegram_commands(state):
    global LAST_UPDATE_ID, PAUSED
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_UPDATE_ID}&timeout=5"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("ok") and res.get("result"):
            for item in res["result"]:
                LAST_UPDATE_ID = item["update_id"] + 1
                text = item.get("message", {}).get("text", "")

                if text == "/status":
                    balance_data = get_balance_from_file()
                    usd_balance = balance_data.get("usd_balance", 0)
                    active_count = sum(1 for v in state.values() if v.get('units', 0) > 0)
                    report = f"[현재 상태 보고]\n가용 현금: ${usd_balance:,.2f}\n운용 종목: {active_count}/{MAX_HOLDINGS}개\n"
                    if PAUSED:
                        report += "❗ 매매 중지 상태 (PAUSED)\n"
                    for t, v in state.items():
                        if v.get('units', 0) > 0:
                            avg_p = v['total_entry_price'] / v['qty']
                            curr_p = v.get('current_price', avg_p)
                            pnl_pct = ((curr_p - avg_p) / avg_p) * 100 if avg_p > 0 else 0
                            report += f"\n[{t}] {v['qty']}주 ({v['units']} Unit)\n평단: ${avg_p:.2f} | 현재: ${curr_p:.2f} ({pnl_pct:+.2f}%)"
                    send_telegram_msg(report)

                elif text == "/stop":
                    PAUSED = True
                    send_telegram_msg("매매가 중지되었습니다. (PAUSED = True)")
                elif text == "/resume":
                    PAUSED = False
                    send_telegram_msg("매매가 재개되었습니다. (PAUSED = False)")
                elif text == "/reset":
                    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
                    if os.path.exists(LAST_LIQUIDATION_FILE): os.remove(LAST_LIQUIDATION_FILE)
                    state.clear()
                    last_liquidated.clear() 
                    send_telegram_msg("상태 파일 및 청산 기록이 완벽하게 초기화되었습니다.")
                elif text == "/positions":
                    report = "=== 현재 포지션 상세 ===\n"
                    for t, v in state.items():
                        if v.get('units', 0) > 0:
                            avg_p = v['total_entry_price'] / v['qty']
                            curr_p = v.get('current_price', avg_p)
                            pnl_pct = ((curr_p - avg_p) / avg_p) * 100 if avg_p > 0 else 0
                            stop_loss = v.get('stop_loss', 0)
                            report += f"\n{t}:\n  수량: {v['qty']}\n  유닛: {v['units']}\n  평단: ${avg_p:.2f}\n  현재: ${curr_p:.2f} ({pnl_pct:+.2f}%)\n  손절가: ${stop_loss:.2f}\n"
                    send_telegram_msg(report)
                elif text == "/balance":
                    bal_data = get_balance_from_file()
                    send_telegram_msg(f"외화 예수금 : ${bal_data.get('usd_balance', 0):,.2f}")
    except Exception as e:
        logger.exception("텔레그램 체크 실패")

def get_balance_from_file():
    try:
        if os.path.exists(BALANCE_FILE):
            with open(BALANCE_FILE, "r") as f:
                return json.load(f)
        else:
            return {"usd_balance": 20000.0, "total_equity": 20000.0, "last_update": "없음"}
    except Exception as e:
        logger.error(f"잔고 파일 읽기 실패: {e}")
        return {"usd_balance": 20000.0, "total_equity": 20000.0, "last_update": "오류"}

def update_cash_balance(amount_change):
    bal_data = get_balance_from_file()
    current_cash = bal_data.get("usd_balance", 20000.0)
    new_cash = current_cash + amount_change
    bal_data["usd_balance"] = new_cash
    safe_save_json(bal_data, BALANCE_FILE)
    return new_cash

# ========================================================
# [MODULE 2.5] 브로커 통신 (재시도 로직 포함)
# ========================================================
def get_access_token():
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
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(body), timeout=15)
            data = res.json()
            if "access_token" in data:
                token = data["access_token"]
                safe_save_json({"token": token, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, token_file)
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


def update_balance_and_positions(state):
    bal_data = get_balance_from_file()
    usd_cash = bal_data.get("usd_balance", 20000.0)

    stock_value = 0.0
    for ticker, pos in state.items():
        if pos.get('units', 0) > 0:
            qty = pos.get('qty', 0)
            current_price = pos.get('current_price', 0)
            stock_value += qty * current_price

    total_equity = usd_cash + stock_value

    balance_data = {
        "usd_balance": usd_cash,
        "total_equity": total_equity,
        "stock_value": stock_value,
        "last_update": datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    }
    safe_save_json(balance_data, BALANCE_FILE)
    logger.info(f"자산 업데이트: 총자산=${total_equity:,.2f}, 현금=${usd_cash:,.2f}, 주식평가=${stock_value:,.2f}")
    return total_equity, usd_cash

def send_us_order(token, ticker, is_buy, qty, price, slippage_factor=SLIPPAGE_FACTOR):
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
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id
    }
    body = {
        "CANO": CANO,
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
                # [수정] CANO, ACNT_PRDT_CD 등 민감정보 제거 후 로깅
                safe_body = {k: v for k, v in body.items() if k not in ['CANO', 'ACNT_PRDT_CD']}
                logger.error(f"[{ticker}] 주문 실패 (시도 {attempt+1}/{MAX_RETRIES}): {data.get('msg1')} | 주문내역: {safe_body}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"[{ticker}] 주문 API 통신 에러 (시도 {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return False

def is_market_open():
    """미국 정규장 시간(평일 09:30 ~ 16:00) 여부를 확인합니다."""
    ny_tz = pytz.timezone('America/New_York')
    ny_now = datetime.now(ny_tz)
    
    # 1. 주말(토=5, 일=6) 필터링
    if ny_now.weekday() >= 5:
        return False
        
    # 2. 정규장 시간(09:30 ~ 16:00) 필터링
    market_open = dt_time(9, 30)
    market_close = dt_time(16, 0)
    
    if market_open <= ny_now.time() < market_close:
        return True
        
    return False

# ========================================================
# [MODULE 3] 전략 엔진
# ========================================================
def get_turtle_signals(ticker, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False)
            if df.empty or len(df) < 200:
                raise ValueError("데이터 부족")

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df['DC_upper'] = df['High'].rolling(55).max()
            df['DC_lower'] = df['Low'].rolling(20).min()
            df['MA200'] = df['Close'].rolling(200).mean()
            df['TR'] = pd.concat([
                (df['High'] - df['Low']),
                (df['High'] - df['Close'].shift()).abs(),
                (df['Low'] - df['Close'].shift()).abs()
            ], axis=1).max(axis=1)
            df['ATR'] = df['TR'].rolling(20).mean()
            #결측치 타당성 검토
            atr_val = float(df.iloc[-2]['ATR'])
            curr_val = float(df.iloc[-1]['Close'])
            
            if math.isnan(atr_val) or math.isnan(curr_val) or atr_val <= 0:
                raise ValueError("데이터 결측치(NaN) 또는 오류 값 존재")

            return {
                'current_price': curr_val,
                'dc_upper': float(df.iloc[-2]['DC_upper']),
                'dc_lower': float(df.iloc[-2]['DC_lower']),
                'ma200': float(df.iloc[-2]['MA200']),
                'atr': atr_val
            }
        except Exception as e:
            logger.warning(f"[{ticker}] 데이터 다운로드 실패 (시도 {attempt+1}/{max_retries+1}): {e}")
            if attempt < max_retries:
                time.sleep(1)
            else:
                return None
    return None

def handle_entry(token, ticker, state, signal, total_equity):
    """진입 및 피라미딩 조건을 확인하고 주문을 실행합니다."""
    global last_liquidated

    if ticker in last_liquidated:
        last_time = datetime.fromisoformat(last_liquidated[ticker])
        if datetime.now(KST) - last_time < timedelta(hours=24):
            return

    p = state.get(ticker, {
        'qty': 0, 'total_entry_price': 0, 'units': 0,
        'last_entry_price': 0, 'stop_loss': 0, 'current_price': signal['current_price'],
        'latest_atr': 0 # [수정] 박제용 ATR 필드 추가
    })
    
    curr = signal['current_price']
    active_count = sum(1 for v in state.values() if v.get('units', 0) > 0)

# 1. 신규 진입 (1차 매수)
    if p['units'] == 0:
        if active_count >= MAX_HOLDINGS:
            return
            
        if curr > signal['dc_upper'] and curr > signal['ma200']:
            # [가비지 틱 방어] 첫 감지 시 1턴 대기
            if not p.get('pending_action', False):
                logger.info(f"[{ticker}] 1차 돌파 시그널 감지. 가비지 틱 방어를 위해 1턴(5분) 대기합니다.")
                p['pending_action'] = True
                state[ticker] = p
                return
                
            # 두 번째 사이클에서도 유지되면 진입 확정
            p['pending_action'] = False
            
            fixed_atr = signal['atr']
            unit_size = math.floor((total_equity * RISK_PER_UNIT) / (STOP_N * fixed_atr))
            if unit_size <= 0:
                return

            cost = curr * unit_size
            usd_cash = get_balance_from_file().get("usd_balance", 0)
            if usd_cash < cost:
                logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 매수 진입 포기.")
                return

            if send_us_order(token, ticker, True, unit_size, curr):
                update_cash_balance(-cost)
                msg = f"[1차 진입] {ticker} 55일 돌파\n수량: {unit_size}주 / 단가: ${curr:.2f}"
                logger.info(msg)
                send_telegram_msg(msg)
                log_trade(ticker, "BUY(1차)", unit_size, curr, 1, fixed_atr)

                p['qty'] = unit_size
                p['total_entry_price'] = cost
                p['units'] = 1
                p['last_entry_price'] = curr
                p['latest_atr'] = fixed_atr 
                p['stop_loss'] = curr - (STOP_N * fixed_atr)
                p['current_price'] = curr
                state[ticker] = p
        else:
            # 시그널 소멸 시 대기 플래그 해제 (가짜 틱)
            if p.get('pending_action', False):
                logger.info(f"[{ticker}] 1차 시그널 소멸. 가비지 틱으로 간주하여 진입을 취소합니다.")
                p['pending_action'] = False
                state[ticker] = p

    # 2. 피라미딩 (추가 매수)
    elif 0 < p['units'] < MAX_UNITS:
        fixed_atr = p['latest_atr']
        pyramid_target = p['last_entry_price'] + (PYRAMID_N * fixed_atr)
        
        if curr > pyramid_target:
            # [가비지 틱 방어] 피라미딩 첫 감지 시 1턴 대기
            if not p.get('pending_action', False):
                logger.info(f"[{ticker}] 피라미딩 시그널 감지. 가비지 틱 방어를 위해 1턴(5분) 대기합니다.")
                p['pending_action'] = True
                state[ticker] = p
                return
                
            # 두 번째 사이클에서도 유지되면 불타기 확정
            p['pending_action'] = False
            
            add_qty = math.floor((total_equity * RISK_PER_UNIT) / (STOP_N * fixed_atr))
            if add_qty <= 0:
                return

            cost = curr * add_qty
            usd_cash = get_balance_from_file().get("usd_balance", 0)
            if usd_cash < cost:
                logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 추가 매수 포기.")
                return

            if send_us_order(token, ticker, True, add_qty, curr):
                update_cash_balance(-cost)
                new_units = p['units'] + 1
                msg = f"[{new_units}차 피라미딩] {ticker} 불타기\n수량: {add_qty}주 / 단가: ${curr:.2f}"
                logger.info(msg)
                send_telegram_msg(msg)
                log_trade(ticker, f"BUY({new_units}차)", add_qty, curr, new_units, fixed_atr)

                p['qty'] += add_qty
                p['total_entry_price'] += cost
                p['units'] = new_units
                p['last_entry_price'] = curr
                p['stop_loss'] = curr - (STOP_N * fixed_atr)
                p['current_price'] = curr
                state[ticker] = p
        else:
            # 시그널 소멸 시 대기 플래그 해제 (가짜 틱)
            if p.get('pending_action', False):
                logger.info(f"[{ticker}] 피라미딩 시그널 소멸. 가비지 틱으로 간주하여 진입을 취소합니다.")
                p['pending_action'] = False
                state[ticker] = p
                
def handle_exit(token, ticker, state, signal):
    """청산 조건을 확인하고 주문을 실행합니다."""
    global last_liquidated

    p = state.get(ticker)
    if not p or p.get('units', 0) == 0:
        return

    curr = signal['current_price']
    
    fixed_atr = p['latest_atr']
    stop_loss_price = p['last_entry_price'] - (STOP_N * fixed_atr)
    
    # [수정] Issue 3: 청산 사유 판별
    exit_reason = None
    if curr < signal['dc_lower']:
        exit_reason = "Trailing Stop(20일 저점 이탈)"
    elif curr < stop_loss_price:
        exit_reason = f"2.0N Hard Stop(손절가 ${stop_loss_price:.2f} 도달)"

    if exit_reason:
        if send_us_order(token, ticker, False, p['qty'], curr):
            # [수정] Issue 1: 최종 수익률(ROI) 계산
            revenue = curr * p['qty']
            cost = p['total_entry_price']
            roi_pct = ((revenue - cost) / cost) * 100 if cost > 0 else 0

            update_cash_balance(revenue)

            # 텔레그램 및 로거 메시지 고도화
            msg = f"[청산] {ticker} 전량 매도\n사유: {exit_reason}\n매도단가: ${curr:.2f}\n최종 수익률: {roi_pct:+.2f}%"
            
            logger.info(msg.replace("\n", " | "))
            send_telegram_msg(msg)
            
            # 외부 로거 및 CSV 데이터 영구 저장
            log_trade(ticker, f"SELL({exit_reason})", p['qty'], curr, 0, fixed_atr)
            save_closed_trade(ticker, curr, p['qty'], cost, revenue, roi_pct, exit_reason)

            last_liquidated[ticker] = datetime.now(KST).isoformat()
            safe_save_json(last_liquidated, LAST_LIQUIDATION_FILE)

            # 상태 초기화
            state[ticker] = {
                'qty': 0, 'total_entry_price': 0, 'units': 0,
                'last_entry_price': 0, 'stop_loss': 0, 'current_price': curr, 'latest_atr': 0
            }



# ========================================================
# [MODULE 4] 전략 엔진 및 실행 제어
# ========================================================
def run_cycle(last_report_hour):
    global PAUSED, last_liquidated
    logger.info("새로운 스캔 사이클 시작")

    # [Issue 5] 마켓 스케줄러: 장외 시간 리소스 절약 및 무의미한 통신 방어
    if not is_market_open() and not PAUSED:
        logger.info("미국 정규장 휴장 시간입니다. 매매 통신을 건너뛰고 대기합니다.")
        return last_report_hour

    token = get_access_token()
    if not token:
        return last_report_hour

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {}

    if os.path.exists(LAST_LIQUIDATION_FILE):
        with open(LAST_LIQUIDATION_FILE, 'r') as f:
            last_liquidated = json.load(f)
    else:
        last_liquidated = {}

    now_kst = datetime.now(KST)
    current_hour = now_kst.hour
    if current_hour != last_report_hour:
        bal_data = get_balance_from_file()
        send_telegram_msg(f"[정기 보고] 정상 가동 중\n총 자산: ${bal_data.get('total_equity', 0):,.2f}\n가용 현금: ${bal_data.get('usd_balance', 0):,.2f}")
        last_report_hour = current_hour

    check_telegram_commands(state)

    if PAUSED:
        logger.info("매매 중지 상태. 스캔만 수행합니다.")
        tickers = load_tickers()
        
        for ticker in tickers:
            try:
                signal = get_turtle_signals(ticker)
                if signal:
                    if ticker in state and state[ticker].get('units', 0) > 0:
                        state[ticker]['current_price'] = signal['current_price']
                        
                handle_exit(token, ticker, state, signal)
                time.sleep(0.6)
            except Exception as e:
                logger.warning(f"[{ticker}] 건너뜀: {e}")
        safe_save_json(state, STATE_FILE)
        return last_report_hour

    tickers = load_tickers()
    count = 0

    for ticker in tickers:
        try:
            signal = get_turtle_signals(ticker)
            if signal is None:
                logger.warning(f"[{ticker}] 데이터 부족으로 스킵")
                continue

            curr = signal['current_price']

            if ticker in state and state[ticker].get('units', 0) > 0:
                state[ticker]['current_price'] = curr

            handle_exit(token, ticker, state, signal)


            if not PAUSED:   # ← 신규 진입만 PAUSED일 때 막음
                bal_data = get_balance_from_file()
                usd_cash = bal_data.get("usd_balance", 20000.0)
                stock_value = sum(pos.get('qty', 0) * pos.get('current_price', 0) for pos in state.values() if pos.get('units', 0) > 0)
                total_equity = usd_cash + stock_value
                handle_entry(token, ticker, state, signal, total_equity)

            time.sleep(0.6)
            count += 1
            if count % 10 == 0:
                logger.info(f"진행 상황: {count}/{len(tickers)} 완료")

        except Exception as e:
            logger.exception(f"[{ticker}] 처리 중 예외: {e}")
        time.sleep(0.6)


    total_equity, usd_cash = update_balance_and_positions(state)
    safe_save_json(state, STATE_FILE)
    logger.info("모든 종목 스캔 완료. 5분 대기...")
    gc.collect()
    return last_report_hour

# ========================================================
# [실행부]
# ========================================================
if __name__ == "__main__":
    start_msg = "터틀 봇 v3.1 가동 시작 (고정 ATR, 수량 공식 수정 반영)"
    logger.info(start_msg)
    send_telegram_msg(start_msg)

    last_reported_hour = -1

    try:
        while True:
            try:
                last_reported_hour = run_cycle(last_reported_hour)
                time.sleep(300)
            except Exception as e:
                logger.error(f"시스템 예외 발생: {e}")
                time.sleep(60)
    except KeyboardInterrupt:
        logger.info("사용자에 의해 시스템이 안전하게 종료되었습니다.")
