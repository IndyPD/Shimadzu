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
            
        # 작업자 UI로부터 시험 시작 명령 대기
        # if bb.get("operator/start_request") and context.status.is_batch_planned():
        #     return LogicEvent.START_BATCH_COMMAND
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

# ----------------------------------------------------
# 2. Logic 배치 시퀀스 전략
# ----------------------------------------------------

class LogicPreparingBatchStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Starting Batch Preparation (Initial check and tool change).")
        # TODO: 1. Device 상태 확인 (ARE_YOU_THERE) 2. Robot에게 Tool Changing 명령 (RobotEvent.START_BATCH)
    
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Device READY와 Robot READY 응답을 모니터링
        # if check_device_ready() and check_robot_ready():
        return LogicEvent.PREP_COMPLETE
        # return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicSupplyingSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Starting Specimen Supply (QR, thickness, alignment).")
        # TODO: Robot FSM에게 픽업 및 측정 시퀀스 명령 전송
        # (RobotEvent.QR_READ_COMPLETE, RobotEvent.PLACE_COMPLETE 등을 모니터링하여 Device FSM에게 GRIP 명령 순차 전달)
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: 시편이 시험기에 장착 완료되고, Device FSM이 REGISTRATION_COMPLETE 이벤트 발생 시
        # if is_specimen_gripped_and_registered():
        return LogicEvent.SUPPLY_COMPLETE
        # return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicTestingSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Starting Tensile Testing (Preload, Test execution).")
        # TODO: Device FSM에게 PRELOAD 및 START_ANA 명령 순차 전송
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Device FSM으로부터 TEST_COMPLETE 이벤트 수신 시
        # if context.device_fsm.has_event(DeviceEvent.TEST_COMPLETE):
        return LogicEvent.TEST_COMPLETE
        # return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicCollectingSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Coordinating Specimen Collection (Extensometer back, Ungripping, Dispose).")
        # TODO: Device FSM에게 EXT_BACK 및 GRIP_OPEN 명령 전송, Robot FSM에게 DISPOSING 명령 전송
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: Robot FSM으로부터 DISPOSE_COMPLETE 이벤트 수신 시
        # if context.robot_fsm.has_event(RobotEvent.DISPOSE_COMPLETE):
        return LogicEvent.COLLECT_COMPLETE
        # return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass

class LogicBatchCompleteStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        Logger.info("Logic: Single Specimen Batch Cycle Complete. Checking for next specimen.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        # TODO: 다음 시편 존재 여부 확인 로직
        # if next_specimen_exists():
        #     return LogicEvent.START_BATCH_COMMAND # 다음 시편으로 루프 복귀
        return LogicEvent.BATCH_FINISHED # 전체 배치 종료 통보
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        pass