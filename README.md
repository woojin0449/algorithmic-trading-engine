# Turtle Trading & Livermore Replay Terminal

터틀 트레이딩(Trend Following) 기법을 시스템화한 자동 매매 봇 및 과거 데이터 복기(Replay)용 대시보드입니다. AWS EC2 환경에서 24/7 가동되며, 주관적 개입 없이 철저한 리스크 관리 규칙에 따라 실행됩니다.

## Core Rules & Constraints

본 시스템은 평균 회귀(Mean Reversion) 로직을 배제하며, 다음의 시스템적 제약을 엄격히 따릅니다.

*   **Risk per Trade:** 1회 매매당 발생할 수 있는 최대 손실을 총 자산의 1%로 제한.
*   **Sizing & Stop Loss:** ATR(Average True Range) 기반. N-value를 통해 포지션 규모와 손절매 라인을 동적으로 계산.
*   **Pyramiding:** 수익 중인 포지션에 한해 피라미딩 허용. 트레일링 스탑과 연계하여 수익 극대화.
*   **No Look-ahead Bias:** Pandas 연산 시 데이터 Shift 처리를 통해 백테스트와 라이브 환경에서의 미래 참조 편향 원천 차단.

## Tech Stack

*   **Language:** Python 3.10+
*   **Data & Math:** Pandas, NumPy
*   **API:** ccxt (Crypto), Korea Investment & Securities Open API (한국투자증권)
*   **Dashboard:** Streamlit
*   **Infrastructure:** AWS EC2, bash (프로세스 관리)

## System Architecture (Refactoring in Progress)

초기 모놀리식(Monolithic) 스크립트에서 목적별 모듈로 분리하는 작업을 진행 중입니다.

*   `app.py`: Streamlit 기반 프론트엔드 대시보드 (자산 현황, 포지션 모니터링, 과거 차트 리플레이)
*   `main.py`: 백그라운드 봇 실행 및 사이클 관리 
*   `logger.py`: 거래 내역 및 시스템 상태 로깅
*   `restart_bot.sh`: EC2 인스턴스 내 메모리 누수 방지 및 봇 강제 재시작 쉘 스크립트

## Notes

*   민감한 API Key 및 Token은 `.env`와 `.gitignore`를 통해 관리되어 레포지토리에 포함되지 않습니다.
*   `balance.json` 및 거래 기록은 `.example` 파일의 포맷을 참조하여 로컬에서 직접 생성 후 구동해야 합니다.
