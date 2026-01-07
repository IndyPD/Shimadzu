#!/usr/bin/env python3
"""
모델 평가 및 정확도 검증 스크립트

학습된 모델의 성능을 다양한 지표로 평가합니다.
"""

import sys
import logging
import json
from pathlib import Path
import numpy as np

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from projects.shimadzu_logic.ml_recovery.data_preprocessor import MotionDataPreprocessor
from projects.shimadzu_logic.ml_recovery.state_predictor import StatePredictor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
Logger = logging.getLogger(__name__)


def evaluate_model():
    """모델 평가 메인 함수"""

    print("=" * 60)
    print("ML Model Evaluation")
    print("=" * 60)

    try:
        # 1. 데이터 로드
        Logger.info("\n[Step 1/3] Loading test data...")
        preprocessor = MotionDataPreprocessor()
        X, y, metadata = preprocessor.load_all_data(min_samples=3)

        print(f"\n데이터셋 정보:")
        print(f"  - 총 샘플: {len(X):,}")
        print(f"  - 상태 종류: {metadata['num_states']}")

        # 2. 모델 로드
        Logger.info("\n[Step 2/3] Loading trained model...")
        predictor = StatePredictor()

        if not predictor.load_model():
            print("\n❌ 학습된 모델을 찾을 수 없습니다.")
            print("먼저 모델을 학습하세요: python -m ml_recovery.train_model")
            return False

        model_info = predictor.get_model_info()
        print(f"\n모델 정보:")
        print(f"  - 모델 종류: {model_info.get('model_type', 'Unknown')}")
        print(f"  - 학습 시 정확도: {model_info.get('test_accuracy', 0) * 100:.2f}%")

        # 3. 전체 데이터셋에 대한 예측
        Logger.info("\n[Step 3/3] Evaluating on full dataset...")

        correct = 0
        total = len(X)
        confidence_scores = []
        state_accuracy = {}

        for i, (position, true_label) in enumerate(zip(X, y)):
            pred_cmd, state_name, confidence = predictor.predict(
                position.tolist(),
                return_confidence=True
            )

            if pred_cmd == true_label:
                correct += 1

            if confidence is not None:
                confidence_scores.append(confidence)

            # 상태별 정확도 계산
            true_state = metadata["cmd_to_name"].get(true_label, f"CMD_{true_label}")
            if true_state not in state_accuracy:
                state_accuracy[true_state] = {"correct": 0, "total": 0}

            state_accuracy[true_state]["total"] += 1
            if pred_cmd == true_label:
                state_accuracy[true_state]["correct"] += 1

            # 진행 상황 표시
            if (i + 1) % 100 == 0:
                print(f"  진행: {i + 1}/{total} ({(i + 1) / total * 100:.1f}%)", end='\r')

        # 결과 계산
        overall_accuracy = correct / total
        avg_confidence = np.mean(confidence_scores) if confidence_scores else 0

        print("\n\n" + "=" * 60)
        print("평가 결과")
        print("=" * 60)

        print(f"\n전체 정확도: {overall_accuracy * 100:.2f}% ({correct}/{total})")
        print(f"평균 신뢰도: {avg_confidence * 100:.2f}%")

        # 목표 달성 여부
        target_accuracy = 0.95
        if overall_accuracy >= target_accuracy:
            print(f"\n✅ 목표 정확도 달성! ({overall_accuracy * 100:.2f}% >= {target_accuracy * 100}%)")
        else:
            print(f"\n⚠️  목표 정확도 미달 ({overall_accuracy * 100:.2f}% < {target_accuracy * 100}%)")
            gap = (target_accuracy - overall_accuracy) * 100
            print(f"   {gap:.2f}%p 더 개선 필요")

        # 상태별 정확도
        print("\n상태별 정확도:")
        print("-" * 60)

        sorted_states = sorted(
            state_accuracy.items(),
            key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0
        )

        for state_name, stats in sorted_states:
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            status = "✅" if acc >= 0.95 else "⚠️" if acc >= 0.85 else "❌"
            print(f"{status} {state_name:30s}: {acc * 100:5.1f}% ({stats['correct']}/{stats['total']})")

        # 낮은 정확도 상태 분석
        low_acc_states = [
            (name, stats) for name, stats in state_accuracy.items()
            if (stats["correct"] / stats["total"] if stats["total"] > 0 else 0) < 0.85
        ]

        if low_acc_states:
            print("\n⚠️  개선이 필요한 상태:")
            for state_name, stats in low_acc_states:
                acc = stats["correct"] / stats["total"]
                print(f"   - {state_name}: {acc * 100:.1f}% (샘플 수: {stats['total']})")
                if stats['total'] < 10:
                    print(f"     → 데이터 부족 (최소 10개 권장)")

        # 평가 결과 저장
        results = {
            "overall_accuracy": float(overall_accuracy),
            "average_confidence": float(avg_confidence),
            "total_samples": total,
            "correct_predictions": correct,
            "state_accuracy": {
                state: {
                    "accuracy": stats["correct"] / stats["total"] if stats["total"] > 0 else 0,
                    "correct": stats["correct"],
                    "total": stats["total"]
                }
                for state, stats in state_accuracy.items()
            }
        }

        results_path = Path(__file__).parent / "models" / "evaluation_results.json"
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n평가 결과 저장: {results_path}")

        print("\n" + "=" * 60)
        return overall_accuracy >= target_accuracy

    except Exception as e:
        Logger.error(f"\n평가 중 오류 발생: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = evaluate_model()
    sys.exit(0 if success else 1)
