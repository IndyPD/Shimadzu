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
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ConnectingStrategy")
        Logger.info("[device] Attempting to connect to devices.")
        # 컨텍스트에서 활성화된 장치 목록을 가져옵니다.
        self.dev_gauge_enable = context.dev_gauge_enable
        self.dev_remoteio_enable = context.dev_remoteio_enable
        self.dev_smz_enable = context.dev_smz_enable
        self.dev_qr_enable = context.dev_qr_enable

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 각 장치의 통신 상태를 블랙보드에서 직접 확인합니다.
        remote_io_ok = True if not self.dev_remoteio_enable else int(bb.get("device/remote/comm_status") or 0) == 1
        gauge_ok = True if not self.dev_gauge_enable else int(bb.get("device/gauge/comm_status") or 0) == 1
        qr_ok = True if not self.dev_qr_enable else int(bb.get("device/qr/comm_status") or 0) == 1
        shimadzu_ok = True if not self.dev_smz_enable else int(bb.get("device/shimadzu/comm_status") or 0) == 1

        all_connected = all([remote_io_ok, gauge_ok, qr_ok, shimadzu_ok])

        if all_connected:
            Logger.info("[device] All enabled devices connected successfully.")
            return DeviceEvent.CONNECTION_SUCCESS

        # 어떤 모듈의 연결이 실패했는지 상세 로그를 남깁니다.
        status_report = []
        if self.dev_remoteio_enable:
            status_report.append(f"RemoteIO: {'OK' if remote_io_ok else 'FAIL'}")
        if self.dev_gauge_enable:
            status_report.append(f"Gauge: {'OK' if gauge_ok else 'FAIL'}")
        if self.dev_qr_enable:
            status_report.append(f"QR: {'OK' if qr_ok else 'FAIL'}")
        if self.dev_smz_enable:
            status_report.append(f"Shimadzu: {'OK' if shimadzu_ok else 'FAIL'}")

        Logger.info(f"[device] Waiting for devices to connect... Status: [{', '.join(status_report)}]")
        
        # 연결 대기 중 다른 위반 사항이 있는지 확인 (예: 비상정지)
        if context.check_violation():
            return DeviceEvent.VIOLATION_DETECT
            
        return DeviceEvent.NONE
            
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ConnectingStrategy with event: {event}")


##
# @class ErrorStrategy
# @brief Strategy for ERROR State (기존 VIOLATED).
class ErrorStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ErrorStrategy")
        # The context.violation_code should already be set by the check that triggered the VIOLATION_DETECT event.
        violation_names = [v.name for v in DeviceViolation if v & context.violation_code]
        Logger.error(f"[device] Violation Detected: {'|'.join(violation_names)}")
        # This strategy now passively waits for an external RECOVER event.
        # The recovery logic is moved to RecoveringStrategy.

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 오류 발생 시 외부 명령 없이 자동으로 복구 상태로 전환합니다.
        return DeviceEvent.RECOVER
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ErrorStrategy with event: {event}")

##
# @class RecoveringStrategy
# @brief Strategy for RECOVERING State.
# @details 소프트 리셋: 에러 케이스에 따라 SW 리셋
class RecoveringStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter RecoveringStrategy. Attempting to resolve violations.")
        # The violation code that led to the ERROR state is still in context.violation_code
        self.violation_to_recover = context.violation_code
        self.reconnect_attempted = False

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 1. 통신 오류인 경우, 자동으로 재연결을 1회 시도합니다.
        if not self.reconnect_attempted:
            self.reconnect_attempted = True  # 재연결은 상태 진입 시 1회만 시도
            
            # 재연결이 필요한 통신 오류가 있는지 확인
            is_comm_error = any([
                self.violation_to_recover & DeviceViolation.REMOTE_IO_COMM_ERR,
                self.violation_to_recover & DeviceViolation.GAUGE_COMM_ERR,
                self.violation_to_recover & DeviceViolation.QR_COMM_ERR
            ])
            Logger.info(f"REMOTE ERROR Std Value : {DeviceViolation.REMOTE_IO_COMM_ERR}")
            Logger.info(f"GAUGE ERROR Std Value : {DeviceViolation.GAUGE_COMM_ERR}")
            Logger.info(f"QR ERROR Std Value : {DeviceViolation.QR_COMM_ERR}")
            Logger.info(f"Detail Error : {self.violation_to_recover}")
            if is_comm_error:
                Logger.info("[device] [Recovery] Communication error detected, attempting auto-reconnection...")
                if self.violation_to_recover & DeviceViolation.REMOTE_IO_COMM_ERR:
                    Logger.info(f"[device] Try Remote IO Reconnect.")
                    if context.reconnect_remote_io() :
                        Logger.info(f"[device] Remote IO Reconnected.")
                    else:
                        Logger.error(f"[device] Failed to reconnect Remote IO.")
                
                if self.violation_to_recover & DeviceViolation.GAUGE_COMM_ERR:
                    Logger.info(f"[device] Try Gauge Reconnect.")
                    if context.reconnect_gauge() :
                        Logger.info(f"[device] Gauge Reconnected.")
                    else:
                        Logger.error(f"[device] Failed to reconnect Gauge.")

                if self.violation_to_recover & DeviceViolation.QR_COMM_ERR:
                    Logger.info(f"[device] Try QR Reconnect.")
                    if context.reconnect_qr() :
                        Logger.info(f"[device] QR Reconnected.")
                    else:
                        Logger.error(f"[device] Failed to reconnect QR.")
                
                Logger.info("[device] [Recovery] Auto-reconnection attempt finished. Re-evaluating status in the next cycle.")
                time.sleep(5.0) # 재연결 후 상태가 업데이트될 시간을 줍니다.
                # 다음 사이클에서 check_violation을 다시 호출하도록 합니다.
                return DeviceEvent.NONE 

        # 2. 위반 사항이 해결되었는지 확인합니다 (자동 재연결 또는 수동 조치 후).
        # check_violation() will run and update context.violation_code
        current_violations = context.check_violation()
        if current_violations == 0:
            Logger.info("[device][Recovery] Violations cleared. Recovery successful.")
            return DeviceEvent.DONE # -> Transitions to READY
        else:
            # Recovery failed, go back to ERROR state
            violation_names = [v.name for v in DeviceViolation if v & current_violations]
            Logger.error(f"[device][Recovery] Failed. Persistent violations: {'|'.join(violation_names)}")
            return DeviceEvent.VIOLATION_DETECT # -> Transitions back to ERROR

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit RecoveringStrategy with event: {event}")

##
# @class StopOffStrategy
# @brief Strategy for STOP_AND_OFF State.
# @details 소프트 리셋: 장치 정지 및 전원 차단
class StopOffStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter StopOffStrategy. Shutting down all devices.")
        self._seq = 0

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # This strategy brings all devices to a safe, powered-off state.
        
        if self._seq == 0:
            Logger.info("[device][Stop] Stopping all device movements.")
            # Stop all actuators
            # context.align_stop()
            # context.indicator_stop()
            # context.EXT_stop()
            
            # If shimadzu is enabled, send stop command
            # if context.dev_smz_enable:
            #     context.smz_stop_measurement()
            
            self._seq = 1
            self.start_time = time.time()
            return DeviceEvent.NONE

        # Wait a moment for stop commands to take effect, then turn off lamps
        if self._seq == 1 and time.time() - self.start_time > 0.5:
            # Logger.info("[device][Stop] Turning off lamps.")
            # context.lamp_off()
            Logger.info("[device][Stop] All devices are in a safe-stop state.")
            return DeviceEvent.DONE

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit StopOffStrategy with event: {event}")


##
# @class ReadyStrategy
# @brief Strategy for READY State (기존 IDLE).
# @details 대기 및 모니터링 상태. 시험 시작 명령을 대기합니다.
class ReadyStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ReadyStrategy")
        Logger.info("[device] Device: Ready and waiting for commands.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        if context.check_violation():
            return DeviceEvent.VIOLATION_DETECT
        # 작업자의 START_COMMAND 대기 로직이 여기에 추가되어야 함
        # 예시: if bb.get("user/start_request"): return DeviceEvent.START_COMMAND
        
        # 수동 장비 제어 테스트 로직
        manual_cmd = bb.get("manual/device/tester")
        if manual_cmd and manual_cmd > 0:
            Logger.info(f"[device] Manual Test Command Executed: {manual_cmd}")
            
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
            elif manual_cmd == 12:
                context.indicator_up()
            elif manual_cmd == 13:
                context.indicator_down()
            elif manual_cmd == 14:
                context.indicator_stop()
            
            # 명령 실행 후 초기화
            bb.set("manual/device/tester", 0)

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ReadyStrategy with event: {event}")


## ----------------------------------------------------
## 시험 공정 전략 (FSM 규칙에 맞추어 추가됨)
## ----------------------------------------------------

class WaitCommandStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter WaitCommandStrategy")
        Logger.info("[device] Device: Waiting for process start command.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # Logic FSM 등 상위에서 명령을 주면 해당 상태로 전이
        device_cmd_key = "process/auto/device/cmd"
        device_cmd = bb.get(device_cmd_key)

        if device_cmd and isinstance(device_cmd, dict):
            # LogicContext에서 command 또는 process 키를 혼용하여 사용하므로 둘 다 확인합니다.
            cmd = device_cmd.get("command") or device_cmd.get("process")

            if cmd == Device_command.QR_READ:
                return DeviceEvent.DO_READ_QR
            elif cmd == Device_command.MEASURE_THICKNESS:
                return DeviceEvent.DO_MEASURE_THICKNESS
            elif cmd == Device_command.ALIGN_SPECIMEN:
                return DeviceEvent.DO_ALIGNER_ACTION
            elif cmd == Device_command.TENSILE_GRIPPER_ON:
                return DeviceEvent.DO_GRIPPER_GRIP
            elif cmd == Device_command.TENSILE_GRIPPER_OFF:
                return DeviceEvent.DO_GRIPPER_RELEASE
            elif cmd == Device_command.EXT_FORWARD:
                return DeviceEvent.DO_EXTENSOMETER_FORWARD
            elif cmd == Device_command.EXT_BACKWARD:
                return DeviceEvent.DO_EXTENSOMETER_BACKWARD
            elif cmd == Device_command.START_TENSILE_TEST:
                return DeviceEvent.DO_TENSILE_TEST

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit WaitCommandStrategy with event: {event}")

class ReadQRStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ReadQRStrategy")
        Logger.info("[device] Device: Reading QR Code.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # QR 리딩 로직 수행
        if context.qr_read(max_error_count=10):
            # Logic FSM에 완료 및 결과 전달
            cmd_data = bb.get("process/auto/device/cmd")
            if isinstance(cmd_data, dict):
                cmd_data["is_done"] = True
                cmd_data["result"] = bb.get("device/qr/result")
                cmd_data["state"] = "done"
                bb.set("process/auto/device/cmd", cmd_data)
            return DeviceEvent.QR_READ_DONE
        else:
            # Logic FSM에 에러 상태 전달
            cmd_data = bb.get("process/auto/device/cmd")
            if isinstance(cmd_data, dict):
                cmd_data["state"] = "error"
                cmd_data["is_done"] = False
                bb.set("process/auto/device/cmd", cmd_data)
            return DeviceEvent.QR_READ_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ReadQRStrategy with event: {event}")

class MeasureThicknessStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter MeasureThicknessStrategy")
        Logger.info("[device] Device: Measuring Thickness.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 게이지 측정 로직
        thickness = context.get_dial_gauge_value()
        cmd_data = bb.get("process/auto/device/cmd")

        if isinstance(cmd_data, dict):
            if thickness is not None and thickness > -999.0: # -999.0은 오류 값으로 가정
                cmd_data["is_done"] = True
                cmd_data["result"] = thickness
                cmd_data["state"] = "done"
                bb.set("process/auto/device/cmd", cmd_data)
                return DeviceEvent.THICKNESS_MEASURE_DONE
            else:
                cmd_data["is_done"] = False
                cmd_data["state"] = "error"
                bb.set("process/auto/device/cmd", cmd_data)
                return DeviceEvent.GAUGE_MEASURE_FAIL
        
        Logger.error("[device] MeasureThicknessStrategy: No command found on blackboard.")
        return DeviceEvent.GAUGE_MEASURE_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit MeasureThicknessStrategy with event: {event}")

class AlignerOpenStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter AlignerOpenStrategy")
        Logger.info("[device] Device: Opening Aligner.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.ALIGNER_OPEN_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit AlignerOpenStrategy with event: {event}")

class AlignerActionStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter AlignerActionStrategy")
        Logger.info("[device] Device: Operating Aligner.")

        self._seq = 0

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 정렬기 동작: PUSH -> 2초 대기 -> PULL
        if self._seq == 0:
            if context.align_push():
                self.start_time = time.time()
                self._seq = 1
            else:
                return DeviceEvent.ALIGNER_FAIL
        
        if self._seq == 1 and time.time() - self.start_time > 2.0:
            if context.align_pull():
                self.start_time = time.time()
                self._seq = 2
            else:
                return DeviceEvent.ALIGNER_FAIL

        if self._seq == 2 and time.time() - self.start_time > 1.0:
            return DeviceEvent.ALIGNER_ACTION_DONE

        return DeviceEvent.NONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        cmd_data = bb.get("process/auto/device/cmd")
        if isinstance(cmd_data, dict):
            is_success = event == DeviceEvent.ALIGNER_ACTION_DONE
            cmd_data["is_done"] = is_success
            cmd_data["state"] = "done" if is_success else "error"
            bb.set("process/auto/device/cmd", cmd_data)
        Logger.info(f"[device] exit AlignerActionStrategy with event: {event}")

class GripperMoveDownStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter GripperMoveDownStrategy")
        Logger.info("[device] Device: Moving Gripper Down.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.GRIPPER_MOVE_DOWN_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit GripperMoveDownStrategy with event: {event}")

class GripperGripStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter GripperGripStrategy")
        Logger.info("[device] Device: Gripping Specimen (Tensile).")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 인장기 그리퍼 잡기
        if context.chuck_close():
            return DeviceEvent.GRIPPER_GRIP_DONE
        else:
            return DeviceEvent.GRIPPER_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        cmd_data = bb.get("process/auto/device/cmd")
        if isinstance(cmd_data, dict):
            is_success = event == DeviceEvent.GRIPPER_GRIP_DONE
            cmd_data["is_done"] = is_success
            cmd_data["state"] = "done" if is_success else "error"
            bb.set("process/auto/device/cmd", cmd_data)
        Logger.info(f"[device] exit GripperGripStrategy with event: {event}")

class RemovePreloadStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter RemovePreloadStrategy")
        Logger.info("[device] Device: Removing Preload.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.REMOVE_PRELOAD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit RemovePreloadStrategy with event: {event}")

class ExtensometerForwardStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ExtensometerForwardStrategy")
        Logger.info("[device] Device: Moving Extensometer Forward.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.EXTENSOMETER_FORWARD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ExtensometerForwardStrategy with event: {event}")

class StartTensileTestStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter StartTensileTestStrategy")
        Logger.info("[device] Device: Starting Tensile Test.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # Logic FSM에서 전달된 파라미터(lotname 등)를 사용해야 하지만,
        # 현재 구조에서는 cmd dict에서 가져와야 함.
        # 여기서는 임시로 lotname을 사용.
        lotname = "DEFAULT_LOT"
        cmd_data = bb.get("process/auto/device/cmd")

        # Shimadzu에 시험 시작 명령 전송
        result = context.smz_start_measurement(lotname=lotname)
        
        # 응답 확인
        if result and result.get('status') == 'OK':
            Logger.info(f"[device] Shimadzu test started successfully for lot: {lotname}")
            return DeviceEvent.TENSILE_TEST_DONE
        else:
            Logger.error(f"[device] Failed to start Shimadzu test: {result}")
            return DeviceEvent.TENSILE_TEST_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        cmd_data = bb.get("process/auto/device/cmd")
        if isinstance(cmd_data, dict):
            is_success = event == DeviceEvent.TENSILE_TEST_DONE
            cmd_data["is_done"] = is_success
            cmd_data["state"] = "done" if is_success else "error"
            bb.set("process/auto/device/cmd", cmd_data)
        Logger.info(f"[device] exit StartTensileTestStrategy with event: {event}")

class ExtensometerBackwardStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter ExtensometerBackwardStrategy")
        Logger.info("[device] Device: Moving Extensometer Backward.")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        return DeviceEvent.EXTENSOMETER_BACKWARD_DONE
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        Logger.info(f"[device] exit ExtensometerBackwardStrategy with event: {event}")

class GripperReleaseStrategy(Strategy):
    def prepare(self, context: DeviceContext, **kwargs):
        bb.set("device/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[device] enter GripperReleaseStrategy")
        Logger.info("[device] Device: Releasing Gripper (Tensile).")

    def operate(self, context: DeviceContext) -> DeviceEvent:
        # 인장기 그리퍼 풀기
        if context.chuck_open():
            return DeviceEvent.GRIPPER_RELEASE_DONE
        else:
            return DeviceEvent.GRIPPER_FAIL
    
    def exit(self, context: DeviceContext, event: DeviceEvent) -> None:
        cmd_data = bb.get("process/auto/device/cmd")
        if isinstance(cmd_data, dict):
            is_success = event == DeviceEvent.GRIPPER_RELEASE_DONE
            cmd_data["is_done"] = is_success
            cmd_data["state"] = "done" if is_success else "error"
            bb.set("process/auto/device/cmd", cmd_data)
        Logger.info(f"[device] exit GripperReleaseStrategy with event: {event}")