from pkg.fsm.base import *


class MyState(OpState):
    INACTIVE = INACTIVE_STATE

    SYSTEM_OP       = 0x100             # SYSTEM OPERATION
    WAIT_CONNECTION = SYSTEM_OP | 0x01  # Waiting for Connection
    VIOLATED        = SYSTEM_OP | 0x21  # Violation detected from STEP Moby
    RECOVERING      = SYSTEM_OP | 0x22  # Recovering from violation
    STOP_AND_OFF    = SYSTEM_OP | 0x23  # Recovering from violation

    MOTION_OP       = 0x200             # MOTION OPERATION
    IDLE            = MOTION_OP | 0x01  # IDLE
    MOVING          = MOTION_OP | 0x02  # Moving


class MyEvent(OpEvent):
    NONE = NONE_EVENT
    DONE                = 1  # DONE to IDLE

    MOVE                = 11  # trigger Move Command
    STOP_EMG            = 12  # Stop EMG
    STOP_MOTION         = 16  # Stop Motion

    VIOLATION_DETECT    = 21  # Violation Detected

    RECOVER             = 31  # start recover


class MyViolation(ViolationType):
    NONE = 0x00

    SW_VIOLATION = 0x01
    SW_FAILURE_UNDEFINED =      SW_VIOLATION << 1  # Tried to connect when is_connected flag is not set

    ISO_VIOLATION =             SW_VIOLATION << 2
    ISO_EMERGENCY_BUTTON =      ISO_VIOLATION << 1  # Safety Guard Input 2*/

    HW_VIOLATION =              ISO_VIOLATION << 2
    HW_NOT_READY =              HW_VIOLATION << 1  # is_ready was fail
    HW_ROBOTSPECS_ERROR =       HW_VIOLATION << 2  #EMERG_ROBOTSPEC_READ_FAILED
    HW_CONNECTION_LOST =        HW_VIOLATION << 3  #EMERG_CONNECTION_LOST
    HW_LOW_BATTERY =            HW_VIOLATION << 4
    HW_MOTOR_STATUS_ERROR =     HW_VIOLATION << 5  #EMERG_MOTOR_STATUS_ERROR
    HW_MOTOR_LOW_BATTERY =      HW_VIOLATION << 6  #EMERG_MOTOR_STATUS_ERROR
    HW_MOTOR_FIRMWARE_ERROR =   HW_VIOLATION << 7  #EMERG_MOTOR_FIRMWARE_ERROR
    RT_TASK_TIME_LIMIT =        HW_VIOLATION << 8
    SOFT_RECOVERY_FAILED =      HW_VIOLATION << 9

    UNKNOWN_VIOLATION =         HW_VIOLATION << 10