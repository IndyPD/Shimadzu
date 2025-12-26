import signal
import sys
import time
import time as _time
import traceback

##################################
#########  Flag Control  #########
##################################


##
# @class Flagger
# @brief a flag holder class
from typing import Callable, Any, List, Dict

from .logging import Logger
from .singleton import SingletonMeta

class MyClass:
    def __init__(self):
        self.is_robot_ready = Flagger()
        self.is_robot_ready.up()
        # t = Thread(target=self._my_thread, args=(self.is_robot_ready,))
        self.blocker = BlockFlagger()
        is_block_running = self.blocker()

    def _my_thread(self, is_robot_ready):
        # with BlockWrapper(
        #         enter_fn=preparing function,
        #         exit_fn=clearing function):
        #     """ do reset protocol 1"""
        #     """ do reset protocol 2"""
        #     delay = FlagDelay(0.5)
        #     filtered_di = delay(di_input)
        pass

class Flagger:
    def __init__(self):
        self.flag = False

    def __call__(self, *args, **kwargs):
        return self.flag

    def up(self):
        self.flag = True

    def down(self):
        self.flag = False

    def set(self, flag):
        self.flag = flag


##
# @class BlockFlagger
# @brief a enter/exit flag setter class
class BlockFlagger(Flagger):
    def __enter__(self):
        self.up()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.down()


##
# @class BlockWrapper
# @brief a enter/exit function
class BlockWrapper:
    def __init__(self, enter_fn, exit_fn):
        self.enter_fn, self.exit_fn = enter_fn, exit_fn

    def __enter__(self):
        self.enter_fn()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_fn()


##
# @class FlagDelay
# @brief check if bool flag continues for a defined time and return delayed flag
class FlagDelay:
    ##
    # @param time_limit limit of error time in seconds
    def __init__(self, time_limit):
        self.time_s = _time.time()
        self.time_limit = time_limit
        self.flag_pre = False

    ##
    # @param flag current flag state
    # @return True if error continues for too long
    def __call__(self, flag: bool):
        flag_pre = self.flag_pre
        self.flag_pre = flag
        if flag:
            if not flag_pre:
                self.time_s = _time.time()
            return (_time.time() - self.time_s) > self.time_limit
        return False

    def force_up(self):
        self.flag_pre = True
        self.time_s = 0


##
# @class TimeProgresss
# @brief get progress
class TimeProgresss:
    def __init__(self, section_num):
        self.section_num = section_num
        self.section_cur, self.percent_cur = 0, 0
        self.section_start = None
        self.time_ref = None

    ##
    # @brief update progress
    # @param section_cur current section index
    # @param percent_cur progress of current section in percentage
    def update_section_progress(self, section_cur, percent_cur):
        self.section_cur = section_cur
        self.percent_cur = percent_cur
        self.section_start = None
        self.time_ref = None

    ##
    # @brief update progress
    # @param section_cur current section index
    def set_section_timer(self, section_cur, time_ref):
        self.section_cur = section_cur
        self.percent_cur = 0
        self.time_ref = time_ref
        self.section_start = _time.time()

    ##
    # @brief return True if timeout not reached
    def check_timeout(self, timeout):
        if self.section_start is not None:
            return _time.time() - self.section_start < timeout
        else:
            return True

    def get_full_progress(self):
        if self.section_start is not None:
            self.percent_cur = min(100, (_time.time() - self.section_start)/self.time_ref*100)
        return 100*self.section_cur/self.section_num + self.percent_cur / self.section_num


###############################
#########  Threading  #########
###############################

from functools import wraps
import threading


def thread_run(target, args=[], kwargs={}, daemon = False):
    t = threading.Thread(target=target, args=args, kwargs=kwargs)
    t.daemon = daemon
    t.start()
    return t


class TimeError:
    def __init__(self, error: Exception, timeout: float = 1.0):
        self.timeout = timeout
        self.time = _time.time()
        self.error = error

    def check_over(self):
        if _time.time() - self.time > self.timeout:
            return True
        return False

    def update_time(self):
        self.time = _time.time()

    def __str__(self):
        return str(self.error)


class PeriodicThread:
    __error_log: Dict[str, TimeError]

    def __init__(self, function, *args, period: float = 0.01, stop_flag: Flagger = None, daemon=True, thread_name="", **kwargs):
        self.function, self.args, self.kwargs = function, args, kwargs
        self.thread_name = thread_name
        self.period = period
        self.stop_flag = stop_flag if stop_flag is not None else Flagger()
        self.last_result = None
        self.__error_log = {}

        self.__periodic_event = threading.Event()
        self.__thread_worker = threading.Thread(target=self.__worker, daemon=daemon)
        self.__thread_periodic = threading.Thread(target=self.__periodic_event_loop, daemon=daemon)

    def __worker(self):
        while not self.stop_flag():
            if not self.__periodic_event.wait(self.period):  # set timeout to prevent iternal lock
                continue
            self.__periodic_event.clear()
            try:
                self.last_result = self.function(*self.args, **self.kwargs)
            except Exception as e:
                e_str = str(e)
                if e_str not in self.__error_log or self.__error_log[e_str].check_over():
                    self.__error_log[e_str] = TimeError(e)
                    # 예외 정보 얻기
                    exc_type, exc_value, exc_traceback = sys.exc_info()

                    # 가장 최근(에러가 발생한) 스택 프레임 정보 추출
                    # -1 인덱스는 리스트의 마지막 요소를 의미
                    tb = traceback.extract_tb(exc_traceback)[-1]

                    # 파일명과 줄번호, 함수명 추출
                    filename = tb.filename
                    lineno = tb.lineno
                    funcname = tb.name
                    Logger.error(f"Exception in PeriodicThread {self.thread_name}({self.function.__module__}.{self.function.__name__})")
                    Logger.error(f"Error occurred at: {filename}, line {lineno} in function '{funcname}'")
                    Logger.error(e_str)
                else:
                    self.__error_log[e_str].update_time()

    def __periodic_event_loop(self):
        periodic_waiter = threading.Event()
        while not self.stop_flag():
            periodic_waiter.wait(self.period)
            self.__periodic_event.set()

    def start(self):
        self.__thread_worker.start()
        self.__thread_periodic.start()

    def join(self):
        self.__thread_worker.join()
        self.__thread_periodic.join()

    def stop(self):
        self.stop_flag.up()

    def is_alive(self):
        return self.__thread_worker.is_alive() or self.__thread_periodic.is_alive()


###############################
#########  Error Try  #########
###############################


def try_or(fn, args=[], kwargs={}, default=None, default_fun=None, callback_error=None, reraise_flag=False, final_fun=None):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if callback_error:
            callback_error(e)
        if reraise_flag:
            reraise(e)
        if default_fun:
            return default_fun()
        else:
            return default
    finally:
        if final_fun is not None:
            final_fun()


class try_wrap(object):
    def __init__(self, default=None, default_fun=None, callback_error=None, reraise_flag=False, final_fun=None):
        self.default = default
        self.default_fun = default_fun
        self.callback_error = callback_error
        self.reraise_flag = reraise_flag
        self.wrapped_by_try = True
        self.final_fun = final_fun

    def __call__(self, func):
        func.wrapped_by_try = True
        def wrapped_f(*args, **kwargs):
            result = try_or(func, args=args, kwargs=kwargs
                            , default=self.default, default_fun=self.default_fun
                            , callback_error=self.callback_error, reraise_flag=self.reraise_flag, final_fun=self.final_fun)
            return result

        wrapped_f.wrapped_by_try = True
        return wrapped_f

def wrap_all_methods(decorator):
    def decorate(cls):
        for attr in cls.__dict__: # there's propably a better way to do this
            if type(getattr(cls, attr)).__name__ == 'function':
                if not hasattr(getattr(cls, attr), 'wrapped_by_try'):
                    setattr(cls, attr, decorator(getattr(cls, attr)))
        return cls
    return decorate

def pass_wrap(func):
    func.wrapped_by_try = True
    @wraps(func)  # Tells debuggers that is is a function wrapper
    def decorator(*args, **kwargs):
        return func(*args, **kwargs)
    return decorator

def reraise(exception):
    raise exception.with_traceback(sys.exc_info()[2])


###########################################
#########  Multi Process Control  #########
###########################################


##
# @class    ConditionUnit
# @brief    Condition unit for FSM.
class ConditionUnit:
    function: Callable[[], Any]
    condition: Any

    def __init__(self, function: Callable[[], Any], condition=True, args=[], kwargs={}):
        self.function = function
        self.condition = condition
        self.args = args
        self.kwargs = kwargs

    def check(self):
        return self.function(*self.args, **self.kwargs) == self.condition


##
# @class    ExecutionUnit
# @brief    Execution unit for FSM. This contains a function and conditions to start and end the function.
#           This is used to execute a function once when the conditions are met and return the result.
#               - skip_conditions: conditions to skip the function
#               - trigger_conditions: conditions to triger the function
#               - end_conditions: conditions to check if the function is well executed
#               - function: function to execute
#               - repeat: Repeat execution on every call after the trigger_conditions are met once
class ExecutionUnit:
    name: str
    function: Callable
    trigger_conditions: List[ConditionUnit]
    end_conditions: List[ConditionUnit]
    executed: bool
    args: List
    kwargs: Dict
    repeat: bool
    fun_timeout: float  # timeout for end_condition check after function execution
    fun_time: float

    def __init__(self, name=None, function=None,
                 skip_conditions=[], trigger_conditions=[], end_conditions=[],
                 args=[], kwargs={}, repeat=False, fun_timeout=None):
        self.name = name
        self.function = function
        self.skip_conditions = skip_conditions
        self.trigger_conditions = trigger_conditions
        self.end_conditions = end_conditions
        self.executed = False
        self.args = args
        self.kwargs = kwargs
        self.repeat = repeat
        self.result = None
        self.fun_timeout = fun_timeout

    def check_skip(self):
        return all([c.check() for c in self.skip_conditions]) if self.skip_conditions else False

    def check_trigger(self):
        return all([c.check() for c in self.trigger_conditions])

    def check_end(self):
        return all([c.check() for c in self.end_conditions])

    ##
    # @brief    execute the function if the trigger_conditions is met and check the end_conditions.
    # @details  This function will be executed periodically in a outer loop.
    # @return   True if the function is executed and the end_conditions is met.
    def execute(self):
        if self.executed:
            if self.repeat:
                Logger.debug(self.name)
                self.result = self.function(*self.args, **self.kwargs)
            if (self.fun_timeout is not None) and (time.time() - self.fun_time > self.fun_timeout):
                return True
            return self.check_end()
        elif self.check_skip():
            self.fun_time = time.time()
            self.executed = True
        elif self.check_trigger():
            self.executed = True
            if self.fun_timeout is not None:
                self.fun_time = time.time()
            if self.function is not None:
                Logger.debug(self.name)
                self.result = self.function(*self.args, **self.kwargs)
        return False


##
# @class ExecutionSequence
# @brief Execution sequence for FSM.
#        This will be called periodically in a outer loop.
#        This will execute all the execution units in the sequence.
#        This will do the check & execute & check for one execution unit in one call.
class ExecutionSequence:
    units: List[ExecutionUnit]
    worker: int

    def __init__(self, units=None):
        self.units = units
        self.worker = 0

    def execute(self):
        if self.is_finished():
            return True
        elif self.units[self.worker].execute():
            self.worker += 1
        return False

    def is_finished(self):
        return self.worker >= len(self.units)

###########################################
#########  Multi Process Control  #########
###########################################
import psutil


def find_proc_by_cmd(cmd):
    for proc in psutil.process_iter():
        if cmd in " ".join(proc.cmdline()):
            return proc.pid
    return None


def kill_proc_by_cmd(cmd):
    for proc in psutil.process_iter():
        if cmd in " ".join(proc.cmdline()):
            proc.send_signal(signal.SIGINT)
