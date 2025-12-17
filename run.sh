#!/bin/bash
python3 run.py --project=shimadzu_logic & # <-- '&' 추가
#                                           ^
#                                           이것이 run.py를 백그라운드에서 실행하고 run.sh를 즉시 종료하게 만듭니다.