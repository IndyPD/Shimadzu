from .logic_strategy import *
from .constants import *

class LogicFSM(FiniteStateMachine):
    context: LogicContext

    def __init__(self, context: LogicContext, *args, **kwargs):
        FiniteStateMachine.__init__(self, LogicState.CONNECTING, context, *args, **kwargs)

    def _setup_rules(self):
        self._rule_table = {
            # 1. 초기화 및 연결
            LogicState.CONNECTING: {
                LogicEvent.CONNECTION_ALL_SUCCESS: LogicState.IDLE,
                LogicEvent.CONNECTION_FAIL: LogicState.ERROR,
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            
            # 2. 에러 및 복구
            LogicState.ERROR: {
                LogicEvent.RECOVER: LogicState.RECOVERING,
                LogicEvent.STOP_EMG: LogicState.STOP_AND_OFF
            },
            LogicState.RECOVERING: {
                LogicEvent.DONE: LogicState.IDLE,
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR
            },
            LogicState.STOP_AND_OFF: {
                LogicEvent.DONE: LogicState.CONNECTING
            },
            
            # 3. 대기 상태 (IDLE)
            LogicState.IDLE: {
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
                LogicEvent.STOP_EMG: LogicState.STOP_AND_OFF,
                LogicEvent.START_AUTO_COMMAND: LogicState.WAIT_COMMAND, # 자동화 모드 진입
                LogicEvent.RECOVER: LogicState.RECOVERING,
            },
            
            # 4. 시험 배치 시퀀스 (새로운 상태 반영)
            LogicState.WAIT_COMMAND: {
                LogicEvent.START_AUTO_COMMAND: LogicState.REGISTER_PROCESS_INFO, # 명령 수신 -> 정보 등록
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.REGISTER_PROCESS_INFO: {
                LogicEvent.REGISTRATION_DONE: LogicState.CHECK_DEVICE_STATUS, # 등록 완료 -> 상태 확인
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.CHECK_DEVICE_STATUS: {
                LogicEvent.STATUS_CHECK_DONE: LogicState.WAIT_PROCESS, # 확인 완료 -> 공정 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.WAIT_PROCESS: {
                LogicEvent.PROCESS_START: LogicState.RUN_PROCESS, # 공정 시작 -> 실행
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.RUN_PROCESS: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK, # 공정 시작 -> 작업 판단
                LogicEvent.PROCESS_STOP: LogicState.WAIT_COMMAND, # 정지 -> 명령 대기
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.DETERMINE_TASK: {
                LogicEvent.DO_PICK_SPECIMEN: LogicState.PICK_SPECIMEN,
                LogicEvent.DO_MEASURE_THICKNESS: LogicState.MEASURE_THICKNESS,
                LogicEvent.DO_ALIGN_SPECIMEN: LogicState.ALIGN_SPECIMEN,
                LogicEvent.DO_LOAD_TENSILE_MACHINE: LogicState.LOAD_TENSILE_MACHINE,
                LogicEvent.DO_START_TENSILE_TEST: LogicState.START_TENSILE_TEST,
                LogicEvent.DO_COLLECT_AND_DISCARD: LogicState.COLLECT_AND_DISCARD,
                LogicEvent.DO_PROCESS_COMPLETE: LogicState.PROCESS_COMPLETE,                
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.PICK_SPECIMEN: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.MEASURE_THICKNESS: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.ALIGN_SPECIMEN: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.LOAD_TENSILE_MACHINE: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.START_TENSILE_TEST: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.COLLECT_AND_DISCARD: {
                LogicEvent.DONE: LogicState.DETERMINE_TASK,
                LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.PROCESS_COMPLETE: {
                LogicEvent.DONE: LogicState.WAIT_COMMAND, # 완료 처리 후 -> 명령 대기 (다음 배치)
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
        }

    def _setup_strategies(self):
        self._strategy_table = {
            LogicState.CONNECTING: LogicConnectingStrategy(),               
            LogicState.ERROR: LogicErrorStrategy(),                         
            LogicState.RECOVERING: LogicRecoveringStrategy(),               
            LogicState.STOP_AND_OFF: LogicStopOffStrategy(),
            LogicState.IDLE: LogicIdleStrategy(),                         
            
            LogicState.WAIT_COMMAND: LogicWaitCommandStrategy(),
            LogicState.REGISTER_PROCESS_INFO: LogicRegisterProcessInfoStrategy(),
            LogicState.CHECK_DEVICE_STATUS: LogicCheckDeviceStatusStrategy(),
            LogicState.WAIT_PROCESS: LogicWaitProcessStrategy(),
            LogicState.RUN_PROCESS: LogicRunProcessStrategy(),
            LogicState.DETERMINE_TASK: LogicDetermineTaskStrategy(),
            LogicState.PICK_SPECIMEN: LogicPickSpecimenStrategy(),
            LogicState.MEASURE_THICKNESS: LogicMeasureThicknessStrategy(),
            LogicState.ALIGN_SPECIMEN: LogicAlignSpecimenStrategy(),
            LogicState.LOAD_TENSILE_MACHINE: LogicLoadTensileMachineStrategy(),
            LogicState.START_TENSILE_TEST: LogicStartTensileTestStrategy(),
            LogicState.COLLECT_AND_DISCARD: LogicCollectAndDiscardStrategy(),
            LogicState.PROCESS_COMPLETE: LogicProcessCompleteStrategy(),
        }