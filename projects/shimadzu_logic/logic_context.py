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

        # DB 동기화 스레드 시작 (test_tray_items 주기적 업데이트)
        self.th_db_sync = threading.Thread(target=self._thread_db_sync, daemon=True)
        self.th_db_sync.start()

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

    def _thread_db_sync(self):
        """
        Blackboard의 공정 데이터를 DB의 test_tray_items 테이블에 주기적으로 동기화합니다.
        """
        while True:
            try:
                batch_data = bb.get("process/auto/batch_data")
                thickness_map = bb.get("process/auto/thickness") or {}
                current_spec_no = bb.get("process/auto/current_specimen_no") or 1
                
                if isinstance(batch_data, dict) and "processData" in batch_data:
                    batch_id = batch_data.get("batch_id")
                    for item in batch_data["processData"]:
                        tray_no = item.get("tray_no")
                        specimen_no = current_spec_no if item.get("seq_status") == 2 else 1
                        seq_status = item.get("seq_status")
                        
                        # 상태 문자열 매핑 (DB.md 3.2 status_str)
                        status_map = {1: "READY", 2: "RUNNING", 3: "DONE"}
                        status_str = status_map.get(seq_status, "UNKNOWN")
                        
                        # 두께 정보 (dimension) 반영
                        dimension = thickness_map.get(str(specimen_no))

                        self.db.update_test_tray_info(
                            tray_no=tray_no,
                            specimen_no=specimen_no,
                            status=seq_status,
                            status_str=status_str,
                            batch_id=batch_id,
                            lot=item.get("lot"),
                            test_spec=item.get("test_method"),
                            dimension=dimension
                        )
            except Exception as e:
                Logger.error(f"[Logic] Error in _thread_db_sync: {e}")
            
            time.sleep(5.0) # 5초 주기로 동기화
    
    def move_to_rack_for_QRRead(self, floor : int = 0, specimen_num : int = 0, Sequence : int = 0) :
        '''
        # Position A Rack
        Docstring for move_to_rack_for_QRRead
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번
        move_to_rack_for_QRRead 로봇 모션, QR Read
        '''

        get_robot_cmd : dict = bb.get(robot_cmd_key)
        
        # 1. rack 앞 이동 후 층별 QR위치 이동 로봇 명령 세팅
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M00_MOVE_TO_RACK,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. rack 앞 이동 후 층별 QR위치 이동 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M00_MOVE_TO_RACK and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                
                Logger.info("[Logic] move_to_rack_for_QRRead: LogicEvent.DONE")
                device_cmd = {
                    "process" : Device_command.QR_READ,
                    "result" : None,
                    "state" : "",
                    "is_done" : False
                }
                bb.set(device_cmd_key, device_cmd)
                Logger.info(f"[Logic] bb.set({device_cmd_key}, {device_cmd})")
                self._seq = 1

            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M00_MOVE_TO_RACK and
                  get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] move_to_rack_for_QRRead failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
        if self._seq == 1 :
            get_device_cmd : dict = bb.get(device_cmd_key)
            if get_device_cmd :
                # 완료 확인
                if (get_device_cmd.get("process") == Device_command.QR_READ and
                    get_device_cmd.get("is_done") == True) :
                    qr_result = get_device_cmd.get("result")
                    
                    # blackboard.json에 정의된 dict 구조를 유지하며 업데이트
                    qr_data = bb.get("process/auto/qr_data") or {}
                    qr_data[str(Sequence)] = qr_result
                    bb.set("process/auto/qr_data", qr_data)
                    Logger.info(f"[Logic] QR Data saved to blackboard: process/auto/qr_data/{Sequence} = {qr_result}")

                    Logger.info(f"[Logic] bb.set({device_cmd_key}, None)")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_device_cmd.get("process") == Device_command.QR_READ and
                      get_device_cmd.get("is_done") == False and
                      get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] move_to_rack_for_QRRead failed:{get_device_cmd}")
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE

    def pick_specimen(self, floor : int = 0, specimen_num : int = 0): # A
        '''
        # Position A Rack
        Docstring for pick_specimen
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번

        pick_specimen 로봇 모션만 함
        '''       
        
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        # device_cmd = bb.get(device_cmd)
        # 1. 시편 잡으로 가기 로봇 명령 세팅
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M01_PICK_SPECIMEN,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. 시편 잡기 명령 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M01_PICK_SPECIMEN and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] pick_specimen: LogicEvent.DONE")
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M01_PICK_SPECIMEN and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] pick_specimen failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE
    
    def move_to_indigator(self, floor : int = 0, specimen_num : int = 0): # B
        '''
        # Position B Indigator
        Docstring for move_to_indigator
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번
        move_to_indigator 로봇 모션만 함
        '''
        
        # 1. 시편 잡고 두께 측정기 앞 이동 로봇 모션 명령 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        # device_cmd = bb.get(device_cmd)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M02_MOVE_TO_INDICATOR,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)

        # 1-1. 시편 잡고 두께 측정기 앞 이동 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M02_MOVE_TO_INDICATOR and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] move_to_indigator: LogicEvent.DONE")
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M02_MOVE_TO_INDICATOR and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] move_to_indigator failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE
   
    def place_specimen_and_measure(self,
                                   floor : int = 0, 
                                   specimen_num : int = 0,
                                   Sequence : int = 0): 
        '''
        # Position B Indigator
        Docstring for place_specimen_and_measure
        :param floor: Description
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번
        :param Sequence: 두께 측정 3번하는거
        place_specimen_and_measure 로봇 모션 and 두께측정 함
        '''
        
        # 1. 시편 잡고 두께 측정기 앞 이동 후 시편 두고 빠지는 모션 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M03_PLACE_AND_MEASURE,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
            
        # 1-1. 시편 잡고 두께 측정기 앞 이동 후 시편 두고 빠지는 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M03_PLACE_AND_MEASURE and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                # 두께 측정 명령 생성
                device_cmd = {
                    "command" : Device_command.MEASURE_THICKNESS,
                    "result" : None,
                    "state" : "",
                    "is_done" : False                               
                }
                Logger.info(f"[Logic] bb.set({device_cmd_key}, {device_cmd})")
                bb.set(device_cmd_key, device_cmd)
                self._seq = 1

            # 에레 확인
            elif (get_robot_cmd.get("process") == Motion_command.M03_PLACE_AND_MEASURE and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] place_specimen_and_measure (robot) failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE   

        # 2. 두께 측정 완료 확인
        get_device_cmd : dict = bb.get(device_cmd_key)
        if self._seq == 1 and get_device_cmd :
            # 완료 확인
            if (get_device_cmd.get("command") == Device_command.MEASURE_THICKNESS and
                get_device_cmd.get("is_done") == True) :
                
                # blackboard.json에 정의된 dict 구조를 유지하며 업데이트
                thickness_data = bb.get("process/auto/thickness") or {}
                thickness_data[str(Sequence)] = get_device_cmd.get("result")
                bb.set("process/auto/thickness", thickness_data)
                
                Logger.info(f"[Logic] bb.set(process/auto/thickness/{Sequence}, {get_device_cmd.get('result')})")
                Logger.info(f"[Logic] bb.set({device_cmd_key}, None)")
                bb.set(device_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] place_specimen_and_measure: LogicEvent.DONE")
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_device_cmd.get("command") == Device_command.MEASURE_THICKNESS and
                get_device_cmd.get("is_done") == False and
                get_device_cmd.get("state") == "error") :
                Logger.error(f"[Logic] place_specimen_and_measure (device) failed: {get_device_cmd}")
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE
                
    def Pick_specimen_out_from_indigator(self, 
                                         floor : int = 0, 
                                         specimen_num : int = 0, 
                                         Sequence : int = 0):
        '''
        Docstring for Pick_specimen_out_from_indigator
        
        :param floor: Description
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번
        :param Sequence: 두께 측정 3번하는거
        Pick_specimen_out_from_indigator 로봇 모션만 함
        '''
        
        
        # 1. 두께 측정기 안 시편 잡아오기 로봇 모션 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M04_PICK_OUT_FROM_INDICATOR,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. 두께 측정기 안 시편 잡아오기 로봇 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M04_PICK_OUT_FROM_INDICATOR and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] Pick_specimen_out_from_indigator: LogicEvent.DONE")
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M04_PICK_OUT_FROM_INDICATOR and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] Pick_specimen_out_from_indigator failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE

    def align_specimen(self, 
                        floor : int = 0, 
                        specimen_num : int = 0, 
                        Sequence : int = 0):
        '''
        Docstring for align_specimen
        place_specimen_and_measure 로봇 모션 and 정렬기 동작 함
        '''

        # 1. 정렬기에 가져다 놓기 명령 전달
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M05_ALIGN_SPECIMEN,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)

        # 1-1. 정렬기 명령 전달 후 모션 완료 대기
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M05_ALIGN_SPECIMEN and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 1
                # 장비제어 명령 세팅 : 정렬기 정렬
                device_cmd = {
                    "command" : Device_command.ALIGN_SPECIMEN,
                    "result" : None,
                    "state" : "",
                    "is_done" : False                               
                }
                Logger.info(f"[Logic] bb.set({device_cmd_key}, {device_cmd})")
                bb.set(device_cmd_key, device_cmd)
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M05_ALIGN_SPECIMEN and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] align_specimen (robot approach) failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
            
        # 2. 시편 정렬 명령 수행
        if self._seq == 1 :
            get_device_cmd : dict = bb.get(device_cmd_key)
            if get_device_cmd :
                # 완료 확인
                if (get_device_cmd.get("command") == Device_command.ALIGN_SPECIMEN and
                    get_device_cmd.get("is_done") == True) :
                    Logger.info(f"[Logic] bb.set({device_cmd_key}, None)")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    Logger.info("[Logic] align_specimen: LogicEvent.DONE")
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_device_cmd.get("command") == Device_command.ALIGN_SPECIMEN and
                    get_device_cmd.get("is_done") == False and
                    get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] align_specimen (device) failed: {get_device_cmd}")
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE

    def Pick_specimen_out_from_align(self, 
                                     floor : int = 0, 
                                     specimen_num : int = 0, 
                                     Sequence : int = 0):
        """
        정렬기에서 정렬된 시편을 잡고 나오는 로봇 모션을 수행합니다.
        """
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M06_PICK_OUT_FROM_ALIGN,
                "target_floor" : floor,
                "target_num" : specimen_num,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M06_PICK_OUT_FROM_ALIGN and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] Pick_specimen_out_from_align: LogicEvent.DONE")
                return LogicEvent.DONE
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M06_PICK_OUT_FROM_ALIGN and
                  get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] Pick_specimen_out_from_align failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
                
    def load_tensile_machine(self, 
                            floor : int = 0, 
                            specimen_num : int = 0, 
                            Sequence : int = 0):
        ''''''
        # 1. 인장기 내 시편 가져다 두기 명령 전달
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M07_LOAD_TENSILE_MACHINE,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        
        # 1-1. 인장기 내 시편 가져다 두기 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M07_LOAD_TENSILE_MACHINE and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 1
                device_cmd = {
                    "process" : Device_command.TENSILE_GRIPPER_ON,
                    "result" : None,
                    "state" : "",
                    "is_done" : False
                }
                Logger.info(f"[Logic] bb.set({device_cmd_key}, {device_cmd})")
                bb.set(device_cmd_key, device_cmd)
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M07_LOAD_TENSILE_MACHINE and
                get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] load_tensile_machine (robot) failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
            
        if self._seq == 1 :
            get_device_cmd : dict = bb.get(device_cmd_key)
            if get_device_cmd :
                # 완료 확인
                if (get_device_cmd.get("process") == Device_command.TENSILE_GRIPPER_ON and
                    get_device_cmd.get("is_done") == True) :
                    Logger.info(f"[Logic] bb.set({device_cmd_key}, None)")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    Logger.info("[Logic] load_tensile_machine: LogicEvent.DONE")
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_device_cmd.get("process") == Device_command.TENSILE_GRIPPER_ON and
                    get_device_cmd.get("is_done") == False and
                    get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] load_tensile_machine (device) failed: {get_device_cmd}")
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE
    
    def retreat_tensile_machine(self,
                                floor : int = 0, 
                                specimen_num : int = 0, 
                                Sequence : int = 0):
        '''
        Docstring for retreat_tensile_machine
        '''
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        # 1. 인장기에서 시편 두고 나오기(인장기 그리퍼가 시편 잡고있음)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M08_RETREAT_TENSILE_MACHINE,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : 0,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. 인장기에서 시편 두고 나오기 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M08_RETREAT_TENSILE_MACHINE and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                Logger.info("[Logic] retreat_tensile_machine: LogicEvent.DONE")
                return LogicEvent.DONE
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M08_RETREAT_TENSILE_MACHINE and
                  get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] retreat_tensile_machine failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            else :
                return LogicEvent.NONE
        
    def pick_tensile_machine(self,
                            floor : int = 0, 
                            specimen_num : int = 0, 
                            Sequence : int = 0):
        ''''''
        
        # 1. 완료 시편(Sequence 상단:1,하단,2) 잡기
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M09_PICK_TENSILE_MACHINE,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == Motion_command.M09_PICK_TENSILE_MACHINE and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 1
                device_cmd = {
                    "process" : Device_command.TENSILE_GRIPPER_OFF,
                    "result" : None,
                    "state" : "",
                    "is_done" : False
                }
                Logger.info(f"[Logic] bb.set({device_cmd_key}, {device_cmd})")
                bb.set(device_cmd_key, device_cmd)
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M09_PICK_TENSILE_MACHINE and
                  get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] pick_tensile_machine (robot) failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
            
        # 2. 인장기 그리퍼 풀기
        if self._seq == 1 :
            get_device_cmd : dict = bb.get(device_cmd_key)
            if get_device_cmd :
                # 완료 확인
                if (get_device_cmd.get("process") == Device_command.TENSILE_GRIPPER_OFF and
                    get_device_cmd.get("is_done") == True) :
                    Logger.info(f"[Logic] bb.set({device_cmd_key}, None)")
                    bb.set(device_cmd_key, None)
                    self._seq = 0
                    Logger.info("[Logic] pick_tensile_machine: LogicEvent.DONE")
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_device_cmd.get("process") == Device_command.TENSILE_GRIPPER_OFF and
                      get_device_cmd.get("is_done") == False and
                      get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] pick_tensile_machine (device) failed: {get_device_cmd}")
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE
    
    def retreat_and_handle_scrap(self,
                                 floor : int = 0, 
                                 specimen_num : int = 0, 
                                 Sequence : int = 0):
        ''''''
        # 1. 완료 시편(Sequence 상단:1, 하단,2) 잡고 후퇴 후 스크랩통에 버리기
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : Motion_command.M10_RETREAT_AND_HANDLE_SCRAP,
                "target_floor" : 0,
                "target_num" : 0,
                "position" : Sequence,
                "state" : ""
            }
            Logger.info(f"[Logic] bb.set({robot_cmd_key}, {robot_cmd})")
            bb.set(robot_cmd_key, robot_cmd)
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if( get_robot_cmd.get("process") == Motion_command.M10_RETREAT_AND_HANDLE_SCRAP and
                get_robot_cmd.get("state") == "done") :
                Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            # 에러 확인
            elif (get_robot_cmd.get("process") == Motion_command.M10_RETREAT_AND_HANDLE_SCRAP and
                  get_robot_cmd.get("state") == "error") :
                Logger.error(f"[Logic] retreat_and_handle_scrap failed: {get_robot_cmd}")
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
            
    def regist_tensil_data(self):
        """
        현재 시편의 시험 조건을 DB에서 조회하여 Device FSM에 등록 명령을 전달하고 완료를 대기합니다.
        이 함수는 Strategy에 의해 반복적으로 호출되는 것을 가정합니다.
        """
        try:
            get_device_cmd = bb.get(device_cmd_key)

            # Step 1: 명령 전송 (아직 전송되지 않았을 경우)
            if self._seq == 0 and get_device_cmd is None:
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
                size1 = thickness_map.get(str(specimen_no), method_details.get("default_thickness", "1.0")) 
                size2 = method_details.get("specimen_width", "10.0")

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
                device_cmd = { "command": "REGISTER_METHOD", "params": regist_data, "state": "", "is_done": False }
                bb.set(device_cmd_key, device_cmd)
                Logger.info(f"[Logic] Sent REGISTER_METHOD command to DeviceFSM for specimen {tpname}")
                self._seq = 1
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1 and get_device_cmd is not None:
                if (get_device_cmd.get("command") == "REGISTER_METHOD" and get_device_cmd.get("is_done")):
                    self._seq = 0
                    bb.set(device_cmd_key, None)
                    if get_device_cmd.get("state") == "done":
                        Logger.info(f"[Logic] DeviceFSM completed method registration.")
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to register method: {get_device_cmd.get('result')}")
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
            if self._seq == 0 and get_device_cmd is None:
                device_cmd = {
                    "command": Device_command.START_TENSILE_TEST,
                    "state": "",
                    "is_done": False
                }
                bb.set(device_cmd_key, device_cmd)
                Logger.info(f"[Logic] Sent START_TENSILE_TEST command to DeviceFSM.")
                self._seq = 1
                return LogicEvent.NONE

            # Step 2: 명령 완료 대기
            elif self._seq == 1 and get_device_cmd is not None:
                if (get_device_cmd.get("command") == Device_command.START_TENSILE_TEST and get_device_cmd.get("is_done")):
                    self._seq = 0
                    bb.set(device_cmd_key, None)
                    if get_device_cmd.get("state") == "done":
                        Logger.info("[Logic] DeviceFSM confirmed tensile test started.")
                        # 인장 시험은 시작 명령만 보내고, 시험 완료는 다른 메커니즘으로 감지하므로 바로 다음 단계로 진행합니다.
                        return LogicEvent.DONE
                    else:
                        Logger.error(f"[Logic] DeviceFSM failed to start tensile test: {get_device_cmd.get('result')}")
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