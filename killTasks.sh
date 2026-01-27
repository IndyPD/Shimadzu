#!/bin/bash

PID_FILE="shimadzu_pid.txt"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "Stopping process with PID: $PID"
    kill -9 $PID
    rm "$PID_FILE"
    echo "Process killed and PID file removed."
else
    echo "PID file not found. Trying to kill by process name..."
    # PID 파일이 없을 경우 프로세스 이름으로 검색하여 종료 (안전장치)
    pkill -f "python3 run.py --project=shimadzu_logic"
    echo "Kill command sent via pkill."
fi