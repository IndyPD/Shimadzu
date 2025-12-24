import time
from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
from pkg.utils.blackboard import GlobalBlackboard
from .devices_fsm import DeviceFsm
from .robot_fsm import RobotFSM
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
    def __init__(self):
        ContextBase.__init__(self)
        self.status = LogicStatus()
        self.violation_code = 0x00
        self._seq = 0

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            # 1. Logic 자체의 상태 확인
            if self.status.is_emg_pushed():
                self.violation_code |= LogicViolation.ISO_EMERGENCY_BUTTON

            if self.status.is_error_state():
                self.violation_code |= LogicViolation.HW_VIOLATION

            if not self.status.is_batch_planned():
                 self.violation_code |= LogicViolation.BATCH_PLAN_MISSING


            return self.violation_code
        except Exception as e:
            Logger.error(f"[Logic] Exception in check_violation: {e}")
            reraise(e)

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
                Logger.info(f"[Logic] bb.set(process/auto/thickness/{Sequence}, {get_device_cmd.get('result')})")
                bb.set(f"process/auto/thickness/{Sequence}",get_device_cmd.get("result"))
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
                    self._seq = 2      
                    # 로봇 모션 명령 세팅 : 정렬된 시편 잡고나오기
                    robot_cmd = {
                        "process" : Motion_command.M06_PICK_OUT_FROM_ALIGN,
                        "target_floor" : 0,
                        "target_num" : 0,
                        "position" : 0,
                        "state" : ""
                    }                                  
                # 에러 확인
                elif (get_device_cmd.get("command") == Device_command.ALIGN_SPECIMEN and
                    get_device_cmd.get("is_done") == False and
                    get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] align_specimen (device) failed: {get_device_cmd}")
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE
                
        # 3. 정렬된 시편 잡고 나오는 모션 실행
        if self._seq == 2 :
            get_robot_cmd : dict = bb.get(robot_cmd_key)
            if get_robot_cmd :
                # 완료 확인
                if (get_robot_cmd.get("process") == Motion_command.M06_PICK_OUT_FROM_ALIGN and
                    get_robot_cmd.get("state") == "done") :
                    Logger.info(f"[Logic] bb.set({robot_cmd_key}, None)")
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    Logger.info("[Logic] align_specimen: LogicEvent.DONE")
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_robot_cmd.get("process") == Motion_command.M06_PICK_OUT_FROM_ALIGN and
                      get_device_cmd.get("state") == "error") :
                    Logger.error(f"[Logic] align_specimen (robot pick out) failed: {get_robot_cmd}")
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
    
        
    def start_tensile_test(self):
        pass

    def collect_and_discard(self):
        pass

    def process_complete(self):
        pass