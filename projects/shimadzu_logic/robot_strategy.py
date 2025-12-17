import time

from pkg.utils.blackboard import GlobalBlackboard
from .robot_context import *

bb = GlobalBlackboard()

# ----------------------------------------------------
# 1. 범용 FSM 전략
# ----------------------------------------------------

class RobotConnectingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Attempting to connect to robot controller.")
    def operate(self, context: RobotContext) -> RobotEvent:
        if not context.check_violation() & RobotViolation.CONNECTION_TIMEOUT.value:
            return RobotEvent.CONNECTION_SUCCESS
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        
class RobotErrorStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        violation_names = [v.name for v in RobotViolation if v.value & context.violation_code]
        Logger.error(f"Robot Violation Detected: {'|'.join(violation_names)}", popup=True)
    def operate(self, context: RobotContext) -> RobotEvent:
        if not context.check_violation():
            return RobotEvent.RECOVER
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        return RobotEvent.NONE

class RobotRecoveringStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Starting recovery process (SW/HW Reset).")
        # 실제 복구 시퀀스 (ExecutionSequence)를 여기에 설정
    def operate(self, context: RobotContext) -> RobotEvent:
        # if recovery_sequence.execute():
        return RobotEvent.DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        # return RobotEvent.NONE

class RobotStopOffStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Emergency Stop Engaged. Turning off motors.")
    def operate(self, context: RobotContext) -> RobotEvent:
        # 안전하게 모터 전원 차단 후, DONE 이벤트 반환
        return RobotEvent.DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotReadyStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Ready and waiting for commands.")

    def operate(self, context: RobotContext) -> RobotEvent:
        if context.check_violation():
            return RobotEvent.VIOLATION_DETECT
        # TODO: Neuromeka로부터 START_BATCH 명령 대기 로직 추가
        # if bb.get("neuromeka/start_batch"):
        #     return RobotEvent.START_BATCH
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

# ----------------------------------------------------
# 2. 로봇 작업 특화 전략
# ----------------------------------------------------

class RobotToolChangingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Checking/Changing to specimen gripper.")
        # TODO: 툴 교체/확인 명령 전송 (Neuromeka 지시 반영)
    def operate(self, context: RobotContext) -> RobotEvent:
        # if tool_changer.status == 'COMPLETE':
        return RobotEvent.TOOL_CHANGE_COMPLETE
        # if tool_changer.status == 'FAIL':
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        #     context.violation_code |= RobotViolation.TOOL_CHANGE_FAIL.value
        #     return RobotEvent.VIOLATION_DETECT
        # return RobotEvent.NONE

class RobotReadingQRStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to QR reading position and capturing.")
        # TODO: QR 리딩 위치 이동 및 리딩 명령 전송
    def operate(self, context: RobotContext) -> RobotEvent:
        # if qr_scanner.result == 'SUCCESS':
        return RobotEvent.QR_READ_COMPLETE
        # if qr_scanner.result == 'FAIL':
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        #     context.violation_code |= RobotViolation.QR_READ_FAIL.value
        #     return RobotEvent.VIOLATION_DETECT
        # return RobotEvent.NONE

class RobotPickingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Executing Specimen Pick operation.")
        # TODO: 픽업 명령 전송 (좌표: 트레이, 두께측정 장치 등)
    def operate(self, context: RobotContext) -> RobotEvent:
        # if gripper.status == 'PICK_SUCCESS':
        return RobotEvent.PICK_COMPLETE
        # if gripper.status == 'PICK_FAIL':
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        #     context.violation_code |= RobotViolation.GRIPPER_FAIL.value
        #     return RobotEvent.VIOLATION_DETECT
        # return RobotEvent.NONE

class RobotPlacingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Executing Specimen Place operation.")

    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Executing Specimen Place operation.")
        # TODO: 플레이싱 명령 전송 (좌표: 두께측정 장치, 정렬 장치, 시험기 그립 등)
    def operate(self, context: RobotContext) -> RobotEvent:
        # if gripper.status == 'PLACE_SUCCESS':
        return RobotEvent.PLACE_COMPLETE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        # return RobotEvent.NONE

class RobotAligningStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Performing alignment operation.")
        # TODO: 정렬 동작 수행 명령 전송
    def operate(self, context: RobotContext) -> RobotEvent:
        # if alignment_unit.status == 'COMPLETE':
        return RobotEvent.ALIGN_COMPLETE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        # return RobotEvent.NONE

class RobotDisposingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Executing broken specimen disposal.")
        # TODO: 폐기통으로 이동 및 시편 해제 명령 전송
    def operate(self, context: RobotContext) -> RobotEvent:
        # if disposal_sequence.status == 'COMPLETE':
        return RobotEvent.DISPOSE_COMPLETE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        # return RobotEvent.NONE

class RobotMovingToWaitStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to a safe waiting position.")

    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to a safe waiting position.")
        # TODO: 대기 장소 (Wait 1, 2, 3)으로 이동 명령 전송
    def operate(self, context: RobotContext) -> RobotEvent:
        # if robot.motion_status == 'IDLE_AT_WAIT_POS':
        return RobotEvent.MOVE_COMPLETE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass
        # return RobotEvent.NONE