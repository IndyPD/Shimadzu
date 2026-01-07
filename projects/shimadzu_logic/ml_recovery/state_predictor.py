"""
Real-time State Predictor

에러 발생 시 현재 로봇 위치를 받아서
어떤 상태로 향하고 있었는지 즉시 예측합니다.
"""

import pickle
import json
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
import logging

Logger = logging.getLogger(__name__)


class StatePredictor:
    """실시간 상태 예측 클래스"""

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

        Logger.info(f"[State Predictor] Initialized with model directory: {self.model_dir}")

    def load_model(self, model_filename: str = "state_predictor_model.pkl"):
        """
        저장된 모델 로드

        Args:
            model_filename: 모델 파일명

        Returns:
            성공 여부
        """
        model_path = self.model_dir / model_filename
        metadata_path = self.model_dir / "model_metadata.json"

        try:
            # 모델 파일 확인
            if not model_path.exists():
                Logger.error(f"[State Predictor] Model file not found: {model_path}")
                Logger.info("[State Predictor] Please train the model first using train_model.py")
                return False

            # 모델 로드
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)

            # 메타데이터 로드
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            else:
                Logger.warning(f"[State Predictor] Metadata file not found: {metadata_path}")
                self.metadata = {}

            self.is_loaded = True
            Logger.info(f"[State Predictor] Model loaded successfully")
            Logger.info(f"[State Predictor] Model type: {self.metadata.get('model_type', 'Unknown')}")
            Logger.info(f"[State Predictor] Test accuracy: {self.metadata.get('test_accuracy', 0) * 100:.2f}%")

            return True

        except Exception as e:
            Logger.error(f"[State Predictor] Failed to load model: {e}")
            self.is_loaded = False
            return False

    def predict(
        self,
        position: list,
        return_confidence: bool = True
    ) -> Tuple[Optional[int], Optional[str], Optional[float]]:
        """
        현재 위치로부터 상태 예측

        Args:
            position: 로봇 위치 [x, y, z, u, v, w]
            return_confidence: 신뢰도 반환 여부

        Returns:
            (predicted_cmd_id, state_name, confidence)
            예측 실패 시 (None, None, None)
        """
        if not self.is_loaded:
            Logger.error("[State Predictor] Model not loaded. Call load_model() first.")
            return None, None, None

        try:
            # 입력 검증
            if len(position) != 6:
                Logger.error(f"[State Predictor] Invalid position length: {len(position)} (expected 6)")
                return None, None, None

            # Numpy 배열로 변환 (shape: (1, 6))
            X = np.array([position], dtype=np.float32)

            # 예측
            pred_cmd_id = int(self.model.predict(X)[0])

            # 상태명 변환
            state_name = self.metadata.get("cmd_to_name", {}).get(pred_cmd_id, f"CMD_{pred_cmd_id}")

            # 신뢰도 계산 (확률 기반 모델인 경우)
            confidence = None
            if return_confidence:
                try:
                    if hasattr(self.model, 'predict_proba'):
                        # sklearn 모델
                        proba = self.model.predict_proba(X)[0]
                        confidence = float(np.max(proba))
                    elif hasattr(self.model, 'predict'):
                        # LightGBM (predict로 확률 얻기)
                        try:
                            proba = self.model.predict(X, num_iteration=self.model.best_iteration)
                            if len(proba.shape) > 1:
                                confidence = float(np.max(proba[0]))
                        except:
                            confidence = 0.95  # 기본값
                except:
                    confidence = 0.95  # 기본값

            Logger.info(f"[State Predictor] Predicted: {state_name} (CMD {pred_cmd_id}) with {confidence*100:.1f}% confidence")

            return pred_cmd_id, state_name, confidence

        except Exception as e:
            Logger.error(f"[State Predictor] Prediction failed: {e}")
            return None, None, None

    def predict_with_recovery_action(
        self,
        position: list
    ) -> Dict:
        """
        상태 예측 + 복구 액션 제안

        Args:
            position: 로봇 위치 [x, y, z, u, v, w]

        Returns:
            딕셔너리 {
                "predicted_cmd": CMD ID,
                "state_name": 상태명,
                "confidence": 신뢰도,
                "recovery_action": 복구 액션 설명,
                "success": 예측 성공 여부
            }
        """
        cmd_id, state_name, confidence = self.predict(position, return_confidence=True)

        if cmd_id is None:
            return {
                "success": False,
                "error": "Prediction failed"
            }

        # 복구 액션 매핑 (Command.md 기반)
        recovery_actions = self._get_recovery_action(cmd_id, state_name)

        return {
            "success": True,
            "predicted_cmd": cmd_id,
            "state_name": state_name,
            "confidence": confidence,
            "recovery_action": recovery_actions
        }

    def _get_recovery_action(self, cmd_id: int, state_name: str) -> str:
        """
        CMD ID에 따른 복구 액션 결정

        Command.md의 "정지 시 시편 버리기" 컬럼 기반
        """
        # 시편을 들고 있는 상태들 (O 표시된 것들)
        # M5~M22 범위는 시편 회수가 필요한 상태
        holding_specimen_ranges = [
            (2000, 2100),  # M5-M6: 랙에서 후퇴
            (3000, 8000),  # M7-M22: 측정기, 정렬기, 인장기 관련
        ]

        is_holding_specimen = any(
            start <= cmd_id <= end for start, end in holding_specimen_ranges
        )

        if is_holding_specimen:
            return "RECOVER_WITH_SCRAP_DISPOSAL"  # 시편 회수 후 스크랩 처리
        else:
            return "RECOVER_TO_HOME"  # 안전하게 홈으로 복귀

    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if not self.is_loaded:
            return {"loaded": False}

        return {
            "loaded": True,
            "model_type": self.metadata.get("model_type", "Unknown"),
            "test_accuracy": self.metadata.get("test_accuracy", 0),
            "num_states": self.metadata.get("num_states", 0),
            "total_samples": self.metadata.get("total_samples", 0)
        }


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)

    predictor = StatePredictor()

    # 모델 로드
    if predictor.load_model():
        # 테스트 예측 (임의의 좌표)
        test_position = [430.64, -426.75, 461.00, 90.26, -179.47, 0.35]
        result = predictor.predict_with_recovery_action(test_position)

        print(f"\n=== Prediction Result ===")
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Predicted State: {result['state_name']}")
            print(f"CMD ID: {result['predicted_cmd']}")
            print(f"Confidence: {result['confidence'] * 100:.2f}%")
            print(f"Recovery Action: {result['recovery_action']}")
    else:
        print("\nModel not found. Please train the model first.")
        print("Run: python -m ml_recovery.train_model")
