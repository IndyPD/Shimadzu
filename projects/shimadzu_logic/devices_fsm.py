from .devices_strategy import *
from .constants import *


class DeviceFsm(FiniteStateMachine):
    context: DeviceContext

    # 초기 상태를 CONNECTING으로 설정 (기존 WAIT_CONNECTION 대체)
    def __init__(self, context: DeviceContext, *args, **kwargs):
        FiniteStateMachine.__init__(self, DeviceState.CONNECTING, context, *args, **kwargs)

    def _setup_rules(self):
        # DeviceState와 DeviceEvent는 devices_cnt_constants.py의 별칭입니다.
        self._rule_table = {
            # 1. 연결 상태: 장치 연결 시도 중
            DeviceState.CONNECTING: {
                DeviceEvent.CONNECTION_SUCCESS: DeviceState.READY,      # 연결 성공 -> 준비 완료
                DeviceEvent.CONNECTION_FAIL: DeviceState.ERROR,         # 연결 실패 -> 에러
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,        # 위반 감지 -> 에러
            },
            
            # 2. 에러 상태: 복구 시도 또는 비상 정지
            DeviceState.ERROR: {
                DeviceEvent.RECOVER: DeviceState.RECOVERING,            # 복구 요청 -> 복구 중
                DeviceEvent.STOP_EMG: DeviceState.STOP_AND_OFF          # 비상 정지 -> 정지/전원 차단
            },
            
            # 3. 복구 중: 복구 작업 진행 중
            DeviceState.RECOVERING: {
                DeviceEvent.DONE: DeviceState.READY,                    # 복구 완료 -> 준비 완료
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR         # 복구 중 위반 감지 -> 에러
            },
            
            # 4. 정지/전원 차단 상태
            DeviceState.STOP_AND_OFF: {
                DeviceEvent.DONE: DeviceState.CONNECTING                # 작업 완료 -> 연결 재시도
            },
            
            # 5. 준비 완료 (IDLE): 시험 대기 상태
            DeviceState.READY: {
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,        # 위반 감지 -> 에러
                DeviceEvent.STOP_EMG: DeviceState.STOP_AND_OFF,         # 비상 정지 -> 정지/전원 차단
                DeviceEvent.START_COMMAND: DeviceState.GRIPPING_SPECIMEN, # 시험 시작 명령 -> 시편 장착 시작
                DeviceEvent.RECOVER: DeviceState.RECOVERING,            # 복구 요청 (소프트 리셋) -> 복구 중
            },
            
            # 6. 시험 공정 시퀀스 (간소화된 예시)
            DeviceState.GRIPPING_SPECIMEN: {
                DeviceEvent.GRIP_CLOSE_COMPLETE: DeviceState.EXT_FORWARD, # 그립 닫기 완료 -> 신율계 전진
                DeviceViolation.GRIP_CLOSE_FAIL: DeviceState.ERROR,         # 그립 닫기 실패 -> 에러
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.EXT_FORWARD: {
                DeviceEvent.EXT_FORWARD_COMPLETE: DeviceState.PRELOADING, # 전진 완료 -> 초기 하중 제거
                DeviceViolation.EXT_MOVEMENT_FAIL: DeviceState.ERROR,       # 전진 실패 -> 에러
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.PRELOADING: {
                DeviceEvent.PRELOAD_COMPLETE: DeviceState.TESTING,      # 초기 하중 제거 완료 -> 시험 진행
                DeviceViolation.PRELOAD_FAIL: DeviceState.ERROR,            # 초기 하중 제거 실패 -> 에러
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.TESTING: {
                DeviceEvent.TEST_COMPLETE: DeviceState.EXT_BACK,        # 시험 완료 -> 신율계 후진
                DeviceViolation.TEST_RUNTIME_ERROR: DeviceState.ERROR,      # 시험 중 오류 -> 에러
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.EXT_BACK: {
                DeviceEvent.EXT_BACK_COMPLETE: DeviceState.UNGRIPPING_SPECIMEN, # 후진 완료 -> 그립 개방
                DeviceViolation.EXT_MOVEMENT_FAIL: DeviceState.ERROR,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.UNGRIPPING_SPECIMEN: {
                DeviceEvent.GRIP_OPEN_COMPLETE: DeviceState.READY,      # 그립 개방 완료 -> 준비 완료 (다음 루프)
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
        }

    def _setup_strategies(self):
        # 전략 클래스 이름도 새 상태명에 맞춰 변경되어야 합니다.
        self._strategy_table = {
            DeviceState.CONNECTING: ConnectingStrategy(),               # 기존 WaitConnectionStrategy
            DeviceState.ERROR: ErrorStrategy(),                         # 기존 ViolatedStrategy
            DeviceState.RECOVERING: RecoveringStrategy(),               
            DeviceState.STOP_AND_OFF: StopOffStrategy(),
            DeviceState.READY: ReadyStrategy(),                         # 기존 IdleStrategy
            
            # 새로운 시험 공정 전략 (임시로 ReadyStrategy 사용, 실제 구현 필요)
            DeviceState.GRIPPING_SPECIMEN: GrippingSpecimenStrategy(),
            DeviceState.PRELOADING: PreloadingStrategy(),
            DeviceState.EXT_FORWARD: ExtForwardStrategy(),
            DeviceState.TESTING: TestingStrategy(),
            DeviceState.EXT_BACK: ExtBackStrategy(),
            DeviceState.UNGRIPPING_SPECIMEN: UngrippingSpecimenStrategy(),
        }