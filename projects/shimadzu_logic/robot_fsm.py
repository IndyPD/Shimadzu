from .robot_strategy import *
from .constants import *


class RobotFSM(FiniteStateMachine):
    context: RobotContext

    def __init__(self, context: RobotContext, *args, **kwargs):
        FiniteStateMachine.__init__(self, RobotState.CONNECTING, context, *args, **kwargs)

    def _setup_rules(self):
        self._rule_table = {
            # 1. 초기 상태: 연결 시도
            RobotState.CONNECTING: {
                RobotEvent.CONNECTION_SUCCESS: RobotState.READY,
                RobotEvent.CONNECTION_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            
            # 2. 에러 및 복구
            RobotState.ERROR: {
                RobotEvent.RECOVER: RobotState.RECOVERING,
                RobotEvent.STOP_EMG: RobotState.STOP_AND_OFF
            },
            RobotState.RECOVERING: {
                RobotEvent.DONE: RobotState.READY,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR
            },
            RobotState.STOP_AND_OFF: {
                RobotEvent.DONE: RobotState.CONNECTING
            },
            
            # 3. 대기 상태: 시험 배치 시작을 대기
            RobotState.READY: {
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
                RobotEvent.STOP_EMG: RobotState.STOP_AND_OFF,
                RobotEvent.START_BATCH: RobotState.TOOL_CHANGING, # 시험 배치 시작 -> 툴 확인/교체
                RobotEvent.RECOVER: RobotState.RECOVERING,
                RobotEvent.DONE: RobotState.READY, # 자체 반복 작업을 위해 DONE 이벤트 사용 가능
                RobotEvent.DISPOSE_COMPLETE: RobotState.READY # 폐기 완료 후 복귀
            },
            
            # 4. 시험 공정 시퀀스
            RobotState.TOOL_CHANGING: {
                RobotEvent.TOOL_CHANGE_COMPLETE: RobotState.READING_QR, # 툴 교체 완료 -> QR 리딩
                RobotViolation.TOOL_CHANGE_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.READING_QR: {
                RobotEvent.QR_READ_COMPLETE: RobotState.PICKING, # QR 리딩 완료 -> 픽업 (첫 번째 작업)
                RobotViolation.QR_READ_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            
            # 5. 픽업/플레이싱/정렬 루프 (두께 측정 및 장착)
            RobotState.PICKING: {
                RobotEvent.PICK_COMPLETE: RobotState.PLACING, # 픽업 완료 -> 플레이싱
                RobotViolation.GRIPPER_FAIL: RobotState.ERROR,
                RobotViolation.MOTION_VIOLATION: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.PLACING: {
                RobotEvent.PLACE_COMPLETE: RobotState.MOVING_TO_WAIT, # 플레이싱 완료 -> 다음 동작 준비 (예: 대기 위치 이동)
                # 시퀀스 내 다음 픽업이 필요한 경우: RobotEvent.PLACE_COMPLETE: RobotState.PICKING
                RobotViolation.GRIPPER_FAIL: RobotState.ERROR,
                RobotViolation.MOTION_VIOLATION: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.ALIGNING: {
                RobotEvent.ALIGN_COMPLETE: RobotState.PICKING, # 정렬 완료 -> 시편 픽업 (시험기 장착용)
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            
            # 6. 대기 및 폐기
            RobotState.MOVING_TO_WAIT: {
                RobotEvent.MOVE_COMPLETE: RobotState.READY, # 대기 장소 도착 -> Ready (시험 완료 대기)
                RobotViolation.MOTION_VIOLATION: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.DISPOSING: {
                RobotEvent.DISPOSE_COMPLETE: RobotState.READY, # 폐기 완료 -> READY (다음 시편 대기 또는 배치 종료)
                RobotViolation.MOTION_VIOLATION: RobotState.ERROR,
                RobotViolation.GRIPPER_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
        }

    def _setup_strategies(self):
        # 각 상태에 대한 전략 클래스 정의 (아래 Strategy 파일에서 구현됨)
        self._strategy_table = {
            RobotState.CONNECTING: RobotConnectingStrategy(),               
            RobotState.ERROR: RobotErrorStrategy(),                         
            RobotState.RECOVERING: RobotRecoveringStrategy(),               
            RobotState.STOP_AND_OFF: RobotStopOffStrategy(),
            RobotState.READY: RobotReadyStrategy(),                         
            
            RobotState.TOOL_CHANGING: RobotToolChangingStrategy(),
            RobotState.READING_QR: RobotReadingQRStrategy(),
            RobotState.PICKING: RobotPickingStrategy(),
            RobotState.PLACING: RobotPlacingStrategy(),
            RobotState.ALIGNING: RobotAligningStrategy(),
            RobotState.DISPOSING: RobotDisposingStrategy(),
            RobotState.MOVING_TO_WAIT: RobotMovingToWaitStrategy(),
        }