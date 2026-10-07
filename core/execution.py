# import math
# from datetime import datetime, timedelta
# import pytz

# from config import *
# from api.kis_broker import send_us_order
# from utils.file_io import safe_save_json, load_json, save_closed_trade
# from utils.logger import logger

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from api.kis_broker import send_us_order, get_order_execution, cancel_order
from utils.file_io import save_closed_trade # 수정된 CSV 저장 함수 임포트

logger = logging.getLogger(__name__)

# 내부 헬퍼 함수: 체결 상태 장부 기록
#신규
def _record_buy_execution(state, pending_order, execution, filled_qty):
    ticker = pending_order["ticker"]
    unit = pending_order["unit"]
    pos = state.setdefault("positions", {}).setdefault(ticker, {
        "qty": 0, "units": 0, "avg_price": 0.0, "current_price": 0.0,
        "stop_loss": pending_order.get("stop_loss", 0.0),
        "latest_atr": pending_order.get("atr", 0.0),
        "pending_action": True, "entries": []
    })
    entries = pos.setdefault("entries", [])

    # KIS ft_ccld_unpr3는 누적 평균 체결 단가
    try:
        execution_price = float(execution.get("ft_ccld_unpr3", 0))
    except (TypeError, ValueError):
        execution_price = 0.0
    if execution_price <= 0:
        execution_price = pending_order.get("order_price", 0.0)

    # 시간 파싱
    ord_tmd = execution.get("ord_tmd")
    if ord_tmd:
        ord_dt = execution.get("ord_dt", datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d"))
        try:
            entry_timestamp = f"{ord_dt[:4]}-{ord_dt[4:6]}-{ord_dt[6:8]}T{ord_tmd[:2]}:{ord_tmd[2:4]}:{ord_tmd[4:6]}+00:00"
        except Exception:
            entry_timestamp = pending_order["timestamp"]
    else:
        entry_timestamp = pending_order["timestamp"]

    existing_entry = next((e for e in entries if e.get("unit") == unit), None)

    if existing_entry:
        # 이중 가중 평균 버그 수정: KIS 평균가를 그대로 덮어씀
        existing_entry["qty"] = filled_qty 
        existing_entry["price"] = execution_price
    else:
        entries.append({
            "unit": unit,
            "qty": filled_qty,
            "price": execution_price,
            "timestamp": entry_timestamp
        })

    entries.sort(key=lambda x: x.get("unit", 0))
    pos["units"] = len(entries)
    
    last_entry = entries[-1]
    pos["latest_atr"] = pending_order.get("atr", pos.get("latest_atr", 0.0))
    pos["stop_loss"] = last_entry["price"] - (2 * pos["latest_atr"])

    logger.info(f"[{ticker}] Unit {unit} 체결 기록 업데이트 (누적: {filled_qty}주 @ ${execution_price:.2f})")


def _finalize_sell_execution(state, pending_order, execution):
    ticker = pending_order["ticker"]
    positions = state.get("positions", {})
    if ticker not in positions:
        return
        
    pos = positions[ticker]
    entries = pos.get("entries", [])
    
    try:
        sell_price = float(execution.get("ft_ccld_unpr3", 0))
    except (TypeError, ValueError):
        sell_price = pending_order.get("order_price", 0.0)

    exit_reason = pending_order.get("reason", "EXIT")
    exit_date = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # [Unit별 개별 수익률 CSV 기록]
    for entry in entries:
        unit = entry.get("unit", 0)
        qty = entry.get("qty", 0)
        entry_price = entry.get("price", 0.0)
        entry_date = entry.get("timestamp", "Unknown")
        
        if qty > 0 and entry_price > 0:
            cost = entry_price * qty
            revenue = sell_price * qty
            roi_pct = ((sell_price - entry_price) / entry_price) * 100
            
            # Unit별 개별 로깅
            save_closed_trade(
                ticker=ticker, 
                unit=unit, # save_closed_trade 헤더에 Unit 추가 권장
                entry_date=entry_date, 
                exit_date=exit_date, 
                entry_price=entry_price, 
                exit_price=sell_price, 
                qty=qty, 
                cost=cost, 
                revenue=revenue, 
                roi_pct=roi_pct, 
                reason=exit_reason
            )
            
    logger.info(f"[{ticker}] 전량 매도 완료. Unit별 CSV 기록 완료.")
    del positions[ticker] # 최종 삭제

# 메인 비즈니스 로직

def resolve_pending_orders(token, config, state):
    pending_list = state.get("pending_orders", [])
    if not pending_list:
        return
    execution_data = get_order_execution(token, config["APP_KEY"], config["APP_SECRET"], config["CANO"], config["ACNT_PRDT_CD"])
    api_orders = {str(int(order["odno"])): order for order in execution_data if order.get("odno")}

    survived_pending = []

    for p_order in pending_list:
        raw_odno = p_order.get("odno")
        # 2. 로컬 주문번호도 비교를 위해 앞의 0 제거 (빈 값 방지)
        odno = str(int(raw_odno)) if raw_odno else ""
        ticker = p_order.get("ticker")
        action = p_order.get("action")
        order_timestamp = p_order.get("timestamp")
        
        should_cancel = False
        #10분 지났을때 초기화
        if order_timestamp:
            try:
                order_dt = datetime.fromisoformat(order_timestamp)
                if (datetime.now(timezone.utc) - order_dt).total_seconds() >= 600:
                    should_cancel = True
            except Exception as e:
                logger.warning(f"[{ticker}] 시간 파싱 실패: {e}")

        if should_cancel:
            logger.info(f"[{ticker}] 10분 경과 미체결 주문 취소 (ODNO:{odno})")
            cancel_order(token, config["APP_KEY"], config["APP_SECRET"], config["CANO"], config["ACNT_PRDT_CD"], ticker, odno, p_order.get("exchange", "NASD"))

            if ticker in state.get("positions", {}):
                state["positions"][ticker]["pending_action"] = False

            continue

        # 5분이 아직 안지났고, api에 없을때 유보
        if odno not in api_orders:
            logger.warning(f"[{ticker}] API 미응답 (ODNO:{odno}). 다음 사이클 대기.")
            survived_pending.append(p_order)
            continue

        # 5분이 아직 안지났고, api에 있을떄.
        match = api_orders[odno]
        
        try:
            filled_qty = int(float(match.get("ft_ccld_qty", 0)))
        except (TypeError, ValueError):
            filled_qty = 0
            
        try:
            nccs_qty = int(float(match.get("nccs_qty", 0)))
        except (TypeError, ValueError):
            nccs_qty = 0

        previous_filled_qty = int(p_order.get("filled_qty", 0))
        newly_filled_qty = filled_qty - previous_filled_qty

        # 1. 새 체결 발생 처리
        if newly_filled_qty > 0:
            logger.info(f"[{ticker}] ODNO:{odno} 신규 체결 {newly_filled_qty}주 (누적 {filled_qty}주)")
            if action == "buy":
                _record_buy_execution(state, p_order, match, filled_qty)
            elif action == "sell":
                logger.info(f"[{ticker}] 매도 부분 체결 {newly_filled_qty}주")
            p_order["filled_qty"] = filled_qty

        # 2. 전량 체결 완료 처리
        if nccs_qty == 0:
            logger.info(f"[{ticker}] 주문(ODNO:{odno}) 전량 체결 확인 완료.")
            if action == "sell":
                _finalize_sell_execution(state, p_order, match)
            if ticker in state.get("positions", {}):
                state["positions"][ticker]["pending_action"] = False
                #여기에 파일 저장기능?
            continue

        logger.info(f"[{ticker}] 미체결 유지 (ODNO:{odno}, 체결:{filled_qty}, 미체결:{nccs_qty})")
        survived_pending.append(p_order)

    state["pending_orders"] = survived_pending

def update_account_balance(state, kis_positions, current_cash, total_equity):
    state["cash_balance"] = current_cash
    state["total_equity"] = total_equity
    
    local_positions = state.setdefault("positions", {})
    pending_orders = state.get("pending_orders", [])
    pending_tickers = {order.get("ticker") for order in pending_orders}

    for ticker, kis_data in kis_positions.items():
        if ticker not in local_positions:
            logger.warning(f"[{ticker}] KIS 잔고 발견. 기존 보유분 초기화.")
            local_positions[ticker] = {
                "qty": kis_data["qty"],
                "units": 1,
                "avg_price": kis_data["avg_price"],
                "current_price": kis_data["now_price"],
                "stop_loss": 0.0,
                "latest_atr": 0.0,
                "pending_action": False,
                "entries": [{
                    "unit": 1,
                    "qty": kis_data["qty"],
                    "price": kis_data["avg_price"],
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")
                }]
            }
        else:
            pos = local_positions[ticker]
            pos["qty"] = kis_data["qty"]
            pos["avg_price"] = kis_data["avg_price"]
            pos["current_price"] = kis_data["now_price"]

    for ticker in list(local_positions.keys()):
        if ticker not in kis_positions:
            if ticker in pending_tickers:
                logger.info(f"[{ticker}] KIS 잔고 무, pending 대기 중. 장부 유지.")
                continue
            logger.info(f"[{ticker}] KIS 잔고에서 소멸. 로컬 포지션 제거.")
            del local_positions[ticker]
    return state

# def update_balance_and_positions(state):
#     bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
#     usd_cash = bal_data["usd_balance"]

#     stock_value = 0.0
#     for ticker, pos in state.items():
#         if pos.get('units', 0) > 0:
#             stock_value += pos.get('qty', 0) * pos.get('current_price', 0)
    
#     total_equity = usd_cash + stock_value

#     balance_data = {
#         "usd_balance": usd_cash,
#         "total_equity": total_equity,
#         "stock_value": stock_value,
#         "last_update": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
#     }
#     safe_save_json(balance_data, BALANCE_FILE)
#     logger.info(f"Asset Update: Total Equity=${total_equity:,.2f}, Cash=${usd_cash:,.2f}, Stocks=${stock_value:,.2f}")
#     return total_equity, usd_cash


# def handle_entry(token, ticker, state, indicators, total_equity):

#     last_liquidated = load_json(LAST_LIQUIDATION_FILE) or {}
#     if ticker in last_liquidated:
#         last_time = datetime.fromisoformat(last_liquidated[ticker])
#         if datetime.now(pytz.timezone('Asia/Seoul')) - last_time < timedelta(hours=24):
#             return

    
#     p = state.get(ticker, {
#         'qty': 0, 'total_entry_price': 0,'units': 0,
#         'last_entry_price': 0, 'stop_loss': 0, 'current_price': indicators['current_price'],
#         'latest_atr': 0, 'pending_action': False
#     })

#     curr = indicators['current_price']
#     active_count = sum(1 for v in state.values() if v.get('units', 0) > 0)

#     # 1. 신규 진입 (1차 매수)
#     if p['units'] == 0:
#         if active_count >= MAX_HOLDINGS:
#             return
            
#         if curr > indicators['dc_upper'] and curr > indicators['ma200']:
#             # [가비지 틱 방어] 첫 감지 시 1턴 대기
#             if not p.get('pending_action', False):
#                 logger.info(f"[{ticker}] 1차 돌파 시그널 감지. 가비지 틱 방어를 위해 1턴(5분) 대기합니다.")
#                 p['pending_action'] = True
#                 state[ticker] = p
#                 return
                
#             # 두 번째 사이클에서도 유지되면 진입 확정
#             p['pending_action'] = False
            
#             fixed_atr = indicators['atr']
#             unit_size = math.floor((total_equity * RISK_PER_UNIT) / (STOP_N * fixed_atr))
#             if unit_size <= 0:
#                 return

#             cost = curr * unit_size
#             bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
#             usd_cash = bal_data["usd_balance"]
#             if usd_cash < cost:
#                 logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 매수 진입 포기.")
#                 return

#             if send_us_order(token, APP_KEY, APP_SECRET, CANO, ticker, True, unit_size, curr):
#                 update_cash_balance(-cost)
#                 msg = f"[1차 진입] {ticker} 55일 돌파\n수량: {unit_size}주 / 단가: ${curr:.2f}"
#                 logger.info(msg)
                

#                 p['qty'] = unit_size
#                 p['total_entry_price'] = cost
#                 p['units'] = 1
#                 p['last_entry_price'] = curr
#                 p['latest_atr'] = fixed_atr 
#                 p['stop_loss'] = curr - (STOP_N * fixed_atr)
#                 p['current_price'] = curr
#                 state[ticker] = p
#         else:
#             # 시그널 소멸 시 대기 플래그 해제
#             if p.get('pending_action', False):
#                 logger.info(f"[{ticker}] 1차 시그널 소멸. 가비지 틱으로 간주하여 진입을 취소합니다.")
#                 p['pending_action'] = False
#                 state[ticker] = p

#     # 2. 피라미딩 (추가 매수)
#     elif 0 < p['units'] < MAX_UNITS:
#         fixed_atr = p['latest_atr']
#         pyramid_target = p['last_entry_price'] + (PYRAMID_N * fixed_atr)
        
#         if curr > pyramid_target:
#             # [가비지 틱 방어] 피라미딩 첫 감지 시 1턴 대기
#             if not p.get('pending_action', False):
#                 logger.info(f"[{ticker}] 피라미딩 시그널 감지. 가비지 틱 방어를 위해 1턴(5분) 대기합니다.")
#                 p['pending_action'] = True
#                 state[ticker] = p
#                 return
                
#             # 두 번째 사이클에서도 유지되면 불타기 확정
#             p['pending_action'] = False
            
#             add_qty = math.floor((total_equity * RISK_PER_UNIT) / (STOP_N * fixed_atr))
#             if add_qty <= 0:
#                 return

#             cost = curr * add_qty
#             bal_data = load_json(BALANCE_FILE) or {"usd_balance": 20000.0}
#             usd_cash = bal_data["usd_balance"]
#             if usd_cash < cost:
#                 logger.warning(f"[{ticker}] 현금 부족: {usd_cash:.2f} < {cost:.2f}. 추가 매수 포기.")
#                 return

#             if send_us_order(token, APP_KEY, APP_SECRET, CANO, ticker, True, add_qty, curr):
#                 update_cash_balance(-cost)
#                 new_units = p['units'] + 1
#                 msg = f"[{new_units}차 피라미딩] {ticker} 불타기\n수량: {add_qty}주 / 단가: ${curr:.2f}"
#                 logger.info(msg.replace("\n", " | "))
                

#                 p['qty'] += add_qty
#                 p['total_entry_price'] += cost
#                 p['units'] = new_units
#                 p['last_entry_price'] = curr
#                 p['stop_loss'] = curr - (STOP_N * fixed_atr)
#                 p['current_price'] = curr
#                 state[ticker] = p
#         else:
#             # 시그널 소멸 시 대기 플래그 해제 (가짜 틱)
#             if p.get('pending_action', False):
#                 logger.info(f"[{ticker}] 피라미딩 시그널 소멸. 가비지 틱으로 간주하여 진입을 취소합니다.")
#                 p['pending_action'] = False
#                 state[ticker] = p

# def handle_exit(token, ticker, state, indicators):
#     """청산 조건을 확인하고 매도합니다."""

#     p = state.get(ticker)
#     if not p or p.get('units', 0) == 0:
#         return

#     curr = indicators['current_price']
    
#     fixed_atr = p['latest_atr']
#     stop_loss_price = p['stop_loss']
    
#     # [수정] Issue 3: 청산 사유 판별
#     exit_reason = None
#     if curr < indicators['dc_lower']:
#         exit_reason = "Trailing Stop(20일 저점 이탈)"
#     elif curr < stop_loss_price:
#         exit_reason = f"2.0N Hard Stop(손절가 ${stop_loss_price:.2f} 도달)"

#     if exit_reason:
#         if send_us_order(token, APP_KEY, APP_SECRET, CANO, ticker, False, p['qty'], curr):
#             # [수정] Issue 1: 최종 수익률(ROI) 계산
#             revenue = curr * p['qty']
#             cost = p['total_entry_price']
#             roi_pct = ((revenue - cost) / cost) * 100 if cost > 0 else 0

#             update_cash_balance(revenue)

#             # 텔레그램 및 로거 메시지 고도화
#             msg = f"[청산] {ticker} 전량 매도\n사유: {exit_reason}\n매도단가: ${curr:.2f}\n최종 수익률: {roi_pct:+.2f}%"
            
#             logger.info(msg.replace("\n", " | "))
#             #텔레그램 전송은 main에서
            
#             #Added file saving functionality.
#             save_closed_trade(ticker, curr, p['qty'], cost, revenue, roi_pct, exit_reason)
            
#             last_liquidated = load_json(LAST_LIQUIDATION_FILE)or {}
#             last_liquidated[ticker] = datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
#             safe_save_json(last_liquidated, LAST_LIQUIDATION_FILE)

#             # 상태 초기화
#             state[ticker] = {
#                 'qty': 0, 'total_entry_price': 0, 'units': 0,
#                 'last_entry_price': 0, 'stop_loss': 0, 'current_price': curr, 'latest_atr': 0
#             }

def handle_entry(token, config, state, ticker, indicators, current_cash, total_equity):
    local_positions = state.setdefault("positions", {})
    pending_orders = state.setdefault("pending_orders", [])
    pos = local_positions.get(ticker)

    if any(order.get("ticker") == ticker for order in pending_orders): return
    if pos and pos.get("pending_action", False): return

    curr_price = indicators["current_price"]
    order_excd = indicators["order_exchange"]
    atr = indicators.get("atr_20", 0.0)
    donchian_high = indicators.get("donchian_high_20", 0.0)

    if atr <= 0: return

    # 1% Risk Rule (RISK_PER_UNIT 변수가 선언되어 있다고 가정. 예: 0.01)
    risk_amount = total_equity * 0.01 
    unit_qty = int(risk_amount / atr)
    if unit_qty <= 0: return

    estimated_cost = unit_qty * curr_price
    if estimated_cost > current_cash: return

    is_buy_signal = False
    signal_type = ""
    target_unit = None

    if not pos:
        if curr_price > donchian_high and curr_price >= indicators["ma200"]:
            is_buy_signal, target_unit, signal_type = True, 1, "NEW_ENTRY(Breakout)"
    else:
        entries = pos.get("entries", [])
        current_units = len(entries)
        if current_units >= 4: return
        
        if not entries: return
        last_entry_price = entries[-1].get("price", 0.0)
        if last_entry_price <= 0: return
        
        if curr_price >= last_entry_price + (0.5 * atr):
            is_buy_signal = True
            target_unit = current_units + 1
            signal_type = f"PYRAMIDING(Unit {target_unit})"

    if not is_buy_signal: return

    logger.info(f"[{ticker}] 매수 신호 ({signal_type}) - Unit {target_unit}, 수량:{unit_qty}주")
    success, odno = send_us_order(token, config["APP_KEY"], config["APP_SECRET"], config["CANO"], ticker, order_excd, True, unit_qty, curr_price)

    if not success or not odno: return

    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pending_orders.append({
        "ticker": ticker, "odno": odno, "action": "buy", "unit": target_unit,
        "qty": unit_qty, "filled_qty": 0, "exchange": order_excd,
        "order_price": curr_price, "atr": atr, "stop_loss": curr_price - (2 * atr),
        "timestamp": now_str
    })

    if not pos:
        local_positions[ticker] = {
            "qty": 0, "units": 0, "avg_price": 0.0, "current_price": curr_price,
            "stop_loss": curr_price - (2 * atr), "latest_atr": atr,
            "pending_action": True, "entries": []
        }
    else:
        pos["pending_action"] = True

def handle_exit(token, config, state, ticker, indicators):
    local_positions = state.get("positions", {})
    pos = local_positions.get(ticker)

    if not pos or pos.get("pending_action", False): return False
    qty = pos.get("qty", 0)
    if qty <= 0: return False

    curr_price = indicators['current_price']
    order_excd = indicators['order_exchange']
    stop_loss = pos.get('stop_loss', 0.0)
    donchian_low = indicators.get('donchian_low_10', 0.0)

    is_sell_signal = False
    signal_type = ""

    if curr_price <= stop_loss:
        is_sell_signal, signal_type = True, "STOP_LOSS (ATR)"
    elif donchian_low > 0 and curr_price <= donchian_low:
        is_sell_signal, signal_type = True, "EXIT (Donchian Low 10)"

    if is_sell_signal:
        logger.info(f"[{ticker}] 매도 신호 ({signal_type}) - 전량({qty}주) 청산")
        success, odno = send_us_order(token, config['APP_KEY'], config['APP_SECRET'], config['CANO'], ticker, order_excd, False, qty, curr_price)

        if success and odno:
            now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state.setdefault("pending_orders", []).append({
                "ticker": ticker, "odno": odno, "action": "sell", "qty": qty, "filled_qty": 0,
                "exchange": order_excd, "order_price": curr_price, "timestamp": now_str, "reason": signal_type
            })
            pos['pending_action'] = True
            return True
    return False
