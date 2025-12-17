import time
from abc import ABC, abstractmethod
from collections import defaultdict, namedtuple
from copy import deepcopy
from typing import Dict, Optional, Callable, List, Any, Union, Tuple
from enum import Enum, IntEnum
from threading import Lock, Event, Thread
from ..utils.logging import Logger
from ..utils.process_control import Flagger, ExecutionSequence, ExecutionUnit, ConditionUnit, PeriodicThread

INACTIVE_STATE = 0x00
NONE_EVENT = 0x00



class OpState(Enum):
    # INACTIVE = INACTIVE_STATE  # this is reserved. put this to all OpState children classes
    
    pass


class OpEvent(Enum):
    # NONE = NONE_EVENT  # this is reserved. put this to all OpEvent children classes
    pass


class StateCall:
    state: OpState
    event: OpEvent
    args: Tuple
    kwargs: Dict

    def __init__(self, state: OpState, event: Optional[OpEvent] = None, *args, **kwargs):
        self.state, self.event, self.args, self.kwargs = state, event, args, kwargs


class ViolationType(Enum):
    pass


class ContextBase:
    state: OpState

    def __init__(self):
        pass

    def set_state(self, state: OpState):
        self.state = state


class Strategy(ABC):
    @abstractmethod
    def prepare(self, context: ContextBase, event: OpEvent, *args, **kwargs):
        pass

    @abstractmethod
    def operate(self, context: ContextBase) -> OpEvent:
        pass

    @abstractmethod
    def exit(self, context: ContextBase, event: OpEvent) -> None:
        pass

class FiniteStateMachine(ABC):
    _rule_table: Dict[OpState, Dict[OpEvent, OpState]]
    _strategy_table: Dict[OpState, Strategy]
    _sub_fsm_table: Dict
    _cur_state: OpState
    _strategy: Optional[Strategy]
    __triggered_call: Optional[StateCall]
    _sub_fsm: 'FiniteStateMachine'
    context: ContextBase
    thread: Optional[PeriodicThread]

    def __init__(self, init_state, context: ContextBase, period: float = 0.02):
        self.context = context
        self.trigger_lock = Lock()  # lock for new state between trigger and update
        self._rule_table = defaultdict(dict)
        self._strategy_table = {}
        self._sub_fsm_table = {}
        self._setup_sub_fsms()
        self._setup_rules()
        self._setup_strategies()
        self._strategy = None
        self.__triggered_call = None
        self._enter_state(StateCall(init_state, None))
        self.period = period
        self.thread = None
        self.__tick = Event()
        self.stop_flag = Flagger()

        self._last_event = None

    ##
    # @brief set self._sub_fsm_table dictionary {OpState: FSM}
    def _setup_sub_fsms(self):
        self._sub_fsm_table = {}

    ##
    # @brief set self._rule_table dictionary {OpState: {OpEvent: OpState}}
    @abstractmethod
    def _setup_rules(self):
        raise(NotImplementedError())

    ##
    # @brief set self._strategy_table dictionary {OpState: Strategy}}
    @abstractmethod
    def _setup_strategies(self):
        raise(NotImplementedError())

    def _enter_state(self, state_call: StateCall):
        if self._strategy is not None:
            self._strategy.exit(context=self.context, event=state_call.event)
        # Logger.debug(f"{self.__class__.__name__}: Enter new state {state_call.state.name}")
        self._cur_state = state_call.state
        self._sub_fsm = self.__get_sub_fsm(state_call.state)
        self._rules = self._rule_table[self._cur_state]
        self._strategy = self._strategy_table[self._cur_state]
        self.context.set_state(self._cur_state)
        self._strategy.prepare(context=self.context, event=state_call.event, *state_call.args, **state_call.kwargs)

    ##
    # @brief return new state for an event.
    def __get_new_state(self, event):
        if event not in self._rules:
            return None
        new_state = self._rules[event]
        if new_state == self._cur_state:
            raise(
                NotImplementedError("Pattern [new_state==cur_state] is not supported ({}>{}>{})".format(
                    self._cur_state.name, event.name, new_state.name)))
        return new_state

    def __get_sub_fsm(self, state):
        return self._sub_fsm_table[state] if state in self._sub_fsm_table else None

    def get_state(self):
        if self._sub_fsm is not None:
            return self._sub_fsm.get_state()
        else:
            return self._cur_state

    def in_states(self, states: List[OpState]):
        return self.get_state() in states

    def get_current_strategy(self):
        return self._strategy_table[self._cur_state]

    def get_inactive_state(self):
        return next(filter(lambda state: state.value == INACTIVE_STATE, self._rule_table.keys()))

    ##
    # @brief get full-depth rule table
    def get_full_rule_table(self):
        _sub_table_dict = deepcopy(
            {state: sub_fsm.get_full_rule_table() for state, sub_fsm in self._sub_fsm_table.items()})
        _inactive_dict = {state: sub_fsm.get_inactive_state() for state, sub_fsm in self._sub_fsm_table.items()}
        forwarding_table = self.get_forwarding_table()

        _rule_table = {state: rule_dict
                       for state, rule_dict in self._rule_table.items()
                       if state not in self._sub_fsm_table}  # get non-sub-fsm state rules
        last_inactive = None
        for state, _sub_table in _sub_table_dict.items():
            for _state, rule_dict in _sub_table.items():  # update local inactive state to forwarded state
                for event, goal_state in rule_dict.items():
                    if goal_state.value == INACTIVE_STATE:  # replace INACTIVE_STATE with forwarded table's target
                        tar_inactive = _inactive_dict[forwarding_table[event]]
                        rule_dict[event] = _sub_table_dict[forwarding_table[event]][tar_inactive][event]
                if _state.value == INACTIVE_STATE:
                    last_inactive = _state
            _rule_table.update(_sub_table)  # collect rules from sub-fsm
        if last_inactive is not None:
            del _rule_table[last_inactive]  # remove lastly updated inactive state
        return _rule_table

    def get_available_events(self, state=None):
        if self._sub_fsm is not None:
            return self._sub_fsm.get_available_events(state)
        else:
            state = self._cur_state if state is None else state
            return sorted(self._rule_table[state].keys(), key=lambda event: event.value)

    ##
    # @brief get outgoing events to the inactive state
    def get_outgoing_events(self):
        return list(set([event
                         for state, rule_dict in self._rule_table.items()
                         for event, goal_state in rule_dict.items()
                         if goal_state.value == INACTIVE_STATE]))

    ##
    # @brief get incoming events from the inactive state
    def get_incoming_events(self):
        return list(set([event
                         for state, rule_dict in self._rule_table.items()
                         for event in rule_dict.keys()
                         if state.value == INACTIVE_STATE]))

    ##
    # @brief get 1-depth event->state forwarding table among sub-fsm models
    def get_forwarding_table(self):
        state_inbound_dict = {state: sub_fsm.get_incoming_events() for state, sub_fsm in self._sub_fsm_table.items()}
        forwarding_table = defaultdict(list)
        for state, event_list in state_inbound_dict.items():
            forwarding_table.update({event: state for event in event_list})
        return forwarding_table

    ##
    # @brief  get meta rules between sub-fsm models
    def get_meta_rules(self):
        forwarding_table = self.get_forwarding_table()
        return {
            state:
                {
                    event: forwarding_table[event]
                    for event in sub_fsm.get_outgoing_events()
                }
            for state, sub_fsm in self._sub_fsm_table.items()
        }

    ##
    # @brief    next state is reserved based on _rule_table and will be changed on the next update() call.
    # @return   True if new state is reserved in either _sub_fsm or this fsm
    def trigger(self, event: OpEvent, *args, **kwargs):
        # Logger.debug(f"Debug {self.__class__.__name__}: Trigger Event {event.name} on {self._cur_state.name}")
        self._last_event = event
        with self.trigger_lock:
            if self._sub_fsm is not None:
                res_sub = self._sub_fsm.trigger(event, *args, **kwargs)
            else:
                res_sub = False

            new_state = self.__get_new_state(event)
            if new_state is not None:
                self.__triggered_call = StateCall(new_state, event, *args, **kwargs)
                res_this = True
                sub_fsm = self.__get_sub_fsm(self.__triggered_call.state)
                if sub_fsm is not None:  # if sub_fsm exist for new_state, it should be triggered
                    res_this = sub_fsm.trigger(event, **kwargs)
                    if not res_this:  # if sub_fsm trigger fails, all trigger should be canceled recursively
                        self.cancel_trigger()
                        res_sub = False
            else:
                res_this = False
            return res_sub or res_this

    def cancel_trigger(self):
        # Logger.debug(f"{self.__class__.__name__}: Cancel trigger")
        if self._sub_fsm is not None:
            self._sub_fsm.cancel_trigger()  # cancel exit trigger of current fsm
        if self.__triggered_call is not None:
            _new_sub = self.__get_sub_fsm(self.__triggered_call.state)
            if _new_sub is not None:
                _new_sub.cancel_trigger()  # cancel entry trigger of current fsm
            self.__triggered_call = None

    def is_trigger_processed(self, event: OpEvent):
        return self.__triggered_call is None or self.__triggered_call.event != event

    ##
    # @brief step one cycle of update and triggering result
    def step(self):
        events = self.update()
        if events:
            self.trigger(events[0])

    ##
    # @brief Update the machine. Need to be called periodically.
    def update(self):
        events = []
        with self.trigger_lock:
            if self.__triggered_call is not None:
                if self._sub_fsm is not None:
                    events += self._sub_fsm.update()  # update sub_fsm to let them know before state transfer
                self._enter_state(self.__triggered_call)
                self.__triggered_call = None

        events += [self._strategy.operate(self.context)]

        if self._sub_fsm is not None:
            events += self._sub_fsm.update()

        return list(filter(lambda x: x is not None and x.value != NONE_EVENT, events))

    def get_rule_table(self):
        return self._rule_table

    def get_strategy_table(self):
        return self._strategy_table

    def get_sub_fsm_table(self):
        return self._sub_fsm_table

    def start_service_background(self):
        if self.thread is not None and self.thread.is_alive():
            return False
        self.thread = PeriodicThread(self.step, period=self.period, stop_flag=self.stop_flag,
                                     thread_name=f"{self.__class__.__name__}")
        self.thread.start()
        return True

    def wait_thread(self):
        while self.thread.is_alive():
            #time.sleep(0.5)
            time.sleep(0.001)

    def stop(self):
        Logger.info(f"{self.__class__.__name__}: Stopping FSM service thread.")
        self.stop_flag.set(True)  # 또는 self.stop_flag.up()
        if self.thread:
            self.thread.join()
            Logger.info(f"{self.__class__.__name__}: FSM service thread stopped.")


class NullStrategy(Strategy):
    def prepare(self, context: ContextBase, **kwargs):
        pass

    def operate(self, context: ContextBase) -> OpEvent:
        pass


class NotImplementedStrategy(Strategy):
    def prepare(self, context: ContextBase, **kwargs):
        raise NotImplementedError

    def operate(self, context: ContextBase) -> OpEvent:
        raise NotImplementedError


