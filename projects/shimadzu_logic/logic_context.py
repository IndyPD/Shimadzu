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
        self._seq = 0
        self.db = db_handler

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
        Logger.info(f"-------------------------------------------------------")
        Logger.info(f"move_to_rack_for_QRRead called.")
        Logger.info(f"floor: {floor}, specimen_num: {specimen_num}, Sequence: {Sequence}")
        Logger.info(f"_seq : {self._seq}")
        Logger.info(f"get_robot_cmd: {get_robot_cmd}")
        Logger.info(f"get_device_cmd: {get_device_cmd}")
        Logger.info(f"-------------------------------------------------------")

        # Step 0: Send command to move to rack front (ID: 1000)
        if self._seq == 0:
            robot_cmd = {
                "process" : MotionCommand.MOVE_TO_RACK,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 0: Sending command to move to rack front.")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 1 # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 1: Wait for rack front move to complete
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Step 1: Move to rack front is done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 2 # Transition to next action
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE # Keep waiting if not done or no cmd yet

        # Step 2: Send command to move to QR scan position
        elif self._seq == 2:
            robot_cmd = {
                "process" : MotionCommand.MOVE_TO_QR_SCAN_POS,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 2: Sending command to move to QR scan position.")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3 # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 3: Wait for QR scan position move to complete
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_QR_SCAN_POS:
                if get_robot_cmd.get("state") == "done":
                    Logger.info("[Logic] Step 3: Move to QR scan position is done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 4 # Transition to next action (device command)
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 4: Send device command for QR read
        elif self._seq == 4:
            device_cmd = {
                "process" : DeviceCommand.QR_READ,
                "result" : None,
                "state" : "",
                "is_done" : False
            }
            Logger.info(f"[Logic] Step 4: Sending command to read QR code.")
            bb.set(device_cmd_key, device_cmd)
            self._seq = 5 # Immediately transition to waiting state
            return LogicEvent.NONE

        # Step 5: Wait for QR read to complete
        elif self._seq == 5:
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
                    bb.set(device_cmd_key, None) # Consume the result
                    self._seq = 0 # Reset sequence for the next call of this function
                    return LogicEvent.DONE
                else: # state == "error"
                    Logger.error(f"[Logic] Step 5 failed: {get_device_cmd}")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

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
        if self._seq == 0:
            robot_cmd = {
                "process" : MotionCommand.PICK_SPECIMEN_FROM_RACK,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_RACK}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 1
            return LogicEvent.NONE
        
        # Step 1: Wait for pick move to complete, then close gripper
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Pick move done. Closing gripper.")
                    bb.set(robot_cmd_key, None)
                    robot_cmd = { "process" : MotionCommand.GRIPPER_CLOSE_FOR_RACK, "state" : "" }
                    bb.set(robot_cmd_key, robot_cmd)
                    self._seq = 2
                    return LogicEvent.NONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 2: Wait for gripper to close, then retreat from rack
        elif self._seq == 2:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 2: Gripper close done. Retreating from rack.")
                    bb.set(robot_cmd_key, None)
                    robot_cmd = {
                        "process" : MotionCommand.RETREAT_FROM_RACK,
                        "target_floor" : floor,
                        "state" : ""
                    }
                    bb.set(robot_cmd_key, robot_cmd)
                    self._seq = 3
                    return LogicEvent.NONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 2 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Step 3: Wait for retreat to complete
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_RACK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Retreat from rack is done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        
        return LogicEvent.NONE

    def Measure_specimen_thickness(self, num: int):
        """
        # Position B Indigator
        시편을 치수 측정기로 옮겨 두께를 측정하고 다시 집어오는 전체 시퀀스를 수행합니다.
        num 값에 따라 측정 위치(1, 2, 3)가 결정됩니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_INDIGATOR
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_INDIGATOR, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_INDIGATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 1
            return LogicEvent.NONE

        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_INDIGATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Move to indicator done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 2
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-PLACE_SPECIMEN_AND_MEASURE
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PLACE_SPECIMEN_AND_MEASURE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PLACE_SPECIMEN_AND_MEASURE} at pos {num}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
            return LogicEvent.NONE

        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_SPECIMEN_AND_MEASURE:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Place specimen done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 4
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-GRIPPER_OPEN_AT_INDIGATOR
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_INDIGATOR, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_OPEN_AT_INDIGATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 5
            return LogicEvent.NONE

        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_INDIGATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Gripper open done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 6
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Robot-Motion-RETREAT_FROM_INDIGATOR_AFTER_PLACE
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PLACE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PLACE}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 7
            return LogicEvent.NONE

        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PLACE:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 7: Retreat from indicator done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 8
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Device-Indigator-MEASURE_THICKNESS
        elif self._seq == 8:
            device_cmd = {"command": DeviceCommand.MEASURE_THICKNESS, "result": None, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 8: Sending command: {DeviceCommand.MEASURE_THICKNESS}")
            bb.set(device_cmd_key, device_cmd)
            self._seq = 9
            return LogicEvent.NONE

        elif self._seq == 9:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.MEASURE_THICKNESS:
                if get_device_cmd.get("is_done"):
                    if get_device_cmd.get("state") == "done":
                        thickness_result = get_device_cmd.get("result")
                        thickness_data = bb.get("process/auto/thickness") or {}
                        thickness_data[str(num)] = thickness_result
                        bb.set("process/auto/thickness", thickness_data)
                        Logger.info(f"[Logic] Step 9: Thickness measurement done. Result: {thickness_result}")
                        bb.set(device_cmd_key, None)
                        self._seq = 10
                    else:  # error
                        Logger.error(f"[Logic] Step 9 failed: {get_device_cmd}")
                        bb.set(device_cmd_key, None)
                        self._seq = 0
                        return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 6: Robot-Motion-PICK_SPECIMEN_FROM_INDIGATOR
        elif self._seq == 10:
            robot_cmd = {"process": MotionCommand.PICK_SPECIMEN_FROM_INDIGATOR, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 10: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_INDIGATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 11
            return LogicEvent.NONE

        elif self._seq == 11:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_INDIGATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 11: Pick from indicator done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 12
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 11 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 7: Robot-Motion-GRIPPER_CLOSE_FOR_INDIGATOR
        elif self._seq == 12:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_INDIGATOR, "state": ""}
            Logger.info(f"[Logic] Step 12: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_INDIGATOR}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 13
            return LogicEvent.NONE

        elif self._seq == 13:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_INDIGATOR:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 13: Gripper close done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 14
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 13 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 8: Robot-Motion-RETREAT_FROM_INDIGATOR_AFTER_PICK
        elif self._seq == 14:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PICK, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 14: Sending command: {MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 15
            return LogicEvent.NONE

        elif self._seq == 15:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_INDIGATOR_AFTER_PICK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 15: Final retreat from indicator is done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 15 failed: {get_robot_cmd}")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        return LogicEvent.NONE
    
    def Specimen_Align(self):
        """
        # Position C Aligner
        시편을 정렬기에 내려놓고 정렬을 수행하는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)
        get_device_cmd = bb.get(device_cmd_key)

        # Seq 1: Robot-Motion-MOVE_TO_ALIGN
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.MOVE_TO_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.MOVE_TO_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 1
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to align done.")
                bb.set(robot_cmd_key, None)
                self._seq = 2
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        # Seq 2: Robot-Motion-PLACE_SPECIMEN_ON_ALIGN
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PLACE_SPECIMEN_ON_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PLACE_SPECIMEN_ON_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_SPECIMEN_ON_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Place specimen on align done.")
                bb.set(robot_cmd_key, None)
                self._seq = 4
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        # Seq 3: Robot-Motion-GRIPPER_OPEN_AT_ALIGN
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_OPEN_AT_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 5
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_ALIGN and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 5: Gripper open at align done.")
                bb.set(robot_cmd_key, None)
                self._seq = 6
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        # Seq 4: Robot-Motion-RETREAT_FROM_ALIGN_AFTER_PLACE
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 7
        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 7: Retreat from align done.")
                bb.set(robot_cmd_key, None)
                self._seq = 8
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        # Seq 5: Device-Align-ALIGN_SPECIMEN
        elif self._seq == 8:
            device_cmd = {"command": DeviceCommand.ALIGN_SPECIMEN, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 8: Sending command: {DeviceCommand.ALIGN_SPECIMEN}")
            bb.set(device_cmd_key, device_cmd)
            self._seq = 9
        elif self._seq == 9:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.ALIGN_SPECIMEN and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 9: Align specimen done.")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                else:
                    Logger.error(f"[Logic] Step 9 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        return LogicEvent.NONE
    
    def Pick_Specimen_From_Align(self):
        """
        # Position C Aligner
        정렬된 시편을 집어서 나오는 전체 시퀀스입니다.
        """
        get_robot_cmd = bb.get(robot_cmd_key)

        # Seq 1: Robot-Motion-PICK_SPECIMEN_FROM_ALIGN
        if self._seq == 0:
            robot_cmd = {"process": MotionCommand.PICK_SPECIMEN_FROM_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 0: Sending command: {MotionCommand.PICK_SPECIMEN_FROM_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 1
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_SPECIMEN_FROM_ALIGN:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 1: Pick from align done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 2
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-GRIPPER_CLOSE_FOR_ALIGN
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_ALIGN, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_ALIGN}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_ALIGN:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 3: Gripper close for align done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 4
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-RETREAT_FROM_ALIGN_AFTER_PICK
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 5
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK:
                if get_robot_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Retreat from align done.")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                elif get_robot_cmd.get("state") == "error":
                    Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
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
            self._seq = 1
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_LOAD and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 2
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-load_tensile_machine
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.LOAD_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.LOAD_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.LOAD_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Load tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 4
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Device-Tensil_gripper-TENSILE_GRIPPER_ON
        elif self._seq == 4:
            device_cmd = {"command": DeviceCommand.TENSILE_GRIPPER_ON, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 4: Sending command: {DeviceCommand.TENSILE_GRIPPER_ON}")
            bb.set(device_cmd_key, device_cmd)
            self._seq = 5
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.TENSILE_GRIPPER_ON and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 5: Tensile gripper on done.")
                    bb.set(device_cmd_key, None)
                    self._seq = 6
                else:
                    Logger.error(f"[Logic] Step 5 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Robot-Motion-GRIPPER_OPEN_AT_TENSILE_MACHINE
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 7
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 7: Gripper open at tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 8
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Robot-Motion-RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 9
            return LogicEvent.NONE
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Retreat from tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 10
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        
        # Seq 6: Robot-Motion-MOVE_TO_HOME
        elif self._seq == 10:
            robot_cmd = {"process": MotionCommand.MOVE_TO_HOME, "state": ""}
            Logger.info(f"[Logic] Step 10: Sending command: {MotionCommand.MOVE_TO_HOME}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 11
            return LogicEvent.NONE
        elif self._seq == 11:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_HOME and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 11: Move to home done.")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 11 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
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
            self._seq = 1
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_PICK and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to tensile for pick done.")
                bb.set(robot_cmd_key, None)
                self._seq = 2
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

        # Seq 2: Robot_Motion-PICK_FROM_TENSILE_MACHINE
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PICK_FROM_TENSILE_MACHINE, "position": num, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PICK_FROM_TENSILE_MACHINE} at pos {num}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PICK_FROM_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Pick from tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 4
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: GRIPPER_CLOSE_FOR_TENSILE_MACHINE
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 5
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 5: Gripper close for tensile machine done.")
                bb.set(robot_cmd_key, None)
                self._seq = 6
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Device-Tensile_gripper-TENSILE_GRIPPER_OFF
        elif self._seq == 6:
            device_cmd = {"command": DeviceCommand.TENSILE_GRIPPER_OFF, "state": "", "is_done": False}
            Logger.info(f"[Logic] Step 6: Sending command: {DeviceCommand.TENSILE_GRIPPER_OFF}")
            bb.set(device_cmd_key, device_cmd)
            self._seq = 7
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.TENSILE_GRIPPER_OFF and get_device_cmd.get("is_done"):
                if get_device_cmd.get("state") == "done":
                    Logger.info(f"[Logic] Step 7: Tensile gripper off done.")
                    bb.set(device_cmd_key, None)
                    self._seq = 8
                else:
                    Logger.error(f"[Logic] Step 7 failed: {get_device_cmd}"); bb.set(device_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 9
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Retreat from tensile machine after pick done.")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT

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
            self._seq = 1
            return LogicEvent.NONE
        elif self._seq == 1:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 1: Move to scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self._seq = 2
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 1 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 2: Robot-Motion-PLACE_IN_SCRAP_DISPOSER
        elif self._seq == 2:
            robot_cmd = {"process": MotionCommand.PLACE_IN_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 2: Sending command: {MotionCommand.PLACE_IN_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 3
            return LogicEvent.NONE
        elif self._seq == 3:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.PLACE_IN_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 3: Place in scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self._seq = 4
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 3 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 3: Robot-Motion-GRIPPER_OPEN_AT_SCRAP_DISPOSER
        elif self._seq == 4:
            robot_cmd = {"process": MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 4: Sending command: {MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 5
            return LogicEvent.NONE
        elif self._seq == 5:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 5: Gripper open at scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self._seq = 6
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 5 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 4: Robot-Motion-RETREAT_FROM_SCRAP_DISPOSER
        elif self._seq == 6:
            robot_cmd = {"process": MotionCommand.RETREAT_FROM_SCRAP_DISPOSER, "state": ""}
            Logger.info(f"[Logic] Step 6: Sending command: {MotionCommand.RETREAT_FROM_SCRAP_DISPOSER}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 7
            return LogicEvent.NONE
        elif self._seq == 7:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.RETREAT_FROM_SCRAP_DISPOSER and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 7: Retreat from scrap disposer done.")
                bb.set(robot_cmd_key, None)
                self._seq = 8
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 7 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE

        # Seq 5: Robot-Motion-MOVE_TO_HOME
        elif self._seq == 8:
            robot_cmd = {"process": MotionCommand.MOVE_TO_HOME, "state": ""}
            Logger.info(f"[Logic] Step 8: Sending command: {MotionCommand.MOVE_TO_HOME}")
            bb.set(robot_cmd_key, robot_cmd)
            self._seq = 9
            return LogicEvent.NONE
        elif self._seq == 9:
            if get_robot_cmd and get_robot_cmd.get("process") == MotionCommand.MOVE_TO_HOME and get_robot_cmd.get("state") == "done":
                Logger.info(f"[Logic] Step 9: Move to home done.")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            elif get_robot_cmd and get_robot_cmd.get("state") == "error":
                Logger.error(f"[Logic] Step 9 failed: {get_robot_cmd}"); bb.set(robot_cmd_key, None); self._seq = 0; return LogicEvent.VIOLATION_DETECT
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
                    self._seq = 0
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
                    self._seq = 0
                    return LogicEvent.VIOLATION_DETECT

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
                self._seq = 1
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1:
                if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.REGISTER_METHOD:
                    if not get_device_cmd.get("is_done"):
                        return LogicEvent.NONE

                    if get_device_cmd.get("state") == "done":
                        Logger.info(f"[Logic] DeviceFSM completed method registration.")
                        bb.set(device_cmd_key, None)
                        self._seq = 0
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to register method: {get_device_cmd.get('result')}")
                        bb.set(device_cmd_key, None)
                        self._seq = 0
                        return LogicEvent.VIOLATION_DETECT
            return LogicEvent.NONE
        except Exception as e:
            Logger.error(f"[Logic] Exception in regist_tensil_data: {e}")
            self._seq = 0
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
                self._seq = 1
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1:
                if get_device_cmd and get_device_cmd.get("command") == DeviceCommand.START_TENSILE_TEST:
                    if not get_device_cmd.get("is_done"):
                        return LogicEvent.NONE

                    if get_device_cmd.get("state") == "done":
                        Logger.info("[Logic] DeviceFSM confirmed tensile test started.")
                        bb.set(device_cmd_key, None)
                        self._seq = 0
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to start tensile test: {get_device_cmd.get('result')}")
                        bb.set(device_cmd_key, None)
                        self._seq = 0
                        return LogicEvent.VIOLATION_DETECT
            
            return LogicEvent.NONE

        except Exception as e:
            Logger.error(f"[Logic] Exception in start_tensile_test: {e}")
            self._seq = 0
            return LogicEvent.VIOLATION_DETECT

    def process_complete(self):
        """ 모든 배치 공정이 완료되었음을 처리하고 FSM을 대기 상태로 전환합니다. """
        Logger.info("[Logic] All batch processes are complete. Returning to command wait state.")
        bb.set("ui/cmd/auto/tensile", 2)  # UI에 공정 완료 상태 전송 (2: 완료)
        return LogicEvent.DONE