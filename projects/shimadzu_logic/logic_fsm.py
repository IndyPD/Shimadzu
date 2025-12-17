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
                LogicEvent.START_BATCH_COMMAND: LogicState.PREPARING_BATCH, # 시험 시작 명령 -> 준비
                LogicEvent.RECOVER: LogicState.RECOVERING,
            },
            
            # 4. 시험 배치 시퀀스
            LogicState.PREPARING_BATCH: {
                LogicEvent.PREP_COMPLETE: LogicState.SUPPLYING_SPECIMEN, # 준비 완료 -> 시편 공급
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.SUPPLYING_SPECIMEN: {
                LogicEvent.SUPPLY_COMPLETE: LogicState.TESTING_SPECIMEN, # 공급 완료 -> 시험 시작
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.TESTING_SPECIMEN: {
                LogicEvent.TEST_COMPLETE: LogicState.COLLECTING_SPECIMEN, # 시험 완료 -> 시편 회수
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            LogicState.COLLECTING_SPECIMEN: {
                LogicEvent.COLLECT_COMPLETE: LogicState.BATCH_COMPLETE, # 회수 완료 -> 배치 완료 처리
                LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
            },
            
            # 5. 종료 및 루프
            LogicState.BATCH_COMPLETE: {
                LogicEvent.START_BATCH_COMMAND: LogicState.PREPARING_BATCH, # 다음 시편이 있다면 루프
                LogicEvent.BATCH_FINISHED: LogicState.IDLE, # 전체 배치 종료 -> IDLE
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
            
            LogicState.PREPARING_BATCH: LogicPreparingBatchStrategy(),
            LogicState.SUPPLYING_SPECIMEN: LogicSupplyingSpecimenStrategy(),
            LogicState.TESTING_SPECIMEN: LogicTestingSpecimenStrategy(),
            LogicState.COLLECTING_SPECIMEN: LogicCollectingSpecimenStrategy(),
            LogicState.BATCH_COMPLETE: LogicBatchCompleteStrategy(),
        }