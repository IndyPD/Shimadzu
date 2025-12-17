from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
import grpc


class MyStatus:
    def __init__(self):
        self.is_ready = Flagger()
        self.is_emg_pushed = Flagger()
        self.is_error_state = Flagger()
        self.is_moving = Flagger()

        self.reset()

    def reset(self):
        self.is_ready.up()
        self.is_emg_pushed.down()
        self.is_error_state.down()


class MyContext(ContextBase):
    status: MyStatus
    violation_code: int

    def __init__(self):
        ContextBase.__init__(self)
        self.status = MyStatus()
        self.violation_code = 0x00

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            if self.status.is_emg_pushed():
                self.violation_code |= MyViolation.ISO_EMERGENCY_BUTTON.value

            if self.status.is_error_state():
                self.violation_code |= MyViolation.HW_VIOLATION.value

            if not self.status.is_ready():
                self.violation_code |= MyViolation.HW_NOT_READY.value

            return self.violation_code
        except Exception as e:
            reraise(e)
