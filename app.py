import streamlit as st
import plotly.graph_objects as plotly_go
import plotly.subplots as sp
import pandas as pd
import numpy as np
import json
import os
import yfinance as yf
from datetime import datetime, timezone, timedelta
from collections import deque

#---------------------------------------------------------
# 1. 페이지 레이아웃 및 최상위 라우팅
#---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Master Trading Terminal")

st.sidebar.title("🧭 System Navigation")
app_mode = st.sidebar.radio("Select Module", ["🐢 Turtle Frontend", "📈 Livermore Replay"])

#=========================================================
# 모듈 1: 기존 터틀 트레이딩 프론트엔드 공간
#=========================================================
if app_mode == "🐢 Turtle Frontend":

    # ==========================================
    # 1. 기본 설정 및 파일 경로
    # ==========================================
    STATE_FILE = "trading_state.json"
    BALANCE_FILE = "balance.json"
    TRADE_FILE = "trade_history.csv"
    CLOSED_TRADE_FILE = "closed_trades.csv" # Phase 1 연동 파일 추가
    LOG_FILE = "bot_status.log"

    KST = timezone(timedelta(hours=9))

    # ==========================================
    # 2. 데이터 로드 및 보안 마스킹 함수 (Issue 6 대응)
    # ==========================================
    def mask_sensitive_info(text):
        """에러 메시지 내 민감 정보를 찾아 마스킹 처리합니다 (Issue 6)"""
        if not isinstance(text, str):
            text = str(text)
        sensitive_keys = ["APP_KEY", "APP_SECRET", "CANO", "TELEGRAM_TOKEN"]
        for key in sensitive_keys:
            val = os.environ.get(key)
            if val and val in text:
                text = text.replace(val, "********")
        return text

    def load_json(filepath, default_val):
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    return json.load(f)
            except Exception as e: 
                st.error(mask_sensitive_info(f"JSON 로드 오류: {e}"))
                return default_val
        return default_val

    def load_csv(filepath):
        if os.path.exists(filepath):
            try:
                return pd.read_csv(filepath)
            except Exception as e: 
                st.error(mask_sensitive_info(f"CSV 로드 오류: {e}"))
                return pd.DataFrame()
        return pd.DataFrame()

    # 색상 입히기 공통 함수
    def color_pnl(val):
        if isinstance(val, str):
            # 문자열 내 숫자가 음수인지 양수인지 판별하기 위한 예방 처리
            clean_val = val.replace('%', '').replace('$', '').replace('+', '')
            try: val = float(clean_val)
            except: return ''
        color = 'red' if val < 0 else 'blue' 
        return f'color: {color}; font-weight: bold;'

    # ==========================================
    # 3. 메인 대시보드 UI
    # ==========================================
    st.title("🐢 Turtle Trading Bot Dashboard (v3.1)")
    st.caption("고정 ATR 로직 및 총자산/현금 분리 동기화 적용 완료")

    # 데이터 로딩
    balance_data = load_json(BALANCE_FILE, {"usd_balance": 20000.0, "total_equity": 20000.0, "stock_value": 0.0, "last_update": "N/A"})
    state_data = load_json(STATE_FILE, {})
    closed_df = load_csv(CLOSED_TRADE_FILE) # Phase 1 청산 이력 가져오기

    st.markdown("---")

    # [섹션 1] 계좌 요약 (Metrics)
    st.subheader("💰 계좌 자산 현황")
    col1, col2, col3, col4 = st.columns(4)

    total_equity = balance_data.get("total_equity", 20000.0)
    usd_cash = balance_data.get("usd_balance", 20000.0)
    stock_val = balance_data.get("stock_value", 0.0)

    # 수익률 계산 (V2 변경 예산인 고정 2만 달러 기준 백분율 계산)
    initial_budget = 20000.0
    total_roi = ((total_equity - initial_budget) / initial_budget) * 100

    with col1:
        st.metric(label="총 자산 (Total Equity)", value=f"${total_equity:,.2f}", delta=f"{total_roi:+.2f}%")
    with col2:
        st.metric(label="가용 현금 (Cash)", value=f"${usd_cash:,.2f}")
    with col3:
        st.metric(label="주식 평가금 (Stock Value)", value=f"${stock_val:,.2f}")
    with col4:
        st.info(f"⏱️ 마지막 업데이트:\n\n{balance_data.get('last_update', 'N/A')}")

    st.markdown("---")

    # [섹션 2] 현재 보유 포지션 (Active Positions)
    st.subheader("📊 현재 운용 중인 포지션")

    active_positions = []
    for ticker, p in state_data.items():
        if p.get('units', 0) > 0:
            qty = p.get('qty', 0)
            total_entry = p.get('total_entry_price', 0)
            avg_price = total_entry / qty if qty > 0 else 0
            curr_price = p.get('current_price', avg_price)
            
            pnl_pct = ((curr_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
            pnl_usd = (curr_price - avg_price) * qty
            active_positions.append({
                "종목 (Ticker)": ticker,
                "유닛 (Units)": p.get('units', 0),
                "수량 (Qty)": qty,
                "평균 단가": f"${avg_price:.2f}",
                "현재가": f"${curr_price:.2f}",
                "고정 ATR": f"${p.get('latest_atr', 0):.2f}",
                "손절선 (Stop Loss)": f"${p.get('stop_loss', 0):.2f}",
                "평가 손익 ($)": pnl_usd,
                "수익률 (%)": pnl_pct
            })

    if active_positions:
        df_pos = pd.DataFrame(active_positions)
        styled_df = df_pos.style.format({
            "평가 손익 ($)": "${:+.2f}",
            "수익률 (%)": "{:+.2f}%"
        }).map(color_pnl, subset=['평가 손익 ($)', '수익률 (%)'])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.info("현재 보유 중인 포지션이 없습니다. (봇이 새로운 추세를 탐색 중입니다.)")

    st.markdown("---")

    # [+] 새로고침 버튼 위치 이동: 실시간 로그 및 체결 기록 바로 위에 배치하여 접근성 극대화
    col_btn1, col_btn2 = st.columns([8, 2])
    with col_btn2:
        if st.button("🔄 시스템 실시간 새로고침", use_container_width=True, type="primary"):
            st.rerun()

    st.markdown("---")

    # [신규 섹션] 전략 성과 분석 및 수익 곡선 (Equity Curve)
    st.subheader("📈 누적 성과 및 자산 곡선 (Trade-by-Trade)")

    if not closed_df.empty:
        # 1. 성과 데이터 전처리
        df_chart = closed_df.copy()
        
        # 'Total_Revenue'와 'Total_Cost' 컬럼이 문자열(예: "$1,000")일 경우를 대비한 안전한 숫자 변환
        if df_chart['Total_Revenue'].dtype == object:
            df_chart['Total_Revenue'] = df_chart['Total_Revenue'].astype(str).str.replace('[\$,]', '', regex=True).astype(float)
        if df_chart['Total_Cost'].dtype == object:
            df_chart['Total_Cost'] = df_chart['Total_Cost'].astype(str).str.replace('[\$,]', '', regex=True).astype(float)

        # 건별 순수익 및 누적 자산 계산
        df_chart['Net_PnL'] = df_chart['Total_Revenue'] - df_chart['Total_Cost']
        df_chart['Cumulative_Equity'] = initial_budget + df_chart['Net_PnL'].cumsum()
        
        # 역대 최고점(High Water Mark) 및 MDD(최대 낙폭) 계산
        df_chart['Running_Max'] = df_chart['Cumulative_Equity'].cummax()
        df_chart['Drawdown'] = ((df_chart['Cumulative_Equity'] - df_chart['Running_Max']) / df_chart['Running_Max']) * 100
        mdd = df_chart['Drawdown'].min()
        current_realized_equity = df_chart['Cumulative_Equity'].iloc[-1]
        realized_roi = ((current_realized_equity - initial_budget) / initial_budget) * 100

        # 2. 핵심 성과 지표 (Metrics) 표기
        m1, m2, m3 = st.columns(3)
        m1.metric(label="총 실현 자산 (Realized Equity)", value=f"${current_realized_equity:,.2f}", delta=f"{realized_roi:+.2f}%")
        m2.metric(label="최대 낙폭 (MDD)", value=f"{mdd:,.2f}%", delta_color="inverse")
        m3.metric(label="총 청산 거래 수", value=f"{len(df_chart)} Trades")

        # 3. Plotly Area 차트 렌더링
        fig = plotly_go.Figure()

        # [추가 제안] 역대 최고 자산 라인 (점선) - MDD를 시각적으로 보여줌
        fig.add_trace(plotly_go.Scatter(
            x=df_chart.index + 1,  # 매매 횟수 (Trade #1, #2 ...)
            y=df_chart['Running_Max'],
            mode='lines',
            line=dict(color='rgba(150, 150, 150, 0.4)', width=1.5, dash='dot'),
            name='High Water Mark',
            hoverinfo='skip'
        ))

        # 사용자 요청: 반투명 Area + 진한 실제 자산 라인
        fig.add_trace(plotly_go.Scatter(
            x=df_chart.index + 1,
            y=df_chart['Cumulative_Equity'],
            mode='lines+markers',
            line=dict(color='#007bff', width=3), # 진한 파란색 라인
            marker=dict(size=6, color='#007bff', line=dict(width=1, color='white')),
            fill='tozeroy',
            fillcolor='rgba(0, 123, 255, 0.15)', # 반투명한 푸른색 Area
            name='Cumulative Equity',
            # 마우스를 올렸을 때 보여줄 데이터 (Exit_Date, 티커, 해당 거래 손익)
            text="청산일: " + df_chart['Exit_Date'] + "<br>종목: " + df_chart['Ticker'] + "<br>건별 손익: $" + df_chart['Net_PnL'].round(2).astype(str),
            hovertemplate="<b>Trade #%{x}</b><br>%{text}<br><b>누적 자산: $%{y:,.2f}</b><extra></extra>"
        ))

        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_title="Trade Sequence (매매 순서)",
            yaxis_title="Total Equity ($)",
            hovermode="x unified",
            showlegend=False,
            template="plotly_white",
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        fig.update_xaxes(showgrid=False, zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(200, 200, 200, 0.2)', zeroline=False)

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("차트를 그릴 청산 데이터가 아직 없습니다.")

    # [섹션 3] 최근 매매 기록 및 시스템 로그
    col_log1, col_log2 = st.columns(2)

    with col_log1:
        st.subheader("📝 최근 매매 체결 기록 (All History)")
        if not closed_df.empty:
            # Issue 2: .head(10) 제거하여 전체 기록 역순 출력 및 스타일링 입히기
            styled_closed_df = closed_df.iloc[::-1].style.format({
                "Total_Cost": "${:,.2f}",
                "Total_Revenue": "${:,.2f}",
                "ROI_Percent": "{:+.2f}%"
            }).map(color_pnl, subset=['ROI_Percent'])
            st.dataframe(styled_closed_df, use_container_width=True)
        else:
            st.write("아직 종결된 청산 매매 기록(closed_trades.csv)이 없습니다.")

    with col_log2:
        st.subheader("🖥️ 봇 실시간 시스템 로그")
        st.text("bot_status.log (최근 15줄)")

        log_file_path = "bot_status.log"
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                tail_lines = deque(f, maxlen=15) 
            st.code("".join(tail_lines), language="log")
        else:
            st.write("로그 파일이 아직 생성되지 않았습니다.")

    # [섹션 4] 파일 다운로드 영역
    st.markdown("---")
    st.subheader("📁 백업 및 로그 파일 다운로드")

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "rb") as f:
            st.download_button(label="📥 bot_status.log 다운로드", data=f, file_name="bot_status.log", mime="text/plain")

# =========================================================
# 모듈 2: 리버모어 백테스팅 터미널 v8.0 (Multi-Market Scale)
# =========================================================
elif app_mode == "📈 Livermore Replay":
    
    # ---------------------------------------------------------
    # 1. 세션 변수 초기화 (고정 변수 탈피)
    # ---------------------------------------------------------
    if 'initial_seed' not in st.session_state: st.session_state.initial_seed = 10000.0
    if 'balance' not in st.session_state: st.session_state.balance = st.session_state.initial_seed
    if 'full_df' not in st.session_state: st.session_state.full_df = pd.DataFrame()
    if 'current_step' not in st.session_state: st.session_state.current_step = 0
    if 'open_positions' not in st.session_state: st.session_state.open_positions = []
    if 'trade_history' not in st.session_state: st.session_state.trade_history = []
    if 'cumulative_pnl' not in st.session_state: st.session_state.cumulative_pnl = 0.0
    if 'trade_counter' not in st.session_state: st.session_state.trade_counter = 1

    def calc_target_price(entry_price, qty, leverage, val_type, val, is_long, is_sl=False):
        if val is None or val == 0.0: return None
        if val_type == 'Price': return val
        
        val = -abs(val) if is_sl else abs(val)
        
        margin = (entry_price * qty) / leverage
        if val_type == 'PnL (USDT/KRW)': pnl_amt = val
        else: pnl_amt = margin * (val / 100.0)
        
        if is_long: return entry_price + (pnl_amt / qty)
        else: return entry_price - (pnl_amt / qty)

    # ---------------------------------------------------------
    # 2. 사이드바: 자본금 설정 추가 및 로딩 로직
    # ---------------------------------------------------------
    with st.sidebar:
        st.header("⏱️ Playback Control")
        if st.button("⏩ Next Candle (Advance 1 Day)", use_container_width=True, type="primary"):
            if not st.session_state.full_df.empty and st.session_state.current_step < len(st.session_state.full_df) - 1:
                st.session_state.current_step += 1
            elif st.session_state.full_df.empty:
                st.warning("Load data first.")
            else:
                st.warning("End of data.")
        st.markdown("---")
        st.header("⚙️ Setup Environment")
        ticker = st.text_input("Ticker Symbol", value="AAPL")
        start_date = st.date_input("Start Date", value=pd.to_datetime("2016-01-01"))
        
        initial_capital = st.number_input("Initial Capital ($/₩)", min_value=1.0, value=10000.0, step=1000.0)
        
        if st.button("📥 Load ALL Market Data"):
            with st.spinner("Downloading Market Data..."):
                df = yf.download(ticker, period="max", progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    
                    df['ma200'] = df['Close'].rolling(window=200).mean()
                    df['Vol_MA'] = df['Volume'].rolling(window=20).mean()
                    df['Vol_Color'] = np.where(df['Close'] >= df['Open'], 'rgba(0, 200, 0, 0.5)', 'rgba(200, 0, 0, 0.5)')
                    df['str_date'] = df.index.strftime('%Y-%m-%d')
                    df = df.dropna(subset=['Close'])
                    
                    if not df.empty:
                        target_dt = pd.to_datetime(start_date)
                        one_year_ago = target_dt - pd.Timedelta(days=365)
                        df = df[df.index >= one_year_ago].copy()
                        
                        df['step'] = np.arange(len(df))
                        target_idx = int(abs(df.index - target_dt).argmin())

                        st.session_state.full_df = df
                        st.session_state.current_step = target_idx
                        st.session_state.initial_seed = initial_capital
                        st.session_state.balance = initial_capital
                        st.session_state.open_positions = []
                        st.session_state.trade_history = []
                        st.session_state.cumulative_pnl = 0.0
                        st.session_state.trade_counter = 1
                        st.success(f"Data Loaded! Jumped to: {df.index[target_idx].strftime('%Y-%m-%d')}")
                    else:
                        st.error("오류: 유효한 가격 데이터가 남아있지 않습니다.")
                else:
                    st.error("데이터를 가져오는 데 실패했습니다.")

    if st.session_state.full_df.empty:
        st.warning("👈 Please load data from the sidebar to start backtesting.")
        st.stop()

    current_step = st.session_state.current_step
    df_view = st.session_state.full_df.iloc[:current_step + 1]
    current_row = df_view.iloc[-1]
    current_date = df_view.index[-1]
    current_price = float(current_row['Close'])

    # ---------------------------------------------------------
    # 3. 메인 대시보드 상단 (차트 & 주문 패널)
    # ---------------------------------------------------------
    col_chart, col_panel = st.columns([7, 3])

    with col_panel:
        st.header("⚡ Command Center")
        
        used_margin = sum(p['margin'] for p in st.session_state.open_positions)
        orderable_amount = st.session_state.balance - used_margin
        
        is_bankrupt = st.session_state.balance < 0
        if is_bankrupt: 
            st.error(f"🚨 BANKRUPTCY: Balance is {st.session_state.balance:,.2f}.")
        else: 
            pnl_abs = st.session_state.balance - st.session_state.initial_seed
            roi_pct = (pnl_abs / st.session_state.initial_seed) * 100
            pnl_color = "#28a745" if pnl_abs >= 0 else "#dc3545" 
            pnl_sign = "+" if pnl_abs >= 0 else ""
            
            st.markdown("#### Total Equity / Orderable")
            st.markdown(f"<h3 style='margin-top:-10px;'>{st.session_state.balance:,.2f} / <span style='color:#007bff;'>{orderable_amount:,.2f}</span></h3>", unsafe_allow_html=True)
            st.markdown(f"**Net PnL:** <span style='color:{pnl_color}; font-weight:bold;'>{pnl_sign}{pnl_abs:,.2f} ({pnl_sign}{roi_pct:.1f}%)</span>", unsafe_allow_html=True)
            
        st.markdown(f"**Date:** {current_date.strftime('%Y-%m-%d')} | **Price:** {current_price:,.2f}")
        view_window = st.slider("Candles to show (Zoom)", min_value=30, max_value=500, value=150, step=10)
        st.markdown("---")
        
        st.markdown("### 🛒 Order Placement")
        col_m1, col_m2 = st.columns(2)
        margin_mode = col_m1.selectbox("Margin Mode", ["Isolated", "Cross"])
        leverage = col_m2.number_input("Leverage (x)", min_value=1, max_value=100, value=1)
        order_price = st.number_input("Order Price", value=current_price, step=0.1)
        
        entry_qty = st.number_input("Quantity", min_value=0.0001, value=1.0, step=0.1, format="%.4f")
        
        notional_value = order_price * entry_qty
        req_margin = notional_value / leverage
        entry_fee = notional_value * 0.0025
        st.caption(f"Req. Margin: {req_margin:,.2f} | Fee (0.25%): {entry_fee:,.2f}")

        use_tp = st.checkbox("Set Take Profit (TP)")
        tp_type, tp_val = "Price", None
        if use_tp:
            c1, c2 = st.columns([1, 2])
            tp_type = c1.selectbox("TP Type", ["Price", "PnL (USDT/KRW)", "ROI (%)"], label_visibility="collapsed")
            tp_val = c2.number_input("TP Value", value=None, placeholder="Blank for none", step=1.0)

        use_sl = st.checkbox("Set Stop Loss (SL)")
        sl_type, sl_val = "Price", None
        if use_sl:
            c1, c2 = st.columns([1, 2])
            sl_type = c1.selectbox("SL Type", ["Price", "PnL (USDT/KRW)", "ROI (%)"], label_visibility="collapsed")
            sl_val = c2.number_input("SL Value", value=None, placeholder="Blank for none", step=1.0)

        col_long, col_short = st.columns(2)
        btn_disabled = is_bankrupt

        if col_long.button("🟢 LONG", use_container_width=True, disabled=btn_disabled):
            if req_margin + entry_fee > orderable_amount:
                st.error("❌ 잔고(Orderable Amount)가 부족하여 매수할 수 없습니다.")
            else:
                tp_p = calc_target_price(order_price, entry_qty, leverage, tp_type, tp_val, True, is_sl=False)
                sl_p = calc_target_price(order_price, entry_qty, leverage, sl_type, sl_val, True, is_sl=True)
                st.session_state.balance -= entry_fee
                st.session_state.open_positions.append({
                    'id': f"{st.session_state.trade_counter}Long", 'type': 'Long', 'entry_date': current_date,
                    'entry_price': order_price, 'qty': entry_qty, 'entry_step': current_step,
                    'sl': sl_p, 'tp': tp_p, 'leverage': leverage, 'margin_mode': margin_mode, 'margin': req_margin
                })
                st.session_state.trade_counter += 1
                st.rerun()
            
        if col_short.button("🔴 SHORT", use_container_width=True, disabled=btn_disabled):
            if req_margin + entry_fee > orderable_amount:
                st.error("❌ 잔고(Orderable Amount)가 부족하여 매도할 수 없습니다.")
            else:
                tp_p = calc_target_price(order_price, entry_qty, leverage, tp_type, tp_val, False, is_sl=False)
                sl_p = calc_target_price(order_price, entry_qty, leverage, sl_type, sl_val, False, is_sl=True)
                st.session_state.balance -= entry_fee
                st.session_state.open_positions.append({
                    'id': f"{st.session_state.trade_counter}Short", 'type': 'Short', 'entry_date': current_date,
                    'entry_price': order_price, 'qty': entry_qty, 'entry_step': current_step,
                    'sl': sl_p, 'tp': tp_p, 'leverage': leverage, 'margin_mode': margin_mode, 'margin': req_margin
                })
                st.session_state.trade_counter += 1
                st.rerun()

        st.markdown("---")
        st.markdown("### 🗂️ Open Positions")
        cross_positions = [p for p in st.session_state.open_positions if p['margin_mode'] == 'Cross']
        if cross_positions and orderable_amount < (sum(p['margin'] for p in cross_positions) * 0.5):
            st.warning("⚠️ CROSS MARGIN WARNING: Liquidation risk across all cross positions.")

        if not st.session_state.open_positions:
            st.info("No open positions.")
        else:
            longs = [p for p in st.session_state.open_positions if p['type'] == 'Long']
            shorts = [p for p in st.session_state.open_positions if p['type'] == 'Short']
            
            def render_grouped_positions(pos_list, pos_type, emoji):
                if pos_list:
                    total_qty = sum(p['qty'] for p in pos_list)
                    avg_price = sum(p['qty'] * p['entry_price'] for p in pos_list) / total_qty
                    current_size = current_price * total_qty
                    
                    if pos_type == 'Long':
                        unreal_pnl = (current_price - avg_price) * total_qty
                        pnl_pct = (current_price - avg_price) / avg_price * 100
                    else:
                        unreal_pnl = (avg_price - current_price) * total_qty
                        pnl_pct = (avg_price - current_price) / avg_price * 100
                    
                    p_col = "#28a745" if unreal_pnl >= 0 else "#dc3545"
                    p_sign = "+" if unreal_pnl >= 0 else ""
                    
                    st.markdown(f"{emoji} **Total {pos_list[0]['leverage']}x {pos_type}** | Qty: {total_qty:.4f} | Avg: **{avg_price:,.2f}** | price: {current_price:,.2f} | PNL: <span style='color:{p_col};'>{p_sign}{unreal_pnl:,.2f}</span> | ROI: <span style='color:{p_col};'>{p_sign}{pnl_pct:.2f}%</span>", unsafe_allow_html=True)
                    
                    with st.expander(f"⚙️ Edit SL/TP & Close Group"):
                        is_long_pos = (pos_type == 'Long')
                        key_suffix = f"{pos_type}"
                        sample_pos = pos_list[-1]

                        use_tp = st.checkbox("Set Take Profit (TP)", key=f"utp_{key_suffix}")
                        tp_type, tp_val = "Price", None
                        if use_tp:
                            c1, c2 = st.columns([1, 2])
                            tp_type = c1.selectbox("TP Type", ["Price", "PnL (USDT/KRW)", "ROI (%)"], label_visibility="collapsed", key=f"tpt_{key_suffix}")
                            default_tp = float(sample_pos['tp']) if sample_pos['tp'] else None
                            tp_val = c2.number_input("TP Value", value=default_tp, placeholder="Blank for none", step=0.1, key=f"tpv_{key_suffix}")

                        use_sl = st.checkbox("Set Stop Loss (SL)", key=f"usl_{key_suffix}")
                        sl_type, sl_val = "Price", None
                        if use_sl:
                            c1, c2 = st.columns([1, 2])
                            sl_type = c1.selectbox("SL Type", ["Price", "PnL (USDT/KRW)", "ROI (%)"], label_visibility="collapsed", key=f"slt_{key_suffix}")
                            default_sl = float(sample_pos['sl']) if sample_pos['sl'] else None
                            sl_val = c2.number_input("SL Value", value=default_sl, placeholder="Blank for none", step=0.1, key=f"slv_{key_suffix}")

                        new_tp = calc_target_price(avg_price, total_qty, sample_pos['leverage'], tp_type, tp_val, is_long_pos, is_sl=False)
                        new_sl = calc_target_price(avg_price, total_qty, sample_pos['leverage'], sl_type, sl_val, is_long_pos, is_sl=True)
                            
                        col_up, col_cl = st.columns(2)
                        if col_up.button("Update SL/TP", key=f"upd_{key_suffix}", use_container_width=True):
                            for p in st.session_state.open_positions:
                                if p['type'] == pos_type:
                                    if use_tp: p['tp'] = new_tp
                                    if use_sl: p['sl'] = new_sl
                            st.success(f"{pos_type} Group SL/TP Updated!")
                            st.rerun()

                        if col_cl.button("Close All", key=f"cl_{pos_type}", use_container_width=True):
                            for p in [p for p in st.session_state.open_positions if p['type'] == pos_type]:
                                exit_fee = (current_price * p['qty']) * 0.0025
                                st.session_state.balance -= exit_fee
                                if p['type'] == 'Long': net_pnl = (current_price - p['entry_price']) * p['qty']
                                else: net_pnl = (p['entry_price'] - current_price) * p['qty']
                                if p['margin_mode'] == 'Isolated' and net_pnl < -p['margin']: net_pnl = -p['margin']
                                st.session_state.cumulative_pnl += (net_pnl - exit_fee)
                                st.session_state.balance += net_pnl
                                st.session_state.trade_history.append({
                                    'ID': p['id'], 'Type': p['type'], 'Entry Date': p['entry_date'].strftime('%Y-%m-%d'),
                                    'Exit Date': current_date.strftime('%Y-%m-%d'), 'Entry Step': p['entry_step'], 'Exit Step': current_step,
                                    'Entry Price': p['entry_price'], 'Exit Price': current_price, 'Size': p['qty'], 'Net P&L': round(net_pnl - exit_fee, 2)
                                })
                            st.session_state.open_positions = [p for p in st.session_state.open_positions if p['type'] != pos_type]
                            st.rerun()

            render_grouped_positions(longs, 'Long', '🟢')
            render_grouped_positions(shorts, 'Short', '🔴')

        # ---------------------------------------------------------
        # (백그라운드) Next Candle 자동 체결 및 청산 로직
        # ---------------------------------------------------------
        if current_step > 0 and not is_bankrupt:
            new_open, new_high, new_low = current_row['Open'], current_row['High'], current_row['Low']
            surviving_positions = []
            for pos in st.session_state.open_positions:
                closed, exit_price, reason = False, 0, ""
                liq_price = 0
                if pos['margin_mode'] == 'Isolated':
                    if pos['type'] == 'Long': liq_price = pos['entry_price'] - (pos['margin'] / pos['qty'])
                    else: liq_price = pos['entry_price'] + (pos['margin'] / pos['qty'])
                
                if pos['margin_mode'] == 'Isolated':
                    if (pos['type'] == 'Long' and new_low <= liq_price) or (pos['type'] == 'Short' and new_high >= liq_price):
                        exit_price = new_open if (pos['type'] == 'Long' and new_open < liq_price) or (pos['type'] == 'Short' and new_open > liq_price) else liq_price
                        closed, reason = True, "Liquidation"

                if not closed:
                    if pos['type'] == 'Long':
                        if pos['sl'] and new_low <= pos['sl']:
                            exit_price = new_open if new_open < pos['sl'] else pos['sl']
                            closed, reason = True, "SL Hit"
                        elif pos['tp'] and new_high >= pos['tp']:
                            exit_price = new_open if new_open > pos['tp'] else pos['tp']
                            closed, reason = True, "TP Hit"
                    elif pos['type'] == 'Short':
                        if pos['sl'] and new_high >= pos['sl']:
                            exit_price = new_open if new_open > pos['sl'] else pos['sl']
                            closed, reason = True, "SL Hit"
                        elif pos['tp'] and new_low <= pos['tp']:
                            exit_price = new_open if new_open < pos['tp'] else pos['tp']
                            closed, reason = True, "TP Hit"
                
                if closed:
                    exit_fee = (exit_price * pos['qty']) * 0.0025
                    st.session_state.balance -= exit_fee
                    net_pnl = (exit_price - pos['entry_price']) * pos['qty'] if pos['type'] == 'Long' else (pos['entry_price'] - exit_price) * pos['qty']
                    if pos['margin_mode'] == 'Isolated' and net_pnl < -pos['margin']:
                        excess_loss = abs(net_pnl) - pos['margin']
                        st.session_state.balance -= excess_loss
                    st.session_state.cumulative_pnl += (net_pnl - exit_fee)
                    st.session_state.balance += net_pnl
                    st.session_state.trade_history.append({
                        'ID': f"{pos['id']} ({reason})", 'Type': pos['type'], 'Entry Date': pos['entry_date'].strftime('%Y-%m-%d'),
                        'Exit Date': current_date.strftime('%Y-%m-%d'), 'Entry Step': pos['entry_step'], 'Exit Step': current_step,
                        'Entry Price': pos['entry_price'], 'Exit Price': exit_price, 'Size': pos['qty'], 'Net P&L': round(net_pnl - exit_fee, 2)
                    })
                else:
                    surviving_positions.append(pos)
            st.session_state.open_positions = surviving_positions

    # ---------------------------------------------------------
    # 4. 차트 렌더링
    # ---------------------------------------------------------
    with col_chart:
        st.subheader("📊 Price & Trend")
        
        load_size = max(250, view_window)
        df_chart = df_view.tail(load_size).copy() 
        
        fig = sp.make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
        x_numeric = df_chart['step']
        hover_text = [f"Date: {d}<br>Step: {s}" for d, s in zip(df_chart['str_date'], df_chart['step'])]

        fig.add_trace(plotly_go.Candlestick(
            x=x_numeric, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], name="Price",
            text=hover_text,
            hovertemplate="%{text}<br>Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<extra></extra>"
        ), row=1, col=1)
        fig.add_trace(plotly_go.Bar(
            x=x_numeric, y=df_chart['Volume'], marker_color=df_chart['Vol_Color'], name="Volume"
        ), row=2, col=1)
        
        if 'Vol_MA' in df_chart.columns:
            fig.add_trace(plotly_go.Scatter(x=x_numeric, y=df_chart['Vol_MA'], line=dict(width=1.5, color='orange'), name='Vol MA(20)'), row=2, col=1)
        if 'ma200' in df_chart.columns:
            fig.add_trace(plotly_go.Scatter(x=x_numeric, y=df_chart['ma200'], line=dict(width=1.5, color='purple'), name='MA200'), row=1, col=1)

        for pt in ['Long', 'Short']:
            group = [p for p in st.session_state.open_positions if p['type'] == pt]
            if group:
                avg_p = sum(p['qty'] * p['entry_price'] for p in group) / sum(p['qty'] for p in group)
                fig.add_hline(y=avg_p, line_width=1, line_color="black", line_dash="solid", annotation_text=f"Avg {pt}", row=1, col=1)
                last_sl = next((p['sl'] for p in reversed(group) if p['sl']), None)
                last_tp = next((p['tp'] for p in reversed(group) if p['tp']), None)
                if last_sl: 
                    fig.add_hline(y=last_sl, line_width=1, line_color="yellow", line_dash="dash", annotation_text=f"SL ({pt})", row=1, col=1)
                if last_tp: 
                    fig.add_hline(y=last_tp, line_width=1, line_color="blue", line_dash="dash", annotation_text=f"TP ({pt})", row=1, col=1)

        for hist in st.session_state.trade_history:
            e_step, x_step = hist.get('Entry Step', 0), hist.get('Exit Step', 0)
            if x_step >= df_chart['step'].min():
                line_color = 'rgba(0, 200, 0, 0.5)' if hist['Net P&L'] >= 0 else 'rgba(200, 0, 0, 0.5)'
                fig.add_trace(plotly_go.Scatter(x=[e_step, x_step], y=[hist['Entry Price'], hist['Exit Price']], mode="lines", line=dict(color=line_color, width=2, dash='dot'), showlegend=False), row=1, col=1)
                marker_symbol = "triangle-up" if hist['Type'] == 'Long' else "triangle-down"
                fig.add_trace(plotly_go.Scatter(x=[e_step], y=[hist['Entry Price']], mode="markers", marker=dict(symbol=marker_symbol, size=10, color="blue"), showlegend=False), row=1, col=1)
                fig.add_trace(plotly_go.Scatter(x=[x_step], y=[hist['Exit Price']], mode="markers", marker=dict(symbol="x", size=10, color="black"), showlegend=False), row=1, col=1)

        tick_step = max(1, len(df_chart) // 10)
        tick_vals = df_chart['step'].iloc[::tick_step]
        tick_text = df_chart['str_date'].iloc[::tick_step]

        x_max = x_numeric.max()
        x_min = max(x_numeric.min(), x_max - view_window + 1)
        visible_data = df_chart[df_chart['step'] >= x_min]
        
        if not visible_data.empty:
            p_min = visible_data['Low'].min()
            p_max = visible_data['High'].max()
            y_elements = [p_min, p_max]
            for pt in ['Long', 'Short']:
                group = [p for p in st.session_state.open_positions if p['type'] == pt]
                if group:
                    avg_p = sum(p['qty'] * p['entry_price'] for p in group) / sum(p['qty'] for p in group)
                    y_elements.append(avg_p)
                    last_sl = next((p['sl'] for p in reversed(group) if p['sl']), None)
                    last_tp = next((p['tp'] for p in reversed(group) if p['tp']), None)
                    if last_sl: y_elements.append(last_sl)
                    if last_tp: y_elements.append(last_tp)
            
            final_y_min = min(y_elements)
            final_y_max = max(y_elements)
            p_margin = (final_y_max - final_y_min) * 0.05 if final_y_max != final_y_min else final_y_max * 0.05
            fig.update_yaxes(range=[final_y_min - p_margin, final_y_max + p_margin], row=1, col=1)
            v_max = visible_data['Volume'].max()
            fig.update_yaxes(range=[0, v_max * 1.1], row=2, col=1)

        fig.update_xaxes(
            range=[x_min - 0.5, x_max + 0.5], 
            tickmode='array', tickvals=tick_vals, ticktext=tick_text,
            rangeslider=dict(visible=False),
            showgrid=True
        )

        fig.update_layout(
            height=700, dragmode="pan",
            yaxis=dict(side="right", fixedrange=False),
            yaxis2=dict(side="right", fixedrange=False),
            legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.5)'),
            template="plotly_white", margin=dict(t=30, b=10, l=10, r=10)
        )
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
        
    # ---------------------------------------------------------
    # 5. 하단: 거래 기록 (Pandas Style 적용)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📜 Trade History")
    if st.session_state.trade_history:
        history_df = pd.DataFrame(st.session_state.trade_history)
        history_df = history_df[['ID', 'Entry Date', 'Exit Date', 'Type', 'Entry Price', 'Exit Price', 'Size', 'Net P&L']]
        
        def style_pnl_live(val):
            color = '#28a745' if val >= 0 else '#dc3545'
            return f'color: {color}; font-weight: bold;'
            
        st.dataframe(history_df.style.map(style_pnl_live, subset=['Net P&L']), use_container_width=True)
    else:
        st.info("No completed trades yet.")
