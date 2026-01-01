import time
import threading
from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
from pkg.utils.blackboard import GlobalBlackboard
from .devices_fsm import DeviceFsm
from .robot_fsm import RobotFSM
from .DB_handler import DBHandler
bb = GlobalBlackboard()

## MOTION CMD Value

PICK_SPECIMEN = 1000
# MEASURE_THICKNESS =  
robot_cmd_key = "process/auto/robot/cmd"
device_cmd_key = "process/auto/device/cmd"

class LogicStatus:
    # Neuromeka 전체 시스템 상태 플래그
    def __init__(self):
        self.is_connected_all = Flagger()  # 모든 서브 모듈 연결 완료
        self.is_ready_all = Flagger()      # 모든 서브 모듈 준비 완료
        self.is_emg_pushed = Flagger()     # 비상 정지 버튼
        self.is_error_state = Flagger()    # 하드웨어/외부 오류 상태
        self.is_batch_planned = Flagger()  # 배치 계획 수립 완료

        self.reset()

    def reset(self):
        self.is_connected_all.down()
        self.is_ready_all.down()
        self.is_emg_pushed.down()
        self.is_error_state.down()
        self.is_batch_planned.down()


class LogicContext(ContextBase):
    status: LogicStatus
    violation_code: int
    db: DBHandler
    def __init__(self, db_handler: DBHandler):
        ContextBase.__init__(self)
        self.status = LogicStatus()
        self.violation_code = 0x00
        self._set_seq = 0
        self._sub_seq = 0
        self.db = db_handler
        self._sub_seq_bk = 0
        self._seq_bk = 0

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            # 1. Logic 자체의 상태 확인
            if self.status.is_emg_pushed():
                self.violation_code |= LogicViolation.ISO_EMERGENCY_BUTTON

            if self.status.is_error_state():
                self.violation_code |= LogicViolation.HW_VIOLATION

            return self.violation_code
        except Exception as e:
            Logger.error(f"[Logic] Exception in check_violation: {e}")
            reraise(e)

    def move_to_rack_for_QRRead(self, floor : int = 0, specimen_num : int = 0, Sequence : int = 0) :
        '''
        # Position A Rack
        Docstring for move_to_rack_for_QRRead
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번
        move_to_rack_for_QRRead 로봇 모션, QR Read
        '''

        # Seq 1 : Robot, Rack 앞 이동
        # Seq 2 : Robot, QR 읽는 위치 이동
        # Seq 3 : Device_QR, QR 코드 읽기 

        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Step 0: Check gripper status, open if not already open
        # Step 0: 그리퍼 상태 확인. 닫혀있으면 열기 명령 전송
        if self._seq == 0:
            gripper_state = bb.get("robot/gripper/actual_state")
            if gripper_state == 1:  # 1: 열림 상태
                Logger.info("[Logic] Gripper is already open. Proceeding.")
                self.set_seq(2)  # Skip to moving to rack
            else:
                Logger.info(f"[Logic] Gripper is not open (state: {gripper_state}). Sending open command.")
                robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_INDICATOR, "state": ""}
                bb.set(robot_cmd_key, robot_cmd)
                self.set_seq(1)
            return LogicEvent.NONE

        # Step 1: Wait for gripper to open
        # Step 1: 그리퍼 열기 완료 대기
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_INDICATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Gripper open command is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(2)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Gripper open command failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 2: Send command to move to rack front (ID: 1000)
        # Step 2: 로봇을 랙 앞으로 이동시키는 명령 전송
        elif self._seq == 2:
            robot_cmd = {
                "process" : MotionCommand.MOVE_TO_RACK,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 0: Sending command to move to rack front.")
            Logger.info(f"[Logic] Step 2: Sending command to move to rack front.")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3) # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 3: Wait for rack front move to complete
        # Step 3: 랙 앞으로 이동 완료 대기
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Step 3: Move to rack front is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(2) # Transition to next action
                    self.set_seq(4) # Transition to next action
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE # Keep waiting if not done or no cmd yet

        # Step 4: Send command to move to QR scan position
        # Step 4: QR 스캔 위치로 이동 명령 전송
        elif self._seq == 4:
            robot_cmd = {
                "process" : MotionCommand.MOVE_TO_QR_SCAN_POS,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 2: Sending command to move to QR scan position.")
            Logger.info(f"[Logic] Step 4: Sending command to move to QR scan position.")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3) # Immediately transition to waiting state
            self.set_seq(5) # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 5: Wait for QR scan position move to complete
        # Step 5: QR 스캔 위치로 이동 완료 대기
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_QR_SCAN_POS:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Step 3: Move to QR scan position is done.")
                    Logger.info("[Logic] Step 5: Move to QR scan position is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(4) # Transition to next action (device command)
                    self.set_seq(6) # Transition to next action (device command)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 6: Send device command for QR read
        # Step 6: QR 읽기 장치에 명령 전송
        elif self._seq == 6:
            device_cmd = {
                "process" : DeviceCommand.QR_READ,
                "result" : None,
                "state" : "",
                "is_done" : False
            }
            Logger.info(f"[Logic] Step 4: Sending command to read QR code.")
            Logger.info(f"[Logic] Step 6: Sending command to read QR code.")
            bb.set(device_cmd_key, device_cmd)
            self.set_seq(5) # Immediately transition to waiting state
            self.set_seq(7) # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 7: Wait for QR read to complete
        # Step 7: QR 읽기 완료 대기
        elif self._seq == 7:
            if get_device_cmd and get_device_cmd.get("process") == DeviceCommand.QR_READ:
                if not get_device_cmd.get("is_done"):
                    return LogicEvent.NONE # 아직 완료되지 않음, 대기

                # is_done이 True이면 성공이든 실패든 처리
                if get_device_cmd.get("state") == "done":
                    qr_result = get_device_cmd.get("result")
                    qr_data = bb.get("process/auto/qr_data") or {}
                    qr_data[str(Sequence)] = qr_result
                    bb.set("process/auto/qr_data", qr_data)
                    Logger.info(f"[Logic] Step 5: QR Read is done. Result: {qr_result}")
                    Logger.info(f"[Logic] Step 7: QR Read is done. Result: {qr_result}")
                    bb.set(device_cmd_key, None) # Consume the result
                    self.set_seq(0) # Reset sequence for the next call of this function
                    return LogicEvent.DONE
                elif get_device_cmd.get("state") == "error": # state == "error"
                    Logger.error(f"[Logic] Step 5 failed: {get_device_cmd}")
                    Logger.error(f"[Logic] Step 7 failed: {get_device_cmd}")
                    bb.set(device_cmd_key, None)
                    # VIOLATION_DETECT 대신 사용자 입력을 대기하는 새로운 시퀀스로 전환
                    Logger.info("[Logic] QR Read failed. Waiting for user command (e.g., retry).")
                    self.set_seq(6) # 사용자 명령 대기 상태
                    self.set_seq(8) # 사용자 명령 대기 상태
                    return LogicEvent.NONE # 현재 Strategy에 머무름
            return LogicEvent.NONE

        # Step 8: Wait for user command after QR failure
        elif self._seq == 8:
            # UI로부터 재시도 명령(예: bb.get("ui/cmd/qr_read/retry") == 1)을 기다립니다.
            # 현재는 별도 UI 명령이 없으므로, 재시도 로직을 구현하고 대기 상태를 유지합니다.
            # UI에서 'ui/cmd/qr_read/retry' 값을 1로 설정하면 재시도합니다.
            if bb.get("ui/cmd/qr_read/retry") == 1:
                bb.set("ui/cmd/qr_read/retry", 0) # 명령 소비
                Logger.info("[Logic] QR Read retry command received. Retrying from Step 4.")
                self.set_seq(4) # QR 읽기 명령을 보내는 단계로 복귀
                Logger.info("[Logic] QR Read retry command received. Retrying from Step 6.")
                self.set_seq(6) # QR 읽기 명령을 보내는 단계로 복귀
            return LogicEvent.NONE # UI 명령이 있을 때까지 계속 대기

        return LogicEvent.NONE

    def pick_specimen(self, floor : int = 0, specimen_num : int = 0): # A
        '''
        # Position A Rack
        Docstring for pick_specimen
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번

        pick_specimen 로봇 모션만 함
        '''       
        get_robot_cmd = bb.get(robot_cmd_key)

        # Step 0: Send command to pick specimen from rack
        # Step 0: Check gripper status, open if not already open
        # Step 0: 그리퍼 상태 확인. 닫혀있으면 열기 명령 전송
        if self._seq == 0:
            gripper_state = bb.get("robot/gripper/actual_state")
            if gripper_state == 1:  # 1 is open
                Logger.info("[Logic] Gripper is already open. Proceeding to pick specimen.")
            if gripper_state == 1:  # 1: 열림 상태
                Logger.info("[Logic] Gripper is already open. Proceeding.")
                self.set_seq(2)
            else:
                Logger.info(f"[Logic] Gripper is not open (state: {gripper_state}). Sending open command.")
                robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_INDICATOR, "state": ""}
                bb.set(robot_cmd_key, robot_cmd)
                self.set_seq(1)
            return LogicEvent.NONE

        # Step 1: Wait for gripper to open
        # Step 1: 그리퍼 열기 완료 대기
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_INDICATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Gripper open command is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(2)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Gripper open command failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 2: Send command to pick specimen from rack
        # Step 2: 랙에서 시편을 집기 위한 위치로 이동 명령 전송
        elif self._seq == 2:
            robot_cmd = {
                "process" : MotionCommand.PICK_SPECIMEN_FROM_RACK,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_RACK}")
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_RACK}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
            self.set_seq(3)
            return LogicEvent.NONE

        # Step 3: Wait for pick move to complete, then close gripper
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Pick move done. Closing gripper.")
                    Logger.info(f"[Logic] Step 3: Pick move done. Closing gripper.")
                    bb.set(robot_cmd_key, None)
                    robot_cmd = { "process" : MotionCommand.GRIPPER_CLOSE_FOR_RACK, "state" : "" }
                    bb.set(robot_cmd_key, robot_cmd)
                    self.set_seq(2)
                    self.set_seq(4)
                    return LogicEvent.NONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 4: Wait for gripper to close, then retreat from rack
        elif self._seq == 4:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 2: Gripper close done. Retreating from rack.")
                    Logger.info(f"[Logic] Step 4: Gripper close done. Retreating from rack.")
                    bb.set(robot_cmd_key, None)
                    robot_cmd = {
                        "process" : MotionCommand.RETREAT_FROM_RACK,
                        "target_floor" : floor,
                        "state" : ""
                    }
                    bb.set(robot_cmd_key, robot_cmd)
                    self.set_seq(3)
                    self.set_seq(5)
                    return LogicEvent.NONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 2 failed: {get_robot_cmd}")
                    Logger.error(f"[Logic] Step 4 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 5: Wait for retreat to complete
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Retreat from rack is done.")
                    Logger.info(f"[Logic] Step 5: Retreat from rack is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        
        return LogicEvent.NONE

    def Move_to_Indicator(self) :
        get_robot_cmd = bb.get(robot_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_INDICATOR
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_INDICATOR, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_INDICATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_INDICATOR and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to indicator done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(0)
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
        return LogicEvent.NONE

    def Measure_specimen_thickness(self, num: int):
        """
        # Position B Indicator
        시편을 치수 측정기로 옮겨 두께를 측정하고 다시 집어오는 전체 시퀀스를 수행합니다.
        num 값에 따라 측정 위치(1, 2, 3)가 결정됩니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-PLACE_SPECIMEN_AND_MEASURE
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.PLACE_SPECIMEN_AND_MEASURE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PLACE_SPECIMEN_AND_MEASURE} at pos {num}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
            return LogicEvent.NONE

        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_SPECIMEN_AND_MEASURE:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Place specimen done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(2)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-GRIPPER_OPEN_AT_INDICATOR
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_INDICATOR, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.GRIPPER_OPEN_AT_INDICATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
            return LogicEvent.NONE

        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_INDICATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Gripper open done.")
                    bb.set("process/auto/specimen_on_indicator", True)
                    Logger.info("[Logic] Specimen is now on the indicator.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(4)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-RETREAT_FROM_INDICATOR_AFTER_PLACE
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PLACE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PLACE}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(5)
            return LogicEvent.NONE

        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PLACE:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Retreat from indicator done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(6)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Device-Indicator-MEASURE_THICKNESS
        elif self._seq == 6:
            device_cmd = {"command": DeviceCommand.MEASURE_THICKNESS, "result": None, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 6: Sending command: {DeviceCommand.MEASURE_THICKNESS}")
            bb.set(device_cmd_key, device_cmd)
            self.set_seq(7)
            return LogicEvent.NONE

        elif self._seq == 7:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.MEASURE_THICKNESS:
                if get_device_cmd.get("is_done"):
                    if get_device_cmd.get("state") == "done":
                        thickness_result = get_device_cmd.get("result")
                        thickness_data = bb.get("process/auto/thickness") or {}
                        thickness_data[str(num)] = thickness_result
                        bb.set("process/auto/thickness", thickness_data)
                        # TEST 화면 두께 측정 현재, 이전 측정 값
                        t_data : dict = bb.get("process_status/thickness_measurement")
                        t_data["previous"] = t_data["current"]
                        t_data["current"] = thickness_result
                        bb.set("process_status/thickness_measurement",t_data)
                        
                        
                        Logger.info(f"[Logic] Step 7: Thickness measurement done. Result: {thickness_result}")
                        bb.set(device_cmd_key, None)
                        self.set_seq(8)
                    else:  # error
                        Logger.error(f"[Logic] Step 7 failed: {get_device_cmd}")
                        bb.set(device_cmd_key, None)
                        self.set_seq(0)
                        return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Robot-Motion-PICK_SPECIMEN_FROM_INDICATOR
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.PICK_SPECIMEN_FROM_INDICATOR, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_INDICATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(9)
            return LogicEvent.NONE

        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_INDICATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 9: Pick from indicator done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(10)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 6: Robot-Motion-GRIPPER_CLOSE_FOR_INDICATOR
        elif self._seq == 10:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_INDICATOR, "state": ""}
            Logger.info(f"[Logic] Step 10: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_INDICATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(11)
            return LogicEvent.NONE

        elif self._seq == 11:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_INDICATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 11: Gripper close done.")
                    bb.set("process/auto/specimen_on_indicator", False)
                    Logger.info("[Logic] Specimen has been picked up from the indicator.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(12)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 11 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 7: Robot-Motion-RETREAT_FROM_INDICATOR_AFTER_PICK
        elif self._seq == 12:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 12: Sending command: {MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(13)
            return LogicEvent.NONE

        elif self._seq == 13:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 13: Final retreat from indicator is done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 13 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        return LogicEvent.NONE

    def Move_to_Align(self) :
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_ALIGN
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to align done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(0)
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
        return LogicEvent.NONE
    
    def Specimen_Align(self):
        """
        # Position C Aligner
        시편을 정렬기에 내려놓고 정렬을 수행하는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-PLACE_SPECIMEN_ON_ALIGN
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.PLACE_SPECIMEN_ON_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PLACE_SPECIMEN_ON_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_SPECIMEN_ON_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Place specimen on align done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(2)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        # Seq 2: Robot-Motion-GRIPPER_OPEN_AT_ALIGN
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.GRIPPER_OPEN_AT_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Gripper open at align done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(4)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        # Seq 3: 인장 시험기 상태에 따라 분기
        elif self._seq == 4:
            # 인장 시험기 상태 확인
            shimadzu_state = bb.get("device/shimadzu/run_state")
            is_tensile_busy = False
            if shimadzu_state and isinstance(shimadzu_state, dict):
                run_status = shimadzu_state.get("RUN")
                if run_status == 'C':  # 'C' means Testing
                    is_tensile_busy = True
            
            if is_tensile_busy:
                # Case 1: 인장 시험기가 사용 중이면, 정렬기에서 후퇴합니다.
                motion_to_perform = MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE
            else:
                # Case 2: 인장 시험기가 대기 중이면, 정렬기 앞에서 대기합니다.
                motion_to_perform = MotionCommand.ALIGNER_FRONT_WAIT

            robot_cmd = {"process": motion_to_perform, "state": ""}
            Logger.info(f"[Logic] Step 4: Tensile busy: {is_tensile_busy}. Sending command: {motion_to_perform}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(5)

        elif self._seq == 5:
            if get_robot_cmd and (get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE or get_robot_cmd.get("process") == MotionCommand.ALIGNER_FRONT_WAIT):
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Motion '{get_robot_cmd.get('process')}' done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(6)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        # Seq 4: Device-Align-ALIGN_SPECIMEN
        elif self._seq == 6:
            device_cmd = {"command": DeviceCommand.ALIGN_SPECIMEN, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 6: Sending command: {DeviceCommand.ALIGN_SPECIMEN}")
            bb.set(device_cmd_key, device_cmd)
            self.set_seq(7)
        elif self._seq == 7:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.ALIGN_SPECIMEN and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 7: Align specimen done.")
                    bb.set(device_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.DONE
                else:
                    Logger.error(f"[Logic] Step 7 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        return LogicEvent.NONE
    
    def Pick_Specimen_From_Align(self):
        """
        # Position C Aligner
        정렬된 시편을 집어서 나오는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)

        # 시퀀스 시작 시점에 인장기 상태를 확인하여 분기합니다.
        if self._seq == 0:
            shimadzu_state = bb.get("device/shimadzu/run_state")
            is_tensile_busy = False
            if shimadzu_state and isinstance(shimadzu_state, dict):
                run_status = shimadzu_state.get("RUN")
                if run_status == 'C':  # 'C' means Testing
                    is_tensile_busy = True
            
            if not is_tensile_busy:
                # 인장기가 시험 중이 아니면, 로봇은 정렬기 앞에서 대기했을 것이므로
                # 이동 동작(Seq 0)을 건너뛰고 그리퍼 닫기(Seq 2)부터 시작합니다.
                Logger.info("[Logic] Tensile is not busy. Robot waited at aligner. Skipping move, starting from seq 2 (Gripper Close).")
                self.set_seq(2)
            else:
                # 인장기가 시험 중이면, 로봇은 후퇴했으므로 다시 정렬기로 이동해야 합니다.
                # 따라서 전체 시퀀스를 Seq 0부터 시작합니다.
                Logger.info("[Logic] Tensile is busy. Robot must return to aligner. Starting full sequence from seq 0.")
                # self._seq는 0으로 유지됩니다.

        # Seq 1: Robot-Motion-PICK_SPECIMEN_FROM_ALIGN
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.PICK_SPECIMEN_FROM_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_ALIGN:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Pick from align done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(2)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-GRIPPER_CLOSE_FOR_ALIGN
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_ALIGN:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Gripper close for align done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(4)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-RETREAT_FROM_ALIGN_AFTER_PICK
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(5)
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Retreat from align done.")
                    bb.set(robot_cmd_key, None)
                    self.set_seq(0)
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        return LogicEvent.NONE
        
    def Load_Specimen_Tensile_Machine(self):
        """
        # Position D Tensile Machine
        시편을 인장 시험기에 장착하는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_TENSILE_MACHINE_FOR_LOAD
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_LOAD, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_LOAD}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_LOAD and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(2)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-load_tensile_machine
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.LOAD_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.LOAD_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.LOAD_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Load tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(4)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Device-Tensil_gripper-TENSILE_GRIPPER_ON
        elif self._seq == 4:
            device_cmd = {"command": DeviceCommand.TENSILE_GRIPPER_ON, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 4: Sending command: {DeviceCommand.TENSILE_GRIPPER_ON}")
            bb.set(device_cmd_key, device_cmd)
            self.set_seq(5)
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.TENSILE_GRIPPER_ON and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Tensile gripper on done.")
                    bb.set(device_cmd_key, None)
                    self.set_seq(6)
                else:
                    Logger.error(f"[Logic] Step 5 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Robot-Motion-GRIPPER_OPEN_AT_TENSILE_MACHINE
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(7)
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 7: Gripper open at tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(8)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Robot-Motion-RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(9)
            return LogicEvent.NONE
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Retreat from tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(10)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        
        # Seq 6: Robot-Motion-MOVE_TO_HOME
        elif self._seq == 10:
            robot_cmd = {"process": MotionCommand.MOVE_TO_HOME, "state": ""}
            Logger.info(f"[Logic] Step 10: Sending command: {MotionCommand.MOVE_TO_HOME}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(11)
            return LogicEvent.NONE
        elif self._seq == 11:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_HOME and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 11: Move to home done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(0)
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 11 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        return LogicEvent.NONE
    
    def Pick_Specimen_From_Tensile_Machine(self, num: int, pos_z: float):
        """
        # Position D Tensile Machine
        인장 시험기에서 시편을 수거하는 전체 시퀀스입니다.
        num: 1-상단 시편(UP), 2-하단 시편(DOWN)
        pos_z: (현재 사용되지 않음)
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_TENSILE_MACHINE_FOR_PICK
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_PICK, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_PICK and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to tensile for pick done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(2)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        # Seq 2: Robot_Motion-PICK_FROM_TENSILE_MACHINE
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PICK_FROM_TENSILE_MACHINE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PICK_FROM_TENSILE_MACHINE} at pos {num}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_FROM_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Pick from tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(4)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: GRIPPER_CLOSE_FOR_TENSILE_MACHINE
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(5)
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 5: Gripper close for tensile machine done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(6)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Device-Tensile_gripper-TENSILE_GRIPPER_OFF
        elif self._seq == 6:
            device_cmd = {"command": DeviceCommand.TENSILE_GRIPPER_OFF, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 6: Sending command: {DeviceCommand.TENSILE_GRIPPER_OFF}")
            bb.set(device_cmd_key, device_cmd)
            self.set_seq(7)
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.TENSILE_GRIPPER_OFF and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 7: Tensile gripper off done.")
                    bb.set(device_cmd_key, None)
                    self.set_seq(8)
                else:
                    Logger.error(f"[Logic] Step 7 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(9)
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Retreat from tensile machine after pick done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(0)
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT

        return LogicEvent.NONE

    def Disposer_Scrap(self):
        """
        # Position E Scrap Disposer
        시험 완료된 시편을 스크랩 처리기에 버리고 홈으로 복귀하는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_SCRAP_DISPOSER
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(1)
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(2)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-PLACE_IN_SCRAP_DISPOSER
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PLACE_IN_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PLACE_IN_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(3)
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_IN_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Place in scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(4)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-GRIPPER_OPEN_AT_SCRAP_DISPOSER
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(5)
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 5: Gripper open at scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(6)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Robot-Motion-RETREAT_FROM_SCRAP_DISPOSER
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.RETREAT_FROM_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(7)
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 7: Retreat from scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(8)
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Robot-Motion-MOVE_TO_HOME
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.MOVE_TO_HOME, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.MOVE_TO_HOME}")
            bb.set(robot_cmd_key, robot_cmd)
            self.set_seq(9)
            return LogicEvent.NONE
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_HOME and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Move to home done.")
                bb.set(robot_cmd_key, None)
                self.set_seq(0)
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self.set_seq(0); return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        return LogicEvent.NONE
        
    def regist_tensil_data(self):
        """
        현재 시편의 시험 조건을 DB에서 조회하여 Device FSM에 등록 명령을 전달하고 완료를 대기합니다.
        이 함수는 Strategy에 의해 반복적으로 호출되는 것을 가정합니다.
        """
        try:
            get_device_cmd = bb.get(device_cmd_key)

            # Step 1: 명령 전송 (아직 전송되지 않았을 경우)
            if self._seq == 0:
                # 1.1. 현재 공정 정보 가져오기
                batch_data = bb.get("process/auto/batch_data")
                current_specimen_in_tray = next((s for s in batch_data['processData'] if s.get('seq_status') == 2), None)
                
                if not current_specimen_in_tray:
                    Logger.error("[Logic] regist_tensil_data: Cannot find running tray.")
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT

                specimen_no = bb.get("process/auto/current_specimen_no")
                test_method_name = current_specimen_in_tray.get("test_method")
                lot_name = current_specimen_in_tray.get("lot")
                batch_id = batch_data.get("batch_id")
                
                # TPNAME은 '배치ID_트레이번호_시편번호' 형식으로 생성
                tpname = f"{batch_id}_{current_specimen_in_tray.get('tray_no')}_{specimen_no}"

                # 1.2. DB에서 시험 방법 상세 정보 조회
                method_details = self.db.get_test_method_details(test_method_name)
                if not method_details:
                    Logger.error(f"[Logic] Failed to get test method details for '{test_method_name}' from DB.")
                    self.set_seq(0)
                    return LogicEvent.VIOLATION_DETECT

                # 각 트레이의 첫 시편(specimen_no == 1) 작업 시작 전, test_method 기준 등록 두께(thickness)를 BB에 기록
                if specimen_no == 1:
                    registered_thickness = method_details.get("thickness")
                    if registered_thickness is not None:
                        t_data = bb.get("process_status/thickness_measurement") or {"current": 0.0, "previous": 0.0}
                        # DB에서 가져온 값은 Decimal 타입일 수 있으므로 float으로 변환
                        t_data["registered"] = float(registered_thickness)
                        bb.set("process_status/thickness_measurement", t_data)
                        Logger.info(f"[Logic] Set registered thickness for tray from DB: {t_data['registered']}")

                # 1.3. 시편 치수 정보 가져오기 (두께 측정 결과)
                thickness_map = bb.get("process/auto/thickness") or {}
                # size1: 두께, size2: 폭 (폭은 시험 방법에 고정되어 있다고 가정)
                size1 = thickness_map.get(str(specimen_no), method_details.get("thickness", "1.0")) 
                size2 = method_details.get("size2", "10.0")

                # 1.4. Shimadzu 등록을 위한 파라미터 dict 구성
                regist_data = {
                    "tpname": tpname, "type_p": method_details.get("type_p", "P"),
                    "size1": str(size1), "size2": str(size2),
                    "test_rate_type": method_details.get("test_rate_type", "S"), "test_rate": method_details.get("test_rate", "50.00"),
                    "detect_yp": method_details.get("detect_yp", "T"), "detect_ys": method_details.get("detect_ys", "T"),
                    "detect_elastic": method_details.get("detect_elastic", "T"), "detect_lyp": method_details.get("detect_lyp", "F"),
                    "detect_ypel": method_details.get("detect_ypel", "F"), "detect_uel": method_details.get("detect_uel", "F"),
                    "detect_ts": method_details.get("detect_ts", "T"), "detect_el": method_details.get("detect_el", "T"),
                    "detect_nv": method_details.get("detect_nv", "F"), "ys_para": method_details.get("ys_para", "0.20"),
                    "nv_type": method_details.get("nv_type", "I"), "nv_para1": method_details.get("nv_para1", "10.00"),
                    "nv_para2": method_details.get("nv_para2", "20.00"), "lotname": lot_name
                }

                # 1.5. Device FSM에 등록 명령 전달
                device_cmd = { "command": DeviceCommand.REGISTER_METHOD, "params": regist_data, "state": "", "is_done": False }
                bb.set(device_cmd_key, device_cmd)
                Logger.info(f"[Logic] Sent REGISTER_METHOD command to DeviceFSM for specimen {tpname}")
                self.set_seq(1)
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1:
                if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.REGISTER_METHOD:
                    if not get_device_cmd.get("is_done"):
                        return LogicEvent.NONE

                    if get_device_cmd.get("state") == "done":
                        Logger.info(f"[Logic] DeviceFSM completed method registration.")
                        bb.set(device_cmd_key, None)
                        self.set_seq(0)
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to register method: {get_device_cmd.get('result')}")
                        bb.set(device_cmd_key, None)
                        self.set_seq(0)
                        return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        except Exception as e:
            Logger.error(f"[Logic] Exception in regist_tensil_data: {e}")
            self.set_seq(0)
            return LogicEvent.VIOLATION_DETECT

    def start_tensile_test(self):
        """
        Device FSM에 인장 시험 시작 명령을 전달하고 완료를 대기합니다.
        이 함수는 Strategy에 의해 반복적으로 호출되는 것을 가정합니다.
        """
        try:
            get_device_cmd = bb.get(device_cmd_key)

            # Step 1: 명령 전송
            if self._seq == 0:
                device_cmd = {
                    "command": DeviceCommand.START_TENSILE_TEST,
                    "state": "",
                    "is_done": False
                }
                bb.set(device_cmd_key, device_cmd)
                Logger.info(f"[Logic] Sent START_TENSILE_TEST command to DeviceFSM.")
                self.set_seq(1)
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1:
                if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.START_TENSILE_TEST:
                    if not get_device_cmd.get("is_done"):
                        return LogicEvent.NONE

                    if get_device_cmd.get("state") == "done":
                        Logger.info("[Logic] DeviceFSM confirmed tensile test started.")
                        bb.set(device_cmd_key, None)
                        self.set_seq(0)
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to start tensile test: {get_device_cmd.get('result')}")
                        bb.set(device_cmd_key, None)
                        self.set_seq(0)
                        return LogicEvent.VIOLATION_DETECT
            
            return LogicEvent.NONE

        except Exception as e:
            Logger.error(f"[Logic] Exception in start_tensile_test: {e}")
            self.set_seq(0)
            return LogicEvent.VIOLATION_DETECT
    def set_seq(self, num) :
        if self._seq != num :
            Logger.info(f"original seq : {self._seq}, new : {num}")
        self._seq = num
    
    def set_sub_seq(self, num) :
        if self._sub_seq != num :
            Logger.info(f"original sub_seq : {self._sub_seq}, new : {num}")
        self._sub_seq = num

    def execute_controlled_stop(self):
        """
        제어된 정지 절차를 수행합니다.
        - 로봇의 현재 위치를 파악하여 안전하게 후퇴합니다.
        - 시편이 장비에 놓여있으면 회수합니다.
        - 시편을 들고 있으면 스크랩 처리를 합니다.
        - 최종적으로 홈 위치로 복귀합니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)

        if self._seq == 0:
            # UI로부터 STOP 명령을 받으면 5초간 대기합니다.
            Logger.info("[Logic] Controlled Stop: Waiting 5 seconds before proceeding...")
            time.sleep(5)

            # Step 0: 현재 상태를 파악하여 다음 행동을 결정합니다.
            current_pos_id = int(bb.get("robot/current/position") or 0)
            is_holding = (bb.get("robot/gripper/actual_state") == 2)
            specimen_on_indicator = bb.get("process/auto/specimen_on_indicator") or False
            
            Logger.info(f"[Logic] Controlled Stop: Start. Position ID: {current_pos_id}, Holding Specimen: {is_holding}, FSM State: {self.state.name}")

            # [추가] 측정 공정 중 시편을 들고 있을 때 정지 명령이 들어온 경우
            if self.state == LogicState.MEASURE_SPECIMEN_THICKNESS and is_holding:
                Logger.info("[Logic] Controlled Stop: Stop during measurement while holding specimen. Retreating from indicator.")
                self.set_seq(15)  # 측정기에서 시편 들고 후퇴하는 상태
                self.set_sub_seq(0)
                # 현재 측정 중인 포인트(1, 2, 또는 3)를 알아내어 후퇴 위치로 지정합니다.
                measure_point = bb.get("process/auto/measure_point") or 1
                self.recovery_pos = int(measure_point)
                return LogicEvent.NONE

            # [수정] 측정 또는 정렬 공정 중에 정지 명령이 들어온 경우, 시편이 장비 위에 있다고 간주하고 회수 절차를 우선적으로 실행합니다.
            if (self.state == LogicState.MEASURE_SPECIMEN_THICKNESS and not is_holding) or specimen_on_indicator:
                Logger.info("[Logic] Controlled Stop: Stop during measurement or specimen on indicator. Recovering specimen from indicator.")
                self.set_seq(10)  # 두께 측정기에서 회수하는 상태
                self.set_sub_seq(0)
                # 현재 측정 중인 포인트(1, 2, 또는 3)를 알아내어 회수 위치로 지정합니다.
                # LogicMeasureSpecimenThicknessStrategy에서 'process/auto/measure_point'를 설정합니다.
                measure_point = bb.get("process/auto/measure_point") or 1
                self.recovery_pos = int(measure_point)
                return LogicEvent.NONE

            if self.state == LogicState.ALIGN_SPECIMEN and not is_holding:
                Logger.info("[Logic] Controlled Stop: Stop during alignment. Recovering specimen from aligner.")
                self.set_seq(20)  # 정렬기에서 회수하는 상태
                self.set_sub_seq(0)
                return LogicEvent.NONE

            # [추가] 정렬 공정 중 시편을 들고 있을 때 정지 명령이 들어온 경우
            if self.state == LogicState.PICK_SPECIMEN_FROM_ALIGN and is_holding:
                Logger.info("[Logic] Controlled Stop: Stop while holding specimen from aligner. Retreating.")
                self.set_seq(25) # 정렬기에서 시편 들고 후퇴
                self.set_sub_seq(0)
                return LogicEvent.NONE

            # Case 1: 시편이 두께 측정기에 놓여 있는 경우 (회수 필요)
            if 3001 <= current_pos_id <= 3003:
                Logger.info("[Logic] Controlled Stop: Specimen is at indicator. Starting recovery.")
                self.set_seq(10)  # 두께 측정기에서 회수하는 상태
                self.set_sub_seq(0)
                self.recovery_pos = current_pos_id - 3000
            # Case 2: 시편이 정렬기에 놓여 있는 경우 (회수 필요)
            elif current_pos_id == 5001:
                Logger.info("[Logic] Controlled Stop: Specimen is at aligner. Starting recovery.")
                self.set_seq(20)  # 정렬기에서 회수하는 상태
                self.set_sub_seq(0)
            # Case 3: 로봇이 시편을 들고 있는 경우 (후퇴 후 스크랩 처리 필요)
            elif is_holding:
                # 로봇의 현재 위치에 따라 필요한 후퇴 동작을 결정합니다.
                if 1011 <= current_pos_id <= 1105:
                    Logger.info("[Logic] Controlled Stop: is_holding Robot is inside rack without specimen. Opening gripper and retreating.")
                    self.set_seq(55) # 랙에서 시편을 잡지 않고 후퇴하는 상태
                    self.set_sub_seq(0)
                elif 2010 <= current_pos_id <= 2100: # 랙 내부
                    Logger.info("[Logic] Controlled Stop: Holding specimen inside rack. Retreating first.")
                    self.set_seq(50) # 랙에서 후퇴하는 상태
                    self.set_sub_seq(0)
                elif 7001 <= current_pos_id <= 7012: # 인장기 내부
                    Logger.info("[Logic] Controlled Stop: Holding specimen inside tensile machine. Retreating first.")
                    self.set_seq(60) # 인장기에서 후퇴하는 상태
                else: # 이미 안전한 위치(Waypoint)에 있다고 판단, 바로 스크랩 처리로 이동
                    Logger.info("[Logic] Controlled Stop: Robot is holding specimen in a safe area. Moving to scrap disposal.")
                    self.set_seq(30)  # 스크랩 처리 상태
                    self.set_sub_seq(0)
            
            # Case 4: 로봇이 시편 잡으로 접근은 했으나 시편 그대로 두고 나오기
            elif 1011 <= current_pos_id <= 1105:
                Logger.info("[Logic] Controlled Stop: Robot is inside rack without specimen. Opening gripper and retreating.")
                self.set_seq(55) # 랙에서 시편을 잡지 않고 후퇴하는 상태
                self.set_sub_seq(0)

            # Case 5: 그 외 (시편 없음), 홈으로 바로 복귀
            else:
                Logger.info("[Logic] Controlled Stop: No specimen to handle. Moving to home.")
                self.set_seq(40)  # 홈으로 복귀하는 상태
                self.set_sub_seq(0)
            return LogicEvent.NONE

        # State 10: 두께 측정기에서 시편 회수
        elif self._seq == 10:
            if self._sub_seq == 0: # PICK
                # 측정기 받침이 내려가 있는지 확인
                indicator_stand_state = bb.get("device/indicator/stand/state")
                if indicator_stand_state == "down":
                    cmd = MotionCommand.PICK_SPECIMEN_FROM_INDICATOR
                    robot_cmd = {"process": cmd, "position": self.recovery_pos, "state": ""}
                    Logger.info(f"[Logic] Controlled Stop: Indicator is down. Sending command: {cmd}")
                    bb.set(robot_cmd_key, robot_cmd)
                    self.set_sub_seq(1)
                else:
                    Logger.warn(f"[Logic] Controlled Stop: Waiting for indicator stand to be 'down'. Current state: {indicator_stand_state}")
                    return LogicEvent.NONE # 대기
            elif self._sub_seq == 1: # Wait for PICK
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(2)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # CLOSE
                cmd = MotionCommand.GRIPPER_CLOSE_FOR_INDICATOR
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # Wait for CLOSE
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(4)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 4: # RETREAT
                cmd = MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK
                robot_cmd = {"process": cmd, "position": self.recovery_pos, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(5)
            elif self._sub_seq == 5: # Wait for RETREAT
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Recovery from indicator complete. Moving to home.")
                    self.set_sub_seq(6) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 6: # 홈으로 이동 명령
                cmd = MotionCommand.THICK_GAUGE_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(7)
            elif self._sub_seq == 7: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 15: 두께 측정기에서 시편을 들고 후퇴
        elif self._seq == 15:
            if self._sub_seq == 0: # RETREAT
                cmd = MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK
                robot_cmd = {"process": cmd, "position": self.recovery_pos, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(1)
            elif self._sub_seq == 1: # Wait for RETREAT
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Retreat from indicator complete. Moving to home.")
                    self.set_sub_seq(2) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # 홈으로 이동 명령
                cmd = MotionCommand.THICK_GAUGE_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 20: 정렬기에서 시편 회수
        elif self._seq == 20:
            if self._sub_seq == 0:
                # 인장 시험기 상태를 확인하여 로봇의 다음 동작을 결정합니다.
                shimadzu_state = bb.get("device/shimadzu/run_state")
                is_tensile_busy = False
                if shimadzu_state and isinstance(shimadzu_state, dict):
                    run_status = shimadzu_state.get("RUN")
                    if run_status == 'C':  # 'C' means Testing
                        is_tensile_busy = True
                
                if is_tensile_busy:
                    # 인장기가 사용 중이면 로봇은 후퇴한 상태이므로, 다시 정렬기로 이동해야 합니다.
                    Logger.info("[Logic] Controlled Stop (Aligner): Tensile is busy. Robot must move back to aligner.")
                    cmd = MotionCommand.MOVE_TO_ALIGN
                    robot_cmd = {"process": cmd, "state": ""}
                    bb.set(robot_cmd_key, robot_cmd)
                    self.set_sub_seq(1) # 이동 완료 대기 후 접근
                else:
                    # 인장기가 대기 중이면 로봇은 정렬기 앞(5012)에서 대기하고 있으므로, 접근(5011) 동작 없이 바로 시편을 집습니다.
                    Logger.info("[Logic] Controlled Stop (Aligner): Tensile not busy, robot at wait pos. Skipping move, proceeding to gripper close.")
                    self.set_sub_seq(4) # 바로 그리퍼 닫기 단계로 이동
            elif self._sub_seq == 1: # MOVE_TO_ALIGN 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    self.set_sub_seq(2) # 시편 집기 접근 단계로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # PICK (접근)
                cmd = MotionCommand.PICK_SPECIMEN_FROM_ALIGN
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending approach command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # Wait for PICK
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(4)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 4: # CLOSE (정렬기 상태 확인 후)
                aligner_state = bb.get("device/align/state")
                if aligner_state == "pull":
                    cmd = MotionCommand.GRIPPER_CLOSE_FOR_ALIGN
                    robot_cmd = {"process": cmd, "state": ""}
                    Logger.info(f"[Logic] Controlled Stop: Aligner is 'pull'. Sending command: {cmd}")
                    bb.set(robot_cmd_key, robot_cmd)
                    self.set_sub_seq(5)
                else:
                    Logger.warn(f"[Logic] Controlled Stop: Waiting for aligner to be 'pull' before closing gripper. Current state: {aligner_state}")
                    return LogicEvent.NONE # 대기
            elif self._sub_seq == 5: # Wait for CLOSE
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(6)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 6: # RETREAT
                cmd = MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(7)
            elif self._sub_seq == 7: # Wait for RETREAT
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Recovery from aligner complete. Moving to home.")
                    self.set_sub_seq(8) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 8: # 홈으로 이동 명령
                cmd = MotionCommand.ALIGNER_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(9)
            elif self._sub_seq == 9: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 25: 정렬기에서 시편을 들고 후퇴
        elif self._seq == 25:
            if self._sub_seq == 0: # RETREAT
                cmd = MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(1)
            elif self._sub_seq == 1: # Wait for RETREAT
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Retreat from aligner complete. Moving to home.")
                    self.set_sub_seq(2) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # 홈으로 이동 명령
                cmd = MotionCommand.ALIGNER_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 30: 스크랩 처리
        elif self._seq == 30:
            # 이 상태는 시편을 들고 안전한 위치에 있을 때 진입합니다.
            # 경로: 현재 위치 -> 스크랩 처리기 -> 폐기 -> 홈
            # 
            if self._sub_seq == 0: # 스크랩 처리기로 이동
                cmd = MotionCommand.MOVE_TO_SCRAP_DISPOSER
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, {"process": cmd, "state": ""}); self.set_sub_seq(1)
            elif self._sub_seq == 1: # 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(2)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # 스크랩 처리기에 놓기
                cmd = MotionCommand.PLACE_IN_SCRAP_DISPOSER
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, {"process": cmd, "state": ""}); self.set_sub_seq(3)
            elif self._sub_seq == 3: # 놓기 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(4)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 4: # 그리퍼 열기
                cmd = MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, {"process": cmd, "state": ""}); self.set_sub_seq(5)
            elif self._sub_seq == 5: # 열기 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done": bb.set(robot_cmd_key, None); self.set_sub_seq(6)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 6: # 스크랩 처리기에서 후퇴
                cmd = MotionCommand.RETREAT_FROM_SCRAP_DISPOSER
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, {"process": cmd, "state": ""}); self.set_sub_seq(7)
            elif self._sub_seq == 7: # 후퇴 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Scrap disposal complete.")
                    self.set_seq(40); self.set_sub_seq(0)  # 최종 홈 복귀 상태로 전환
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 40: 홈으로 복귀
        elif self._seq == 40:
            if self._sub_seq == 0:
                # 현재 위치에 따라 적절한 홈 복귀 명령을 선택합니다.
                current_pos_id = int(bb.get("robot/current/position") or 0)
                home_cmd = MotionCommand.MOVE_TO_HOME # 기본 홈 복귀 명령
                
                # Command.md의 후퇴 시퀀스에 따라, 각 Waypoint에서 Home으로 가는 전용 명령이 있다면 사용합니다.
                if current_pos_id == RobotMotionCommand.RACK_FRONT_RETURN: # 랙 앞
                    home_cmd = MotionCommand.RACK_FRONT_HOME
                elif current_pos_id in [RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_1, RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_2, RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_3]: # 측정기 앞
                    home_cmd = MotionCommand.THICK_GAUGE_FRONT_HOME
                elif current_pos_id == RobotMotionCommand.ALIGNER_FRONT_RETURN: # 정렬기 앞
                    home_cmd = MotionCommand.ALIGNER_FRONT_HOME
                elif current_pos_id == RobotMotionCommand.TENSILE_FRONT_RETURN: # 인장기 앞
                    home_cmd = MotionCommand.TENSILE_TESTER_FRONT_HOME
                elif current_pos_id == RobotMotionCommand.SCRAP_FRONT_RETURN: # 스크랩 처리기 앞
                    home_cmd = MotionCommand.SCRAP_DISPOSER_FRONT_HOME

                Logger.info(f"[Logic] Controlled Stop: Sending final home command: {home_cmd}")
                bb.set(robot_cmd_key, {"process": home_cmd, "state": ""}); self.set_sub_seq(1)
            elif self._sub_seq == 1:
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None); Logger.info("[Logic] Controlled Stop: Sequence finished at Home.")
                    self.set_seq(0); self.set_sub_seq(0)
                    return LogicEvent.PROCESS_STOP
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        
        # State 50: 랙에서 후퇴
        elif self._seq == 50:
            if self._sub_seq == 0:
                current_pos_id = int(bb.get("robot/current/position") or 0)
                floor = (current_pos_id - 1000) // 10
                cmd = MotionCommand.PICK_SPECIMEN_FROM_RACK
                robot_cmd = {"process": cmd, "target_floor": floor, "target_num": 0, "position": 0, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(1)
            elif self._sub_seq == 1:
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Retreat from rack complete. Moving to home.")
                    self.set_sub_seq(2) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # 홈으로 이동 명령
                cmd = MotionCommand.RACK_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 55: 랙에서 시편을 잡지 않고 후퇴 (제어된 정지)
        elif self._seq == 55:
            if self._sub_seq == 0: # 그리퍼 열기 (안전 조치)
                cmd = MotionCommand.GRIPPER_OPEN_AT_INDICATOR # 범용 그리퍼 열기 명령 (ID: 90)
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(1)
            elif self._sub_seq == 1: # 그리퍼 열기 완료 대기
                if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_INDICATOR:
                    if get_robot_cmd.get("state") == "done":
                        bb.set(robot_cmd_key, None)
                        self.set_sub_seq(2)
                    elif get_robot_cmd.get("state") == "error":
                        return LogicEvent.VIOLATION_DETECT
                # 이전 명령의 완료/에러는 무시하고 현재 명령의 결과를 기다립니다.
            elif self._sub_seq == 2: # 랙에서 후퇴
                current_pos_id = int(bb.get("robot/current/position") or 0)
                # current_pos_id가 1011~1105 범위에 있을 것으로 예상
                floor = (current_pos_id - 1000) // 10
                # [중요] 여기서 PICK_SPECIMEN_FROM_RACK을 사용하는 것은 의도된 동작입니다.
                # 이 명령은 target_num=0, position=0 파라미터와 함께 사용될 때,
                # 시편을 잡지 않고 랙 내부에서 안전하게 후퇴하는 동작을 수행합니다.
                # MotionCommand.RETREAT_FROM_RACK은 시편을 든 상태에서의 후퇴를 가정하므로 여기서는 적합하지 않습니다.
                cmd = MotionCommand.PICK_SPECIMEN_FROM_RACK
                robot_cmd = {"process": cmd, "target_floor": floor, "target_num": 0, "position": 0, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # 후퇴 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Retreat from rack complete.")
                    self.set_seq(40) # 홈으로 복귀 상태로 전환
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # State 60: 인장기에서 후퇴
        elif self._seq == 60:
            if self._sub_seq == 0:
                cmd = MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(1)
            elif self._sub_seq == 1:
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Retreat from tensile machine complete. Moving to home.")
                    self.set_sub_seq(2) # 홈으로 이동
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            elif self._sub_seq == 2: # 홈으로 이동 명령
                cmd = MotionCommand.TENSILE_TESTER_FRONT_HOME
                robot_cmd = {"process": cmd, "state": ""}
                Logger.info(f"[Logic] Controlled Stop: Sending command: {cmd}")
                bb.set(robot_cmd_key, robot_cmd)
                self.set_sub_seq(3)
            elif self._sub_seq == 3: # 홈 이동 완료 대기
                if get_robot_cmd and get_robot_cmd.get("state") == "done":
                    bb.set(robot_cmd_key, None)
                    Logger.info("[Logic] Controlled Stop: Move to home complete. Proceeding to scrap disposal.")
                    self.set_seq(30) # 스크랩 처리로 이동
                    self.set_sub_seq(0)
                elif get_robot_cmd and get_robot_cmd.get("state") == "error": return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
            
        return LogicEvent.NONE

       

    def process_complete(self):
        """ 모든 배치 공정이 완료되었음을 처리하고 FSM을 대기 상태로 전환합니다. """
        Logger.info("[Logic] All batch processes are complete. Returning to command wait state.")
        bb.set("ui/cmd/auto/tensile", 2)  # UI에 공정 완료 상태 전송 (2: 완료)
        return LogicEvent.DONE