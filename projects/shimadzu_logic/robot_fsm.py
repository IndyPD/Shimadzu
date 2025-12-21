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
                RobotEvent.PROGRAM_AUTO_ON_DONE: RobotState.PROGRAM_AUTO_ON, # 자동 모드 켜기
                RobotEvent.RECOVER: RobotState.RECOVERING,
            },
            
            # 4. 로봇 동작 시퀀스
            RobotState.PROGRAM_AUTO_ON: {
                RobotEvent.PROGRAM_AUTO_ON_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.WAIT_AUTO_COMMAND: {
                RobotEvent.DO_AUTO_MOTION_PROGRAM_MANUAL_OFF: RobotState.PROGRAM_MANUAL_OFF,
                RobotEvent.DO_AUTO_MOTION_TOOL_CHANGE: RobotState.AUTO_MOTION_TOOL_CHANGE,
                RobotEvent.DO_AUTO_MOTION_MOVE_HOME: RobotState.AUTO_MOTION_MOVE_HOME,
                RobotEvent.DO_AUTO_MOTION_APPROACH_RACK: RobotState.AUTO_MOTION_APPROACH_RACK,
                RobotEvent.DO_AUTO_GRIPPER_OPEN: RobotState.AUTO_GRIPPER_OPEN,
                RobotEvent.DO_AUTO_GRIPPER_CLOSE: RobotState.AUTO_GRIPPER_CLOSE,
                RobotEvent.DO_AUTO_MOTION_MOVE_TO_QR: RobotState.AUTO_MOTION_MOVE_TO_QR,
                RobotEvent.DO_AUTO_MOTION_APPROACH_PICK: RobotState.AUTO_MOTION_APPROACH_PICK,
                RobotEvent.DO_AUTO_MOTION_PICK_SPECIMEN: RobotState.AUTO_MOTION_PICK_SPECIMEN,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_TRAY: RobotState.AUTO_MOTION_RETRACT_FROM_TRAY,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_RACK: RobotState.AUTO_MOTION_RETRACT_FROM_RACK,
                RobotEvent.DO_AUTO_MOTION_APPROACH_THICKNESS: RobotState.AUTO_MOTION_APPROACH_THICKNESS,
                RobotEvent.DO_AUTO_MOTION_ENTER_THICKNESS_POS_1: RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_1,
                RobotEvent.DO_AUTO_MOTION_ENTER_THICKNESS_POS_2: RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_2,
                RobotEvent.DO_AUTO_MOTION_ENTER_THICKNESS_POS_3: RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_3,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_THICKNESS: RobotState.AUTO_MOTION_RETRACT_FROM_THICKNESS,
                RobotEvent.DO_AUTO_MOTION_APPROACH_ALIGNER: RobotState.AUTO_MOTION_APPROACH_ALIGNER,
                RobotEvent.DO_AUTO_MOTION_ENTER_ALIGNER: RobotState.AUTO_MOTION_ENTER_ALIGNER,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_ALIGNER: RobotState.AUTO_MOTION_RETRACT_FROM_ALIGNER,
                RobotEvent.DO_AUTO_MOTION_APPROACH_TENSILE: RobotState.AUTO_MOTION_APPROACH_TENSILE,
                RobotEvent.DO_AUTO_MOTION_ENTER_TENSILE: RobotState.AUTO_MOTION_ENTER_TENSILE,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_TENSILE: RobotState.AUTO_MOTION_RETRACT_FROM_TENSILE,
                RobotEvent.DO_AUTO_MOTION_APPROACH_SCRAP: RobotState.AUTO_MOTION_APPROACH_SCRAP,
                RobotEvent.DO_AUTO_MOTION_ENTER_SCRAP: RobotState.AUTO_MOTION_ENTER_SCRAP,
                RobotEvent.DO_AUTO_MOTION_RETRACT_FROM_SCRAP: RobotState.AUTO_MOTION_RETRACT_FROM_SCRAP,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.PROGRAM_MANUAL_OFF: {
                RobotEvent.PROGRAM_MANUAL_OFF_DONE: RobotState.READY,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_MOVE_HOME: {
                RobotEvent.AUTO_MOTION_MOVE_HOME_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_TOOL_CHANGE: {
                RobotEvent.AUTO_MOTION_TOOL_CHANGE_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotViolation.TOOL_CHANGE_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_RACK: {
                RobotEvent.AUTO_MOTION_APPROACH_RACK_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_GRIPPER_OPEN: {
                RobotEvent.AUTO_GRIPPER_OPEN_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_GRIPPER_CLOSE: {
                RobotEvent.AUTO_GRIPPER_CLOSE_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_MOVE_TO_QR: {
                RobotEvent.AUTO_MOTION_MOVE_TO_QR_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotViolation.QR_READ_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_PICK: {
                RobotEvent.AUTO_MOTION_APPROACH_PICK_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_PICK_SPECIMEN: {
                RobotEvent.AUTO_MOTION_PICK_SPECIMEN_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotViolation.GRIPPER_FAIL: RobotState.ERROR,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_TRAY: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_TRAY_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_RACK: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_RACK_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_THICKNESS: {
                RobotEvent.AUTO_MOTION_APPROACH_THICKNESS_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_1: {
                RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_1_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_2: {
                RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_2_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_3: {
                RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_3_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_THICKNESS: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_THICKNESS_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_ALIGNER: {
                RobotEvent.AUTO_MOTION_APPROACH_ALIGNER_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_ALIGNER: {
                RobotEvent.AUTO_MOTION_ENTER_ALIGNER_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_ALIGNER: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_ALIGNER_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_TENSILE: {
                RobotEvent.AUTO_MOTION_APPROACH_TENSILE_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_TENSILE: {
                RobotEvent.AUTO_MOTION_ENTER_TENSILE_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_TENSILE: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_TENSILE_DONE: RobotState.WAIT_AUTO_COMMAND, # 시험 후 스크랩 이동
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_APPROACH_SCRAP: {
                RobotEvent.AUTO_MOTION_APPROACH_SCRAP_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_ENTER_SCRAP: {
                RobotEvent.AUTO_MOTION_ENTER_SCRAP_DONE: RobotState.WAIT_AUTO_COMMAND,
                RobotEvent.VIOLATION_DETECT: RobotState.ERROR,
            },
            RobotState.AUTO_MOTION_RETRACT_FROM_SCRAP: {
                RobotEvent.AUTO_MOTION_RETRACT_FROM_SCRAP_DONE: RobotState.WAIT_AUTO_COMMAND, # 사이클 완료 후 대기
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
            
            RobotState.PROGRAM_AUTO_ON: RobotProgramAutoOnStrategy(),
            RobotState.PROGRAM_MANUAL_OFF: RobotProgramManualOffStrategy(),
            RobotState.WAIT_AUTO_COMMAND: RobotWaitAutoCommandStrategy(),
            RobotState.AUTO_MOTION_MOVE_HOME: RobotMoveHomeStrategy(),
            RobotState.AUTO_MOTION_TOOL_CHANGE: RobotToolChangeStrategy(),
            RobotState.AUTO_MOTION_APPROACH_RACK: RobotApproachRackStrategy(),
            RobotState.AUTO_GRIPPER_OPEN: RobotAutoGripperOpenStrategy(),
            RobotState.AUTO_GRIPPER_CLOSE: RobotAutoGripperCloseStrategy(),
            RobotState.AUTO_MOTION_MOVE_TO_QR: RobotMoveToQRStrategy(),
            RobotState.AUTO_MOTION_APPROACH_PICK: RobotApproachPickStrategy(),
            RobotState.AUTO_MOTION_PICK_SPECIMEN: RobotPickSpecimenStrategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_TRAY: RobotRetractFromTrayStrategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_RACK: RobotRetractFromRackStrategy(),
            RobotState.AUTO_MOTION_APPROACH_THICKNESS: RobotApproachThicknessStrategy(),
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_1: RobotEnterThicknessPos1Strategy(),
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_2: RobotEnterThicknessPos2Strategy(),
            RobotState.AUTO_MOTION_ENTER_THICKNESS_POS_3: RobotEnterThicknessPos3Strategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_THICKNESS: RobotRetractFromThicknessStrategy(),
            RobotState.AUTO_MOTION_APPROACH_ALIGNER: RobotApproachAlignerStrategy(),
            RobotState.AUTO_MOTION_ENTER_ALIGNER: RobotEnterAlignerStrategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_ALIGNER: RobotRetractFromAlignerStrategy(),
            RobotState.AUTO_MOTION_APPROACH_TENSILE: RobotApproachTensileStrategy(),
            RobotState.AUTO_MOTION_ENTER_TENSILE: RobotEnterTensileStrategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_TENSILE: RobotRetractFromTensileStrategy(),
            RobotState.AUTO_MOTION_APPROACH_SCRAP: RobotApproachScrapStrategy(),
            RobotState.AUTO_MOTION_ENTER_SCRAP: RobotEnterScrapStrategy(),
            RobotState.AUTO_MOTION_RETRACT_FROM_SCRAP: RobotRetractFromScrapStrategy(),
        }