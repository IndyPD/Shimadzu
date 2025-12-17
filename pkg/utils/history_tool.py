from collections import deque
from enum import Enum
from typing import Callable, Any


class HistoryMark(Enum):
    NONE = 0
    SAVE = 1


##
# @class History
# @brief History logger util class for undo/redo function implementation
class History:
    ##
    # @param fun_backup custom backup function. Should return backup data instance
    # @param fun_load function called to load backup data. Takes return values of fun_backup.
    def __init__(self,
                 fun_backup: Callable[[], Any],
                 fun_load: Callable[..., Any],
                 maxlen=10):
        self.fun_backup = fun_backup
        self.fun_load = fun_load
        self.undo_stack = deque(maxlen=maxlen)
        self.redo_stack = deque(maxlen=maxlen)

    def mark_save(self):
        self.undo_stack.append(HistoryMark.SAVE)

    def check_saved(self):
        return len(self.undo_stack) == 0 or self.undo_stack[-1] == HistoryMark.SAVE

    def make_backup(self):
        self.undo_stack.append(self.fun_backup())
        self.redo_stack.clear()

    def can_undo(self):
        return any([not isinstance(item, HistoryMark) for item in self.undo_stack])

    def can_redo(self):
        return len(self.redo_stack) > 0

    def undo(self):
        if self.can_undo():
            self.redo_stack.append(self.fun_backup())
            while True:
                popped = self.undo_stack.pop()
                if not isinstance(popped, HistoryMark):
                    break
            self.fun_load(popped)
        else:
            raise RuntimeError("No undo action")

    def redo(self):
        if self.can_redo():
            self.undo_stack.append(self.fun_backup())
            self.fun_load(self.redo_stack.pop())
        else:
            raise RuntimeError("No redo action")

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()