import time

from pkg.utils.blackboard import GlobalBlackboard
from .devices_context import *

bb = GlobalBlackboard()

##
# @class ConnectingStrategy
# @brief Strategy for CONNECTING State (기존 WAIT_CONNECTION).
# @details 장치 연결을 시도하고 성공/실패 이벤트를 반환합니다.
class ConnectingStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        # 장치 연결 시도 로직 (Shimadzu, Ext)
        Logger.info("Attempting to connect to devices.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 실제 장치 연결 상태를 확인
        if not context.check_violation() & DeviceViolation.CONNECTION_TIMEOUT.value:
            # 여기서는 연결 성공으로 가정하고 DONE (CONNECTION_SUCCESS) 이벤트 대신 DONE 사용
            # return DeviceEvent.CONNECTION_SUCCESS 
            return DeviceEvent.DONE # FSM 호환을 위해 DONE 사용
        
        # 위반이 감지되면 ERROR로 전환 요청
        if context.check_violation():
            return DeviceEvent.VIOLATION_DETECT
            
        return DeviceEvent.NONE

    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass


##
# @class ErrorStrategy
# @brief Strategy for ERROR State (기존 VIOLATED).
class ErrorStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        violation_names = [violation.name for violation in DeviceViolation if violation.value & context.violation_code]
        # Logger.error(f"Violation Detected: "
        #              f"{'|'.join(violation_names)}", popup=True)

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 위반 코드가 해제되면 복구 이벤트 발생
        if not context.check_violation():
            return DeviceEvent.RECOVER
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass


##
# @class RecoveringStrategy
# @brief Strategy for RECOVERING State.
# @details 소프트 리셋: 에러 케이스에 따라 SW 리셋
class RecoveringStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        self.exec_seq = ExecutionSequence([
            ExecutionUnit("SW Recover", function=bb.set, args=("recover/sw/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/sw/done",), condition=1)),
            ExecutionUnit("HW Recover", function=bb.set, args=("recover/hw/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/hw/done",), condition=1)),
            ExecutionUnit("HW Reboot", function=bb.set, args=("recover/reboot/trigger", True),
                          end_conditions=ConditionUnit(bb.get, args=("recover/reboot/done",), condition=1)),
        ])

    def operate(self, context: DeviceContext) -> DeviceEvent:
        if self.exec_seq.execute():
            return DeviceEvent.DONE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

##
# @class StopOffStrategy
# @brief Strategy for STOP_AND_OFF State.
# @details 소프트 리셋: 장치 정지 및 전원 차단
class StopOffStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        self.exec_seq = ExecutionSequence([
            ExecutionUnit("Stop", function=Logger.info, args=("stopped",)),
            ExecutionUnit("Off", function=Logger.info,
                          args=("turned off",),
                          end_conditions=ConditionUnit(
                              lambda: context.check_violation() & DeviceViolation.ISO_EMERGENCY_BUTTON.value
                          ))
        ])

    def operate(self, context: DeviceContext) -> DeviceEvent:
        if self.exec_seq.execute():
            return DeviceEvent.DONE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass


##
# @class ReadyStrategy
# @brief Strategy for READY State (기존 IDLE).
# @details 대기 및 모니터링 상태. 시험 시작 명령을 대기합니다.
class ReadyStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Ready and waiting for commands.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        if context.check_violation():
            return DeviceEvent.VIOLATION_DETECT
            
        # 작업자의 START_COMMAND 대기 로직이 여기에 추가되어야 함
        # 예시: if bb.get("user/start_request"): return DeviceEvent.START_COMMAND
        
        # 수동 장비 제어 테스트 로직
        manual_cmd = bb.get("manual/device/tester")
        if manual_cmd and manual_cmd > 0:
            Logger.info(f"[Device] Manual Test Command Executed: {manual_cmd}")
            
            if manual_cmd == 1:
                context.chuck_open()
            elif manual_cmd == 2:
                context.chuck_close()
            elif manual_cmd == 3:
                context.EXT_move_forword()
            elif manual_cmd == 4:
                context.EXT_move_backward()
            elif manual_cmd == 5:
                context.EXT_stop()
            elif manual_cmd == 6:
                context.align_push()
            elif manual_cmd == 7:
                context.align_pull()
            elif manual_cmd == 8:
                context.align_stop()
            elif manual_cmd == 9:
                context.get_dial_gauge_value()
            elif manual_cmd == 10:
                context.smz_are_you_there()
            elif manual_cmd == 11:
                context.smz_ask_sys_status()
            
            # 명령 실행 후 초기화
            bb.set("manual/device/tester", 0)

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass


## ----------------------------------------------------
## 시험 공정 전략 (FSM 규칙에 맞추어 추가됨)
## ----------------------------------------------------

class WaitCommandStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Waiting for process start command.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # Logic FSM 등 상위에서 START_COMMAND를 주면 전이
        # if bb.get("device/start_command"):
        #     return DeviceEvent.START_COMMAND
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class ReadQRStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Reading QR Code.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # QR 리딩 로직 수행
        # 성공 시:
        return DeviceEvent.QR_READ_DONE
        # 실패 시: return DeviceEvent.QR_READ_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class MeasureThicknessStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Measuring Thickness.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 게이지 측정 로직
        return DeviceEvent.THICKNESS_MEASURE_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class AlignerOpenStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Opening Aligner.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.ALIGNER_OPEN_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class AlignerActionStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Operating Aligner.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.ALIGNER_ACTION_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class GripperMoveDownStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Moving Gripper Down.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.GRIPPER_MOVE_DOWN_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class GripperGripStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Gripping Specimen.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.GRIPPER_GRIP_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class RemovePreloadStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Removing Preload.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.REMOVE_PRELOAD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class ExtensometerForwardStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Moving Extensometer Forward.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.EXTENSOMETER_FORWARD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class StartTensileTestStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Starting Tensile Test.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 시험 완료 대기
        return DeviceEvent.TENSILE_TEST_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class ExtensometerBackwardStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Moving Extensometer Backward.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.EXTENSOMETER_BACKWARD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

class GripperReleaseStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Device: Releasing Gripper.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.GRIPPER_RELEASE_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass