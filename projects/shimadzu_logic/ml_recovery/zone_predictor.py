"""
Zone-based State Predictor

현재 위치로 어느 구역에서 작업 중이었는지 예측
6개 Zone으로 분류하여 높은 정확도 달성
"""

import pickle
import json
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
import logging

from zone_classifier import ZoneClassifier, WorkZone

Logger = logging.getLogger(__name__)


class ZonePredictor:
    """Zone 기반 실시간 예측 클래스"""

    def __init__(self, model_dir: str = None):
        """
        Args:
            model_dir: 학습된 모델이 저장된 경로
        """
        if model_dir is None:
            current_dir = Path(__file__).parent
            self.model_dir = current_dir / "models"
        else:
            self.model_dir = Path(model_dir)

        self.model = None
        self.metadata = None
        self.is_loaded = False

        Logger.info(f"[Zone Predictor] Initialized with model directory: {self.model_dir}")

    def load_model(self, model_filename: str = "zone_predictor_model.pkl"):
        """
        저장된 Zone 모델 로드

        Args:
            model_filename: 모델 파일명

        Returns:
            성공 여부
        """
        model_path = self.model_dir / model_filename
        metadata_path = self.model_dir / "model_metadata.json"

        try:
            if not model_path.exists():
                Logger.error(f"[Zone Predictor] Model file not found: {model_path}")
                return False

            # 모델 로드
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)

            # 메타데이터 로드
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = {}

            self.is_loaded = True
            Logger.info(f"[Zone Predictor] Model loaded successfully")
            Logger.info(f"[Zone Predictor] Model type: {self.metadata.get('model_type', 'Unknown')}")
            Logger.info(f"[Zone Predictor] Test accuracy: {self.metadata.get('test_accuracy', 0) * 100:.2f}%")

            return True

        except Exception as e:
            Logger.error(f"[Zone Predictor] Failed to load model: {e}")
            self.is_loaded = False
            return False

    def predict(
        self,
        position: list,
        return_confidence: bool = True
    ) -> Tuple[Optional[WorkZone], Optional[str], Optional[float]]:
        """
        현재 위치로부터 Zone 예측

        Args:
            position: 로봇 위치 [x, y, z, u, v, w]
            return_confidence: 신뢰도 반환 여부

        Returns:
            (predicted_zone, zone_name, confidence)
        """
        if not self.is_loaded:
            Logger.error("[Zone Predictor] Model not loaded. Call load_model() first.")
            return None, None, None

        try:
            if len(position) != 6:
                Logger.error(f"[Zone Predictor] Invalid position length: {len(position)}")
                return None, None, None

            # 예측
            X = np.array([position], dtype=np.float32)

            # 모델 타입에 따라 예측 방식 변경
            model_type = self.metadata.get('model_type', 'Unknown')

            if model_type == "LightGBM":
                # LightGBM Booster는 확률을 반환
                pred_proba = self.model.predict(X)[0]  # (num_classes,) 배열
                pred_zone_id = int(np.argmax(pred_proba))
                # 0-based를 1-based로 변환 (zone_id_mapping 사용)
                zone_id_mapping = self.metadata.get('zone_id_mapping', {})
                # JSON에서 로드하면 키가 문자열일 수 있음
                pred_zone_id = zone_id_mapping.get(str(pred_zone_id), zone_id_mapping.get(pred_zone_id, pred_zone_id + 1))
                confidence = float(np.max(pred_proba)) if return_confidence else None
            else:
                # RandomForest는 클래스를 직접 반환
                pred_zone_id = int(self.model.predict(X)[0])
                # 신뢰도 계산
                confidence = None
                if return_confidence:
                    try:
                        if hasattr(self.model, 'predict_proba'):
                            proba = self.model.predict_proba(X)[0]
                            confidence = float(np.max(proba))
                        else:
                            confidence = 0.95
                    except:
                        confidence = 0.95

            pred_zone = WorkZone(pred_zone_id)
            zone_name = ZoneClassifier.get_zone_name(pred_zone)

            Logger.info(f"[Zone Predictor] Predicted: {zone_name} ({pred_zone.name}) with {confidence*100:.1f}% confidence")

            return pred_zone, zone_name, confidence

        except Exception as e:
            Logger.error(f"[Zone Predictor] Prediction failed: {e}")
            return None, None, None

    def predict_with_recovery_action(self, position: list) -> Dict:
        """
        Zone 예측 + 복구 액션 제안

        Args:
            position: 로봇 위치 [x, y, z, u, v, w]

        Returns:
            예측 결과 딕셔너리
        """
        zone, zone_name, confidence = self.predict(position, return_confidence=True)

        if zone is None:
            return {
                "success": False,
                "error": "Prediction failed"
            }

        # 복구 액션 결정
        recovery_action = ZoneClassifier.zone_to_recovery_action(zone)

        # Zone 상세 정보
        zone_info = ZoneClassifier.get_zone_info(zone)

        return {
            "success": True,
            "predicted_zone": zone.name,
            "zone_name": zone_name,
            "confidence": confidence,
            "recovery_action": recovery_action,
            "zone_info": zone_info,
        }

    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if not self.is_loaded:
            return {"loaded": False}

        return {
            "loaded": True,
            "model_type": "Zone-based Classifier",
            "test_accuracy": self.metadata.get("test_accuracy", 0),
            "num_zones": self.metadata.get("num_states", 0),
            "total_samples": self.metadata.get("total_samples", 0),
        }


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)

    predictor = ZonePredictor()

    if predictor.load_model():
        # 테스트 예측
        test_position = [-213.72, -179.88, 702.74, -54.72, 88.20131, 123.596]
        result = predictor.predict_with_recovery_action(test_position)

        print(f"\n=== Zone Prediction Result ===")
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Predicted Zone: {result['zone_name']}")
            print(f"Confidence: {result['confidence'] * 100:.2f}%")
            print(f"Recovery Action: {result['recovery_action']}")
            print(f"\nZone Info:")
            zone_info = result.get('zone_info', {})
            print(f"  - 영문명: {zone_info.get('name_en')}")
            print(f"  - 설명: {zone_info.get('description')}")
            print(f"  - 주요 동작: {', '.join(zone_info.get('typical_actions', []))}")
    else:
        print("\nZone model not found. Please train first:")
        print("python -m projects.shimadzu_logic.ml_recovery.train_zone_model")
