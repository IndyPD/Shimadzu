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
        # Device FSM과 Robot FSM이 모두 READY 상태인지 확인하여 연결 완료 처리
        if context.status.is_connected_all():
            return LogicEvent.CONNECTION_ALL_SUCCESS
        
        Logger.info("Logic: Waiting for all modules to connect...")
        return LogicEvent.NONE

    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicErrorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        violation_names = [v.name for v in LogicViolation if v & context.violation_code]
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
        if bb.get("ui/cmd/auto/tensile") == 1: # ACTION_MAP_TENSIL["start"]
            return LogicEvent.START_AUTO_COMMAND
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
        if bb.get("ui/cmd/auto/tensile") == 1:
            return LogicEvent.START_AUTO_COMMAND
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
        # 하위 FSM(Robot, Device)의 상태를 모니터링하며 전체 공정 시퀀스를 제어합니다.
        # 1. Robot FSM에게 동작 명령을 내리고 완료를 대기합니다.
        # 2. Device FSM에게 동작 명령을 내리고 완료를 대기합니다.
        
        # [예시 시퀀스 제어 로직]
        # if context.robot_fsm.get_state() == RobotState.WAIT_AUTO_COMMAND:
        #     # 다음 로봇 동작 명령 전달 (예: 시편 픽업)
        #     # context.robot_fsm.trigger(RobotEvent.DO_AUTO_MOTION_APPROACH_RACK)
        #     pass

        # TODO: 실제 시퀀스 제어 로직 구현 (Robot Move -> Device Measure -> Robot Move ...)
        # 현재는 시뮬레이션을 위해 공정 완료 이벤트를 즉시 반환합니다.
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicDetermineTaskStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Determining next task.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: 배치 계획에 따라 다음 작업(시편 번호 등) 결정
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicPickSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Picking specimen.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Robot FSM에 시편 픽업 명령 전달 및 완료 대기
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicMeasureThicknessStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Measuring thickness.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Robot/Device FSM 협업하여 두께 측정 수행
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicAlignSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Aligning specimen.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Robot/Device FSM 협업하여 시편 정렬 수행
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicLoadTensileMachineStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Loading tensile machine.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Robot FSM으로 시편 장착, Device FSM으로 그리퍼 체결
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicStartTensileTestStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Starting tensile test.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Device FSM에 시험 시작 명령 전달 및 완료 대기
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicCollectAndDiscardStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Collecting and discarding specimen.")
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Device 그리퍼 해제 후 Robot이 시편 수거하여 폐기함으로 이동
        return LogicEvent.DONE
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicProcessCompleteStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Process complete.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass