from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay

from pkg.configs.global_config import GlobalConfig

class RobotStatus:
    # FSM 상태 확인을 위한 플래그
    def __init__(self):
        self.is_connected = Flagger()    # 로봇 컨트롤러 연결 상태
        self.is_ready = Flagger()        # 로봇 준비 상태 (원점 복귀, 초기화 완료)
        self.is_emg_pushed = Flagger()   # 비상 정지 버튼
        self.is_error_state = Flagger()  # 하드웨어/외부 오류 상태
        self.is_moving = Flagger()       # 로봇 동작 중 여부

        self.reset()

    def reset(self):
        self.is_connected.down()
        self.is_ready.down()
        self.is_emg_pushed.down()
        self.is_error_state.down()
        self.is_moving.down()


class RobotContext(ContextBase):
    status: RobotStatus
    violation_code: int

    def __init__(self):
        ContextBase.__init__(self)
        self.status = RobotStatus()
        self.violation_code = 0x00

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            # 1. 비상 정지 및 일반 HW 오류
            if self.status.is_emg_pushed():
                self.violation_code |= RobotViolation.ISO_EMERGENCY_BUTTON.value

            if self.status.is_error_state():
                self.violation_code |= RobotViolation.HW_VIOLATION.value
            
            # 2. 로봇 연결 및 준비 상태
            if not self.status.is_connected():
                self.violation_code |= RobotViolation.CONNECTION_TIMEOUT.value
                
            if self.status.is_connected() and not self.status.is_ready():
                 self.violation_code |= RobotViolation.HW_NOT_READY.value
            
            # TODO: 로봇 동작 중 충돌/경로 오류(MOTION_VIOLATION) 감지 로직 추가

            return self.violation_code
        except Exception as e:
            reraise(e)