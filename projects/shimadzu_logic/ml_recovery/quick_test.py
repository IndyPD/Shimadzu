#!/usr/bin/env python3
"""
Zone Predictor 빠른 테스트

사용법:
    프로젝트 루트에서: python -m projects.shimadzu_logic.ml_recovery.quick_test
    또는 이 디렉토리에서: python quick_test.py
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from projects.shimadzu_logic.ml_recovery.zone_predictor import ZonePredictor

# 예측기 초기화
predictor = ZonePredictor()
predictor.load_model()

# 현재 로봇 위치 (예시)
current_position = [430.64, -426.75, 461.00, 90.26, -179.47, 0.35]

# Zone 예측
result = predictor.predict_with_recovery_action(current_position)

# 결과 출력
print(f"\n좌표: {current_position}")
print(f"→ Zone: {result['zone_name']}")
print(f"→ 신뢰도: {result['confidence']*100:.1f}%")
print(f"→ 복구: {result['recovery_action']}\n")
