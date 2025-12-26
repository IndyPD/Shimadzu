from pkg.fsm.base import *
from datetime import datetime
import inspect
import threading

def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class IndyState(OpState):
    SYSTEM_OFF                          = 0
    SYSTEM_ON                           = 1
    VIOLATE                             = 2
    RECOVER_HARD                        = 3
    RECOVER_SOFT                        = 4
    IDLE                                = 5
    MOVING                              = 6
    TEACHING                            = 7
    COLLISION                           = 8
    STOP_AND_OFF                        = 9
    COMPLIANCE                          = 10
    BRAKE_CONTROL                       = 11
    SYSTEM_RESET                        = 12
    SYSTEM_SWITCH                       = 13
    VIOLATE_HARD                        = 15
    MANUAL_RECOVER                      = 16
    TELE_OP                             = 17


# =======================================================
# 1. LogicState (Neuromeka 전체 제어 상태) 정의
# =======================================================
class LogicState(OpState):
    INIT                                = 0             # 초기화/시스템 시작
    CONNECTING                          = 1             # 모든 서브 모듈(Device, Robot) 연결 시도 중
    ERROR                               = 2             # 심각한 오류 발생 (Error State)
    IDLE                                = 3             # 시험 시작 대기 (READY 상태와 동일)
    RECOVERING                          = 4             # 복구 시도 중
    STOP_AND_OFF                        = 5             # 비상 정지 및 전원 차단 상태
    
    # 시험 배치(Batch) 관리 주요 상태
    WAIT_COMMAND                        = 6             # 1. 명령 대기
    REGISTER_PROCESS_INFO               = 7             # 2. 공정 정보 등록
    CHECK_DEVICE_STATUS                 = 8             # 3. 장비 상태 확인
    WAIT_PROCESS                        = 9             # 4. 자동화 공정 대기
    RUN_PROCESS                         = 10            # 5. 자동화 공정 실행
    DETERMINE_TASK                      = 11            # 6. 작업 내용 판단
    MOVE_TO_RACK_FOR_QR                 = 12            # 7. QR 리딩을 위한 랙 이동
    PICK_SPECIMEN                       = 13            # 8. 시편 잡기 (A)
    MOVE_TO_INDIGATOR                   = 14            # 9. 측정기 이동 (B)
    PLACE_SPECIMEN_AND_MEASURE          = 15            # 10. 시편 거치 및 측정 (B)
    PICK_SPECIMEN_OUT_FROM_INDIGATOR    = 16            # 11. 측정기에서 시편 반출 (B)
    ALIGN_SPECIMEN                      = 17            # 12. 시편 정렬 (C)
    PICK_SPECIMEN_OUT_FROM_ALIGN        = 24            # 12-1. 정렬기에서 시편 반출 (C)
    LOAD_TENSILE_MACHINE                = 18            # 13. 인장기 장착 (D)
    RETREAT_TENSILE_MACHINE             = 19            # 14. 인장기 후퇴 (D)
    START_TENSILE_TEST                  = 20            # 15. 인장 시험 시작 (D)
    PICK_TENSILE_MACHINE                = 21            # 16. 인장기 시편 수거 (D)
    RETREAT_AND_HANDLE_SCRAP            = 22            # 17. 후퇴 및 스크랩 처리 (D)    
    PROCESS_COMPLETE                    = 23            # 18. 공정 완료    
    RESET_DATA                          = 25            # 19. 데이터 리셋
    

    
# 2. LogicEvent (Neuromeka 전체 제어 이벤트) 정의
class LogicEvent(OpEvent):
    NONE                                = 0
    VIOLATION_DETECT                    = 1             # 서브 모듈(Device/Robot)로부터 위반 감지
    STOP_EMG                            = 2             # 비상 정지 이벤트
    DONE                                = 3             # 현재 전략/작업 완료
    RECOVER                             = 4             # 복구 요청 이벤트
    
    # LogicState 기반 이벤트
    START_AUTO_COMMAND                  = 5             # 자동화 공정 시작 명령
    REGISTRATION_DONE                   = 6             # 공정 정보 등록 완료
    STATUS_CHECK_DONE                   = 7             # 장비 상태 확인 완료
    PROCESS_START                       = 8             # 자동화 공정 시작
    PROCESS_STOP                        = 9             # 공정 정지 (현재 모션 완료 후 정지)
    PROCESS_STEP_STOP                   = 10            # 공정 단계 정지 (현재 공정 완료 후 정지)
    PROCESS_PAUSE                       = 11            # 공정 일시 정지
    PROCESS_FINISHED                    = 12            # 자동화 공정 완료
    
    # 연결 상태 이벤트
    CONNECTION_ALL_SUCCESS              = 13            # 모든 모듈 연결 성공
    CONNECTION_FAIL                     = 14            # 연결 실패
    
    # 명령 실행 이벤트 (DO_Command)
    DO_START_AUTO                       = 20            # 자동화 공정 시작 실행
    DO_REGISTER_INFO                    = 21            # 공정 정보 등록 실행
    DO_CHECK_STATUS                     = 22            # 장비 상태 확인 실행
    DO_RUN_PROCESS                      = 23            # 공정 실행
    DO_STOP                             = 24            # 정지 실행
    DO_PAUSE                            = 25            # 일시 정지 실행
    DO_STEP_STOP                        = 26            # 단계 정지 실행
    DO_DETERMINE_TASK                   = 27            # 작업 내용 판단 실행
    DO_MOVE_TO_RACK_FOR_QR              = 28            # QR 리딩을 위한 랙 이동 실행
    DO_PICK_SPECIMEN                    = 29            # 시편 잡고 나오기 실행
    DO_MOVE_TO_INDIGATOR                = 30            # 측정기 이동 실행
    DO_PLACE_SPECIMEN_AND_MEASURE       = 31            # 시편 거치 및 측정 실행
    DO_PICK_SPECIMEN_OUT_FROM_INDIGATOR = 32            # 측정기 시편 반출 실행
    DO_ALIGN_SPECIMEN                   = 33            # 시편 정렬 실행
    DO_PICK_SPECIMEN_OUT_FROM_ALIGN     = 41            # 정렬기 시편 반출 실행
    DO_LOAD_TENSILE_MACHINE             = 34            # 인장기 장착 실행
    DO_RETREAT_TENSILE_MACHINE          = 35            # 인장기 후퇴 실행
    DO_START_TENSILE_TEST               = 36            # 인장 시험 시작 실행
    DO_PICK_TENSILE_MACHINE             = 37            # 인장기 시편 수거 실행
    DO_RETREAT_AND_HANDLE_SCRAP         = 38            # 후퇴 및 스크랩 처리 실행
    DO_PROCESS_COMPLETE                 = 39            # 공정 완료 실행
    DO_DATA_RESET                       = 40            # 데이터 리셋 실행
    

# 3. LogicViolation (Neuromeka 전체 제어 위반) 정의
class LogicViolation(ViolationType):
    NONE                                = 0
    # 서브 모듈 위반을 집계
    DEVICE_CRITICAL_FAIL                = 1 << 0        # Device(시험기/신율계) 제어 중 심각한 오류 발생
    ROBOT_CRITICAL_FAIL                 = 1 << 1        # Robot 제어 중 심각한 오류 발생
    BATCH_PLAN_MISSING                  = 1 << 2        # 배치 계획이 수립되지 않음
    ISO_EMERGENCY_BUTTON                = 1 << 8
    HW_VIOLATION                        = 1 << 9
    HW_NOT_READY                        = 1 << 10

# =======================================================
# 4. DeviceState (시험기 제어 상태) 정의 - Device는 이제 Logic의 서브 모듈로 간주
# =======================================================
class DeviceState(OpState):
    INIT                                = 0             # 초기화/시스템 시작 (Initialization)
    CONNECTING                          = 1             # 장치(Shimadzu, Ext) 연결 시도 중 (Connecting)
    ERROR                               = 2             # 장치 또는 공정에서 심각한 오류 발생 (Error State)
    READY                               = 3             # 시험 시작 준비 완료 (Ready/Idle)
    
    # Device의 구체적인 상태는 Logic FSM 내부에서 이벤트로 처리 (겹치는 상태 제거)
    RECOVERING                          = 10            # 복구 시도 중 (Recovering)
    STOP_AND_OFF                        = 11            # 비상 정지 및 전원 차단 상태
    
    WAIT_COMMAND                        = 12            # 명령 대기
    READ_QR                             = 13            # QR 읽기
    MEASURE_THICKNESS                   = 14            # 두께 측정
    ALIGNER_OPEN                        = 15            # 정렬기 벌리기
    ALIGNER_ACTION                      = 16            # 정렬기 작동
    GRIPPER_MOVE_DOWN                   = 17            # 인장기 그리퍼 아래로 이동
    GRIPPER_GRIP                        = 18            # 인장기 그리퍼 잡기
    GRIPPER_RELEASE                     = 19            # 인장기 그리퍼 풀기
    REMOVE_PRELOAD                      = 20            # 초기 하중 제거
    EXTENSOMETER_FORWARD                = 21            # 신율계 전진
    EXTENSOMETER_BACKWARD               = 22            # 신율계 후진
    START_TENSILE_TEST                  = 23            # 인장시험 시작



# 5. DeviceEvent (시험기 제어 이벤트) 정의 - Logic FSM의 서브 이벤트로 활용
class DeviceEvent(OpEvent):
    NONE                                = 0
    VIOLATION_DETECT                    = 1             # 위반 감지 (System Violation)
    STOP_EMG                            = 2             # 비상 정지
    DONE                                = 3             # 작업 완료
    RECOVER                             = 4             # 복구 요청
    
    START_COMMAND                       = 5             # Logic에서 Device FSM에게 시험 시작 명령
    STOP_COMMAND                        = 6             # Logic에서 Device FSM에게 시험 중지 명령
    CONNECTION_SUCCESS                  = 7             # Device FSM의 연결 완료 보고
    CONNECTION_FAIL                     = 8             # Device FSM의 연결 실패 보고
    DEVICE_READY                        = 9             # Device FSM의 준비 완료 보고
    
    QR_READ_DONE                        = 10            # QR 읽기 완료
    THICKNESS_MEASURE_DONE              = 11            # 두께 측정 완료
    ALIGNER_OPEN_DONE                   = 12            # 정렬기 벌리기 완료
    ALIGNER_ACTION_DONE                 = 13            # 정렬기 작동 완료
    GRIPPER_MOVE_DOWN_DONE              = 14            # 인장기 그리퍼 아래로 이동 완료
    GRIPPER_GRIP_DONE                   = 15            # 인장기 그리퍼 잡기 완료
    GRIPPER_RELEASE_DONE                = 16            # 인장기 그리퍼 풀기 완료
    REMOVE_PRELOAD_DONE                 = 17            # 초기 하중 제거 완료
    EXTENSOMETER_FORWARD_DONE           = 18            # 신율계 전진 완료
    EXTENSOMETER_BACKWARD_DONE          = 19            # 신율계 후진 완료
    TENSILE_TEST_DONE                   = 20            # 인장시험 완료
    
    # 장비별 에러 상황 이벤트
    QR_READ_FAIL                        = 21            # QR 읽기 실패
    GAUGE_MEASURE_FAIL                  = 22            # 게이지 측정 실패
    ALIGNER_FAIL                        = 23            # 정렬기 동작 실패
    GRIPPER_FAIL                        = 24            # 인장기 그리퍼 동작 실패
    GRIPPER_MOVE_FAIL                   = 25            # 인장기 이동 실패
    EXTENSOMETER_FAIL                   = 26            # 신율계 동작 실패
    TENSILE_TEST_FAIL                   = 27            # 인장시험 명령 실패
    PRELOAD_FAIL                        = 28            # 초기 하중 제거 실패
    
    # 명령 실행 이벤트 (DO_Command)
    DO_READ_QR                          = 30            # QR 읽기 실행
    DO_MEASURE_THICKNESS                = 31            # 두께 측정 실행
    DO_ALIGNER_OPEN                     = 32            # 정렬기 벌리기 실행
    DO_ALIGNER_ACTION                   = 33            # 정렬기 작동 실행
    DO_GRIPPER_MOVE_DOWN                = 34            # 인장기 그리퍼 하강 실행
    DO_GRIPPER_GRIP                     = 35            # 인장기 그리퍼 잡기 실행
    DO_GRIPPER_RELEASE                  = 36            # 인장기 그리퍼 풀기 실행
    DO_REMOVE_PRELOAD                   = 37            # 초기 하중 제거 실행
    DO_EXTENSOMETER_FORWARD             = 38            # 신율계 전진 실행
    DO_EXTENSOMETER_BACKWARD            = 39            # 신율계 후진 실행
    DO_TENSILE_TEST                     = 40            # 인장시험 실행

# 6. DeviceViolation (시험기 제어 위반) 정의 - Logic FSM으로 보고됨
class DeviceViolation(ViolationType):
    NONE                                = 0
    CONNECTION_TIMEOUT                  = 1 << 0        # 장치 연결 시도 시간 초과
    INITIAL_CHECK_FAIL                  = 1 << 1        # 상태 재확인(ARE_YOU_THERE) 실패
    REGISTER_FAIL                       = 1 << 2        # 시험 조건 등록 실패
    GRIP_CLOSE_FAIL                     = 1 << 3        # 시험기 그립 닫기 실패
    PRELOAD_FAIL                        = 1 << 4        # 초기 하중 제거 실패/오류
    TEST_START_FAIL                     = 1 << 5        # 인장 시험 시작 요청 실패
    EXT_MOVEMENT_FAIL                   = 1 << 6        # 신율계 전진/후진 명령 실패
    TEST_RUNTIME_ERROR                  = 1 << 7        # ANA_RESULT에 시험 중 오류 코드가 포함됨
    ISO_EMERGENCY_BUTTON                = 1 << 8
    HW_VIOLATION                        = 1 << 9
    HW_NOT_READY                        = 1 << 10

# =======================================================
# 7. RobotState (로봇 제어 상태) 정의 - Robot은 Logic의 서브 모듈로 간주
# =======================================================
class RobotState(OpState):
    INIT                                = 0             # 초기화/시스템 시작 (Initialization)
    CONNECTING                          = 1             # 로봇 컨트롤러 연결 시도 중 (Connecting)
    ERROR                               = 2             # 로봇 동작 또는 공정에서 심각한 오류 발생 (Error State)
    READY                               = 3             # 작업 대기 상태 (Ready/Idle)
    RECOVERING                          = 4             # 복구 시도 중 (Recovering)
    STOP_AND_OFF                        = 5             # 비상 정지 및 전원 차단 상태
    
    MANUAL_GRIPPER_OPEN                 = 6             # 수동 그리퍼 열기
    MANUAL_GRIPPER_CLOSE                = 7             # 수동 그리퍼 닫기

    PROGRAM_AUTO_ON                     = 8             # 로봇 프로그램 켜기(자동모드)
    PROGRAM_MANUAL_OFF                  = 9             # 로봇 프로그램 끄기(수동모드)
    
    AUTO_MOTION_TOOL_CHANGE             = 10            # 툴 교체
    AUTO_MOTION_MOVE_HOME               = 11            # 홈 위치 이동
    AUTO_MOTION_APPROACH_RACK           = 12            # 렉 앞 접근
    AUTO_GRIPPER_OPEN                   = 13            # 로봇 그리퍼 열기
    AUTO_GRIPPER_CLOSE                  = 14            # 로봇 그리퍼 닫기
    AUTO_MOTION_MOVE_TO_QR              = 15            # 렉 작업 대상 층 Tray QR 인식 위치 이동
    AUTO_MOTION_APPROACH_PICK           = 16            # 렉 작업 대상 층 Tray 시편 잡는 위치 앞 이동
    AUTO_MOTION_PICK_SPECIMEN           = 17            # 렉 작업 대상 층 Tray 내 시편 잡기
    AUTO_MOTION_RETRACT_FROM_TRAY       = 18            # 렉 작업 대상 층 Tray 앞 후퇴
    AUTO_MOTION_RETRACT_FROM_RACK       = 19            # 렉 앞 후퇴
    AUTO_MOTION_APPROACH_THICKNESS      = 20            # 두께측정기 앞 이동
    AUTO_MOTION_ENTER_THICKNESS_POS_1   = 21            # 두께측정기 1번 위치 진입
    AUTO_MOTION_ENTER_THICKNESS_POS_2   = 22            # 두께측정기 2번 위치 진입
    AUTO_MOTION_ENTER_THICKNESS_POS_3   = 23            # 두께측정기 3번 위치 진입
    AUTO_MOTION_RETRACT_FROM_THICKNESS  = 24            # 두께측정기 앞 후퇴
    AUTO_MOTION_APPROACH_ALIGNER        = 25            # 정렬기 앞 이동
    AUTO_MOTION_ENTER_ALIGNER           = 26            # 정렬기 진입
    AUTO_MOTION_RETRACT_FROM_ALIGNER    = 27            # 정렬기 앞 후퇴
    AUTO_MOTION_APPROACH_TENSILE        = 28            # 인장시험기 앞 이동
    AUTO_MOTION_ENTER_TENSILE           = 29            # 인장시험기 진입
    AUTO_MOTION_RETRACT_FROM_TENSILE    = 30            # 인장시험기 앞 후퇴
    AUTO_MOTION_APPROACH_SCRAP          = 31            # 스크랩 통 위치 앞 이동
    AUTO_MOTION_ENTER_SCRAP             = 32            # 스크랩 통 진입
    AUTO_MOTION_RETRACT_FROM_SCRAP      = 33            # 스크랩 통 위치 앞 후퇴
    WAIT_AUTO_COMMAND                   = 34            # 자동 공정 명령 대기
    

# 8. RobotEvent (로봇 제어 이벤트) 정의 - Logic FSM의 서브 이벤트로 활용
class RobotEvent(OpEvent):
    NONE                                = 0
    VIOLATION_DETECT                    = 1             # 위반 감지 이벤트
    STOP_EMG                            = 2             # 비상 정지 이벤트
    DONE                                = 3             # 현재 전략/작업 완료
    RECOVER                             = 4             # 복구 요청 이벤트
    CONNECTION_SUCCESS                  = 5             # 연결 성공
    CONNECTION_FAIL                     = 6             # 연결 실패

    MANUAL_GRIPPER_OPEN_DONE            = 7             # 수동 그리퍼 열기 완료
    MANUAL_GRIPPER_CLOSE_DONE           = 8             # 수동 그리퍼 닫기 완료

    PROGRAM_AUTO_ON_DONE                = 9             # 로봇 프로그램 켜기 완료
    PROGRAM_MANUAL_OFF_DONE             = 10            # 로봇 프로그램 끄기 완료
    AUTO_MOTION_TOOL_CHANGE_DONE        = 11            # 툴 교체 완료
    AUTO_MOTION_MOVE_HOME_DONE          = 12            # 홈 위치 이동 완료
    AUTO_MOTION_APPROACH_RACK_DONE      = 13            # 렉 앞 접근 완료
    AUTO_GRIPPER_OPEN_DONE              = 14            # 로봇 그리퍼 열기 완료
    AUTO_GRIPPER_CLOSE_DONE             = 15            # 로봇 그리퍼 닫기 완료
    AUTO_MOTION_MOVE_TO_QR_DONE         = 16            # QR 인식 위치 이동 완료
    AUTO_MOTION_APPROACH_PICK_DONE      = 17            # 시편 잡는 위치 앞 이동 완료
    AUTO_MOTION_PICK_SPECIMEN_DONE      = 18            # 시편 잡기 완료
    AUTO_MOTION_RETRACT_FROM_TRAY_DONE  = 19            # Tray 앞 후퇴 완료
    AUTO_MOTION_RETRACT_FROM_RACK_DONE  = 20            # 렉 앞 후퇴 완료
    AUTO_MOTION_APPROACH_THICKNESS_DONE = 21            # 두께측정기 앞 이동 완료
    AUTO_MOTION_ENTER_THICKNESS_POS_1_DONE = 22         # 두께측정기 1번 위치 진입 완료
    AUTO_MOTION_ENTER_THICKNESS_POS_2_DONE = 23         # 두께측정기 2번 위치 진입 완료
    AUTO_MOTION_ENTER_THICKNESS_POS_3_DONE = 24         # 두께측정기 3번 위치 진입 완료
    AUTO_MOTION_RETRACT_FROM_THICKNESS_DONE = 25        # 두께측정기 앞 후퇴 완료
    AUTO_MOTION_APPROACH_ALIGNER_DONE   = 26            # 정렬기 앞 이동 완료
    AUTO_MOTION_ENTER_ALIGNER_DONE      = 27            # 정렬기 진입 완료
    AUTO_MOTION_RETRACT_FROM_ALIGNER_DONE = 28          # 정렬기 앞 후퇴 완료
    AUTO_MOTION_APPROACH_TENSILE_DONE   = 29            # 인장시험기 앞 이동 완료
    AUTO_MOTION_ENTER_TENSILE_DONE      = 30            # 인장시험기 진입 완료
    AUTO_MOTION_RETRACT_FROM_TENSILE_DONE = 31          # 인장시험기 앞 후퇴 완료
    AUTO_MOTION_APPROACH_SCRAP_DONE     = 32            # 스크랩 통 위치 앞 이동 완료
    AUTO_MOTION_ENTER_SCRAP_DONE        = 33            # 스크랩 통 진입 완료
    AUTO_MOTION_RETRACT_FROM_SCRAP_DONE = 34            # 스크랩 통 위치 앞 후퇴 완료
    
    # 명령 실행 이벤트 (DO_Command)
    DO_AUTO_MOTION_PROGRAM_AUTO_ON      = 40            # 로봇 프로그램 켜기 실행
    DO_AUTO_MOTION_PROGRAM_MANUAL_OFF   = 41            # 로봇 프로그램 끄기 실행
    DO_AUTO_MOTION_TOOL_CHANGE          = 42            # 툴 교체 실행
    DO_AUTO_MOTION_MOVE_HOME            = 43            # 홈 위치 이동 실행
    DO_AUTO_MOTION_APPROACH_RACK        = 44            # 렉 앞 접근 실행
    DO_AUTO_GRIPPER_OPEN                = 45            # 그리퍼 열기 실행
    DO_AUTO_GRIPPER_CLOSE               = 46            # 그리퍼 닫기 실행
    DO_AUTO_MOTION_MOVE_TO_QR           = 47            # QR 위치 이동 실행
    DO_AUTO_MOTION_APPROACH_PICK        = 48            # 픽업 위치 접근 실행
    DO_AUTO_MOTION_PICK_SPECIMEN        = 49            # 시편 픽업 실행
    DO_AUTO_MOTION_RETRACT_FROM_TRAY    = 50            # 트레이 후퇴 실행
    DO_AUTO_MOTION_RETRACT_FROM_RACK    = 51            # 렉 후퇴 실행
    DO_AUTO_MOTION_APPROACH_THICKNESS   = 52            # 두께측정기 접근 실행
    DO_AUTO_MOTION_ENTER_THICKNESS_POS_1 = 53           # 두께측정 1번 위치 진입 실행
    DO_AUTO_MOTION_ENTER_THICKNESS_POS_2 = 54           # 두께측정 2번 위치 진입 실행
    DO_AUTO_MOTION_ENTER_THICKNESS_POS_3 = 55           # 두께측정 3번 위치 진입 실행
    DO_AUTO_MOTION_RETRACT_FROM_THICKNESS = 56          # 두께측정기 후퇴 실행
    DO_AUTO_MOTION_APPROACH_ALIGNER     = 57            # 정렬기 접근 실행
    DO_AUTO_MOTION_ENTER_ALIGNER        = 58            # 정렬기 진입 실행
    DO_AUTO_MOTION_RETRACT_FROM_ALIGNER = 59            # 정렬기 후퇴 실행
    DO_AUTO_MOTION_APPROACH_TENSILE     = 60            # 인장시험기 접근 실행
    DO_AUTO_MOTION_ENTER_TENSILE        = 61            # 인장시험기 진입 실행
    DO_AUTO_MOTION_RETRACT_FROM_TENSILE = 62            # 인장시험기 후퇴 실행
    DO_AUTO_MOTION_APPROACH_SCRAP       = 63            # 스크랩 통 접근 실행
    DO_AUTO_MOTION_ENTER_SCRAP          = 64            # 스크랩 통 진입 실행
    DO_AUTO_MOTION_RETRACT_FROM_SCRAP   = 65            # 스크랩 통 후퇴 실행


# 9. RobotViolation (로봇 제어 위반) 정의 - Logic FSM으로 보고됨
class RobotViolation(ViolationType):
    NONE                                = 0
    CONNECTION_TIMEOUT                  = 1 << 0        # 로봇 컨트롤러 통신 시간 초과
    TOOL_CHANGE_FAIL                    = 1 << 1        # 툴 교체 실패 (툴 미장착 등)
    QR_READ_FAIL                        = 1 << 2        # QR 리딩 실패 (코드 인식 불가 등)
    GRIPPER_FAIL                        = 1 << 3        # 그리퍼 동작 실패 (시편 놓침 등)
    COLLISION_VIOLATION                 = 1 << 4        # 이동 중 충돌, 티칭 오류, 경로 이탈 등
    ISO_EMERGENCY_BUTTON                = 1 << 8
    HW_VIOLATION                        = 1 << 9
    HW_NOT_READY                        = 1 << 10

# 10. Indy Conty 프로그램 상태 정의
class ProgramState(IntEnum):
    PROG_IDLE                           = 0
    PROG_RUNNING                        = 1
    PROG_PAUSING                        = 2
    PROG_STOPPING                       = 3

# 11. Indy opstate 정의 
class DigitalState(IntEnum):
    OFF_STATE                           = 0
    ON_STATE                            = 1
    UNUSED_STATE                        = 2

# 12. Indy Conty 프로그램 제어 명령 정의
class ProgramControl(IntEnum):
    PROG_IDLE                           = 0
    PROG_START                          = 1
    PROG_RESUME                         = 2
    PROG_PAUSE                          = 3
    PROG_STOP                           = 4

class Robot_OP_State(IntEnum):
    # Indy's FSM state
    OP_SYSTEM_OFF                       = 0
    OP_SYSTEM_ON                        = 1
    OP_VIOLATE                          = 2
    OP_RECOVER_HARD                     = 3
    OP_RECOVER_SOFT                     = 4
    OP_IDLE                             = 5
    OP_MOVING                           = 6
    OP_TEACHING                         = 7
    OP_COLLISION                        = 8
    OP_STOP_AND_OFF                     = 9
    OP_COMPLIANCE                       = 10
    OP_BRAKE_CONTROL                    = 11
    OP_SYSTEM_RESET                     = 12
    OP_SYSTEM_SWITCH                    = 13
    OP_VIOLATE_HARD                     = 15
    OP_MANUAL_RECOVER                   = 16
    TELE_OP                             = 17

# 13. Remote IO DI (Digital Input) 신호 정의
class DigitalInput(IntEnum):
    """
    PLC DI (Digital Input) 신호 목록
    address는 이미지의 address - 1 값입니다.
    """
    AUTO_MANUAL_SELECT_SW               = 0
    RESET_SW                            = 1
    # address 3은 비어있음
    SOL_SENSOR                          = 3
    BCR_OK                              = 4
    BCR_ERROR                           = 5
    BUSY                                = 6
    # address 8은 비어있음
    ENO_01_SW                           = 8
    EMO_02_SI                           = 9
    EMO_03_SI                           = 10
    EMO_04_SI                           = 11
    DOOR_1_OPEN                         = 12
    DOOR_2_OPEN                         = 13
    DOOR_3_OPEN                         = 14
    DOOR_4_OPEN                         = 15
    GRIPPER_1_CLAMP                     = 16
    # address 18은 비어있음
    GRIPPER_2_CLAMP                     = 18
    # address 20은 비어있음
    EXT_FW_SENSOR                       = 20
    EXT_BW_SENSOR                       = 21
    # address 23~24는 비어있음
    INDICATOR_GUIDE_DOWN                = 24
    INDICATOR_GUIDE_UP                  = 25
    ALIGN_1_PUSH                        = 26
    ALIGN_1_PULL                        = 27
    ALIGN_2_PUSH                        = 28
    ALIGN_2_PULL                        = 29
    ALIGN_3_PUSH                        = 30
    ALIGN_3_PULL                        = 31
    ATC_1_1_SENSOR                      = 32
    ATC_1_2_SENSOR                      = 33
    SCRAPBOX_SENSOR                     = 34
    ATC_2_1_SENSOR                      = 35
    ATC_2_2_SENSOR                      = 36

# 14. Remote IO DO (Digital Output) 신호 정의
class DigitalOutput(IntEnum):
    """
    PLC DO (Digital Output) 신호 목록
    address는 이미지의 address - 1 값입니다.
    """
    TOWER_LAMP_RED                      = 0
    TOWER_LAMP_GREEN                    = 1
    TOWER_LAMP_YELLOW                   = 2
    TOWER_BUZZER                        = 3
    # address 5는 비어있음
    BCR_TGR                             = 5
    LOCAL_LAMP_R                        = 6
    # address 8은 비어있음
    RESET_SW_LAMP                       = 8
    DOOR_4_LAMP                         = 9
    # address 11~14는 비어있음
    INDICATOR_UP                        = 14
    INDICATOR_DOWN                      = 15
    ALIGN_1_PUSH                        = 16
    ALIGN_1_PULL                        = 17
    ALIGN_2_PUSH                        = 18
    ALIGN_2_PULL                        = 19
    ALIGN_3_PUSH                        = 20
    ALIGN_3_PULL                        = 21
    GRIPPER_1_UNCLAMP                   = 22
    LOCAL_LAMP_L                        = 23
    GRIPPER_2_UNCLAMP                   = 24
    LOCAL_LAMP_C                        = 25
    EXT_FW                              = 26
    EXT_BW                              = 27

class Motion_command:
    M00_MOVE_TO_RACK                    = "move_to_rack"
    M01_PICK_SPECIMEN                   = "pick_specimen"
    M02_MOVE_TO_INDICATOR               = "move_to_indigator"
    M03_PLACE_AND_MEASURE               = "place_specimen_and_measure"
    M04_PICK_OUT_FROM_INDICATOR         = "Pick_specimen_out_from_indigator"
    M05_ALIGN_SPECIMEN                  = "align_specimen"
    M06_PICK_OUT_FROM_ALIGN             = "Pick_specimen_out_from_align"
    M07_LOAD_TENSILE_MACHINE            = "load_tensile_machine"
    M08_RETREAT_TENSILE_MACHINE         = "retreat_tensile_machine"
    M09_PICK_TENSILE_MACHINE            = "pick_tensile_machine"
    M10_RETREAT_AND_HANDLE_SCRAP        = "retreat_and_handle_scrap"

class Device_command:
    MEASURE_THICKNESS                   = "measure_thickness"
    ALIGN_SPECIMEN                      = "align_specimen"
    TENSILE_GRIPPER_ON                  = "tessile_gripper_on"
    TENSILE_GRIPPER_OFF                 = "tessile_gripper_off"
    EXT_FORWARD                         = "ext_forward"
    EXT_BACKWARD                        = "ext_backward"
    START_TENSILE_TEST                  = "start_tensile_test"
    STOP_TENSILE_TEST                   = "stop_tensile_test"
    PAUSE_TENSILE_TEST                  = "pause_tensile_test"
    RESUME_TENSILE_TEST                 = "resume_tensile_test"
    QR_READ                             = "qr_read"
