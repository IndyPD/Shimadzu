#!/usr/bin/env python3
"""
Zone 기반 모델 학습 스크립트 v2

업데이트:
- TENSILE 관련 motion data 추가 반영
- 519개 motion data 파일 활용
- 개선된 데이터 전처리 및 증강
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

# Home 위치 정의 (이 위치에 있을 때만 HOME Zone으로 학습)
HOME_POS = np.array([-50.0, 30.0, -160.0, 180.0, -40.0, 90.0])


def main():
    """Zone 기반 학습 파이프라인 v2 - TENSILE 포함"""

    print("=" * 70)
    print("Zone-based State Prediction Model Training v2")
    print("TENSILE 포함 - 519개 motion data 파일 활용")
    print("=" * 70)

    try:
        # 1. 데이터 로드
        Logger.info("\n[Step 1/6] Loading motion data...")
        preprocessor = MotionDataPreprocessor()
        X, y_cmd, metadata = preprocessor.load_all_data(min_samples=3)

        print(f"\n📊 원본 데이터셋:")
        print(f"  - 총 샘플: {len(X):,}")
        print(f"  - CMD 종류: {metadata['num_states']}")
        print(f"  - Feature 차원: {X.shape[1]} (6-DOF)")

        # 2. CMD ID → Zone 변환
        Logger.info("\n[Step 2/6] Converting CMD IDs to Zones...")
        y_zone_raw = np.array([ZoneClassifier.cmd_to_zone(cmd).value for cmd in y_cmd])

        # UNKNOWN (0)인 데이터 필터링
        valid_mask = y_zone_raw != 0
        unknown_count = len(y_zone_raw) - np.sum(valid_mask)

        if unknown_count > 0:
            Logger.warning(f"⚠️ UNKNOWN Zone 데이터 {unknown_count:,}개 제외됨")
            X = X[valid_mask]
            y_zone_raw = y_zone_raw[valid_mask]

        if len(X) == 0:
            Logger.error("❌ 유효한 학습 데이터가 없습니다.")
            return False

        # HOME Zone 위치 기반 필터링
        # WorkZone.HOME인 경우, 실제 위치가 HOME_POS와 가까운지 확인
        home_zone_val = WorkZone.HOME.value
        is_home_label = (y_zone_raw == home_zone_val)
        
        # 각 축별 오차 5.0 이내인 경우만 HOME으로 인정 (엄격한 기준 적용)
        # X는 (N, 6) 형태
        pos_diff = np.abs(X - HOME_POS)
        is_at_home_pos = np.all(pos_diff < 5.0, axis=1)
        
        # HOME 레이블이지만 위치가 HOME이 아닌 데이터 제거 (이동 중인 데이터 등)
        # (HOME이 아니거나) OR (HOME이면서 위치도 HOME인 경우) 만 유지
        keep_mask = (~is_home_label) | (is_at_home_pos)
        
        X = X[keep_mask]
        y_zone_raw = y_zone_raw[keep_mask]
        Logger.info(f"🏠 Home 위치 필터링 완료: {np.sum(~keep_mask):,}개 샘플 제외됨 (이동 중인 Home 데이터)")

        # LightGBM은 레이블이 0부터 시작해야 하므로 변환
        # WorkZone은 1~6이므로 1을 빼서 0~5로 변환
        y_zone = y_zone_raw - 1

        # Zone ID 매핑 저장 (나중에 예측 시 복원용)
        zone_id_mapping = {
            i: i + 1 for i in range(len(set(y_zone)))  # 0→1, 1→2, ..., 5→6
        }

        # Zone 분포 확인
        unique_zones, zone_counts = np.unique(y_zone, return_counts=True)
        zone_distribution = {}

        print(f"\n🎯 Zone 변환 결과:")
        print(f"  - Zone 종류: {len(unique_zones)}")
        print(f"\n📈 Zone별 샘플 분포:")

        for zone_id, count in zip(unique_zones, zone_counts):
            # 원래 Zone 값으로 복원 (0→1, 1→2, ...)
            original_zone_id = zone_id + 1
            zone = WorkZone(original_zone_id)
            zone_name = ZoneClassifier.get_zone_name(zone)
            zone_distribution[zone_name] = count
            percentage = count / len(X) * 100
            print(f"  - {zone_name:15s}: {count:6,} samples ({percentage:5.1f}%)")

        # 3. 데이터셋 품질 체크
        Logger.info("\n[Step 3/6] Data quality check...")
        print(f"\n🔍 데이터 품질 분석:")

        # 각 Zone별 최소/최대 샘플 수
        min_samples = min(zone_counts)
        max_samples = max(zone_counts)
        print(f"  - 최소 샘플 Zone: {min_samples:,}")
        print(f"  - 최대 샘플 Zone: {max_samples:,}")
        print(f"  - 샘플 불균형 비율: {max_samples / min_samples:.1f}x")

        # 4. 데이터 증강 (필요시)
        if len(X) < 5000:
            Logger.info(f"\n[Step 4/6] 데이터 증강 수행 중...")
            print(f"  현재 샘플: {len(X):,}")
            X_augmented, y_zone_augmented = preprocessor.augment_data(X, y_zone, noise_level=0.03)
            print(f"  증강 후: {len(X_augmented):,} (증가: {len(X_augmented) - len(X):,})")
            X, y_zone = X_augmented, y_zone_augmented
        else:
            Logger.info(f"\n[Step 4/6] 충분한 데이터 ({len(X):,} samples) - 증강 생략")

        # 5. 모델 학습
        Logger.info("\n[Step 5/6] Training Zone classification model...")
        trainer = ModelTrainer()

        # LightGBM 사용 가능 여부 확인
        try:
            import lightgbm
            use_lgb = True
            print("  🚀 사용 모델: LightGBM (고속 gradient boosting)")
        except ImportError:
            use_lgb = False
            print("  🌲 사용 모델: RandomForest (sklearn)")

        # Zone 메타데이터 준비
        zone_metadata = {
            "total_samples": len(X),
            "num_states": len(unique_zones),
            "state_counts": zone_distribution,
            "cmd_to_name": {
                int(zone_id): ZoneClassifier.get_zone_name(WorkZone(zone_id + 1))
                for zone_id in unique_zones
            },
            "unique_cmds": sorted([int(z) for z in unique_zones]),
            "model_type_desc": "Zone-based (TENSILE 포함)",
            "data_version": "v2_with_tensile",
            "motion_data_files": 519,
            "zone_id_mapping": zone_id_mapping,  # 0-based → 1-based 변환 정보
        }

        results = trainer.train(X, y_zone, zone_metadata, test_size=0.2, use_lgb=use_lgb)

        # 6. 결과 출력
        print(f"\n" + "=" * 70)
        print(f"✅ 학습 완료!")
        print(f"=" * 70)
        print(f"\n📊 모델 성능:")
        print(f"  - 모델 종류: {results['model_type']}")
        print(f"  - 정확도: {results['accuracy'] * 100:.2f}%")
        print(f"  - 학습 샘플: {results['train_samples']:,}")
        print(f"  - 테스트 샘플: {results['test_samples']:,}")

        # 목표 달성 확인
        print(f"\n🎯 목표 달성도:")
        if results['accuracy'] >= 0.95:
            print(f"  ✅ 우수! ({results['accuracy'] * 100:.2f}% >= 95%)")
        elif results['accuracy'] >= 0.90:
            print(f"  ✅ 양호 ({results['accuracy'] * 100:.2f}% >= 90%)")
        elif results['accuracy'] >= 0.80:
            print(f"  ⚠️  보통 ({results['accuracy'] * 100:.2f}% >= 80%)")
        else:
            print(f"  ❌ 개선 필요 ({results['accuracy'] * 100:.2f}% < 80%)")

        # 7. 모델 저장
        Logger.info("\n[Step 6/6] Saving Zone model...")
        trainer.save_model(filename="zone_predictor_model.pkl")

        print(f"\n💾 모델 저장 완료:")
        print(f"  - 모델 파일: ml_recovery/models/zone_predictor_model.pkl")
        print(f"  - 메타데이터: ml_recovery/models/model_metadata.json")

        # 8. Zone별 상세 정보
        print(f"\n" + "=" * 70)
        print(f"📋 Zone별 상세 정보")
        print(f"=" * 70)

        for zone_id in sorted(unique_zones):
            # 원래 Zone 값으로 복원 (0→1, 1→2, ...)
            original_zone_id = zone_id + 1
            zone = WorkZone(original_zone_id)
            zone_name = ZoneClassifier.get_zone_name(zone)
            zone_info = ZoneClassifier.get_zone_info(zone)
            sample_count = zone_distribution.get(zone_name, 0)

            print(f"\n{zone_name} ({zone.name}):")
            print(f"  - 영문명: {zone_info.get('name_en', 'N/A')}")
            print(f"  - 설명: {zone_info.get('description', 'N/A')}")
            print(f"  - 샘플 수: {sample_count:,}")
            print(f"  - 주요 동작: {', '.join(zone_info.get('typical_actions', []))}")

        print(f"\n" + "=" * 70)
        print(f"🎉 Zone 기반 학습 완료! (TENSILE 포함)")
        print(f"=" * 70)

        return True

    except Exception as e:
        Logger.error(f"\n❌ 학습 중 오류 발생: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
