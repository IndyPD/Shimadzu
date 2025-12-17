from .strategy import *
from .constants import *


class MyFSM(FiniteStateMachine):
    context: MyContext

    def __init__(self, context: MyContext, *args, **kwargs):
        FiniteStateMachine.__init__(self, MyState.WAIT_CONNECTION, context, *args, **kwargs)

    def _setup_rules(self):
        self._rule_table = {
            MyState.WAIT_CONNECTION: {
                MyEvent.DONE: MyState.IDLE,
                MyEvent.RECOVER: MyState.RECOVERING,
            },
            MyState.VIOLATED: {
                MyEvent.RECOVER: MyState.RECOVERING
            },
            MyState.RECOVERING: {
                MyEvent.DONE: MyState.IDLE,
                MyEvent.VIOLATION_DETECT: MyState.VIOLATED
            },
            MyState.STOP_AND_OFF: {
                MyEvent.DONE: MyState.WAIT_CONNECTION
            },
            MyState.IDLE: {
                MyEvent.RECOVER: MyState.RECOVERING,
                MyEvent.VIOLATION_DETECT: MyState.VIOLATED,
                MyEvent.MOVE: MyState.MOVING,
                MyEvent.STOP_EMG: MyState.STOP_AND_OFF
            },
            MyState.MOVING: {
                MyEvent.STOP_EMG: MyState.STOP_AND_OFF,
                MyEvent.VIOLATION_DETECT: MyState.VIOLATED,
                MyEvent.STOP_MOTION: MyState.RESETTING_IDLE,
                MyEvent.DONE: MyState.IDLE
            }
        }

    def _setup_strategies(self):
        self._strategy_table = {
            MyState.WAIT_CONNECTION: WaitConnectionStrategy(),
            MyState.VIOLATED: ViolatedStrategy(),
            MyState.RECOVERING: RecoveringStrategy(),
            MyState.STOP_AND_OFF: StopOffStrategy(),
            MyState.IDLE: IdleStrategy(),
            MyState.MOVING: MovingStrategy()
        }
