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
                DeviceEvent.DONE: DeviceState.CONNECTING,               # 작업 완료 -> 연결 재시도
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,        # 위반 감지 -> 에러
            },
            
            # 5. 준비 완료 (IDLE): 시험 대기 상태
            DeviceState.READY: {
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,        # 위반 감지 -> 에러
                DeviceEvent.STOP_EMG: DeviceState.STOP_AND_OFF,         # 비상 정지 -> 정지/전원 차단
                DeviceEvent.START_COMMAND: DeviceState.WAIT_COMMAND,    # 준비 완료 -> 명령 대기 진입
                DeviceEvent.RECOVER: DeviceState.RECOVERING,            # 복구 요청 (소프트 리셋) -> 복구 중
            },
            
            # 6. 시험 공정 시퀀스
            DeviceState.WAIT_COMMAND: {
                DeviceEvent.DO_READ_QR: DeviceState.READ_QR,            # QR 읽기 실행
                DeviceEvent.DO_MEASURE_THICKNESS: DeviceState.MEASURE_THICKNESS,
                DeviceEvent.DO_ALIGNER_ACTION: DeviceState.ALIGNER_ACTION,
                DeviceEvent.DO_GRIPPER_GRIP: DeviceState.GRIPPER_GRIP,
                DeviceEvent.DO_GRIPPER_RELEASE: DeviceState.GRIPPER_RELEASE,
                DeviceEvent.DO_GRIPPER_1_GRIP: DeviceState.GRIPPER_1_GRIP,
                DeviceEvent.DO_GRIPPER_1_RELEASE: DeviceState.GRIPPER_1_RELEASE,
                DeviceEvent.DO_GRIPPER_2_GRIP: DeviceState.GRIPPER_2_GRIP,
                DeviceEvent.DO_GRIPPER_2_RELEASE: DeviceState.GRIPPER_2_RELEASE,
                DeviceEvent.DO_EXTENSOMETER_FORWARD: DeviceState.EXTENSOMETER_FORWARD,
                DeviceEvent.DO_EXTENSOMETER_BACKWARD: DeviceState.EXTENSOMETER_BACKWARD,
                DeviceEvent.DO_TENSILE_TEST: DeviceState.START_TENSILE_TEST,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
                DeviceEvent.DO_REGISTER_METHOD: DeviceState.REGISTER_METHOD,
                DeviceEvent.DO_ASK_PRELOAD: DeviceState.ASK_PRELOAD,
            },
            DeviceState.READ_QR: {
                DeviceEvent.QR_READ_DONE: DeviceState.WAIT_COMMAND, # 완료 -> 명령 대기
                DeviceEvent.QR_READ_FAIL: DeviceState.WAIT_COMMAND, # 실패 -> 명령 대기 (오류는 blackboard에 기록됨)
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.MEASURE_THICKNESS: {
                DeviceEvent.THICKNESS_MEASURE_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GAUGE_MEASURE_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.ALIGNER_OPEN: {
                DeviceEvent.ALIGNER_OPEN_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.ALIGNER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.ALIGNER_ACTION: {
                DeviceEvent.ALIGNER_ACTION_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.ALIGNER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_MOVE_DOWN: {
                DeviceEvent.GRIPPER_MOVE_DOWN_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_MOVE_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_GRIP: {
                DeviceEvent.GRIPPER_GRIP_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.REMOVE_PRELOAD: {
                DeviceEvent.REMOVE_PRELOAD_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.PRELOAD_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.EXTENSOMETER_FORWARD: {
                DeviceEvent.EXTENSOMETER_FORWARD_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.EXTENSOMETER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.START_TENSILE_TEST: {
                DeviceEvent.TENSILE_TEST_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.TENSILE_TEST_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.EXTENSOMETER_BACKWARD: {
                DeviceEvent.EXTENSOMETER_BACKWARD_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.EXTENSOMETER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_RELEASE: {
                DeviceEvent.GRIPPER_RELEASE_DONE: DeviceState.WAIT_COMMAND, # 풀기 완료 -> 명령 대기 (사이클 종료)
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.REGISTER_METHOD: {
                DeviceEvent.REGISTER_METHOD_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.REGISTER_METHOD_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_1_GRIP: {
                DeviceEvent.GRIPPER_1_GRIP_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_1_RELEASE: {
                DeviceEvent.GRIPPER_1_RELEASE_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_2_GRIP: {
                DeviceEvent.GRIPPER_2_GRIP_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.GRIPPER_2_RELEASE: {
                DeviceEvent.GRIPPER_2_RELEASE_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.GRIPPER_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            },
            DeviceState.ASK_PRELOAD: {
                DeviceEvent.ASK_PRELOAD_DONE: DeviceState.WAIT_COMMAND,
                DeviceEvent.ASK_PRELOAD_FAIL: DeviceState.WAIT_COMMAND,
                DeviceEvent.VIOLATION_DETECT: DeviceState.ERROR,
            }
        }

    def _setup_strategies(self):
        self._strategy_table = {
            DeviceState.CONNECTING: ConnectingStrategy(),               # 기존 WaitConnectionStrategy
            DeviceState.ERROR: ErrorStrategy(),                         # 기존 ViolatedStrategy
            DeviceState.RECOVERING: RecoveringStrategy(),               
            DeviceState.STOP_AND_OFF: StopOffStrategy(),
            DeviceState.READY: ReadyStrategy(),                         # 기존 IdleStrategy
            
            # 새로운 시험 공정 전략
            DeviceState.WAIT_COMMAND: WaitCommandStrategy(),
            DeviceState.READ_QR: ReadQRStrategy(),
            DeviceState.MEASURE_THICKNESS: MeasureThicknessStrategy(),
            DeviceState.ALIGNER_OPEN: AlignerOpenStrategy(),
            DeviceState.ALIGNER_ACTION: AlignerActionStrategy(),
            DeviceState.GRIPPER_MOVE_DOWN: GripperMoveDownStrategy(),
            DeviceState.GRIPPER_GRIP: GripperGripStrategy(),
            DeviceState.REMOVE_PRELOAD: RemovePreloadStrategy(),
            DeviceState.EXTENSOMETER_FORWARD: ExtensometerForwardStrategy(),
            DeviceState.START_TENSILE_TEST: StartTensileTestStrategy(),
            DeviceState.EXTENSOMETER_BACKWARD: ExtensometerBackwardStrategy(),
            DeviceState.GRIPPER_RELEASE: GripperReleaseStrategy(),
            DeviceState.REGISTER_METHOD: RegisterMethodStrategy(),
            DeviceState.GRIPPER_1_GRIP: Gripper1GripStrategy(),
            DeviceState.GRIPPER_1_RELEASE: Gripper1ReleaseStrategy(),
            DeviceState.GRIPPER_2_GRIP: Gripper2GripStrategy(),
            DeviceState.GRIPPER_2_RELEASE: Gripper2ReleaseStrategy(),
            DeviceState.ASK_PRELOAD: AskPreloadStrategy(),
        }