from pkg.fsm.base import *


# =======================================================
# 1. LogicState (Neuromeka 전체 제어 상태) 정의
# =======================================================
class LogicState(OpState):
    INIT = 0            # 초기화/시스템 시작
    CONNECTING = 1      # 모든 서브 모듈(Device, Robot) 연결 시도 중
    ERROR = 2           # 심각한 오류 발생 (Error State)
    IDLE = 3            # 시험 시작 대기 (READY 상태와 동일)
    RECOVERING = 4      # 복구 시도 중
    STOP_AND_OFF = 5    # 비상 정지 및 전원 차단 상태
    
    # 시험 배치(Batch) 관리 주요 상태
    PREPARING_BATCH = 6 # 초기 상태 확인 및 툴 교체 조정
    SUPPLYING_SPECIMEN = 7 # 시편 공급 모듈 관리 (QR 리딩, 두께 측정, 정렬)
    TESTING_SPECIMEN = 8 # 시험 수행 모듈 관리 (그립, 초기하중, 인장시험)
    COLLECTING_SPECIMEN = 9 # 파단 시편 회수 및 폐기 관리
    BATCH_COMPLETE = 10 # 배치 완료 및 종료 통보

# 2. LogicEvent (Neuromeka 전체 제어 이벤트) 정의
class LogicEvent(OpEvent):
    NONE = 0
    VIOLATION_DETECT = 1        # 서브 모듈(Device/Robot)로부터 위반 감지
    STOP_EMG = 2                # 비상 정지 이벤트
    DONE = 3                    # 현재 전략/작업 완료
    RECOVER = 4                 # 복구 요청 이벤트
    
    # 배치 흐름 이벤트 (Neuromeka 시퀀스)
    START_BATCH_COMMAND = 5     # 작업자로부터 시험 시작 버튼 조작
    CONNECTION_ALL_SUCCESS = 6  # 모든 서브 모듈 연결 완료
    CONNECTION_FAIL = 7         # 연결 실패
    
    PREP_COMPLETE = 8           # 배치 준비 완료 (툴 교체, 초기 상태 확인 완료)
    SUPPLY_COMPLETE = 9         # 시편 공급 및 장착 완료 (시험 직전 상태)
    TEST_COMPLETE = 10          # 인장 시험 수행 완료 (파단 후)
    COLLECT_COMPLETE = 11       # 시편 회수 및 폐기 완료
    BATCH_FINISHED = 12         # 전체 배치 프로세스 종료

# 3. LogicViolation (Neuromeka 전체 제어 위반) 정의
class LogicViolation(ViolationType):
    NONE = 0
    # 서브 모듈 위반을 집계
    DEVICE_CRITICAL_FAIL = 1 << 0    # Device(시험기/신율계) 제어 중 심각한 오류 발생
    ROBOT_CRITICAL_FAIL = 1 << 1     # Robot 제어 중 심각한 오류 발생
    BATCH_PLAN_MISSING = 1 << 2      # 배치 계획이 수립되지 않음
    ISO_EMERGENCY_BUTTON = 1 << 8
    HW_VIOLATION = 1 << 9
    HW_NOT_READY = 1 << 10

# =======================================================
# 4. DeviceState (시험기 제어 상태) 정의 - Device는 이제 Logic의 서브 모듈로 간주
# =======================================================
class DeviceState(OpState):
    INIT = 0            # 초기화/시스템 시작 (Initialization)
    CONNECTING = 1      # 장치(Shimadzu, Ext) 연결 시도 중 (Connecting)
    ERROR = 2           # 장치 또는 공정에서 심각한 오류 발생 (Error State)
    READY = 3           # 시험 시작 준비 완료 (Ready/Idle)
    
    # Device의 구체적인 상태는 Logic FSM 내부에서 이벤트로 처리 (겹치는 상태 제거)
    RECOVERING = 10         # 복구 시도 중 (Recovering)
    STOP_AND_OFF = 11       # 비상 정지 및 전원 차단 상태
    
    GRIPPING_SPECIMEN = 12  # 시편 그립 중
    EXT_FORWARD = 13        # 신율계 전진 중
    PRELOADING = 14         # 초기 하중 제거 중
    TESTING = 15            # 인장 시험 진행 중
    EXT_BACK = 16           # 신율계 후진 중
    UNGRIPPING_SPECIMEN = 17 # 시편 그립 해제 중

# 5. DeviceEvent (시험기 제어 이벤트) 정의 - Logic FSM의 서브 이벤트로 활용
class DeviceEvent(OpEvent):
    NONE = 0
    START_COMMAND = 1           # Logic에서 Device FSM에게 시험 시작 명령
    STOP_COMMAND = 2            # Logic에서 Device FSM에게 시험 중지 명령
    CONNECTION_SUCCESS = 3      # Device FSM의 연결 완료 보고
    CONNECTION_FAIL = 4         # Device FSM의 연결 실패 보고
    DEVICE_READY = 5            # Device FSM의 준비 완료 보고
    REGISTER_COMPLETE = 6       # 시험 조건 등록 완료
    GRIP_CLOSE_COMPLETE = 7     # 시험기 그립 닫기 완료
    EXT_FORWARD_COMPLETE = 8    # 신율계 전진 완료
    PRELOAD_COMPLETE = 9        # 초기 하중 제거 완료
    TEST_START_ACK = 10         # 인장 시험 시작 응답 수신
    TEST_COMPLETE = 11          # 인장 시험 결과 수신 (파단 후)
    EXT_BACK_COMPLETE = 12      # 신율계 후진 완료
    GRIP_OPEN_COMPLETE = 13     # 시험기 그립 열기 완료
    SPECIMEN_COLLECTED = 14     # 로봇이 시편 회수 완료
    DONE = 15                   # 현재 전략/작업 완료
    RECOVER = 16                # 복구 요청 이벤트
    VIOLATION_DETECT = 17       # 위반 감지 이벤트
    STOP_EMG = 18               # 비상 정지 이벤트
    # (GRIPPING_SPECIMEN 등 상태는 이제 Logic FSM 내에서 Strategy로 관리)

# 6. DeviceViolation (시험기 제어 위반) 정의 - Logic FSM으로 보고됨
class DeviceViolation(ViolationType):
    NONE = 0
    CONNECTION_TIMEOUT = 1 << 0     # 장치 연결 시도 시간 초과
    INITIAL_CHECK_FAIL = 1 << 1     # 상태 재확인(ARE_YOU_THERE) 실패
    REGISTER_FAIL = 1 << 2          # 시험 조건 등록 실패
    GRIP_CLOSE_FAIL = 1 << 3        # 시험기 그립 닫기 실패
    PRELOAD_FAIL = 1 << 4           # 초기 하중 제거 실패/오류
    TEST_START_FAIL = 1 << 5        # 인장 시험 시작 요청 실패
    EXT_MOVEMENT_FAIL = 1 << 6      # 신율계 전진/후진 명령 실패
    TEST_RUNTIME_ERROR = 1 << 7     # ANA_RESULT에 시험 중 오류 코드가 포함됨
    ISO_EMERGENCY_BUTTON = 1 << 8
    HW_VIOLATION = 1 << 9
    HW_NOT_READY = 1 << 10

# =======================================================
# 7. RobotState (로봇 제어 상태) 정의 - Robot은 Logic의 서브 모듈로 간주
# =======================================================
class RobotState(OpState):
    INIT = 0            # 초기화/시스템 시작 (Initialization)
    CONNECTING = 1      # 로봇 컨트롤러 연결 시도 중 (Connecting)
    ERROR = 2           # 로봇 동작 또는 공정에서 심각한 오류 발생 (Error State)
    READY = 3           # 작업 대기 상태 (Ready/Idle)
    RECOVERING = 4      # 복구 시도 중 (Recovering)
    STOP_AND_OFF = 5    # 비상 정지 및 전원 차단 상태
    
    TOOL_CHANGING = 6   # 툴 교체 중
    READING_QR = 7      # 트레이/시편 QR 리딩 중
    PICKING = 8         # 시편 픽업 중
    PLACING = 9         # 시편 플레이싱 중
    ALIGNING = 10       # 정렬 장치에서 정렬 동작 수행 중
    DISPOSING = 11      # 파단 시편 폐기통으로 버리는 중
    MOVING_TO_WAIT = 12 # 대기 장소로 이동 중

# 8. RobotEvent (로봇 제어 이벤트) 정의 - Logic FSM의 서브 이벤트로 활용
class RobotEvent(OpEvent):
    NONE = 0
    VIOLATION_DETECT = 1        # 위반 감지 이벤트
    STOP_EMG = 2                # 비상 정지 이벤트
    DONE = 3                    # 현재 전략/작업 완료
    RECOVER = 4                 # 복구 요청 이벤트
    CONNECTION_SUCCESS = 5      # 연결 성공
    CONNECTION_FAIL = 6         # 연결 실패
    START_BATCH = 7             # Logic에서 Robot FSM에게 시험 배치 시작 명령
    TOOL_CHECK_COMPLETE = 8     # 툴 확인 완료 (교체 필요 여부 판단)
    TOOL_CHANGE_COMPLETE = 9    # 툴 교체 완료
    QR_READ_COMPLETE = 10       # QR 리딩 완료 (메타데이터 보고 완료)
    PICK_COMPLETE = 11          # 시편 픽업 완료
    PLACE_COMPLETE = 12         # 시편 플레이싱 완료
    ALIGN_COMPLETE = 13         # 정렬 동작 수행 완료
    MOVE_COMPLETE = 14          # 대기 장소 이동 완료
    DISPOSE_COMPLETE = 15       # 파단 시편 폐기 완료

# 9. RobotViolation (로봇 제어 위반) 정의 - Logic FSM으로 보고됨
class RobotViolation(ViolationType):
    NONE = 0
    CONNECTION_TIMEOUT = 1 << 0     # 로봇 컨트롤러 통신 시간 초과
    TOOL_CHANGE_FAIL = 1 << 1       # 툴 교체 실패 (툴 미장착 등)
    QR_READ_FAIL = 1 << 2           # QR 리딩 실패 (코드 인식 불가 등)
    GRIPPER_FAIL = 1 << 3           # 그리퍼 동작 실패 (시편 놓침 등)
    MOTION_VIOLATION = 1 << 4       # 이동 중 충돌, 티칭 오류, 경로 이탈 등
    ISO_EMERGENCY_BUTTON = 1 << 8
    HW_VIOLATION = 1 << 9
    HW_NOT_READY = 1 << 10

# 10. Indy Conty 프로그램 상태 정의
class ProgramState(IntEnum):
    PROG_IDLE = 0
    PROG_RUNNING = 1
    PROG_PAUSING = 2
    PROG_STOPPING = 3

# 11. Indy opstate 정의 
class DigitalState(IntEnum):
    OFF_STATE = 0
    ON_STATE = 1
    UNUSED_STATE = 2

# 12. Indy Conty 프로그램 제어 명령 정의
class ProgramControl(IntEnum):
    PROG_IDLE = 0
    PROG_START = 1
    PROG_RESUME = 2
    PROG_PAUSE = 3
    PROG_STOP = 4

class Robot_OP_State(IntEnum):
    # Indy's FSM state
    OP_SYSTEM_OFF = 0
    OP_SYSTEM_ON = 1
    OP_VIOLATE = 2
    OP_RECOVER_HARD = 3
    OP_RECOVER_SOFT = 4
    OP_IDLE = 5
    OP_MOVING = 6
    OP_TEACHING = 7
    OP_COLLISION = 8
    OP_STOP_AND_OFF = 9
    OP_COMPLIANCE = 10
    OP_BRAKE_CONTROL = 11
    OP_SYSTEM_RESET = 12
    OP_SYSTEM_SWITCH = 13
    OP_VIOLATE_HARD = 15
    OP_MANUAL_RECOVER = 16
    TELE_OP = 17

# 13. Remote IO DI (Digital Input) 신호 정의
class DigitalInput(Enum):
    """
    PLC DI (Digital Input) 신호 목록
    address는 이미지의 address - 1 값입니다.
    """
    AUTO_MANUAL_SELECT_SW = 0
    RESET_SW = 1
    # address 3은 비어있음
    SOL_SENSOR = 3
    BCR_OK = 4
    BCR_ERROR = 5
    BUSY = 6
    # address 8은 비어있음
    ENO_01_SW = 8
    EMO_02_SI = 9
    EMO_03_SI = 10
    EMO_04_SI = 11
    DOOR_1_OPEN = 12
    DOOR_2_OPEN = 13
    DOOR_3_OPEN = 14
    DOOR_4_OPEN = 15
    GRIPPER_1_CLAMP = 16
    # address 18은 비어있음
    GRIPPER_2_CLAMP = 18
    # address 20은 비어있음
    EXT_FW_SENSOR = 20
    EXT_BW_SENSOR = 21
    # address 23~24는 비어있음
    INDICATOR_GUIDE_DOWN = 24
    INDICATOR_GUIDE_UP = 25
    ALIGN_1_PUSH = 26
    ALIGN_1_PULL = 27
    ALIGN_2_PUSH = 28
    ALIGN_2_PULL = 29
    ALIGN_3_PUSH = 30
    ALIGN_3_PULL = 31
    ATC_1_1_SENSOR = 32
    ATC_1_2_SENSOR = 33
    SCRAPBOX_SENSOR = 34
    ATC_2_1_SENSOR = 35
    ATC_2_2_SENSOR = 36

# 14. Remote IO DO (Digital Output) 신호 정의
class DigitalOutput(Enum):
    """
    PLC DO (Digital Output) 신호 목록
    address는 이미지의 address - 1 값입니다.
    """
    TOWER_LAMP_RED = 0
    TOWER_LAMP_GREEN = 1
    TOWER_LAMP_YELLOW = 2
    TOWER_BUZZER = 3
    # address 5는 비어있음
    BCR_TGR = 5
    LOCAL_LAMP_R = 6
    # address 8은 비어있음
    RESET_SW_LAMP = 8
    DOOR_4_LAMP = 9
    # address 11~14는 비어있음
    INDICATOR_UP = 14
    INDICATOR_DOWN = 15
    ALIGN_1_PUSH = 16
    ALIGN_1_PULL = 17
    ALIGN_2_PUSH = 18
    ALIGN_2_PULL = 19
    ALIGN_3_PUSH = 20
    ALIGN_3_PULL = 21
    GRIPPER_1_UNCLAMP = 22
    LOCAL_LAMP_L = 23
    GRIPPER_2_UNCLAMP = 24
    LOCAL_LAMP_C = 25
    EXT_FW = 26
    EXT_BW = 27