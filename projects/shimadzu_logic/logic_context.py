from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

class LogicStatus:
    # Neuromeka 전체 시스템 상태 플래그
    def __init__(self):
        self.is_connected_all = Flagger()  # 모든 서브 모듈 연결 완료
        self.is_ready_all = Flagger()      # 모든 서브 모듈 준비 완료
        self.is_emg_pushed = Flagger()     # 비상 정지 버튼
        self.is_error_state = Flagger()    # 하드웨어/외부 오류 상태
        self.is_batch_planned = Flagger()  # 배치 계획 수립 완료

        self.reset()

    def reset(self):
        self.is_connected_all.down()
        self.is_ready_all.down()
        self.is_emg_pushed.down()
        self.is_error_state.down()
        self.is_batch_planned.down()


class LogicContext(ContextBase):
    status: LogicStatus
    violation_code: int
    
    # 서브 모듈 FSM 인스턴스를 저장할 필드
    # device_fsm: DeviceFSM
    # robot_fsm: RobotFSM

    def __init__(self):
        ContextBase.__init__(self)
        self.status = LogicStatus()
        self.violation_code = 0x00
        # self.device_fsm = DeviceFSM(...)
        # self.robot_fsm = RobotFSM(...)

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            # 1. Logic 자체의 상태 확인
            if self.status.is_emg_pushed():
                self.violation_code |= LogicViolation.ISO_EMERGENCY_BUTTON.value

            if self.status.is_error_state():
                self.violation_code |= LogicViolation.HW_VIOLATION.value

            if not self.status.is_batch_planned():
                 self.violation_code |= LogicViolation.BATCH_PLAN_MISSING.value

            # 2. 서브 모듈 상태 보고 (실제 구현 시 서브 FSM의 violation_code를 통합)
            # if self.device_fsm.get_state() == DeviceState.ERROR:
            #     self.violation_code |= LogicViolation.DEVICE_CRITICAL_FAIL.value
            
            # if self.robot_fsm.get_state() == RobotState.ERROR:
            #     self.violation_code |= LogicViolation.ROBOT_CRITICAL_FAIL.value

            return self.violation_code
        except Exception as e:
            reraise(e)

