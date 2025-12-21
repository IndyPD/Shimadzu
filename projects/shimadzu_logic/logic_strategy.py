import time

from pkg.utils.blackboard import GlobalBlackboard
from .logic_context import *

bb = GlobalBlackboard()

# ----------------------------------------------------
# 1. 범용 FSM 전략
# ----------------------------------------------------

class LogicConnectingStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Starting connection checks for all modules (Device & Robot).")

    def operate(self, context: LogicContext) -> LogicEvent:
        if not context.status.is_connected_all():
            # TODO: Device FSM과 Robot FSM의 CONNECTING 상태를 모니터링하고 성공/실패 이벤트 반환
            # if context.device_fsm.get_state() == DeviceState.READY and context.robot_fsm.get_state() == RobotState.READY:
            #     context.status.is_connected_all.up()
            #     return LogicEvent.CONNECTION_ALL_SUCCESS
            # 임시로 DONE 이벤트 반환
            Logger.info("Logic: All modules connected successfully.")
            return LogicEvent.CONNECTION_ALL_SUCCESS
        Logger.info("Logic: Waiting for all modules to connect...")
        return LogicEvent.NONE

    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicErrorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        violation_names = [v.name for v in LogicViolation if v.value & context.violation_code]
        Logger.error(f"Logic Critical Violation Detected: {'|'.join(violation_names)}", popup=True)
        # TODO: 모든 서브 모듈에 정지/에러 명령 전파
    def operate(self, context: LogicContext) -> LogicEvent:
        if not context.check_violation():
            return LogicEvent.RECOVER
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicRecoveringStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Coordinating full system recovery.")
        # TODO: Device FSM과 Robot FSM에 복구 명령을 순차적으로 전송
    def operate(self, context: LogicContext) -> LogicEvent:
        # if sub_module_recovery_complete:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass
        # return LogicEvent.NONE

class LogicStopOffStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Emergency Stop - Coordinating full system shutdown.")
        # TODO: 모든 서브 모듈에 Stop/Off 명령 전파
    def operate(self, context: LogicContext) -> LogicEvent:
        # if shutdown_complete:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass
        # return LogicEvent.NONE

class LogicIdleStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: System Idle and waiting for batch start command.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        if context.check_violation():
            return LogicEvent.VIOLATION_DETECT
            
        # 자동화 모드 진입 명령 대기
        # if bb.get("ui/auto_mode_start"):
        #     return LogicEvent.START_AUTO_COMMAND
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

# ----------------------------------------------------
# 2. Logic 배치 시퀀스 전략
# ----------------------------------------------------

class LogicWaitCommandStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Waiting for batch start command.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        # if bb.get("ui/start_batch"):
        #     return LogicEvent.START_AUTO_COMMAND
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicRegisterProcessInfoStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Registering process info.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # DB/MES 등록 로직
        return LogicEvent.REGISTRATION_DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicCheckDeviceStatusStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Checking device status.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # 장비 상태 확인 로직
        return LogicEvent.STATUS_CHECK_DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicWaitProcessStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Waiting for process start.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.PROCESS_START
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicRunProcessStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Running process loop.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        # 하위 FSM 제어 및 모니터링
        return LogicEvent.PROCESS_FINISHED
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicProcessCompleteStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Process complete.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass