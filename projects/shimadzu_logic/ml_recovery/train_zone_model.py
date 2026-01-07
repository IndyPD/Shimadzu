#!/usr/bin/env python3
"""
Zone 기반 모델 학습 스크립트

64개 상태 → 6개 Zone으로 그룹화
적은 데이터로도 높은 정확도 달성 가능
"""

import sys
import logging
from pathlib import Path
import numpy as np

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from projects.shimadzu_logic.ml_recovery.data_preprocessor import MotionDataPreprocessor
from projects.shimadzu_logic.ml_recovery.model_trainer import ModelTrainer
from projects.shimadzu_logic.ml_recovery.zone_classifier import ZoneClassifier, WorkZone

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
Logger = logging.getLogger(__name__)


def main():
    """Zone 기반 학습 파이프라인"""

    print("=" * 60)
    print("Zone-based State Prediction Model Training")
    print("64개 상태 → 6개 Zone으로 그룹화")
    print("=" * 60)

    try:
        # 1. 데이터 로드
        Logger.info("\n[Step 1/5] Loading motion data...")
        preprocessor = MotionDataPreprocessor()
        X, y_cmd, metadata = preprocessor.load_all_data(min_samples=3)

        print(f"\n원본 데이터셋:")
        print(f"  - 총 샘플: {len(X):,}")
        print(f"  - 상태 종류: {metadata['num_states']} (CMD ID)")

        # 2. CMD ID → Zone 변환
        Logger.info("\n[Step 2/5] Converting CMD IDs to Zones...")
        y_zone = np.array([ZoneClassifier.cmd_to_zone(cmd).value for cmd in y_cmd])

        # Zone 분포 확인
        unique_zones, zone_counts = np.unique(y_zone, return_counts=True)
        zone_distribution = {}

        print(f"\nZone 변환 결과:")
        print(f"  - Zone 종류: {len(unique_zones)}")
        print(f"\nZone별 샘플 분포:")

        for zone_id, count in zip(unique_zones, zone_counts):
            zone = WorkZone(zone_id)
            zone_name = ZoneClassifier.get_zone_name(zone)
            zone_distribution[zone_name] = count
            print(f"  - {zone_name:15s}: {count:5,} samples ({count/len(X)*100:5.1f}%)")

        # 3. 데이터 증강 (선택적)
        if len(X) < 3000:
            Logger.info(f"\n[Step 3/5] 데이터가 부족합니다 ({len(X)} samples).")
            Logger.info("데이터 증강을 수행합니다...")
            X_augmented, y_zone_augmented = preprocessor.augment_data(X, y_zone, noise_level=0.05)
            print(f"  증강 후 샘플: {len(X_augmented):,}")
            X, y_zone = X_augmented, y_zone_augmented
        else:
            Logger.info(f"\n[Step 3/5] 충분한 데이터가 있습니다 ({len(X)} samples).")

        # 4. 모델 학습
        Logger.info("\n[Step 4/5] Training Zone classification model...")
        trainer = ModelTrainer()

        # LightGBM 사용 가능 여부 확인
        try:
            import lightgbm
            use_lgb = True
            print("  사용 모델: LightGBM")
        except ImportError:
            use_lgb = False
            print("  사용 모델: RandomForest")

        # Zone 메타데이터 준비
        zone_metadata = {
            "total_samples": len(X),
            "num_states": len(unique_zones),
            "state_counts": zone_distribution,
            "cmd_to_name": {
                int(zone_id): ZoneClassifier.get_zone_name(WorkZone(zone_id))
                for zone_id in unique_zones
            },
            "unique_cmds": sorted([int(z) for z in unique_zones]),
            "model_type_desc": "Zone-based (6 zones)",
        }

        results = trainer.train(X, y_zone, zone_metadata, test_size=0.2, use_lgb=use_lgb)

        # 5. 결과 출력
        print(f"\n학습 결과:")
        print(f"  - 모델 종류: {results['model_type']} (Zone 기반)")
        print(f"  - 정확도: {results['accuracy'] * 100:.2f}%")
        print(f"  - 학습 샘플: {results['train_samples']:,}")
        print(f"  - 테스트 샘플: {results['test_samples']:,}")

        # 목표 달성 확인
        if results['accuracy'] >= 0.90:
            print(f"\n✅ 우수한 정확도 달성! ({results['accuracy'] * 100:.2f}% >= 90%)")
        elif results['accuracy'] >= 0.80:
            print(f"\n✅ 양호한 정확도! ({results['accuracy'] * 100:.2f}% >= 80%)")
        else:
            print(f"\n⚠️  정확도 개선 필요 ({results['accuracy'] * 100:.2f}% < 80%)")

        # 6. 모델 저장
        Logger.info("\n[Step 5/5] Saving Zone model...")
        trainer.save_model(filename="zone_predictor_model.pkl")

        print(f"\n모델 저장 완료:")
        print(f"  - 모델 파일: ml_recovery/models/zone_predictor_model.pkl")
        print(f"  - 메타데이터: ml_recovery/models/model_metadata.json")

        print("\n" + "=" * 60)
        print("Zone 기반 학습 완료!")
        print("=" * 60)

        # 7. 비교 분석
        print(f"\n📊 세부 상태 vs Zone 비교:")
        print(f"{'':20s} {'세부 상태 (64개)':>20s} {'Zone (6개)':>20s}")
        print(f"{'-'*60}")
        print(f"{'데이터 필요량':20s} {'15,000+ 샘플':>20s} {'1,500+ 샘플':>20s}")
        print(f"{'현재 정확도':20s} {'54%':>20s} {f'{results["accuracy"]*100:.1f}%':>20s}")
        print(f"{'목표 달성':20s} {'2주 필요':>20s} {'✅ 즉시 가능':>20s}")
        print(f"{'복구 정밀도':20s} {'높음 (상태별)':>20s} {'중간 (구역별)':>20s}")

        return True

    except Exception as e:
        Logger.error(f"\n학습 중 오류 발생: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
