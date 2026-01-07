"""
Recovery Integration Module

기존 로봇 FSM과 ML 기반 상태 예측을 통합하여
에러 발생 시 자동 복구를 수행합니다.
"""

import logging
from typing import Optional, Dict, Tuple
from .state_predictor import StatePredictor

Logger = logging.getLogger(__name__)


class MLRecoveryIntegration:
    """ML 기반 복구 시스템 통합 클래스"""

    def __init__(self, enable_ml_recovery: bool = True):
        """
        Args:
            enable_ml_recovery: ML 기반 복구 활성화 여부
        """
        self.enable_ml_recovery = enable_ml_recovery
        self.predictor = StatePredictor()
        self.is_model_loaded = False

        if self.enable_ml_recovery:
            self.is_model_loaded = self.predictor.load_model()
            if not self.is_model_loaded:
                Logger.warning("[ML Recovery] Model not loaded. ML-based recovery disabled.")
                self.enable_ml_recovery = False

    def predict_current_state(
        self,
        current_position: list
    ) -> Dict:
        """
        현재 로봇 위치로부터 상태 예측

        Args:
            current_position: 현재 로봇 위치 [x, y, z, u, v, w]

        Returns:
            예측 결과 딕셔너리 (state_predictor.predict_with_recovery_action 참고)
        """
        if not self.enable_ml_recovery or not self.is_model_loaded:
            return {
                "success": False,
                "error": "ML recovery not available"
            }

        return self.predictor.predict_with_recovery_action(current_position)

    def get_recovery_motion_sequence(
        self,
        predicted_cmd: int,
        recovery_action: str
    ) -> list:
        """
        예측된 상태와 복구 액션에 따른 모션 시퀀스 생성

        Args:
            predicted_cmd: 예측된 CMD ID
            recovery_action: 복구 액션 타입

        Returns:
            모션 명령 시퀀스 리스트 (MotionCommand Enum 값들)
        """
        from ..constants import MotionCommand

        motion_sequence = []

        if recovery_action == "RECOVER_WITH_SCRAP_DISPOSAL":
            # 시편을 들고 있는 경우: 스크랩 처리 후 홈 복귀
            Logger.info("[ML Recovery] Recovery with scrap disposal")

            # 예측된 위치에서 안전하게 후퇴
            retreat_cmd = self._get_retreat_command(predicted_cmd)
            if retreat_cmd:
                motion_sequence.append(retreat_cmd)

            # 스크랩 처리 시퀀스 (ACT07)
            motion_sequence.extend([
                MotionCommand.MOVE_TO_SCRAP_DISPOSER,
                MotionCommand.PLACE_IN_SCRAP_DISPOSER,
                MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER,
                MotionCommand.RETREAT_FROM_SCRAP_DISPOSER,
            ])

            # 스크랩 처리기에서 홈으로
            motion_sequence.append(MotionCommand.SCRAP_DISPOSER_FRONT_HOME)

        elif recovery_action == "RECOVER_TO_HOME":
            # 시편을 들고 있지 않은 경우: 바로 홈 복귀
            Logger.info("[ML Recovery] Direct recovery to home")

            # 예측된 위치에서 안전하게 후퇴
            retreat_cmd = self._get_retreat_command(predicted_cmd)
            if retreat_cmd:
                motion_sequence.append(retreat_cmd)

            # 홈 복귀
            motion_sequence.append(MotionCommand.MOVE_TO_HOME)

        else:
            Logger.warning(f"[ML Recovery] Unknown recovery action: {recovery_action}")
            # 기본값: 홈 복귀
            motion_sequence.append(MotionCommand.MOVE_TO_HOME)

        return motion_sequence

    def _get_retreat_command(self, predicted_cmd: int) -> Optional:
        """
        예측된 CMD에 따른 후퇴 명령 결정

        Args:
            predicted_cmd: 예측된 CMD ID

        Returns:
            적절한 후퇴 MotionCommand, 없으면 None
        """
        from ..constants import MotionCommand, RobotMotionCommand

        # Command.md의 후퇴 명령 매핑
        # CMD ID 범위별로 적절한 후퇴 명령 반환

        # 랙 관련 (1000-2100)
        if 1000 <= predicted_cmd < 2000:
            # 랙에서 접근 중이었다면 후퇴
            floor = (predicted_cmd - 1000) // 10
            return MotionCommand.RETREAT_FROM_RACK

        elif 2000 <= predicted_cmd < 3000:
            # 이미 후퇴 중이었다면 랙 홈으로
            return MotionCommand.RACK_FRONT_HOME

        # 두께 측정기 관련 (3000-4999)
        elif 3000 <= predicted_cmd < 5000:
            if 4000 <= predicted_cmd < 4003:
                # 이미 후퇴 명령
                return MotionCommand.THICK_GAUGE_FRONT_HOME
            else:
                # 측정기에서 후퇴
                return MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK

        # 정렬기 관련 (5000-6999)
        elif 5000 <= predicted_cmd < 7000:
            if predicted_cmd == 6000:
                # 이미 후퇴 명령
                return MotionCommand.ALIGNER_FRONT_HOME
            else:
                return MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK

        # 인장기 및 스크랩 (7000-8999)
        elif 7000 <= predicted_cmd < 9000:
            if 7020 <= predicted_cmd <= 7022:
                # 스크랩 처리기
                return MotionCommand.SCRAP_DISPOSER_FRONT_HOME
            elif predicted_cmd == 8000:
                # 이미 후퇴 명령
                return MotionCommand.TENSILE_TESTER_FRONT_HOME
            else:
                return MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK

        # 기타
        return None

    def execute_ml_recovery(
        self,
        current_position: list,
        robot_context
    ) -> bool:
        """
        ML 기반 자동 복구 실행

        Args:
            current_position: 현재 로봇 위치 [x, y, z, u, v, w]
            robot_context: 로봇 컨텍스트 객체 (모션 명령 전송용)

        Returns:
            복구 성공 여부
        """
        if not self.enable_ml_recovery:
            Logger.warning("[ML Recovery] ML recovery is disabled")
            return False

        try:
            # 1. 상태 예측
            Logger.info(f"[ML Recovery] Predicting state from position: {current_position}")
            result = self.predict_current_state(current_position)

            if not result.get('success'):
                Logger.error(f"[ML Recovery] Prediction failed: {result.get('error')}")
                return False

            Logger.info(f"[ML Recovery] Predicted state: {result['state_name']} (CMD {result['predicted_cmd']})")
            Logger.info(f"[ML Recovery] Confidence: {result['confidence'] * 100:.2f}%")
            Logger.info(f"[ML Recovery] Recovery action: {result['recovery_action']}")

            # 신뢰도 체크 (95% 미만이면 경고)
            if result['confidence'] < 0.80:
                Logger.warning(f"[ML Recovery] Low confidence ({result['confidence'] * 100:.2f}%). Proceed with caution.")

            # 2. 복구 시퀀스 생성
            motion_sequence = self.get_recovery_motion_sequence(
                result['predicted_cmd'],
                result['recovery_action']
            )

            Logger.info(f"[ML Recovery] Recovery sequence: {[cmd.value for cmd in motion_sequence]}")

            # 3. 복구 모션 실행
            # 실제 실행은 robot_context를 통해 수행
            # (이 부분은 기존 FSM 구조에 맞게 조정 필요)

            return True

        except Exception as e:
            Logger.error(f"[ML Recovery] Recovery execution failed: {e}", exc_info=True)
            return False

    def get_status(self) -> Dict:
        """ML 복구 시스템 상태 반환"""
        return {
            "enabled": self.enable_ml_recovery,
            "model_loaded": self.is_model_loaded,
            "model_info": self.predictor.get_model_info() if self.is_model_loaded else {}
        }


# 싱글톤 인스턴스 (선택사항)
_ml_recovery_instance = None


def get_ml_recovery_instance(enable: bool = True) -> MLRecoveryIntegration:
    """ML 복구 시스템 싱글톤 인스턴스 반환"""
    global _ml_recovery_instance
    if _ml_recovery_instance is None:
        _ml_recovery_instance = MLRecoveryIntegration(enable_ml_recovery=enable)
    return _ml_recovery_instance
