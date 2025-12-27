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
                RobotEvent.DO_AUTO_MOTION_PROGRAM_AUTO_ON: RobotState.PROGRAM_AUTO_ON, # 자동 모드 켜기
                RobotEvent.RECOVER: RobotState.RECOVERING,
            },
            
            # 4. 로봇 동작 시퀀스
            RobotState.PROGRAM_AUTO_ON: {
                RobotEvent.PROGRAM_AUTO_ON_DONE: RobotState.WAIT_AUTO_COMMAND,
            },
            RobotState.WAIT_AUTO_COMMAND: {
                RobotEvent.DO_AUTO_MOTION_PROGRAM_MANUAL_OFF: RobotState.PROGRAM_MANUAL_OFF, # 수동 모드 전환
                RobotEvent.DO_MOTION: RobotState.AUTO_MOTION_EXECUTE, # 범용 모션 실행
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_EXECUTE: {
                RobotEvent.MOTION_DONE: RobotState.WAIT_AUTO_COMMAND, # 모션 완료 -> 명령 대기
                RobotEvent.MOTION_FAIL: RobotState.ERROR,           # 모션 실패 -> 에러
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            }
        }

    def _setup_strategies(self):
        # 각 상태에 대한 전략 클래스 정의 (아래 Strategy 파일에서 구현됨)
        self._strategy_table = {
            RobotState.CONNECTING: RobotConnectingStrategy(),
            RobotState.ERROR: RobotErrorStrategy(),
            RobotState.RECOVERING: RobotRecoveringStrategy(),
            RobotState.STOP_AND_OFF: RobotStopOffStrategy(),
            RobotState.READY: RobotReadyStrategy(),

            RobotState.PROGRAM_AUTO_ON: RobotProgramAutoOnStrategy(),
            RobotState.PROGRAM_MANUAL_OFF: RobotProgramManualOffStrategy(),
            RobotState.WAIT_AUTO_COMMAND: RobotWaitAutoCommandStrategy(),
            RobotState.AUTO_MOTION_EXECUTE: RobotExecuteMotionStrategy(),
        }