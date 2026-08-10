#!/bin/bash

# 1. 실행 중인 파이썬 봇과 대시보드 강제 종료
pkill -9 -f main.py
pkill -9 -f streamlit

# 2. 메모리가 완전히 반환될 때까지 10초 대기
sleep 10

# 3. 봇 폴더로 이동 및 가상환경 활성화
cd /home/ubuntu/turtle_bot
source venv/bin/activate

# 4. 봇과 대시보드 다시 백그라운드 실행
nohup python3 main.py > /dev/null 2>&1 &
nohup python3 -m streamlit run app.py --server.port 8080 > /dev/null 2>&1 &

# (선택) 재시작 완료 시간을 로그로 남기기
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 시스템 정기 재시작 완료" >> restart_history.log
