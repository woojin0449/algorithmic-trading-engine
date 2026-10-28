from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo
from api.kis_broker import send_us_order, get_order_execution, cancel_order
from utils.file_io import save_closed_trade
from config import RISK_PER_UNIT, STOP_N, PYRAMID_N, MAX_UNITS
from utils.logger import logger
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
    old_stop = pos.get("stop_loss", 0.0)
    new_stop = last_entry["price"] - (STOP_N * pos["latest_atr"])

    if len(entries) == 1 or old_stop <= 0:
        # 최초 진입: 실제 체결가 기준으로 반영
        pos["stop_loss"] = new_stop
        logger.info(
            f"[{ticker}] Stop Loss 설정 ${new_stop:.2f} "
            f"(unit {unit} @ ${last_entry['price']:.2f}, ATR={pos['latest_atr']:.2f})"
        )
    elif new_stop > old_stop:
        # 피라미딩: 기존 stop보다 높을 때만 상향 -> 전체 포지션 손절선이 함께 올라감
        pos["stop_loss"] = new_stop
        logger.info(
            f"[{ticker}] Stop Loss 상향 ${old_stop:.2f} → ${new_stop:.2f} "
            f"(unit {unit} @ ${last_entry['price']:.2f}, ATR={pos['latest_atr']:.2f})"
        )
    else:
        # 슬리피지로 신규 유닛 체결가가 낮아도 손절선은 유지
        logger.info(
            f"[{ticker}] Stop Loss 유지 ${old_stop:.2f} "
            f"(신규 계산 ${new_stop:.2f} 무시, unit {unit} @ ${last_entry['price']:.2f})"
        )


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

        # 새 체결 발생 처리
        if newly_filled_qty > 0:
            logger.info(f"[{ticker}] ODNO:{odno} 신규 체결 {newly_filled_qty}주 (누적 {filled_qty}주)")
            if action == "buy":
                _record_buy_execution(state, p_order, match, filled_qty)
            elif action == "sell":
                logger.info(f"[{ticker}] 매도 부분 체결 {newly_filled_qty}주")
            p_order["filled_qty"] = filled_qty

        # 전량 체결 완료 처리
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

def handle_entry(token, config, state, ticker, indicators, current_cash, total_equity):
    local_positions = state.setdefault("positions", {})
    pending_orders = state.setdefault("pending_orders", [])
    pos = local_positions.get(ticker)

    if any(order.get("ticker") == ticker for order in pending_orders):
        return
    if pos and pos.get("pending_action", False):
        return

    curr_price = indicators["current_price"]
    order_excd = indicators["order_exchange"]

    # strategy와 스키마 명칭 불일치 버그 수정
    atr = indicators.get("atr", 0.0)
    donchian_high = indicators.get("dc_upper", 0.0)
    ma200 = indicators.get("ma200", 0.0)

    # 디버그할때 용이하게 수정. Silent return 제거
    if not atr or atr <= 0:
        logger.info(f"[{ticker}] 매수 SKIP: ATR 결측/0 (atr={atr})")
        return
    if donchian_high <= 0:
        logger.info(f"[{ticker}] 매수 SKIP: DC_upper 결측 (dc_upper={donchian_high})")
        return
    if ma200 <= 0:
        logger.info(f"[{ticker}] 매수 SKIP: MA200 결측 (ma200={ma200})")
        return

    # 1% 리스크와 STOP_N * ATR 반영
    #   기존: risk_amount / atr  -> 손절폭 무시로 수량 2배 과대
    risk_amount = total_equity * RISK_PER_UNIT
    risk_per_share = STOP_N * atr
    qty_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

    # 현금 여유분과 작은 값 채택 -> 현금부족 silent return 제거
    qty_by_cash = int((current_cash * 0.98) / curr_price) if curr_price > 0 else 0
    unit_qty = min(qty_by_risk, qty_by_cash)
    if unit_qty <= 0:
        logger.info(f"[{ticker}] 매수 SKIP: 수량 0 (risk_qty={qty_by_risk}, cash_qty={qty_by_cash})")
        return

    is_buy_signal = False
    signal_type = ""
    target_unit = None

    if not pos:
        if curr_price > donchian_high and curr_price >= ma200:
            is_buy_signal, target_unit, signal_type = True, 1, "NEW_ENTRY(Breakout 55H)"
    else:
        entries = pos.get("entries", [])
        current_units = len(entries)
        if current_units >= MAX_UNITS:         # config의 MAX_UNITS 사용
            return
        if not entries:
            return
        last_entry_price = entries[-1].get("price", 0.0)
        if last_entry_price <= 0:
            return
        if curr_price >= last_entry_price + (PYRAMID_N * atr):  # config PYRAMID_N
            is_buy_signal = True
            target_unit = current_units + 1
            signal_type = f"PYRAMIDING(Unit {target_unit})"

    if not is_buy_signal:
        return

    logger.info(f"[{ticker}] 매수 신호 ({signal_type}) - Unit {target_unit}, 수량:{unit_qty}주 @ ${curr_price:.2f}")
    success, odno = send_us_order(token, config["APP_KEY"], config["APP_SECRET"], config["CANO"], ticker, order_excd, True, unit_qty, curr_price)

    # 주문 실패도 로그로 남김
    if not success or not odno:
        logger.error(f"[{ticker}] 매수 주문 실패 (success={success}, odno={odno})")
        return

    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pending_orders.append({
        "ticker": ticker, "odno": odno, "action": "buy", "unit": target_unit,
        "qty": unit_qty, "filled_qty": 0, "exchange": order_excd,
        "order_price": curr_price, "atr": atr, "stop_loss": curr_price - (STOP_N * atr),
        "timestamp": now_str
    })

    if not pos:
        local_positions[ticker] = {
            "qty": 0, "units": 0, "avg_price": 0.0, "current_price": curr_price,
            "stop_loss": curr_price - (STOP_N * atr), "latest_atr": atr,
            "pending_action": True, "entries": []
        }
    else:
        # [의도 명시] 피라미딩 신호 시점에는 stop_loss를 올리지 않는다.
        #  → 주문은 아직 "포지션"이 아니므로 미리 손절을 올리면 미체결 시 조기 손절 위험.
        #  → 실제 손절선 상향은 체결 후 _record_buy_execution에서
        #    (신규 유닛 실제 체결가 - STOP_N * ATR) 기준, 단조 상향으로 수행된다.
        pos["pending_action"] = True


def handle_exit(token, config, state, ticker, indicators):
    local_positions = state.get("positions", {})
    pos = local_positions.get(ticker)

    # Silent return 제거. 각 SKIP 사유에 로그. 단,정상 흐름은 debug 레벨로 낮춤
    if not pos:
        logger.debug(f"[{ticker}] EXIT SKIP: 로컬 포지션 없음")
        return False

    curr_price = indicators['current_price']
    order_excd = indicators['order_exchange']
    stop_loss = pos.get('stop_loss', 0.0)
    donchian_low = indicators.get('dc_lower', 0.0)

    # pending_action=True 케이스 분류
    # 매수(피라미딩/최초) 미체결 대기 중에도 stop-loss 이탈 시
    # 매수 주문 즉시 취소 + 보유 잔량 전량 시장가 청산

    if pos.get("pending_action", False):
        all_pending = state.get("pending_orders", [])
        pending_buys = [o for o in all_pending if o.get("ticker") == ticker and o.get("action") == "buy"]
        pending_sells = [o for o in all_pending if o.get("ticker") == ticker and o.get("action") == "sell"]

        # 매도 주문이 이미 나가있으면 중복 청산방지를 위해 대기
        if pending_sells:
            if pending_buys:
                logger.warning(f"[{ticker}] 매수/매도 주문 동시 존재 - 데이터 이상 식별. 매도 pending 우선 처리.")
            logger.debug(f"[{ticker}] EXIT SKIP: 매도 주문 진행 중")
            return False

        if pending_buys:
            # 스탑로스 초기값 세팅 0일때 대기
            if stop_loss <= 0 or curr_price > stop_loss:
                logger.debug(
                    f"[{ticker}] EXIT SKIP: 매수 pending 대기 "
                    f"(price={curr_price:.2f}, stop={stop_loss:.2f})"
                )
                return False
            
            logger.warning(
                f"[{ticker}] 매수 pending 중 stop loss 이탈 "
                f"(price={curr_price:.2f} <= stop={stop_loss:.2f}). "
                f"매수 주문 즉시 취소 + 보유 잔량 전량 청산 시도."
            )
            for buy_order in list(pending_buys):
                raw_odno = buy_order.get("odno")
                odno = str(int(raw_odno)) if raw_odno else ""
                if odno:
                    try:
                        cancel_order(
                            token, config["APP_KEY"], config["APP_SECRET"],
                            config["CANO"], config["ACNT_PRDT_CD"],
                            ticker, odno, buy_order.get("exchange", "NASD")
                        )
                        logger.info(f"[{ticker}] 매수 주문 취소 요청 완료 (ODNO:{odno})")
                    except Exception as e:
                        #취소 실패시 청산 실행
                        logger.error(f"[{ticker}] 매수 주문 취소 실패 (ODNO:{odno}): {e}")
                else:
                    logger.warning(f"[{ticker}] 취소 대상 ODNO 비어있음. pending_order에서만 제거.")
                #재시도 무한반복 방지
                try:
                    state["pending_orders"].remove(buy_order)
                except ValueError:
                    pass
            
            pos["pending_action"] = False

            #최초 진입이 미체결일시 -> 청산 잔량 없음
            if pos.get("qty", 0) <= 0:
                logger.info(f"[{ticker}] 보유 잔고 없음 (qty=0). 매수 주문 취소만 수행.")
                return False
        
        else:
            ## pending_action=True인데 pending_buys 값이 없음. -> pending 해제
            logger.warning(
                f"[{ticker}] pending_action=True 지만 pending_orders에 해당 주문 없음. pending 해제."
            )
            pos["pending_action"] = False
    
    #공통 청산 판단
    qty = pos.get("qty", 0)
    if qty <= 0:
        logger.warning(f"[{ticker}] EXIT SKIP: 보유 수량 비정상 (qty={qty})")
        return False

    if stop_loss <= 0 and donchian_low <= 0:
        logger.warning(
            f"[{ticker}] EXIT 불가: stop_loss({stop_loss})와 dc_lower({donchian_low})가 모두 무효값"
        )
        return

    is_sell_signal = False
    signal_type = ""

    if stop_loss > 0 and curr_price <= stop_loss:
        is_sell_signal, signal_type = True, "STOP_LOSS (ATR)"
    elif donchian_low > 0 and curr_price <= donchian_low:
        is_sell_signal, signal_type = True, "EXIT (Donchian Low 20)"

    if not is_sell_signal:
        logger.debug(
            f"[{ticker}] EXIT 신호 없음 "
            f"(price={curr_price:.2f}, stop={stop_loss:.2f}, dc_low={donchian_low:.2f})"
        )
        return False
        
    logger.info(f"[{ticker}] 매도 신호 ({signal_type}) - 전량({qty}주) 청산 @ ${curr_price:.2f}")
    success, odno = send_us_order(
        token, config['APP_KEY'], config['APP_SECRET'], config['CANO'],
        ticker, order_excd, False, qty, curr_price
    )
    if not success or not odno:
        logger.error(f"[{ticker}] 매도 주문 실패 (success={success}, odno={odno})")
        return False
    

    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.setdefault("pending_orders", []).append({
        "ticker": ticker, "odno": odno, "action": "sell", "qty": qty, "filled_qty": 0,
        "exchange": order_excd, "order_price": curr_price, "timestamp": now_str, "reason": signal_type
    })
    pos['pending_action'] = True
    return True



