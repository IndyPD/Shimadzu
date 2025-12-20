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
        # if bb.get("robot/start_auto"):
        #     return RobotEvent.PROGRAM_AUTO_ON_DONE
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

# ----------------------------------------------------
# 2. 로봇 작업 특화 전략
# ----------------------------------------------------

class RobotProgramAutoOnStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Turning on Auto Mode.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.PROGRAM_AUTO_ON_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotProgramManualOffStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Turning off Auto Mode (Manual).")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.PROGRAM_MANUAL_OFF_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotWaitAutoCommandStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Waiting for auto process start command.")
    def operate(self, context: RobotContext) -> RobotEvent:
        # if bb.get("robot/start_process"):
        #     return RobotEvent.START_PROCESS
        return RobotEvent.NONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotMoveHomeStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to Home.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_MOVE_HOME_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotToolChangeStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Changing Tool.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_TOOL_CHANGE_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachRackStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Rack.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_RACK_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotAutoGripperOpenStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Opening Gripper.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_GRIPPER_OPEN_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotAutoGripperCloseStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Closing Gripper.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_GRIPPER_CLOSE_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotMoveToQRStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to QR Position.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_MOVE_TO_QR_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachPickStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Pick Position.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_PICK_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotPickSpecimenStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Picking Specimen.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_PICK_SPECIMEN_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromTrayStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Tray.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_TRAY_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromRackStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Rack.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_RACK_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachThicknessStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Thickness Gauge.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_THICKNESS_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterThicknessPos1Strategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 1.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_1_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterThicknessPos2Strategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 2.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_2_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterThicknessPos3Strategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 3.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_3_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromThicknessStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Thickness Gauge.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_THICKNESS_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachAlignerStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Aligner.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_ALIGNER_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterAlignerStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Aligner.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_ALIGNER_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromAlignerStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Aligner.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_ALIGNER_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachTensileStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Tensile Machine.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_TENSILE_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterTensileStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Tensile Machine.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_TENSILE_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromTensileStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Tensile Machine.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_TENSILE_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotApproachScrapStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Scrap Box.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_APPROACH_SCRAP_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotEnterScrapStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Scrap Box.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_ENTER_SCRAP_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass

class RobotRetractFromScrapStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Scrap Box.")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.AUTO_MOTION_RETRACT_FROM_SCRAP_DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        pass