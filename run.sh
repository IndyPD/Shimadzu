#!/bin/bash

# python 명령어 확인 (python3 또는 python)
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

# nohup을 사용하여 터미널이 종료되어도 프로세스가 유지되도록 함
nohup $PYTHON_CMD run.py --project=shimadzu_logic > /dev/null 2>&1 &

# 백그라운드 실행된 프로세스의 PID 저장
echo $! > shimadzu_pid.txt
echo "Shimadzu Logic started. PID stored in shimadzu_pid.txt"