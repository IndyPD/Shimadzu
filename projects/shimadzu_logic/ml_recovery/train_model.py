#!/usr/bin/env python3
"""
모델 학습 스크립트

사용법:
    python -m ml_recovery.train_model
    또는
    python projects/shimadzu_logic/ml_recovery/train_model.py
"""

import sys
import logging
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from projects.shimadzu_logic.ml_recovery.data_preprocessor import MotionDataPreprocessor
from projects.shimadzu_logic.ml_recovery.model_trainer import ModelTrainer

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
Logger = logging.getLogger(__name__)


def main():
    """메인 학습 파이프라인"""

    print("=" * 60)
    print("ML-based State Prediction Model Training")
    print("=" * 60)

    try:
        # 1. 데이터 로드
        Logger.info("\n[Step 1/4] Loading motion data...")
        preprocessor = MotionDataPreprocessor()
        X, y, metadata = preprocessor.load_all_data(min_samples=3)

        print(f"\n데이터셋 정보:")
        print(f"  - 총 샘플 수: {metadata['total_samples']:,}")
        print(f"  - 상태 종류: {metadata['num_states']}")
        print(f"\n상태별 샘플 분포:")
        for state, count in sorted(metadata['state_counts'].items(), key=lambda x: -x[1])[:10]:
            print(f"  - {state}: {count} samples")

        # 데이터 부족 시 자동 증강
        if metadata['total_samples'] < 5000:
            Logger.info(f"\n[Step 2/4] 데이터가 부족합니다 ({metadata['total_samples']} samples).")
            Logger.info("데이터 증강을 자동으로 수행합니다...")
            X, y = preprocessor.augment_data(X, y, noise_level=0.05)
            print(f"  증강 후 샘플 수: {len(X):,}")

        # 2. 모델 학습
        Logger.info("\n[Step 3/4] Training model...")
        trainer = ModelTrainer()

        # LightGBM 사용 가능 여부 확인
        try:
            import lightgbm
            use_lgb = True
            print("  사용 모델: LightGBM (고성능)")
        except ImportError:
            use_lgb = False
            print("  사용 모델: RandomForest (LightGBM 미설치)")
            print("  더 나은 성능을 위해 'pip install lightgbm' 권장")

        results = trainer.train(X, y, metadata, test_size=0.2, use_lgb=use_lgb)

        # 3. 결과 출력
        print(f"\n학습 결과:")
        print(f"  - 모델 종류: {results['model_type']}")
        print(f"  - 정확도: {results['accuracy'] * 100:.2f}%")
        print(f"  - 학습 샘플: {results['train_samples']:,}")
        print(f"  - 테스트 샘플: {results['test_samples']:,}")

        # 95% 목표 달성 확인
        if results['accuracy'] >= 0.95:
            print(f"\n✅ 목표 정확도 달성! ({results['accuracy'] * 100:.2f}% >= 95%)")
        else:
            print(f"\n⚠️  목표 정확도 미달 ({results['accuracy'] * 100:.2f}% < 95%)")
            print("   더 많은 데이터를 수집하거나 데이터 증강을 시도해보세요.")

        # 4. 모델 저장
        Logger.info("\n[Step 4/4] Saving model...")
        trainer.save_model()

        print(f"\n모델 저장 완료:")
        print(f"  - 모델 파일: ml_recovery/models/state_predictor_model.pkl")
        print(f"  - 메타데이터: ml_recovery/models/model_metadata.json")

        print("\n" + "=" * 60)
        print("학습 완료! 이제 상태 예측을 사용할 수 있습니다.")
        print("=" * 60)

        # 테스트 예측 수행
        print("\n테스트 예측 수행 중...")
        from projects.shimadzu_logic.ml_recovery.state_predictor import StatePredictor

        predictor = StatePredictor()
        if predictor.load_model():
            # 첫 번째 샘플로 테스트
            test_pos = X[0].tolist()
            result = predictor.predict_with_recovery_action(test_pos)

            if result.get('success'):
                print(f"\n샘플 예측 결과:")
                print(f"  - 위치: {test_pos}")
                print(f"  - 예측 상태: {result['state_name']}")
                print(f"  - 신뢰도: {result['confidence'] * 100:.2f}%")
                print(f"  - 복구 액션: {result['recovery_action']}")

        return True

    except FileNotFoundError as e:
        Logger.error(f"\n데이터 디렉토리를 찾을 수 없습니다: {e}")
        Logger.error("motion_data 폴더에 JSON 파일이 있는지 확인하세요.")
        return False

    except Exception as e:
        Logger.error(f"\n학습 중 오류 발생: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
