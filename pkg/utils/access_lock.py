from threading import Lock
from typing import Callable, Any, List, Dict


##
# @class BundleLock
# @brief Handle a bundle of locks as one
class BundleLock:
    locks: List  # list of Locks

    def __init__(self, locks):
        self.locks = locks

    def locked(self):
        return any([lock.locked() for lock in self.locks])

    def acquire(self, blocking=True, timeout=-1):
        results = [lock.acquire(blocking=blocking, timeout=timeout) for lock in self.locks]
        if all(results):
            return True
        else:
            for res, lock in zip(results, self.locks):
                if res:
                    lock.release()
            return False

    def release(self):
        for lock in self.locks:
            try:
                lock.release()
            except Exception as e:
                print(e)

    __enter__ = acquire

    def __exit__(self, t, v, tb):
        self.release()


##
# @class TaggedLock
# @brief Lock with Holder Tag and finish callback
# @remark
#       Usage: with lock(HOLDER_KEY, callback, args, kwargs, blocking, timeout):
#       or lock.acquire(HOLDER_KEY, callback, args, kwargs, blocking, timeout)
#       Raise TimeoutError if timeout in with context
#       release returns False if timeout
class TaggedLock:
    params: List  # reserved list of holder, callback, args, kwargs, blocking, timeout
    holder: Any
    callback: Callable[..., Any]
    args: List
    kwargs: Dict
    output: Any

    def __init__(self, holder=None, callback: Callable[..., Any] = None, args=[], kwargs={}, blocking=True, timeout=-1,
                 lock=None):
        self._lock = Lock() if lock is None else lock
        self.output = None
        self(holder, callback, args, kwargs, blocking, timeout)

    def __call__(self, holder=None, callback: Callable[..., Any] = None, args=[], kwargs={}, blocking=True, timeout=-1):
        self.params = [holder, callback, args, kwargs, blocking, timeout]
        return self

    ##
    # @param holder     id_col for the lock holder
    # @param callback   callback to call when lock is released
    # @param args       arguments for the callback
    # @param kwargs     keyword arguments for the callback
    def acquire(self, holder, callback: Callable[..., Any] = None, args=[], kwargs={}, blocking=True, timeout=-1):
        if self._lock.acquire(blocking=blocking, timeout=timeout):
            self.holder = holder
            self.callback = callback
            self.args = args
            self.kwargs = kwargs
            return True
        else:
            return False

    def release(self):
        self._lock.release()
        self.output = None
        if self.callback is not None:
            self.output = self.callback(*self.args, **self.kwargs)
        self()  # clear callback
        return self.output

    def locked(self):
        return self._lock.locked()

    def __enter__(self):
        if not self.acquire(*self.params):
            raise TimeoutError("Failed to lock {}: Occupied by {}".format(self.params[0], self.holder))

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


##
# @class BypassLock
# @brief Bypass lock with a with: block
class BypassLock:
    def __init__(self, lock, callback: Callable[..., Any] = None, args=[], kwargs={}):
        self.lock = lock
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        self.lock.release()

    def __exit__(self, type, value, traceback):
        self.lock.acquire()
        self.callback(*self.args, **self.kwargs)
