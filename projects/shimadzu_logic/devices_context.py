from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
from pkg.utils.file_io import load_json, save_json

# Mitutoyogauge import 추가
from .devices.mitutoyogauge import MitutoyoGauge
from .devices.remote_io import AutonicsEIPClient
from .devices.shimadzu_client import ShimadzuClient

from pkg.configs.global_config import GlobalConfig
global_config = GlobalConfig()

from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

import time

class DeviceContext(ContextBase):
    violation_code: int

    def __init__(self):
        ContextBase.__init__(self)

        config_path = 'projects/shimadzu_logic/configs/configs.json'
        config : dict = load_json(config_path)
        self.debug_mode = config.get("debug_mode")
        Logger.info(f"[device] Debug mode : {self.debug_mode}")
        Logger.info(f"[device] configs : {config.get('remote_io')}")
        Logger.info(f"[device] configs : {config.get('shimadzu_ip')} : {config.get('shimadzu_port')}")

        self.dev_gauge_enable = True
        self.dev_remoteio_enable = True
        self.dev_smz_enable = True 
        
        # MitutoyoGauge 장치 인스턴스 생성
        if self.dev_gauge_enable :
            self.gauge = MitutoyoGauge(connection_type=2)  # 예: connection_type=2는 시리얼 통신을 의미
            self.gauge.connect()
        # 측정, 상태 확인 명령 전송 방지 변수
        self.gauge_initial_check_done = False
        self.gauge_measurement_done = False

        # remote I/O 장치 인스턴스 생성
        if self.dev_remoteio_enable :
            self.iocontroller = AutonicsEIPClient()
            self.th_IO_reader = self.iocontroller.connect()
        self.remote_input_data = []
        self.remote_output_data = []
        self.remote_comm_state = False


        # ShimadzuClient 장치 인스턴스 생성
        if self.dev_smz_enable :
            self.shimadzu_client = ShimadzuClient(host=config.get("shimadzu_ip"),
                                                port=config.get("shimadzu_port"))
            self.shimadzu_client.connect()

            result = self.shimadzu_client.send_init()
            Logger.info(f"[ShimadzuClient] Init Response: {result}")
            time.sleep(0.5)

        # self.shimadzu_test()
        # Logger.info(f"[ShimadzuClient] AreYouThere Response: {result}")
        # time.sleep(0.5)

        self.violation_code = 0x00

        # read_IO_status 주기적 스레드 추가 self.th_IO_reader를 while문에서 사용
        self.flag_IO_reader = Flagger()
        self.delay_IO_reader = FlagDelay(0.1)  # 0.1초 간격으로 I/O 상태 읽기
        self.th_IO_reader = Thread(target=self._thread_IO_reader, daemon=True)
        self.th_IO_reader.start()
    
    def shimadzu_test(self) :
        # you are there 명령어 테스트
        result = self.shimadzu_client.send_are_you_there()
        Logger.info(f"[ShimadzuClient] AreYouThere Response: {result}")
        time.sleep(0.5)
        result = self.shimadzu_client.send_ask_sys_status()
        Logger.info(f"[ShimadzuClient] AskSysStatus Response: {result}")
        time.sleep(0.5)
        result = self.shimadzu_client.send_start_run(lotname="D_20251215_001")
        Logger.info(f"[ShimadzuClient] StartMeasurement Response: {result}")
        time.sleep(0.5)
        result = self.shimadzu_client.send_stop_ana()
        Logger.info(f"[ShimadzuClient] StopMeasurement Response: {result}")
        time.sleep(0.5)
        result = self.shimadzu_client.send_ask_register(
            tpname="UI_TEST_FULL_PARAMS", 
            type_p="P", 
            size1="15.0000", 
            size2="8.5000",
            test_rate_type="S",
            test_rate="50.00",
            detect_yp="T", detect_ys="T", detect_elastic="T", detect_lyp="F", 
            detect_ypel="F", detect_uel="F", detect_ts="T", detect_el="T", detect_nv="F",
            ys_para="0.20", 
            nv_type="I", 
            nv_para1="10.00", 
            nv_para2="20.00",
            lotname="LOT_FULL_TEST"
        )
        Logger.info(f"[ShimadzuClient] AskRegister Response: {result}")
        time.sleep(1)

    def _thread_IO_reader(self):
        while self.th_IO_reader :
            time.sleep(0.1)
            self.read_IO_status()

    def check_violation(self) -> int:
        self.violation_code = 0
        # 비트 위치가 명확하고 코드가 짧아집니다.
        # N번째 비트 = 1 << N

        GAUGE_COMM_ERR     = 1 << 0  # 0b00000001 (1)
        GAUGE_DEVICE_ERROR = 1 << 1 # 0b00000010 (2)
        SMZ_COMM_ERR       = 1 << 2  # 0b00000100 (4)
        SMZ_DEVICE_ERR     = 1 << 3  # 0b00001000 (8)  <-- 위치 재조정 (Remote IO와 충돌 방지)
        REMOTE_IO_COMM_ERR = 1 << 4  # 0b00010000 (16)  <-- 위치 재조정
        REMOTE_IO_DEVICE_ERR = 1 << 5  # 0b00100000 (32)  <--
        #Error Code 관련 추가
        
        try:
            # Device Violation을 사용하도록 업데이트
            gauge_violation = [False,0]
            smz_violation = [False,0]
            remoteio_violation = [False,0]

            # TODO: 여기에 Shimadzu/Ext 통신 상태 확인 및 Timeout/InitialCheckFail 로직 추가 필요
            if self.dev_gauge_enable :
                gauge_state = self.get_dial_gauge_status()
                if not gauge_state :
                    gauge_violation =[True, GAUGE_COMM_ERR]    # 통신 연결 에러

            if self.dev_smz_enable :
                smz_state = self.smz_ask_sys_status()
                '''
                dict: {
                    "MODE": "A"(Auto) or "M"(Manual),
                    "RUN": "N"(Standby), "C"(Testing), "B"(Return), "F"(Stop), "R"(Ready), "E"(Error),
                    "KEY": Optional status info name,
                    "VALUE": Optional status info content,
                    "LOAD": float,
                    "TEMP": float
                }
                '''                    
                if self.debug_mode : 
                    Logger.info(f"[DeviceContext] Shimadzu System State: {smz_state}")
                    pass
                if smz_state != False :
                    smz_mode = smz_state.get("MODE")
                    smz_run = smz_state.get("RUN")
                    smz_key = smz_state.get("KEY")
                    smz_value = smz_state.get("VALUE")
                    smz_load = smz_state.get("LOAD")
                    smz_temp = smz_state.get("TEMP")
                    if smz_run == "E" :
                        smz_violation = [True, SMZ_DEVICE_ERR]    # 장비 에러

                else :
                    smz_violation = [True, SMZ_COMM_ERR]    # 통신 연결 에러
                
            if self.dev_remoteio_enable :
                if not self.remote_comm_state :
                    remoteio_violation = [True, REMOTE_IO_COMM_ERR]    # 통신 연결 에러

            
            # 장비 모든 상태 확인 후  error code 생성
            if gauge_violation[0] or smz_violation[0] or remoteio_violation[0] :
                self.violation_code = gauge_violation[1] | smz_violation[1] | remoteio_violation[1]

            time.sleep(0.3)
            return self.violation_code
        except Exception as e:
            Logger.error(f"[device] Error in check_violation: {e}")
            reraise(e)

    def read_IO_status(self):
        '''
        Read Remote I/O value\n
        set blackborad
        '''
        if not hasattr(self, 'iocontroller') or self.iocontroller is None:
            return
        try:
            self.remote_input_data = self.iocontroller.read_input_data()
            self.remote_output_data = self.iocontroller.read_output_data()
            Logger.info(f"Remote I/O Input Data: {self.remote_input_data}")
            bb.set("device/remote/input/entire", self.remote_input_data)
            bb.set("device/remote/output/entire", self.remote_output_data)
            
            # Input 데이터 bb set DigitalInput 기반
            bb.set("device/remote/input/SELECT_SW", self.remote_input_data[DigitalInput.AUTO_MANUAL_SELECT_SW])
            bb.set("device/remote/input/RESET_SW", self.remote_input_data[DigitalInput.RESET_SW])
            bb.set("device/remote/input/SOL_SENSOR", self.remote_input_data[DigitalInput.SOL_SENSOR])
            bb.set("device/remote/input/BCR_OK", self.remote_input_data[DigitalInput.BCR_OK])
            bb.set("device/remote/input/BCR_ERROR", self.remote_input_data[DigitalInput.BCR_ERROR])
            bb.set("device/remote/input/BUSY", self.remote_input_data[DigitalInput.BUSY])
            bb.set("device/remote/input/ENO_01_SW", self.remote_input_data[DigitalInput.ENO_01_SW])
            bb.set("device/remote/input/EMO_02_SI", self.remote_input_data[DigitalInput.EMO_02_SI])
            bb.set("device/remote/input/EMO_03_SI", self.remote_input_data[DigitalInput.EMO_03_SI])
            bb.set("device/remote/input/EMO_04_SI", self.remote_input_data[DigitalInput.EMO_04_SI])
            bb.set("device/remote/input/DOOR_1_OPEN", self.remote_input_data[DigitalInput.DOOR_1_OPEN])
            bb.set("device/remote/input/DOOR_2_OPEN", self.remote_input_data[DigitalInput.DOOR_2_OPEN])
            bb.set("device/remote/input/DOOR_3_OPEN", self.remote_input_data[DigitalInput.DOOR_3_OPEN])
            bb.set("device/remote/input/DOOR_4_OPEN", self.remote_input_data[DigitalInput.DOOR_4_OPEN])
            bb.set("device/remote/input/GRIPPER_1_CLAMP", self.remote_input_data[DigitalInput.GRIPPER_1_CLAMP])
            bb.set("device/remote/input/GRIPPER_2_CLAMP", self.remote_input_data[DigitalInput.GRIPPER_2_CLAMP])
            bb.set("device/remote/input/EXT_FW_SENSOR", self.remote_input_data[DigitalInput.EXT_FW_SENSOR])
            bb.set("device/remote/input/EXT_BW_SENSOR", self.remote_input_data[DigitalInput.EXT_BW_SENSOR])
            bb.set("device/remote/input/INDICATOR_GUIDE_UP", self.remote_input_data[DigitalInput.INDICATOR_GUIDE_UP])
            bb.set("device/remote/input/INDICATOR_GUIDE_DOWN", self.remote_input_data[DigitalInput.INDICATOR_GUIDE_DOWN])
            bb.set("device/remote/input/ALIGN_1_PUSH", self.remote_input_data[DigitalInput.ALIGN_1_PUSH])
            bb.set("device/remote/input/ALIGN_1_PULL", self.remote_input_data[DigitalInput.ALIGN_1_PULL])
            bb.set("device/remote/input/ALIGN_2_PUSH", self.remote_input_data[DigitalInput.ALIGN_2_PUSH])
            bb.set("device/remote/input/ALIGN_2_PULL", self.remote_input_data[DigitalInput.ALIGN_2_PULL])
            bb.set("device/remote/input/ALIGN_3_PUSH", self.remote_input_data[DigitalInput.ALIGN_3_PUSH])
            bb.set("device/remote/input/ALIGN_3_PULL", self.remote_input_data[DigitalInput.ALIGN_3_PULL])
            bb.set("device/remote/input/ATC_1_1_SENSOR", self.remote_input_data[DigitalInput.ATC_1_1_SENSOR])
            bb.set("device/remote/input/ATC_1_2_SENSOR", self.remote_input_data[DigitalInput.ATC_1_2_SENSOR])
            bb.set("device/remote/input/SCRAPBOX_SENSOR", self.remote_input_data[DigitalInput.SCRAPBOX_SENSOR])
            bb.set("device/remote/input/ATC_2_1_SENSOR", self.remote_input_data[DigitalInput.ATC_2_1_SENSOR])
            bb.set("device/remote/input/ATC_2_2_SENSOR", self.remote_input_data[DigitalInput.ATC_2_2_SENSOR])

            # Output 데이터 bb set DigitalOutput 기반            
            bb.set("device/remote/output/TOWER_LAMP_RED", self.remote_output_data[DigitalOutput.TOWER_LAMP_RED])
            bb.set("device/remote/output/TOWER_LAMP_GREEN", self.remote_output_data[DigitalOutput.TOWER_LAMP_GREEN])
            bb.set("device/remote/output/TOWER_LAMP_YELLOW", self.remote_output_data[DigitalOutput.TOWER_LAMP_YELLOW])
            bb.set("device/remote/output/TOWER_BUZZER", self.remote_output_data[DigitalOutput.TOWER_BUZZER])
            bb.set("device/remote/output/BCR_TGR", self.remote_output_data[DigitalOutput.BCR_TGR])
            bb.set("device/remote/output/LOCAL_LAMP_R", self.remote_output_data[DigitalOutput.LOCAL_LAMP_R])
            bb.set("device/remote/output/RESET_SW_LAMP", self.remote_output_data[DigitalOutput.RESET_SW_LAMP])
            bb.set("device/remote/output/DOOR_4_LAMP", self.remote_output_data[DigitalOutput.DOOR_4_LAMP])
            bb.set("device/remote/output/INDICATOR_UP", self.remote_output_data[DigitalOutput.INDICATOR_UP])
            bb.set("device/remote/output/INDICATOR_DOWN", self.remote_output_data[DigitalOutput.INDICATOR_DOWN])
            bb.set("device/remote/output/ALIGN_1_PUSH", self.remote_output_data[DigitalOutput.ALIGN_1_PUSH])
            bb.set("device/remote/output/ALIGN_1_PULL", self.remote_output_data[DigitalOutput.ALIGN_1_PULL])
            bb.set("device/remote/output/ALIGN_2_PUSH", self.remote_output_data[DigitalOutput.ALIGN_2_PUSH])
            bb.set("device/remote/output/ALIGN_2_PULL", self.remote_output_data[DigitalOutput.ALIGN_2_PULL])
            bb.set("device/remote/output/ALIGN_3_PUSH", self.remote_output_data[DigitalOutput.ALIGN_3_PUSH])
            bb.set("device/remote/output/ALIGN_3_PULL", self.remote_output_data[DigitalOutput.ALIGN_3_PULL])
            bb.set("device/remote/output/GRIPPER_1_UNCLAMP", self.remote_output_data[DigitalOutput.GRIPPER_1_UNCLAMP])
            bb.set("device/remote/output/LOCAL_LAMP_L", self.remote_output_data[DigitalOutput.LOCAL_LAMP_L])
            bb.set("device/remote/output/GRIPPER_2_UNCLAMP", self.remote_output_data[DigitalOutput.GRIPPER_2_UNCLAMP])
            bb.set("device/remote/output/LOCAL_LAMP_C", self.remote_output_data[DigitalOutput.LOCAL_LAMP_C])
            bb.set("device/remote/output/EXT_FW", self.remote_output_data[DigitalOutput.EXT_FW])
            bb.set("device/remote/output/EXT_BW", self.remote_output_data[DigitalOutput.EXT_BW])
            self.remote_comm_state = True
        except Exception as e:
            Logger.error(f"[device] Error in read_IO_status: {e}")
            reraise(e)
            self.remote_comm_state = False


    def chuck_open(self) :
        '''
        Docstring for chuck_open
        :return: sucess True, fail False
        '''
        try :
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 1
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 1 and
                read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 1):
                Logger.info(f"[device] Chuck Open Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck Open Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_open: {e}")
            reraise(e)
            return False

    def chuck_close(self) :
        '''
        Docstring for chuck_close       
        :return: sucess True, fail False
        '''
        try :
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 0
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 0 and
                read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 0):
                Logger.info(f"[device] Chuck Close Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck Close Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_close: {e}")
            reraise(e)
            return False
        
    def chuck_check(self) -> bool:
        '''
        Docstring for chuck_check
        :return: sucess True, fail False
        '''
        try :
            read_data = self.iocontroller.read_input_data()
            if (read_data[DigitalInput.GRIPPER_1_CLAMP] == 1 and
                read_data[DigitalInput.GRIPPER_2_CLAMP] == 1) :
                self.chuck_close()
                return True
            else :
                return False
        
        except Exception as e:
            Logger.error(f"[device] Error in chuck_check: {e}")
            reraise(e)
            return False
        
    def EXT_move_forword(self) :
        '''
        Docstring for EXT_move_forword
        :return: sucess True, fail False        
        ''' 
        try :
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.EXT_FW] = 1
            output_data[DigitalOutput.EXT_BW] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 1 and
                read_data[DigitalOutput.EXT_BW] == 0):
                Logger.info(f"[device] EXT Move Forward Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Move Forward Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_forword: {e}")
            reraise(e)
            return False
        
    def EXT_move_backward(self) :
        '''
        Docstring for EXT_move_backward
        :return: sucess True, fail False        
        ''' 
        try :
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.EXT_FW] = 0
            output_data[DigitalOutput.EXT_BW] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 0 and
                read_data[DigitalOutput.EXT_BW] == 1):
                Logger.info(f"[device] EXT Move Backward Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Move Backward Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_backward: {e}")
            reraise(e)
            return False
    
    def EXT_move_check(self,direction : int) -> bool:
        '''
        Docstring for EXT_move_check
        :param direction: 1 for forward, 2 for backward
        :return: sucess True, fail False
        '''
        try :
            read_data = self.iocontroller.read_input_data()
            if direction == 1 :
                if read_data[DigitalInput.EXT_FW_SENSOR] == 1 and read_data[DigitalInput.EXT_BW_SENSOR] == 0 :
                    self.EXT_stop()
                    return True
                else :
                    return False
            elif direction == 2 :
                if read_data[DigitalInput.EXT_FW_SENSOR] == 0 and read_data[DigitalInput.EXT_BW_SENSOR] == 1 :
                    self.EXT_stop()
                    return True
                else :
                    return False
            else :
                Logger.error(f"[device] EXT_move_check: Invalid direction {direction}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_check: {e}")
            # 혹시나해서 넣어두는 정지
            self.EXT_stop()
            reraise(e)
            return False

    def EXT_stop(self) :
        '''
        Docstring for EXT_stop    
        :return: sucess True, fail False    
        ''' 
        try :
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.EXT_FW] = 0
            output_data[DigitalOutput.EXT_BW] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 0 and
                read_data[DigitalOutput.EXT_BW] == 0):
                Logger.info(f"[device] EXT Stop Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Stop Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_stop: {e}")
            reraise(e)
            return False
    
    # Alignment Push/Pull 신호 제어 함수들
    def align_push(self) -> bool:
        '''
        Docstring for align_push
        
        :return: sucess True, fail False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.ALIGN_1_PUSH] = 1
            output_data[DigitalOutput.ALIGN_1_PULL] = 0
            output_data[DigitalOutput.ALIGN_2_PUSH] = 1
            output_data[DigitalOutput.ALIGN_2_PULL] = 0
            output_data[DigitalOutput.ALIGN_3_PUSH] = 1
            output_data[DigitalOutput.ALIGN_3_PULL] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.ALIGN_1_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_1_PULL] == 0 and
                read_data[DigitalOutput.ALIGN_2_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_2_PULL] == 0 and
                read_data[DigitalOutput.ALIGN_3_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_3_PULL] == 0):
                Logger.info(f"[device] Align Push Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Align Push Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in align_push: {e}")
            reraise(e)
            return False
        
    def align_pull(self) -> bool:
        '''
        Docstring for align_pull
        :return: sucess True, fail False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.ALIGN_1_PUSH] = 0
            output_data[DigitalOutput.ALIGN_1_PULL] = 1
            output_data[DigitalOutput.ALIGN_2_PUSH] = 0
            output_data[DigitalOutput.ALIGN_2_PULL] = 1
            output_data[DigitalOutput.ALIGN_3_PUSH] = 0
            output_data[DigitalOutput.ALIGN_3_PULL] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.ALIGN_1_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_1_PULL] == 1 and
                read_data[DigitalOutput.ALIGN_2_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_2_PULL] == 1 and
                read_data[DigitalOutput.ALIGN_3_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_3_PULL] == 1):
                Logger.info(f"[device] Align Pull Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Align Pull Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in align_pull: {e}")
            reraise(e)
            return False
    
    def align_stop(self) -> bool:
        '''
        Docstring for align_stop
        
        :return: sucess True, fail False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.ALIGN_1_PUSH] = 0
            output_data[DigitalOutput.ALIGN_1_PULL] = 0
            output_data[DigitalOutput.ALIGN_2_PUSH] = 0
            output_data[DigitalOutput.ALIGN_2_PULL] = 0
            output_data[DigitalOutput.ALIGN_3_PUSH] = 0
            output_data[DigitalOutput.ALIGN_3_PULL] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.ALIGN_1_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_1_PULL] == 0 and
                read_data[DigitalOutput.ALIGN_2_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_2_PULL] == 0 and
                read_data[DigitalOutput.ALIGN_3_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_3_PULL] == 0):
                Logger.info(f"[device] Align Stop Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Align Stop Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in align_stop: {e}")
            reraise(e)
            return False

    def align_check(self, direction : int) -> bool:
        '''
        Docstring for align_check
        Based on input_data 
        : param: direction : 1 for push, 2 for pull
        : return: sucess True, fail False
        '''
        try :
            read_data = self.iocontroller.read_input_data()
            if direction == 1 :
                if (read_data[DigitalInput.ALIGN_1_PUSH] == 1 and
                    read_data[DigitalInput.ALIGN_1_PULL] == 0 and
                    read_data[DigitalInput.ALIGN_2_PUSH] == 1 and
                    read_data[DigitalInput.ALIGN_2_PULL] == 0 and
                    read_data[DigitalInput.ALIGN_3_PUSH] == 1 and
                    read_data[DigitalInput.ALIGN_3_PULL] == 0):
                    self.align_stop()
                    return True
                else :
                    return False
            elif direction == 2 :
                if (read_data[DigitalInput.ALIGN_1_PUSH] == 0 and
                    read_data[DigitalInput.ALIGN_1_PULL] == 1 and
                    read_data[DigitalInput.ALIGN_2_PUSH] == 0 and
                    read_data[DigitalInput.ALIGN_2_PULL] == 1 and
                    read_data[DigitalInput.ALIGN_3_PUSH] == 0 and
                    read_data[DigitalInput.ALIGN_3_PULL] == 1):
                    self.align_stop()
                    return True
                else :
                    return False
            else :
                Logger.info(f"[device] align_check: Invalid direction {direction}")
        except Exception as e:
            Logger.error(f"[device] Error in align_check: {e}")
            reraise(e)
            return False
    
    # dial gauge 관련 함수들
    # dial gauge 측정 함수
    def get_dial_gauge_value(self) -> float:
        '''
        Docstring for get_dial_gauge_value
        
        
        :return: gauge measurement valuee
        :rtype: float
        '''
        try:
            self.gauge_measurement_done = True
            value = self.gauge.request_data()
            bb.set("device/gauge/thickness", value)
            Logger.info(f"[device] Dial Gauge Value: {value}")
            self.gauge_measurement_done = False
            return value
        except Exception as e:
            Logger.error(f"[device] Error in get_dial_gauge_value: {e}")
            reraise(e)
            return -999.0  # 오류 시 반환 값
    
    def get_dial_gauge_status(self) -> bool :
        '''
        Docstring for get_dial_gauge_status
        
        :return: gauge connect state
        :rtype: bool
        '''
        try:
            if self.gauge_measurement_done :
                return
            
            value = self.gauge.request_data()
            if value is not None :
                return True 
            else :
                return False
        except Exception as e:
            Logger.error(f"[device] Error in get_dial_gauge_status: {e}")
            reraise(e)
            return False

    # shimadzu client 래핑 함수들
    def smz_ask_register(self, regist_data: dict, **params) -> Optional[Dict[str, Any]]:
        '''
        Docstring for smz_ask_register
        
        :param regist_data: test data
        :type regist_data: dict
        :return: sucess True, fail False
        :rtype: boolean
        '''
        try:
            bb.set("device/shimadzu/ask_register/params", regist_data)
            tpname = regist_data.get("tpname")
            type_p = regist_data.get("type_p")
            size1 = regist_data.get("size1")
            size2 = regist_data.get("size2")
            test_rate_type = regist_data.get("test_rate_type")
            test_rate = regist_data.get("test_rate")
            detect_yp = regist_data.get("detect_yp")
            detect_ys = regist_data.get("detect_ys")
            detect_elastic = regist_data.get("detect_elastic")
            detect_lyp = regist_data.get("detect_lyp")
            detect_ypel = regist_data.get("detect_ypel")
            detect_uel = regist_data.get("detect_uel")
            detect_ts = regist_data.get("detect_ts")
            detect_el = regist_data.get("detect_el")
            detect_nv = regist_data.get("detect_nv")
            ys_para = regist_data.get("ys_para")
            nv_type = regist_data.get("nv_type")
            nv_para1 = regist_data.get("nv_para1")
            nv_para2 = regist_data.get("nv_para2")
            lotname = regist_data.get("lotname")
            
            result = self.shimadzu_client.send_ask_register(tpname=tpname,
                                                            type_p=type_p,
                                                            size1=size1,
                                                            size2=size2,
                                                            test_rate_type=test_rate_type,
                                                            test_rate=test_rate,
                                                            detect_yp=detect_yp,
                                                            detect_ys=detect_ys,
                                                            detect_elastic=detect_elastic,
                                                            detect_lyp=detect_lyp,
                                                            detect_ypel=detect_ypel,
                                                            detect_uel=detect_uel,
                                                            detect_ts=detect_ts,
                                                            detect_el=detect_el,
                                                            detect_nv=detect_nv,
                                                            ys_para=ys_para,
                                                            nv_type=nv_type,
                                                            nv_para1=nv_para1,
                                                            nv_para2=nv_para2,
                                                            lotname=lotname)
            return result
        
        except Exception as e:
            reraise(e)
            return False
    
    def smz_start_measurement(self, lotname: str) -> Optional[Dict[str, Any]]:
        '''
        Docstring for smz_start_measurement
        :param lotname : UI 또는 DB에서 받은 데이터
        :type lotname : str
        :return: sucess True, fail False
        '''
        try:
            result = self.shimadzu_client.send_start_run(lotname=lotname)
            return result
        except Exception as e:
            reraise(e)
            return False
    
    def smz_stop_measurement(self) -> Optional[Dict[str, Any]]:
        '''
        Docstring for smz_stop_measurement
        :return: sucess True, fail False
        '''
        try:
            result = self.shimadzu_client.send_stop_ana()
            return result
        except Exception as e:
            reraise(e)
            return False
    
    def smz_are_you_there(self) -> Optional[Dict[str, Any]]:
        '''
        Docstring for smz_are_you_there
        :return: sucess True, fail False
        '''
        try:
            result = self.shimadzu_client.send_are_you_there()
            return result
        except Exception as e:
            reraise(e)
            return False

    def smz_ask_sys_status(self) -> Optional[Dict[str, Any]]:
        '''
        Docstring for smz_ask_sys_status
        :return: sucess True, fail False
        '''
        try:
            result = self.shimadzu_client.send_ask_sys_status()
            return result
        except Exception as e:
            reraise(e)
            return False