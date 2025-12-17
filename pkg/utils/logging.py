import os
import sys
import datetime
import time
import cgitb
from collections import deque
from enum import Enum
from typing import List, Union, Tuple

from .file_io import *
from .singleton import SingletonMeta

REL_LOG_DIR = 'LOG'
LOG_DIR = os.path.join(get_proj_path(), REL_LOG_DIR)
DIR_API_LOG = os.path.join(get_proj_path(), "local/api_log")
create_dir(LOG_DIR)
create_dir(DIR_API_LOG)
MAX_LOG_NUM = 50
MAX_LOG_SIZE_BYTES = 1000000
LOG_QUEUE_RESULT_KEY_IS_NEW_FILE = "is_new_file"
LOG_QUEUE_RESULT_KEY_QUEUE = "queue"
LOG_QUEUE_RESULT_KEY_NEXT_SEEK_INDEX = "nextSeekIndex"


class LogLevel(Enum):
    FATAL = 0
    ERROR = 1
    WARN = 2
    INFO = 3
    DEBUG = 4
    TRACE = -1


LOG_LEVEL_DEFAULT = LogLevel.INFO


def get_error_info():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if exc_tb is not None:
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        return exc_type, fname, exc_tb.tb_lineno
    else:
        return "", "", 0


def get_log_list():
    file_list = os.listdir(LOG_DIR)
    log_list = sorted([item for item in file_list if item.endswith('.log')])
    trash_list = sorted(set(file_list) - set(log_list))
    return log_list, trash_list


def clear_trash():
    log_list, trash_list = get_log_list()
    for trash in trash_list:
        try:
            os.remove(os.path.join(LOG_DIR, trash))
        except Exception as e:
            Logger.error("[Error in Logger] removing trash file - " + str(e))


def regulate_log_number():
    while True:
        log_list, trash_list = get_log_list()

        if len(log_list) < MAX_LOG_NUM:
            break
        else:
            try:
                os.remove(os.path.join(LOG_DIR, log_list[0]))
            except Exception as e:
                Logger.error("[Error in Logger] removing old log - " + str(e))


class Logger(metaclass=SingletonMeta):
    __last_poke_time: float = time.time()
    _file_name: str
    _file_path: str

    LOG_API = False

    def __init__(self):
        self.log_level = LOG_LEVEL_DEFAULT
        self._log_file = None
        self.popup_queue = deque(maxlen=10)
        self.popup_idx = 0
        self.popup_last = 0
        self.language = 'ENGLISH'

        self.open_new_log()

    def open_new_log(self):
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception as e:
                print("[Error in Logger] closing new log file" + str(e))
            self._log_file = None

        while True:
            clear_trash()
            regulate_log_number()
            self._file_name = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S.log')
            self._file_path = os.path.join(LOG_DIR, self._file_name)
            try:
                self._log_file = open(self._file_path, 'w')
                break
            except Exception as e:
                print("[Error in Logger] creating new log file")
                time.sleep(0.1)

    def __del__(self):
        try:
            self._log_file.close()
        except Exception as e:
            print("[Error in Logger] closing new log file" + str(e))
        self._log_file = None
        clear_trash()

    def set_instance_log_level(self, level: LogLevel):
        self.log_level = level

    def print_log(self, level: LogLevel, _format: str, *args, popup=False, **kwargs):
        if level.value <= self.log_level.value:
            if len(args) > 0:
                for arg in args:
                    _format = _format + f" {arg}"
            if len(kwargs) > 0:
                _format = _format + f" {kwargs}"
            self.save_log(level, _format)
            print(_format)
            if popup:
                self.popup_idx += 1
                self.popup_queue.append((self.popup_idx, level, _format))

    def save_log(self, level: LogLevel, message):
        if os.path.getsize(self._file_path) > MAX_LOG_SIZE_BYTES:
            self.open_new_log()
        save_msg = datetime.datetime.now().strftime(f'[%Y-%m-%d|%H:%M:%S]{f"[{level.name}]":8}')+message
        self._log_file.write(save_msg + "\n")
        self._log_file.flush()

    def __get_log_queue(self, seek_index=0, default_buffer_size=1024 * 1024, pass_informal=False):
        result = {
            LOG_QUEUE_RESULT_KEY_IS_NEW_FILE: False,
            LOG_QUEUE_RESULT_KEY_QUEUE: [],
            LOG_QUEUE_RESULT_KEY_NEXT_SEEK_INDEX: 0
        }
        try:
            with open(self._file_path, 'r') as log_read:
                log_read.seek(seek_index)
                total_read_bytes = seek_index
                read_lines = []
                is_new_file = False
                while True:
                    read_line = log_read.read(default_buffer_size)
                    read_bytes = len(read_line)
                    total_read_bytes += read_bytes
                    if read_bytes > 0:
                        while pass_informal and "[TRACE]" in read_line:
                            trace_start_idx = read_line.find("[TRACE]") - 22
                            trace_end_idx_set = [read_line[trace_start_idx+30:].find("[%s]" % tag) 
                                                 for tag in LogLevel.__members__]
                            trace_end_idx_set = list(filter(lambda x: x != -1, trace_end_idx_set))
                            trace_end_idx = (trace_start_idx+8+min(trace_end_idx_set)) if trace_end_idx_set else -1
                            read_line = read_line[:trace_start_idx]+read_line[trace_end_idx:]
                        read_lines.append(read_line)
                    if read_bytes < default_buffer_size:
                        if seek_index != 0 and len(read_lines) == 0\
                                and seek_index > os.path.getsize(self._file_path):
                            result = self.__get_log_queue(0, default_buffer_size)
                            result[LOG_QUEUE_RESULT_KEY_IS_NEW_FILE] = True
                            is_new_file = True
                        break

                if not is_new_file:
                    read_lines = "".join(read_lines).split("\n")
                    length = len(read_lines)

                    if length > 0 and len(read_lines[-1]) == 0:
                        read_lines = read_lines[:-1]

                    result[LOG_QUEUE_RESULT_KEY_QUEUE] = read_lines
                    result[LOG_QUEUE_RESULT_KEY_NEXT_SEEK_INDEX] = total_read_bytes
        except Exception as err:
            self.error(err)
        return result

    @classmethod
    def get_log_queue(cls, seek_index=0, default_buffer_size=1024 * 1024, pass_informal=False):
        return cls().__get_log_queue(seek_index, default_buffer_size, pass_informal=pass_informal)

    @classmethod
    def set_log_level(cls, level: Union[int, LogLevel]):
        if isinstance(level, LogLevel):
            cls().set_instance_log_level(level)
        elif isinstance(level, int):
            cls().set_instance_log_level({level.value: level for level in LogLevel}[level])

    @classmethod
    def get_log_level(cls) -> LogLevel:
        return cls().log_level

    @classmethod
    def log(cls, level: LogLevel, _format: str, *args, popup=False, **kwargs):
        cls().print_log(level, _format, *args, popup=popup, **kwargs)

    @classmethod
    def fatal(cls, _format, *args, popup=False, **kwargs):
        exc_type, exc_file, exc_line = get_error_info()
        cls.log(LogLevel.FATAL, 
                "[FATAL] %s, %i : %s" % (exc_file, exc_line, str(_format)), *args, popup=popup, **kwargs)
        try:
            cls.log(LogLevel.TRACE, "[TRACE] "+get_trace_info())
        except Exception as e:
            exit(-1)
            pass

    @classmethod
    def error(cls, _format, *args, popup=False, **kwargs):
        cls.log(LogLevel.ERROR, str(_format), *args, popup=popup, **kwargs)

    @classmethod
    def warn(cls, _format, *args, popup=False, **kwargs):
        cls.log(LogLevel.WARN, str(_format), *args, popup=popup, **kwargs)

    @classmethod
    def info(cls, _format, *args, popup=False, **kwargs):
        cls.log(LogLevel.INFO, str(_format), *args, popup=popup, **kwargs)

    @classmethod
    def debug(cls, _format, *args, popup=False, **kwargs):
        cls.log(LogLevel.DEBUG, str(_format),  *args, popup=popup, **kwargs)

    @classmethod
    def log_error_trace(cls):
        cls.log(LogLevel.TRACE, get_trace_info())

    ##
    # @param print_fun Logger.{error, warn,info, debug}
    @classmethod
    def make_format_logger(cls, print_fun, statement):
        def log_error(error):
            print_fun(statement + " : " + str(error))
        return log_error

    @classmethod
    def timecheck(cls, func):
        def decorated(*args, **kwargs):
            t1 = time.time()
            res = func(*args, **kwargs)
            t2 = time.time()
            cls.debug(func.__name__+' elapsed time: ' + str((t2-t1)*1000) + 'ms')
            return res

        return decorated

    @classmethod
    def poke(cls, func):
        def decorated(*args, **kwargs):
            cls.__last_poke_time = time.time()
            return func(*args, **kwargs)

        return decorated

    @classmethod
    def update_poke_time(cls):
        cls.__last_poke_time = time.time()

    ##
    # @return seconds
    @classmethod
    def get_idle_time(cls):
        return time.time() - cls.__last_poke_time

    @classmethod
    def get_popup_log(cls, seek_index: int = 0) -> Tuple[int, List[Tuple[LogLevel, str]]]:
        update_last = True
        if seek_index < 0:
            update_last = False
            seek_index = cls().popup_last
        popup_queue = cls().popup_queue
        seek_to = seek_index
        out_que = []
        for idx, level, msg in reversed(popup_queue):
            if idx > seek_index:
                if idx > seek_to:
                    seek_to = idx
                out_que.insert(0, (level, msg))
        if update_last:
            cls().popup_last = seek_to
        return seek_to, out_que

    @classmethod
    def set_api_log(cls, onoff):
        cls.LOG_API = onoff

    @classmethod
    def log_api(cls, func):
        def decorated(self, request, content):
            output = func(self, request, content)
            if cls.LOG_API:
                try:
                    save_pickle(
                        os.path.join(DIR_API_LOG,
                                     datetime.datetime.now().strftime(f'%Y-%m-%d_%H-%M-%S_{func.__name__}.api')),
                        dict(function=func.__name__,
                             request=request.SerializeToString(),
                             request_type=f"{request.__class__.__module__}.{request.__class__.__name__}",
                             output=output.SerializeToString(),
                             output_type=f"{output.__class__.__module__}.{output.__class__.__name__}")
                    )
                except Exception as e:
                    Logger.error(f"Error in logging api for {func}")
                    Logger.error(str(e))
            return output
        return decorated


def get_trace_info():
    return cgitb.text(sys.exc_info())
