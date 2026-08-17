import math
from datetime import datetime, timedelta
import pytz

from config import *
from api.kis_broker import send_us_order
from utils.file_io import safe_save_json, load_json
from utils.logger import logger


def update_cash_balance(amount_change):
    #BALANCE_FILE config 에 존재 config 만들어야함.
    bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
    new_cash = bal_data["usd_balance"] + amount_change
    bal_data["usd_balance"] = new_cash
    safe_save_json(bal_data, BALANCE_FILE)
    return new_cash

def update_balance_and_positions(state):
    bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
    usd_cash = bal_data["usd_balance"]

    stock_value = 0.0
    for ticker, pos in state.items():
        if pos.get('units', 0) > 0:
            stock_value += pos.get('qty', 0) * pos.get('current_price', 0)
    
    total_equity = usd_cash + stock_value

    balance_data = {
        "usd_balance": usd_cash,
        "total_equity": total_equity,
        "stock_value": stock_value,
        "last_update": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    }
    safe_save_json(balance_data, BALANCE_FILE)
    logger.info(f"Asset Update: Total Equity=${total_equity:,.2f}, Cash=${usd_cash:,.2f}, Stocks=${stock_value:,.2f}")
    return total_equity, usd_cash


def handle_entry(token, ticker, state, indicators, total_equity):

    last_liquidated = load_json(LAST_LIQUIDATION_FILE) or {}
    if ticker in last_liquidated:
        last_time = datetime.fromisoformat(last_liquidated[ticker])
        if datetime.now(pytz.timezone('Asia/Seoul')) - last_time < timedelta(hours=24):
            return

    
    p = state.get(ticker, {
        'qty': 0, 'total_entry_price': 0,'units': 0,
        'last_entry_price': 0, 'stop_loss': 0, 'current_price': indicators['current_price'],
        'latest_atr': 0, 'pending_action': False
    })

    curr = indicators['current_price']
    active_count = sum(1 for v in state.values() if v.get('units', 0) > 0)

    # 1. 신규 진입 (1차 매수)
    if p['units'] == 0:
        if active_count >= MAX_HOLDINGS:
            return
            
        if curr > indicators['dc_upper'] and curr > indicators['ma200']:
            # [가비지 틱 방어] 첫 감지 시 1턴 대기
            if not p.get('pending_action', False):
                logger.info(f"[{ticker}] 1차 돌파 시그널 감지. 가비지 틱 방어를 위해 1턴(5분) 대기합니다.")
                p['pending_action'] = True
                state[ticker] = p
                return
                
            # 두 번째 사이클에서도 유지되면 진입 확정
            p['pending_action'] = False
            
            fixed_atr = indicators['atr']
            unit_size = math.floor((total_equity * RISK_PER_UNIT) / (STOP_N * fixed_atr))
            if unit_size <= 0:
                return

            cost = curr * unit_size
            bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
            usd_cash = bal_data["usd_balance"]
            if usd_cash < cost:
                logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 매수 진입 포기.")
                return

            if send_us_order(token, ticker, True, unit_size, curr):
                update_cash_balance(-cost)
                msg = f"[1차 진입] {ticker} 55일 돌파\n수량: {unit_size}주 / 단가: ${curr:.2f}"
                logger.info(msg)
                

                p['qty'] = unit_size
                p['total_entry_price'] = cost
                p['units'] = 1
                p['last_entry_price'] = curr
                p['latest_atr'] = fixed_atr 
                p['stop_loss'] = curr - (STOP_N * fixed_atr)
                p['current_price'] = curr
                state[ticker] = p
        else:
            # 시그널 소멸 시 대기 플래그 해제
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
            bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
            usd_cash = bal_data["usd_balance"]
            if usd_cash < cost:
                logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 추가 매수 포기.")
                return

            if send_us_order(token, ticker, True, add_qty, curr):
                update_cash_balance(-cost)
                new_units = p['units'] + 1
                msg = f"[{new_units}차 피라미딩] {ticker} 불타기\n수량: {add_qty}주 / 단가: ${curr:.2f}"
                logger.info(msg.replace("\n", " | "))
                

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

def handle_exit(token, ticker, state, indicators):
    """청산 조건을 확인하고 매도합니다."""

    p = state.get(ticker)
    if not p or p.get('units', 0) == 0:
        return

    curr = indicators['current_price']
    
    fixed_atr = p['latest_atr']
    stop_loss_price = p['stop_loss']
    
    # [수정] Issue 3: 청산 사유 판별
    exit_reason = None
    if curr < indicators['dc_lower']:
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
            #텔레그램 전송은 main에서
            
            last_liquidated = load_json(LAST_LIQUIDATION_FILE)or {}
            last_liquidated[ticker] = datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
            safe_save_json(last_liquidated, LAST_LIQUIDATION_FILE)

            # 상태 초기화
            state[ticker] = {
                'qty': 0, 'total_entry_price': 0, 'units': 0,
                'last_entry_price': 0, 'stop_loss': 0, 'current_price': curr, 'latest_atr': 0
            }


