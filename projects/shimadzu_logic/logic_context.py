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
            Logger.error(f"[LogicContext] Exception in check_violation: {e}")
            reraise(e)

    # LogicState.DETERMINE_TASK: {
    #     LogicEvent.DO_PICK_SPECIMEN: LogicState.PICK_SPECIMEN,
    #     LogicEvent.DO_MEASURE_THICKNESS: LogicState.MEASURE_THICKNESS,
    #     LogicEvent.DO_ALIGN_SPECIMEN: LogicState.ALIGN_SPECIMEN,
    #     LogicEvent.DO_LOAD_TENSILE_MACHINE: LogicState.LOAD_TENSILE_MACHINE,
    #     LogicEvent.DO_START_TENSILE_TEST: LogicState.START_TENSILE_TEST,
    #     LogicEvent.DO_COLLECT_AND_DISCARD: LogicState.COLLECT_AND_DISCARD,
    #     LogicEvent.DO_PROCESS_COMPLETE: LogicState.PROCESS_COMPLETE,                
    #     LogicEvent.PROCESS_PAUSE: LogicState.WAIT_PROCESS, # 일시정지 -> 대기
    #     LogicEvent.VIOLATION_DETECT: LogicState.ERROR,
    # },    

    def pick_specimen(self, floor : int = 0, specimen_num : int = 0): # A
        '''
        # Position A Rack
        Docstring for pick_specimen
        :param floor: 작업 대상 층
        :param specimen_num: 작업 대상 쟁반 내 순번

        pick_specimen 로봇 모션만 함
        '''
        robot_cmd_key = "process/auto/robot/cmd"
        device_cmd_key = "process/auto/device/cmd"
        
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        # device_cmd = bb.get(device_cmd)
        # 1. 시편 잡으로 가기 로봇 명령 세팅
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : "pick_specimen",
                "target_floor" : floor,
                "target_num" : specimen_num,
                "place_position" : 0,
                "state" : ""
            }
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. 시편 잡기 명령 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == "pick_specimen" and
                get_robot_cmd.get("state") == "done") :
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == "pick_specimen" and
                get_robot_cmd.get("state") == "error") :
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
        robot_cmd_key = "process/auto/robot/cmd"
        device_cmd_key = "process/auto/device/cmd"
        
        # 1. 시편 잡고 두께 측정기 앞 이동 로봇 모션 명령 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        # device_cmd = bb.get(device_cmd)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : "move_to_indigator",
                "target_floor" : floor,
                "target_num" : specimen_num,
                "place_position" : 0,
                "state" : ""
            }
            bb.set(robot_cmd_key, robot_cmd)

        # 1-1. 시편 잡고 두께 측정기 앞 이동 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == "move_to_indigator" and
                get_robot_cmd.get("state") == "done") :
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == "move_to_indigator" and
                get_robot_cmd.get("state") == "error") :
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                self._seq = 1
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
        robot_cmd_key = "process/auto/robot/cmd"
        device_cmd_key = "process/auto/device/cmd"

        # 1. 시편 잡고 두께 측정기 앞 이동 후 시편 두고 빠지는 모션 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : "place_specimen_and_measure",
                "target_floor" : floor,
                "target_num" : specimen_num,
                "place_position" : Sequence,
                "state" : ""
            }
            bb.set(robot_cmd_key, robot_cmd)
            
        # 1-1. 시편 잡고 두께 측정기 앞 이동 후 시편 두고 빠지는 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == "place_specimen_and_measure" and
                get_robot_cmd.get("state") == "done") :
                bb.set(robot_cmd_key, None)
                # 두께 측정 명령 생성
                device_cmd = {
                    "command" : "measure_thickness",
                    "result" : None,
                    "state" : "",
                    "is_done" : False                               
                }
                bb.set(device_cmd_key, device_cmd)
                self._seq = 1

            # 에레 확인
            elif (get_robot_cmd.get("process") == "place_specimen_and_measure" and
                get_robot_cmd.get("state") == "error") :
                return LogicEvent.VIOLATION_DETECT
            
            # 작업 대기
            else :
                return LogicEvent.NONE   

        # 2. 두께 측정 완료 확인
        get_device_cmd : dict = bb.get(device_cmd_key)
        if self._seq == 1 and get_device_cmd :
            # 완료 확인
            if (get_device_cmd.get("command") == "measure_thickness" and
                get_device_cmd.get("is_done") == True) :
                bb.set(f"process/auto/thickness/{Sequence}",get_device_cmd.get("result"))
                bb.set(device_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_device_cmd.get("command") == "measure_thickness" and
                get_device_cmd.get("is_done") == False and
                get_device_cmd.get("state") == "error") :
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
        robot_cmd_key = "process/auto/robot/cmd"
        device_cmd_key = "process/auto/device/cmd"
        
        # 1. 두께 측정기 안 시편 잡아오기 로봇 모션 세팅
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : "Pick_specimen_out_from_indigator",
                "target_floor" : floor,
                "target_num" : specimen_num,
                "place_position" : Sequence,
                "state" : ""
            }
            bb.set(robot_cmd_key, robot_cmd)
        # 1-1. 두께 측정기 안 시편 잡아오기 로봇 모션 완료 확인
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == "Pick_specimen_out_from_indigator" and
                get_robot_cmd.get("state") == "done") :
                bb.set(robot_cmd_key, None)
                self._seq = 0
                return LogicEvent.DONE
            
            # 에러 확인
            elif (get_robot_cmd.get("process") == "Pick_specimen_out_from_indigator" and
                get_robot_cmd.get("state") == "error") :
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
        robot_cmd_key = "process/auto/robot/cmd"
        device_cmd_key = "process/auto/device/cmd"
        
        # 1. 정렬기에 가져다 놓기 명령 전달
        get_robot_cmd : dict = bb.get(robot_cmd_key)
        if self._seq == 0 and get_robot_cmd == None :
            robot_cmd = {
                "process" : "align_specimen",
                "target_floor" : floor,
                "target_num" : specimen_num,
                "place_position" : Sequence,
                "state" : ""
            }
            bb.set(robot_cmd_key, robot_cmd)

        # 1-1. 정렬기 명령 전달 후 모션 완료 대기
        elif self._seq == 0 and get_robot_cmd :
            # 완료 확인
            if (get_robot_cmd.get("process") == "align_specimen" and
                get_robot_cmd.get("state") == "done") :
                bb.set(robot_cmd_key, None)
                self._seq = 1
                # 장비제어 명령 세팅 : 정렬기 정렬
                device_cmd = {
                    "command" : "align_specimen",
                    "result" : None,
                    "state" : "",
                    "is_done" : False                               
                }
                bb.set(device_cmd_key, device_cmd)
            # 에러 확인
            elif (get_robot_cmd.get("process") == "align_specimen" and
                get_robot_cmd.get("state") == "error") :
                return LogicEvent.VIOLATION_DETECT
            # 작업 대기
            else :
                return LogicEvent.NONE
            
        # 2. 시편 정렬 명령 수행
        if self._seq == 1 :
            get_device_cmd : dict = bb.get(device_cmd_key)
            if get_device_cmd :
                # 완료 확인
                if (get_device_cmd.get("command") == "align_specimen" and
                    get_device_cmd.get("is_done") == True) :
                    bb.set(device_cmd_key, None)
                    self._seq = 2      
                    # 로봇 모션 명령 세팅 : 정렬된 시편 잡고나오기
                    robot_cmd = {
                        "process" : "Pick_specimen_out_from_align",
                        "target_floor" : 0,
                        "target_num" : 0,
                        "place_position" : 0,
                        "state" : ""
                    }                                  
                # 에러 확인
                elif (get_device_cmd.get("command") == "align_specimen" and
                    get_device_cmd.get("is_done") == False and
                    get_device_cmd.get("state") == "error") :
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE
                
        # 3. 정렬된 시편 잡고 나오는 모션 실행
        if self._seq == 2 :
            get_robot_cmd : dict = bb.get(robot_cmd_key)
            if get_robot_cmd :
                # 완료 확인
                if (get_robot_cmd.get("process") == "Pick_specimen_out_from_align" and
                    get_robot_cmd.get("state") == "done") :
                    bb.set(robot_cmd_key, None)
                    self._seq = 0
                    return LogicEvent.DONE
                # 에러 확인
                elif (get_robot_cmd.get("process") == "Pick_specimen_out_from_align" and
                      get_device_cmd.get("state") == "error") :
                    return LogicEvent.VIOLATION_DETECT
                # 작업 대기
                else :
                    return LogicEvent.NONE
        
    def load_tensile_machine(self, 
                        floor : int = 0, 
                        specimen_num : int = 0, 
                        Sequence : int = 0):
        pass

    def start_tensile_test(self):
        pass

    def collect_and_discard(self):
        pass

    def process_complete(self):
        pass