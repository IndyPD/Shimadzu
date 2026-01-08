#!/usr/bin/env python3
"""
Zone Predictor 빠른 테스트 (TENSILE 포함)

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

print("=" * 60)
print("Zone Predictor 테스트 - TENSILE 포함")
print("=" * 60)

# 예측기 초기화
predictor = ZonePredictor()
predictor.load_model()

# 테스트 케이스들
test_cases = [
    {
        "name": "TENSILE_FRONT_MOVE 샘플",
        "position": [178.38316, -171.36317, 811.9799, -96.42069, 0.9467065, 108.355156]
    },
    {
        "name": "ALIGNER 영역 샘플",
        "position": [-274.75452, -182.44957, 784.11884, -89.917244, 88.350426, 87.87211]
    },
    {
        "name": "RACK 영역 샘플",
        "position": [430.64, -426.75, 461.00, 90.26, -179.47, 0.35]
    }
]

for i, test in enumerate(test_cases, 1):
    print(f"\n[테스트 {i}] {test['name']}")
    print(f"좌표: {test['position'][:3]}...")  # x, y, z만 표시

    # Zone 예측
    result = predictor.predict_with_recovery_action(test['position'])

    # 결과 출력
    print(f"  → Zone: {result['zone_name']}")
    print(f"  → 신뢰도: {result['confidence']*100:.1f}%")
    print(f"  → 복구 액션: {result['recovery_action']}")

print("\n" + "=" * 60)
print("테스트 완료!")
print("=" * 60 + "\n")
