import time

from pkg.utils.blackboard import GlobalBlackboard
from .context import *

bb = GlobalBlackboard()
##
# @class WaitConnectionStrategy
# @brief Strategy for WAIT_CONNECTION State.
# @details wait for device connection
class WaitConnectionStrategy(Strategy):
    def prepare(self, context: MyContext, **kwargs):
        pass

    def operate(self, context: MyContext) -> MyEvent:
        if not context.check_violation() & MyViolation.HW_CONNECTION_LOST.value:
            return MyEvent.DONE
        return MyEvent.NONE

    def exit(self, context: ContextBase, event: OpEvent) -> None:
        pass


##
# @class ViolatedStrategy
# @brief Strategy for VIOLATED State.
class ViolatedStrategy(Strategy):
    def prepare(self, context: MyContext, **kwargs):
        violation_names = [violation.name for violation in MyViolation if violation.value & context.violation_code]
        Logger.error(f"Violation Detected: "
                     f"{'|'.join(violation_names)}", popup=True)

    def operate(self, context: MyContext) -> MyEvent:
        if not context.check_violation():
            return MyEvent.RECOVER
        return MyEvent.NONE


##
# @class RecoveringStrategy
# @brief Strategy for RECOVERING State.
# @details soft reset: reset SW depending on error case
class RecoveringStrategy(Strategy):
    def prepare(self, context: MyContext, **kwargs):
        self.exec_seq = ExecutionSequence([
            ExecutionUnit("SW Recover", function=bb.set, args=("recover/sw/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/sw/done",), condition=1)),
            ExecutionUnit("HW Recover", function=bb.set, args=("recover/hw/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/hw/done",), condition=1)),
            ExecutionUnit("HW Reboot", function=bb.set, args=("recover/reboot/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/reboot/done",), condition=1)),
        ])  # start or resume program and keep checking if program is paused

    def operate(self, context: MyContext) -> MyEvent:
        if self.exec_seq.execute():
            return MyEvent.DONE
        return MyEvent.NONE

##
# @class StopOffStrategy
# @brief Strategy for STOP_AND_OFF State.
# @details soft reset: stop and turn off device
class StopOffStrategy(Strategy):
    def prepare(self, context: MyContext, **kwargs):
        self.exec_seq = ExecutionSequence([
            ExecutionUnit("Stop", function=Logger.info, args=("stopped",)),
            ExecutionUnit("Off", function=Logger.info,
                          args=("turned off",),
                          end_conditions=ConditionUnit(
                              lambda: context.check_violation() & MyViolation.HW_CONNECTION_LOST.value
                          ))
        ])

    def operate(self, context: MyContext) -> MyEvent:
        if self.exec_seq.execute():
            return MyEvent.DONE
        return MyEvent.NONE


##
# @class IdleStrategy
# @brief    check violation and motion status this is just resting and monitoring state.
#           entering this state does not stop actions
class IdleStrategy(Strategy):
    def operate(self, context: MyContext) -> MyEvent:
        if context.check_violation():
            return MyEvent.VIOLATION_DETECT
        return MyEvent.NONE


##
# @class MovingStrategy
# @brief Strategy for MOVING State.
# @details monitor violation, motion status, and collision to switch state
class MovingStrategy(Strategy):
    def operate(self, context: MyContext) -> MyEvent:
        if context.check_violation():
            return MyEvent.VIOLATION_DETECT
        if not context.status.is_moving():
            return MyEvent.DONE
        return MyEvent.NONE
