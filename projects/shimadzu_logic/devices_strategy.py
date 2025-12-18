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

# 기존 MovingStrategy는 삭제하고, 공정별 Strategy로 대체
# DeviceState.GRIPPING_SPECIMEN 에 대한 전략
class GrippingSpecimenStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending GRIP_CLOSE command to Shimadzu.")
        # TODO: Shimadzu에 GRIP_CLOSE 명령 전송 로직 구현

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # GRIP_CLOSE 완료 응답/타임아웃 대기
        # if shimadzu.check_status('GRIP_CLOSED'):
        #     return DeviceEvent.GRIP_CLOSE_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

# DeviceState.EXT_FORWARD 에 대한 전략
class ExtForwardStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending EXT_FORWARD command to Extensometer Unit.")
        # TODO: Ext에 신율계 전진 명령 전송 로직 구현
        
    def operate(self, context: DeviceContext) -> DeviceEvent:
        # Ext 전진 완료 응답/타임아웃 대기
        # if ext.check_status('FORWARD_COMPLETE'):
        #     return DeviceEvent.EXT_FORWARD_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass
        
# DeviceState.PRELOADING 에 대한 전략
class PreloadingStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending ASK_PRELOAD command to Shimadzu.")
        # TODO: Shimadzu에 초기 하중 제거 명령 전송 로직 구현

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # PRELOAD 완료 응답/타임아웃 대기
        # if shimadzu.check_status('PRELOAD_COMPLETE'):
        #     return DeviceEvent.PRELOAD_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

# DeviceState.TESTING 에 대한 전략
class TestingStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending START_ANA command to Shimadzu (Testing starts).")
        # TODO: Shimadzu에 인장 시험 시작 명령 전송 로직 구현

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 시험 완료(ANA_RESULT) 대기
        # if shimadzu.check_status('TEST_COMPLETE'):
        #     return DeviceEvent.TEST_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

# DeviceState.EXT_BACK 에 대한 전략
class ExtBackStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending EXT_BACK command to Extensometer Unit.")
        # TODO: Ext에 신율계 후진 명령 전송 로직 구현

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # Ext 후진 완료 응답/타임아웃 대기
        # if ext.check_status('BACK_COMPLETE'):
        #     return DeviceEvent.EXT_BACK_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass

# DeviceState.UNGRIPPING_SPECIMEN 에 대한 전략
class UngrippingSpecimenStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        Logger.info("Sending GRIP_OPEN command to Shimadzu.")
        # TODO: Shimadzu에 GRIP_OPEN 명령 전송 로직 구현

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # GRIP_OPEN 완료 응답/타임아웃 대기
        # if shimadzu.check_status('GRIP_OPEN_COMPLETE'):
        #     return DeviceEvent.GRIP_OPEN_COMPLETE
        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        pass