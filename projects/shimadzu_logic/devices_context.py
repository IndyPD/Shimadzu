from datetime import timedelta
from .constants import *
import os
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay
from pkg.utils.file_io import load_json, save_json

# Mitutoyogauge import 추가
from .devices.mitutoyogauge import MitutoyoGauge
from .devices.remote_io import AutonicsEIPClient
from .devices.shimadzu_client import ShimadzuClient
from .devices.QR_reader import QRReader

from pkg.configs.global_config import GlobalConfig
global_config = GlobalConfig()

from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

import time
import threading
import traceback
from .DB_handler import DBHandler

class DeviceContext(ContextBase):
    violation_code: int
    db: DBHandler

    def __init__(self, db_handler: DBHandler):
        ContextBase.__init__(self)
        self.db = db_handler

        # 스크립트 위치를 기준으로 설정 파일의 절대 경로 생성
        config_dir = os.path.join(os.path.dirname(__file__), 'configs')
        config_path = os.path.join(config_dir, 'configs.json')
        config: dict = load_json(config_path)
        self.debug_mode = config.get("debug_mode")
        Logger.info(f"[device] Debug mode : {self.debug_mode}")
        Logger.info(f"[device] RemoteIO configs : {config.get('remote_io')}")
        Logger.info(f"[device] Shimadzu configs : {config.get('shimadzu_ip')} : {config.get('shimadzu_port')}")

        self._io_lock = threading.Lock()

        self.dev_gauge_enable = True
        self.dev_remoteio_enable = True
        self.dev_smz_enable = True 
        self.dev_qr_enable = True

        self.dev_smz_check_time = datetime.now()
        
        # MitutoyoGauge 장치 인스턴스 생성
        if self.dev_gauge_enable :
            Logger.info(f"[device] Gauge Initialized")
            self.gauge = MitutoyoGauge(connection_type=1)  # 예: connection_type=1는 시리얼 통신을 의미
        # 측정, 상태 확인 명령 전송 방지 변수
        self.gauge_initial_check_done = False
        self.gauge_measurement_done = False
        self.chuck_open_start_time = 0

        # remote I/O 장치 인스턴스 생성
        if self.dev_remoteio_enable :
            Logger.info(f"[device] remote I/O Initialized")
            self.iocontroller = AutonicsEIPClient()
            # self.th_IO_reader = self.iocontroller.connect()
            time.sleep(0.5)
            self.remote_input_data = self.iocontroller.current_di_value
            self.remote_output_data = self.iocontroller.current_do_value
        else :
            self.remote_input_data = [0] * 48
            self.remote_output_data = [0] * 32
        self.remote_comm_state = False
        # 통신 오류 카운터 및 임계값
        self.remote_io_error_count = 0
        self.gauge_error_count = 0
        self.qr_error_count = 0
        self.COMM_ERROR_THRESHOLD = 10  # 10회 연속 통신 오류 발생 시 위반으로 판단

        # QRReader 장치 인스턴스 생성
        if self.dev_qr_enable:
            self.qr_reader = QRReader()
            # QR 데이터 수신 시 블랙보드에 자동으로 저장하도록 콜백 등록
            self.qr_reader.on_qr_data = lambda data: bb.set("device/qr/result", data)
            self.qr_reader.connect()
            Logger.info("[device] QR Reader Initialized")
            time.sleep(1)
            self.qr_reader.quit()

        # ShimadzuClient 장치 인스턴스 생성
        if self.dev_smz_enable :
            self.shimadzu_client = ShimadzuClient(host=config.get("shimadzu_ip"),
                                                port=config.get("shimadzu_port"))
            result = self.shimadzu_client.connect()

            # result = self.shimadzu_client.send_init()
            Logger.info(f"[ShimadzuClient] Init Response: {result}")
            time.sleep(0.5)
            result = self.shimadzu_client.send_are_you_there()
            if result is not None:
                Logger.info(f"[ShimadzuClient] Connected to Shimadzu Device Successfully.")
            else:
                Logger.error(f"[ShimadzuClient] Failed to connect to Shimadzu Device.")


        # self.shimadzu_test()
        # Logger.info(f"[ShimadzuClient] AreYouThere Response: {result}")
        # time.sleep(0.5)

        self.violation_code = 0x00

        # read_IO_status 주기적 스레드 추가 self.th_IO_reader를 while문에서 사용
        self.flag_IO_reader = Flagger()
        self.delay_IO_reader = FlagDelay(0.1)  # 0.1초 간격으로 I/O 상태 읽기
        self.th_IO_reader = Thread(target=self._thread_IO_reader, daemon=True)
        self.th_IO_reader.start()

        # UI DO 제어 핸들러 스레드 추가
        self.th_UI_DO_handler = Thread(target=self._thread_UI_DO_handler, daemon=True)
        self.th_UI_DO_handler.start()

        # 주기적으로 타워 램프 상태를 제어하는 스레드 추가
        self.th_tower_lamp_controller = Thread(target=self._thread_tower_lamp_controller, daemon=True)
        self.th_tower_lamp_controller.start()

        # 주기적으로 통신 상태를 블랙보드에 업데이트하는 스레드 추가
        self.th_comm_status_updater = Thread(target=self._thread_comm_status_updater, daemon=True)
        self.th_comm_status_updater.start()

        Logger.info(f"[device] All device Init Complete")

        # 초기 장비 설정
        # 장비 내 램프 켜기
        try :
            # TODO remote io 연결확인 후
            self.read_IO_status() # 초기 설정을 위해 현재 I/O 상태를 동기적으로 읽어옴
            if self.remote_input_data[DigitalInput.SOL_SENSOR] == 1:
                Logger.info(f"[device] SOL_SENSOR is ON. Performing initial device setup.")

                Logger.info(f"[device] lamp on")
                self.lamp_on()

                # 정렬기 후퇴
                if bb.get("device/align/state") != "pull":
                    Logger.info(f"[device] align stop")
                    self.align_stop()
                    time.sleep(1)

                    Logger.info(f"[device] align pull")
                    self.align_pull()
                    time.sleep(0.1)
                else:
                    Logger.info(f"[device] Aligner is already in pull state.")

                # 측정기 받침 내리기
                if bb.get("device/indicator/stand/state") != "down":
                    Logger.info(f"[device] indicator stand down")
                    self.indicator_stand_down()
                    time.sleep(0.1)
                else:
                    Logger.info(f"[device] Indicator stand is already down.")
            else:
                Logger.info(f"[device] SOL_SENSOR is OFF. Skipping initial device setup.")
                # SOL_SENSOR가 꺼져있을 때는 안전을 위해 램프도 끕니다.
                Logger.info(f"[device] lamp off")
                self.lamp_off()

        except Exception as e:
            Logger.error(f"[device] Error in __init__: {e}\n{traceback.format_exc()}")
            reraise(e)
    
    def _is_io_writable(self) -> bool:
        """
        Remote I/O에 쓰기 작업이 가능한지 확인합니다.
        (컨트롤러 존재 및 데이터 유효성)
        """
        if not self.dev_remoteio_enable:
            return False
            
        if not hasattr(self, 'iocontroller') or self.iocontroller is None:
            Logger.error("[device] I/O write failed: iocontroller is not initialized.")
            return False

        if not isinstance(self.remote_output_data, list) or len(self.remote_output_data) < 32:
            Logger.error(f"[device] I/O write failed: remote_output_data is invalid (len: {len(self.remote_output_data) if self.remote_output_data is not None else 'None'}).")
            return False
            
        return True

    
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
            self.read_IO_status()
            # self.delay_IO_reader.sleep() # 0.1초 주기로 실행
            time.sleep(0.1)

    def _thread_UI_DO_handler(self):
        """
        Blackboard의 트리거를 감시하여 UI로부터의 DO 제어 명령을 처리하는 스레드입니다.
        """
        while True:
            try:
                if bb.get("ui/cmd/do_control/trigger") == 1:
                    if bb.get("device/remote/input/SELECT_SW") != 1:
                        data = bb.get("ui/cmd/do_control/data")
                        if isinstance(data, dict):
                            address = data.get("addr")
                            val = data.get("value")
                            Logger.info(f"[Device] DO_Control : {address} {val}")
                            self.UI_DO_Control(int(address), int(val))
                    else :
                        Logger.info(f"[Device] DO_Control command ignored: System is in MANUAL mode (SELECT_SW != 1).")
                        
                    # 처리 완료 후 트리거 리셋
                    bb.set("ui/cmd/do_control/trigger", 0)
                
            except Exception as e:
                Logger.error(f"[device] Error in _thread_UI_DO_handler: {e}\n{traceback.format_exc()}")
            time.sleep(0.1)

    def _thread_tower_lamp_controller(self):
        """
        주기적으로 시스템 상태를 확인하여 타워 램프를 제어합니다.
        - 에러: 빨간색 램프 점멸
        - 공정 중: 녹색 램프 켜짐
        - 대기: 노란색 램프 점멸
        """
        blink_state = False
        while True:
            try:
                # 현재 FSM 상태를 블랙보드에서 가져옵니다.

                logic_fsm = bb.get("logic/fsm/strategy")
                device_fsm = bb.get("device/fsm/strategy")
                robot_fsm = bb.get("robot/fsm/strategy")

                if type(logic_fsm) == dict and type(device_fsm) == dict and type(robot_fsm) == dict:
                    logic_fsm_state = logic_fsm.get("state")
                    device_fsm_state = device_fsm.get("state")
                    robot_fsm_state = robot_fsm.get("state")
                    # 상태 결정
                    is_error = "ERROR" in (logic_fsm_state or "") or \
                            "ERROR" in (device_fsm_state or "") or \
                            "ERROR" in (robot_fsm_state or "")
                    
                    is_idle = logic_fsm_state in ["IDLE", "WAIT_COMMAND", "PROCESS_COMPLETE", "CONNECTING"]

                    # I/O 쓰기 중 충돌을 방지하기 위해 lock을 사용합니다.
                    with self._io_lock:
                        output_data = self.remote_output_data.copy()
                        blink_state = not blink_state

                        if is_error:
                            # 빨간색 점멸, 나머지 꺼짐
                            output_data[DigitalOutput.TOWER_LAMP_RED] = 1 if blink_state else 0
                            output_data[DigitalOutput.TOWER_LAMP_GREEN] = 0
                            output_data[DigitalOutput.TOWER_LAMP_YELLOW] = 0
                        elif is_idle:
                            # 노란색 점멸, 나머지 꺼짐
                            output_data[DigitalOutput.TOWER_LAMP_RED] = 0
                            output_data[DigitalOutput.TOWER_LAMP_GREEN] = 0
                            output_data[DigitalOutput.TOWER_LAMP_YELLOW] = 1 if blink_state else 0
                        else: # 공정 중
                            # 녹색 켜짐, 나머지 꺼짐
                            output_data[DigitalOutput.TOWER_LAMP_RED] = 0
                            output_data[DigitalOutput.TOWER_LAMP_GREEN] = 1
                            output_data[DigitalOutput.TOWER_LAMP_YELLOW] = 0

                        if self.dev_remoteio_enable and hasattr(self, 'iocontroller'):
                            self.iocontroller.write_output_data(output_data)
                            self.remote_output_data = output_data
            except Exception as e:
                Logger.error(f"[device] Error in _thread_tower_lamp_controller: {e}")
            
            time.sleep(0.5) # 0.5초 간격으로 점멸 (1Hz)

    def _thread_comm_status_updater(self):
        """
        주기적으로 각 장치의 통신 상태를 확인하고 블랙보드에 업데이트합니다.
        """
        Logger.info(f"[device] _thread_comm_status_updater started")
        while True:
            try:
                # Remote I/O
                if self.dev_remoteio_enable:
                    # read_IO_status()가 self.remote_comm_state를 업데이트합니다.
                    pass

                # Gauge
                if self.dev_gauge_enable:
                    gauge_status = self.get_dial_gauge_status()
                    if gauge_status:
                        bb.set("device/gauge/comm_status", 1)
                        self.gauge_error_count = 0
                    else:
                        bb.set("device/gauge/comm_status", 0)
                        self.gauge_error_count += 1

                # QR Reader
                if self.dev_qr_enable:
                    qr_status = self.qr_reader.is_connected
                    if qr_status:
                        bb.set("device/qr/comm_status", 1)
                        self.qr_error_count = 0
                    else:
                        bb.set("device/qr/comm_status", 0)
                        self.qr_error_count += 1

                # Shimadzu
                if self.dev_smz_enable :
                    smz_run_state = self.smz_ask_sys_status()
                    bb.set("device/shimadzu/comm_status", 1 if smz_run_state else 0)
                    # if smz_run_state:
                    #     bb.set("device/shimadzu/run_state", smz_run_state)
                # else :
                #     bb.set("device/shimadzu/comm_status", 1)
                
                # Robot과 Vision은 각자의 Context에서 처리될 것으로 예상됩니다.

            except Exception as e:
                Logger.error(f"[device] Error in _thread_comm_status_updater: {e}\n{traceback.format_exc()}")
            
            time.sleep(1.0) # 1초 간격으로 업데이트
        Logger.info(f"[device] _thread_comm_status_updater stopped")

    def check_violation(self) -> int:
        self.violation_code = 0
        try:
            # 1. 통신 오류 확인 (오류 카운터 기반)
            if self.dev_remoteio_enable and self.remote_io_error_count >= self.COMM_ERROR_THRESHOLD:
                Logger.info(f"[device] Check violation : Remote IO Communication Error Detected")
                self.violation_code |= DeviceViolation.REMOTE_IO_COMM_ERR
            
            if self.dev_gauge_enable and self.gauge_error_count >= self.COMM_ERROR_THRESHOLD:
                Logger.info(f"[device] Check violation : Gauge Communication Error Detected")
                self.violation_code |= DeviceViolation.GAUGE_COMM_ERR
                
            if self.dev_qr_enable and self.qr_error_count >= self.COMM_ERROR_THRESHOLD:
                Logger.info(f"[device] Check violation : QR Communication Error Detected")
                self.violation_code |= DeviceViolation.QR_COMM_ERR

            # 2. Shimadzu 통신 및 장치 상태 확인
            if self.dev_smz_enable and datetime.now() - self.dev_smz_check_time > timedelta(seconds=5) :
                self.dev_smz_check_time =  datetime.now()
                # if not self.smz_are_you_there():
                #     Logger.info(f"[device] Check violation : Shimadzu Communication Error Detected")
                #     self.violation_code |= DeviceViolation.SMZ_COMM_ERR
                # else:
                    
                smz_state = self.smz_ask_sys_status()
                try :
                    if smz_state is False:
                        Logger.info(f"[device] Check violation : Shimadzu Device Error Detected")
                        self.violation_code |= DeviceViolation.SMZ_COMM_ERR
                    elif smz_state is not None :
                        if smz_state.get("RUN") == "E":
                            Logger.info(f"[device] Check violation : Shimadzu Device Error Detected")
                            self.violation_code |= DeviceViolation.SMZ_DEVICE_ERR
                except Exception as e:
                    Logger.error(f"[device] SMZ Ask system status result : {smz_state}")
                    Logger.error(f"[device] Error parsing Shimadzu status: {e}\n{traceback.format_exc()}")
                    self.violation_code |= DeviceViolation.SMZ_COMM_ERR
            
            # 3. Remote I/O 장치 오류 확인 (EMO 등)
            if self.dev_remoteio_enable and self.remote_comm_state:
                # EMO 신호는 NC(Normally Closed)이므로 0일 때 트리거된 것으로 간주
                emo_triggered = (self.remote_input_data[DigitalInput.EMO_02_SI] == 0 or 
                                 self.remote_input_data[DigitalInput.EMO_03_SI] == 0 or 
                                 self.remote_input_data[DigitalInput.EMO_04_SI] == 0)
                
                sol_sensor = self.remote_input_data[DigitalInput.SOL_SENSOR]
                if sol_sensor == 0:
                    Logger.info(f"[device] Check violation : Sol Sensor Error Detected")
                    self.violation_code |= DeviceViolation.SOL_SENSOR_ERR
                if emo_triggered:
                    Logger.info(f"[device] Check violation : EMO Error Detected")
                    self.violation_code |= DeviceViolation.ISO_EMERGENCY_BUTTON # EMO는 더 구체적인 위반으로 처리

            return self.violation_code
        except Exception as e:
            Logger.error(f"[device] Error in check_violation: {e}\n{traceback.format_exc()}")
            reraise(e)
    
    def read_IO_status(self):
        '''
        Read Remote I/O value\n
        set blackborad
        '''
        if not hasattr(self, 'iocontroller') or self.iocontroller is None:
            return
        try:
            with self._io_lock:
                self.remote_input_data = self.iocontroller.read_input_data()
                self.remote_output_data = self.iocontroller.read_output_data()
            
            # 데이터 읽기 실패 또는 데이터 길이 미달 시 예외 처리
            # DI는 48개, DO는 32개의 배열 길이를 기대합니다.
            # if not self.remote_input_data or len(self.remote_input_data) < 48:
            #     raise IndexError(f"DI 데이터가 비정상입니다. 예상 길이: 48, 실제 길이: {len(self.remote_input_data) if self.remote_input_data is not None else 0}")
            
            # if not self.remote_output_data or len(self.remote_output_data) < 32:
            #     raise IndexError(f"DO 데이터가 비정상입니다. 예상 길이: 32, 실제 길이: {len(self.remote_output_data) if self.remote_output_data is not None else 0}")

            
            
            # Logger.info(f"[Device] DI : {self.remote_input_data}")
            # Logger.info(f"[Device] DO : {self.remote_output_data}")
            if len(self.remote_input_data) == 48 :
                bb.set("device/remote/input/entire", self.remote_input_data)
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

            # 측정기 받침 상태 저장
            if (bb.get("device/remote/input/INDICATOR_GUIDE_UP") == 1 and
                bb.get("device/remote/input/INDICATOR_GUIDE_DOWN") == 0) :
                bb.set("device/indicator/stand/state","up")
            elif (bb.get("device/remote/input/INDICATOR_GUIDE_UP") == 0 and
                  bb.get("device/remote/input/INDICATOR_GUIDE_DOWN") == 1) :
                bb.set("device/indicator/stand/state","down")
            else :
                bb.set("device/indicator/stand/state","")
            
            # 정렬기 상태 저장
            if (bb.get("device/remote/input/ALIGN_1_PUSH") == 1 and
                bb.get("device/remote/input/ALIGN_1_PULL") == 0 and
                bb.get("device/remote/input/ALIGN_2_PUSH") == 1 and
                bb.get("device/remote/input/ALIGN_2_PULL") == 0 and
                bb.get("device/remote/input/ALIGN_3_PUSH") == 1 and
                bb.get("device/remote/input/ALIGN_3_PULL") == 0) :
                bb.set("process_status/aligner_status","정렬")
                bb.set("device/align/state","push")

            elif (bb.get("device/remote/input/ALIGN_1_PUSH") == 0 and
                  bb.get("device/remote/input/ALIGN_1_PULL") == 1 and
                  bb.get("device/remote/input/ALIGN_2_PUSH") == 0 and
                  bb.get("device/remote/input/ALIGN_2_PULL") == 1 and
                  bb.get("device/remote/input/ALIGN_3_PUSH") == 0 and
                  bb.get("device/remote/input/ALIGN_3_PULL") == 1) :
                bb.set("process_status/aligner_status","해제")
                bb.set("device/align/state","pull")


            


            if len(self.remote_output_data) == 32 :
                bb.set("device/remote/output/entire", self.remote_output_data)
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

            # Remote IO 통신이 복구되었을 때 (꺼졌다가 다시 켜짐)
            # if not self.remote_comm_state and (
            #     self.remote_output_data[DigitalOutput.LOCAL_LAMP_R] != 1 or
            #     self.remote_output_data[DigitalOutput.LOCAL_LAMP_C] != 1 or
            #     self.remote_output_data[DigitalOutput.LOCAL_LAMP_L] != 1
            # ):
            #     Logger.info("[device] Remote IO System Error Detected.")
            #     Logger.info("[device] Remote IO connection restored (was disconnected). Restoring Lamp status (R, C, L ON).")                
            #     self.lamp_on()

            self.remote_comm_state = True
            # Logger.info(f"[device] Connect state : {self.remote_comm_state}")
            bb.set("device/remote/comm_status", 1 if self.remote_comm_state else 0)
            self.remote_io_error_count = 0  # 성공 시 에러 카운트 리셋
        except Exception as e:
            Logger.error(f"[device] Error in read_IO_status: {e}\n{traceback.format_exc()}")
            self.remote_comm_state = False
            bb.set("device/remote/comm_status", 0)
            self.remote_io_error_count += 1
            Logger.info(f"[device] Remote IO read error count: {self.remote_io_error_count}")

    def UI_DO_Control(self, address: int, value: int) -> bool:
        '''
        UI로부터 요청받은 특정 주소(address)의 디지털 출력(DO)을 제어합니다.
        :param address: 제어할 DO 비트 인덱스
        :param value: 설정할 값 (0 또는 1)
        :return: 성공 여부
        '''
        try:
            if not self._is_io_writable():
                return False
            with self._io_lock:
                output_data = self.remote_output_data.copy()
                output_data[address] = value
                self.iocontroller.write_output_data(output_data)
            Logger.info(f"[device] UI_DO_Control: DO {address} set to {value}")
            return True
        except Exception as e:
            Logger.error(f"[device] Error in UI_DO_Control: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    # TODO Lamp C, L, R 제어 함수 만들기
    def lamp_on(self) :
        '''
        Docstring for lamp_on
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()

            output_data[DigitalOutput.LOCAL_LAMP_C] = 1
            output_data[DigitalOutput.LOCAL_LAMP_L] = 1
            output_data[DigitalOutput.LOCAL_LAMP_R] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.LOCAL_LAMP_C] == 1 and
                read_data[DigitalOutput.LOCAL_LAMP_L] == 1 and
                read_data[DigitalOutput.LOCAL_LAMP_R] == 1):
                Logger.info(f"[device] Lamp On Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Lamp On Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in lamp_on: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    
    def lamp_off(self) :
        '''
        Docstring for lamp_on
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.LOCAL_LAMP_C] = 0
            output_data[DigitalOutput.LOCAL_LAMP_L] = 0
            output_data[DigitalOutput.LOCAL_LAMP_R] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.LOCAL_LAMP_C] == 0 and
                read_data[DigitalOutput.LOCAL_LAMP_L] == 0 and
                read_data[DigitalOutput.LOCAL_LAMP_R] == 0):
                Logger.info(f"[device] Lamp Off Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Lamp Off Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in lamp_off: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    # 인장기 그리퍼 열기/닫기 확인 함수들
    def chuck_open(self) :
        '''
        Docstring for chuck_open
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            # output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 0 현재 사용 X
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            # if (read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 0 and
            #     read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 0):
            if (read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 0):
                Logger.info(f"[device] Chuck Open Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck Open Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_open: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def chuck_open_non_blocking(self) -> str:
        '''
        Non-blocking chuck open with 20s delay.
        :return: "running", "done", "error"
        '''
        try:
            if not self._is_io_writable():
                return "error"

            # Start sequence
            if self.chuck_open_start_time == 0:
                output_data = self.remote_output_data.copy()
                output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 0  # 현재 사용 
                output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 0
                self.iocontroller.write_output_data(output_data)
                
                self.chuck_open_start_time = time.time()
                Logger.info(f"[device] Chuck Open Command Sent. Waiting 20s for completion.")
                return "running"

            # Check timer
            if time.time() - self.chuck_open_start_time >= 20.0:
                # Timer finished
                self.chuck_open_start_time = 0
                Logger.info(f"[device] Chuck Open 20s Wait Complete.")
                return "done"
            
            return "running"

        except Exception as e:
            Logger.error(f"[device] Error in chuck_open_non_blocking: {e}\n{traceback.format_exc()}")
            self.chuck_open_start_time = 0
            return "error"

    def chuck_close(self) :
        '''
        Docstring for chuck_close       
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 1 # 현재는 동시에 관리
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 1 and
                read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 1):
                Logger.info(f"[device] Chuck Close Command Sent Successfully.")
                return True
            # if (read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 1):
            #     Logger.info(f"[device] Chuck Close Command Sent Successfully.")
            #     return True
            else:
                Logger.error(f"[device] Chuck Close Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_close: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in chuck_check: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def chuck_1_close(self) :
        '''
        상단 그리퍼(GRIPPER_1) 닫기
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 1:
                Logger.info(f"[device] Chuck 1 (Upper) Close Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck 1 (Upper) Close Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_1_close: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def chuck_2_close(self) :
        '''
        하단 그리퍼(GRIPPER_2) 닫기
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 1:
                Logger.info(f"[device] Chuck 2 (Lower) Close Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck 2 (Lower) Close Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_2_close: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def chuck_1_open(self) :
        '''
        상단 그리퍼(GRIPPER_1) 열기
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_1_UNCLAMP] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if read_data[DigitalOutput.GRIPPER_1_UNCLAMP] == 0:
                Logger.info(f"[device] Chuck 1 (Upper) Open Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck 1 (Upper) Open Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_1_open: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def chuck_2_open(self) :
        '''
        하단 그리퍼(GRIPPER_2) 열기
        :return: sucess True, fail False
        '''
        try :
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.GRIPPER_2_UNCLAMP] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if read_data[DigitalOutput.GRIPPER_2_UNCLAMP] == 0:
                Logger.info(f"[device] Chuck 2 (Lower) Open Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Chuck 2 (Lower) Open Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in chuck_2_open: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    # 신율계 전후진 제어 및 확인 함수들    
    def EXT_move_forword(self) :
        '''
        Docstring for EXT_move_forword
        :return: sucess True, fail False        
        ''' 
        try :
            if not self._is_io_writable():
                return False
            
            with self._io_lock:
                output_data = self.remote_output_data.copy()
                output_data[DigitalOutput.EXT_FW] = 1
                output_data[DigitalOutput.EXT_BW] = 0
                self.iocontroller.write_output_data(output_data)
            
            time.sleep(1)  # 신호가 반영될 시간을 약간 줌
            with self._io_lock:
                read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 1 and
                read_data[DigitalOutput.EXT_BW] == 0):
                Logger.info(f"[device] EXT Move Forward Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Move Forward Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_forword: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
        
    def EXT_move_backward(self) :
        '''
        Docstring for EXT_move_backward
        :return: sucess True, fail False        
        ''' 
        try :
            if not self._is_io_writable():
                return False
            
            with self._io_lock:
                output_data = self.remote_output_data.copy()
                output_data[DigitalOutput.EXT_FW] = 0
                output_data[DigitalOutput.EXT_BW] = 1
                self.iocontroller.write_output_data(output_data)
            
            time.sleep(1)  # 신호가 반영될 시간을 약간 줌
            with self._io_lock:
                read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 0 and
                read_data[DigitalOutput.EXT_BW] == 1):
                Logger.info(f"[device] EXT Move Backward Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Move Backward Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_backward: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    
    def EXT_move_check(self,direction : int) -> bool:
        '''
        Docstring for EXT_move_check
        :param direction: 1 for forward, 2 for backward
        :return: sucess True, fail False
        '''
        try :
            with self._io_lock:
                read_data = self.iocontroller.read_input_data()
            if direction == 1 :
                if read_data[DigitalInput.EXT_FW_SENSOR] == 1 and read_data[DigitalInput.EXT_BW_SENSOR] == 0 :
                    # self.EXT_stop()
                    return True
                else :
                    return False
            elif direction == 2 :
                if read_data[DigitalInput.EXT_FW_SENSOR] == 0 and read_data[DigitalInput.EXT_BW_SENSOR] == 1 :
                    # self.EXT_stop()
                    return True
                else :
                    return False
            else :
                Logger.error(f"[device] EXT_move_check: Invalid direction {direction}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_move_check: {e}\n{traceback.format_exc()}")
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
            if not self._is_io_writable():
                return False
            
            with self._io_lock:
                output_data = self.remote_output_data.copy()
                output_data[DigitalOutput.EXT_FW] = 0
                output_data[DigitalOutput.EXT_BW] = 0
                self.iocontroller.write_output_data(output_data)
            
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            with self._io_lock:
                read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.EXT_FW] == 0 and
                read_data[DigitalOutput.EXT_BW] == 0):
                Logger.info(f"[device] EXT Stop Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] EXT Stop Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in EXT_stop: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    
    # Alignment Push/Pull 신호 제어 함수들
    def align_push(self) -> bool:
        '''
        Docstring for align_push
        
        :return: sucess True, fail False
        '''
        try:
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            # 1st 1번
            output_data[DigitalOutput.ALIGN_1_PUSH] = 1
            output_data[DigitalOutput.ALIGN_1_PULL] = 0
            
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.ALIGN_1_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_1_PULL] == 0):
                Logger.info(f"[device] Align #1 Push Command Sent Successfully.")
                time.sleep(1)
                
            else:
                Logger.error(f"[device] Align #1 Push Command Failed. read_data: {read_data}")
                return False
            # 2nd 2,3 번 움직이기
            output_data[DigitalOutput.ALIGN_2_PUSH] = 1
            output_data[DigitalOutput.ALIGN_2_PULL] = 0
            output_data[DigitalOutput.ALIGN_3_PUSH] = 1
            output_data[DigitalOutput.ALIGN_3_PULL] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()

            if (read_data[DigitalOutput.ALIGN_2_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_2_PULL] == 0 and
                read_data[DigitalOutput.ALIGN_3_PUSH] == 1 and
                read_data[DigitalOutput.ALIGN_3_PULL] == 0):
                Logger.info(f"[device] Align #2, #3 Push Command Sent Successfully.")
                
            else:
                Logger.error(f"[device] Align #2, #3 Push Command Failed. read_data: {read_data}")
                return False
            
            return True
        
        except Exception as e:
            Logger.error(f"[device] Error in align_push: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
        
    def align_pull(self) -> bool:
        '''
        Docstring for align_pull
        :return: sucess True, fail False
        '''
        try:
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            # 1st 1번
            output_data[DigitalOutput.ALIGN_1_PUSH] = 0
            output_data[DigitalOutput.ALIGN_1_PULL] = 1
            
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.ALIGN_1_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_1_PULL] == 1):
                Logger.info(f"[device] Align #1 Pull Command Sent Successfully.")
                time.sleep(1)
                
            else:
                Logger.error(f"[device] Align #1 Pull Command Failed. read_data: {read_data}")
                return False
            
            # 2nd 2,3 번 움직이기
            output_data[DigitalOutput.ALIGN_2_PUSH] = 0
            output_data[DigitalOutput.ALIGN_2_PULL] = 1
            output_data[DigitalOutput.ALIGN_3_PUSH] = 0
            output_data[DigitalOutput.ALIGN_3_PULL] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)  # 신호가 반영될 시간을 약간 줌
            read_data = self.iocontroller.read_output_data()

            if (read_data[DigitalOutput.ALIGN_2_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_2_PULL] == 1 and
                read_data[DigitalOutput.ALIGN_3_PUSH] == 0 and
                read_data[DigitalOutput.ALIGN_3_PULL] == 1):
                Logger.info(f"[device] Align #2, #3 Pull Command Sent Successfully.")
                
            else:
                Logger.error(f"[device] Align #2, #3 Pull Command Failed. read_data: {read_data}")
                return False
            
            return True
        except Exception as e:
            Logger.error(f"[device] Error in align_pull: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    
    def align_stop(self) -> bool:
        '''
        Docstring for align_stop
        
        :return: sucess True, fail False
        '''
        try:
            if not self._is_io_writable():
                return False
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
            Logger.error(f"[device] Error in align_stop: {e}\n{traceback.format_exc()}")
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
                    return True
                else :
                    return False
            else :
                Logger.info(f"[device] align_check: Invalid direction {direction}")
        except Exception as e:
            Logger.error(f"[device] Error in align_check: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False
    
    def indicator_stand_up(self) -> bool:
        '''
        인디게이터 가이드를 위로 이동시킵니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 1
            output_data[DigitalOutput.INDICATOR_DOWN] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.INDICATOR_UP] == 1 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 0):
                Logger.info(f"[device] Indicator Stand Up Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Indicator Stand Up Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_stand_up: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def indicator_stand_down(self) -> bool:
        '''
        인디게이터 가이드를 아래로 이동시킵니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            if not self._is_io_writable():
                return False
            Logger.info(f"[device] Indicator Stand Down Command Sent.")
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 0
            output_data[DigitalOutput.INDICATOR_DOWN] = 1
            self.iocontroller.write_output_data(output_data)
            Logger.info(f"[device] Remote IO Indicator Stand Down Command Sent Successfully.")
            time.sleep(0.1)
            Logger.info(f"[device] Remote IO Indicator Stand read State")
            read_data = self.iocontroller.read_output_data()
            Logger.info(f"[device] Remote IO Indicator Stand read State: {read_data}")
            if (read_data[DigitalOutput.INDICATOR_UP] == 0 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 1):
                Logger.info(f"[device] Indicator Stand Down Command Sent Successfully.")
                time.sleep(1)
                return True
            else:
                Logger.error(f"[device] Indicator Stand Down Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_stand_down: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def indicator_stand_stop(self) -> bool:
        '''
        인디게이터 가이드 이동을 정지합니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            if not self._is_io_writable():
                return False
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 0
            output_data[DigitalOutput.INDICATOR_DOWN] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.INDICATOR_UP] == 0 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 0):
                Logger.info(f"[device] Indicator Stand Stop Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Indicator Stand Stop Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_stand_stop: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in get_dial_gauge_value: {e}\n{traceback.format_exc()}")
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
            bb.set("device/gauge/comm_state/value",value)
            if value is not None :
                return True 
            else :
                return False
        except Exception as e:
            Logger.error(f"[device] Error in get_dial_gauge_status: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def qr_read(self, max_error_count: int = 30) -> bool:
        '''
        QR 코드를 읽고 결과를 블랙보드에 저장합니다.
        :param max_error_count: 연속 에러(파싱 실패 포함) 허용 횟수
        :return: 성공 시 True, 실패 시 False
        '''
        if not self.dev_qr_enable:
            return False
            
        try:
            # 연결 상태 확인 및 필요 시 재연결
            if not self.qr_reader.is_connected:
                if not self.qr_reader.connect():
                    return False

            # TEST1 명령 전송 및 결과 대기 (입력받은 에러 횟수 적용)
            result = self.qr_reader.request_test(1, max_error_count)
            if result.get("status") == "success":
                qr_data = result.get("data")
                bb.set("device/qr/result", qr_data)
                Logger.info(f"[device] QR Read Success: {qr_data}")
                return True
            
            Logger.error(f"[device] QR Read Failed: {result.get('message')}")
            return False
        except Exception as e:
            Logger.error(f"[device] Error in qr_read: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    # shimadzu client 래핑 함수들
    def smz_ask_register(self, regist_data: dict, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 시험 등록 요청을 전송하고 응답을 기다립니다.

        :param regist_data: test data
        :type regist_data: dict
        :param timeout: 응답 대기 시간 (초, 기본값 5초)
        :type timeout: float
        :return: 성공 시 응답 데이터, 타임아웃 또는 실패 시 None
        :rtype: Optional[Dict[str, Any]]
        '''
        try:
            batch_data = bb.get("process/auto/batch_data")
            if batch_data:
                current_qr_no = regist_data.get("qr_no")
                if current_qr_no:
                    process_data = batch_data.get("processData", [])
                    target_item = next((item for item in process_data if item.get("qr_no") == current_qr_no), None)
                    
                    if target_item:
                        try:
                            db_result = self.db.get_test_method_details(current_qr_no)
                            if db_result:
                                Logger.info(f"[device] Fetched method items from DB for {current_qr_no}")
                                regist_data.update(db_result)
                        except Exception as e:
                            Logger.error(f"[device] Failed to fetch batch method items from DB: {e}")

            bb.set("device/shimadzu/ask_register/params", regist_data)
            batch_id = bb.get("process_status/batch_info")
            specimen_no = bb.get("process/auto/current_specimen_no")
            try_no = bb.get("process/auto/target_floor")

            mtname = db_result.get("test_method")
            # batch ID + tray_no + speimen_no ex) B-20260108-001-t10-s03
            tpname = f"{batch_id}-t{try_no:02d}-s{specimen_no:02d}"
            size1 = db_result.get("size1")
            size2 = db_result.get("size2")
            gl = db_result.get("gl")
            # thickness = bb.get(""specimen/thickness_avg")
            chuckl = db_result.get("chuckl")
            last_tray_no = bb.get("process_status/last_tray_no")
            if last_tray_no != 0 and try_no == last_tray_no:
                if specimen_no == 5:
                    isfinal = 1  # 전체 시험중 마지막 시험인 경우     
            else:
                isfinal = 0  # 마지막 시험이 아닌 경우

            Logger.info(f"[device] Sending ASK_REGISTER to Shimadzu (MTNAME: {mtname}, TPNAME: {tpname}, SIZE1: {size1}, SIZE2: {size2}, GL: {gl}, ChuckL: {chuckl}, ISFinal: {isfinal}, timeout: {timeout}s)")

            result = self.shimadzu_client.send_ask_register(mtname=mtname,
                                                            tpname=tpname,
                                                            size1=size1,
                                                            size2=size2,
                                                            gl=gl,
                                                            chuckl=chuckl,
                                                            isfinal=isfinal,
                                                            timeout=timeout)

            if result is None:
                Logger.info(f"[device] ASK_REGISTER timeout after {timeout}s - No response from Shimadzu")
                return None

            Logger.info(f"[device] ASK_REGISTER response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_ask_register: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None
    
    def smz_start_measurement(self, lotname: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 측정 시작 명령을 전송하고 응답을 기다립니다.

        :param lotname : UI 또는 DB에서 받은 데이터
        :type lotname : str
        :param timeout: 응답 대기 시간 (초, 기본값 5초)
        :type timeout: float
        :return: 성공 시 응답 데이터, 타임아웃 또는 실패 시 None
        :rtype: Optional[Dict[str, Any]]
        '''
        try:
            Logger.info(f"[device] Sending START_RUN to Shimadzu (LOTNAME: {lotname}, timeout: {timeout}s)")
            
            result = self.shimadzu_client.send_start_run(lotname=lotname, timeout=timeout)

            if result is None:
                Logger.info(f"[device] START_RUN timeout after {timeout}s - No response from Shimadzu")
                return None

            Logger.info(f"[device] START_RUN response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_start_measurement: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None
    
    def smz_stop_measurement(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 측정 정지 명령을 전송하고 응답을 기다립니다.

        :param timeout: 응답 대기 시간 (초, 기본값 5초)
        :type timeout: float
        :return: 성공 시 응답 데이터, 타임아웃 또는 실패 시 None
        :rtype: Optional[Dict[str, Any]]
        '''
        try:
            Logger.info(f"[device] Sending STOP_ANA to Shimadzu (emergency stop, timeout: {timeout}s)")

            result = self.shimadzu_client.send_stop_ana(timeout=timeout)

            if result is None:
                Logger.info(f"[device] STOP_ANA timeout after {timeout}s - No response from Shimadzu")
                return None

            Logger.info(f"[device] STOP_ANA response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_stop_measurement: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None
    
    def smz_are_you_there(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 접속 확인 요청을 보내고 응답을 기다립니다.

        Args:
            timeout: 응답 대기 시간 (초, 기본값 1초)

        Returns:
            성공 시 응답 데이터 {"command": "I_AM_HERE", "params": {...}}
            타임아웃 또는 실패 시 None
        '''
        try:
            # 연결 상태 확인
            is_connected = self.shimadzu_client.is_connected if self.shimadzu_client else False
            Logger.info(f"[device] Shimadzu connection status: {is_connected}")
            Logger.info(f"[device] Sending ARE_YOU_THERE to Shimadzu (timeout: {timeout}s)")

            result = self.shimadzu_client.send_are_you_there(timeout=timeout)

            if result is None:
                Logger.info(f"[device] ARE_YOU_THERE timeout after {timeout}s - No response from Shimadzu")
                return None

            Logger.info(f"[device] ARE_YOU_THERE response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_are_you_there: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None

    def smz_ask_sys_status(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 시스템 상태 확인 요청을 보내고 응답을 기다립니다.

        Args:
            timeout: 응답 대기 시간 (초, 기본값 1초)

        Returns:
            성공 시 응답 데이터 {"command": "SYS_STATUS", "params": {...}}
            타임아웃 또는 실패 시 None
        '''
        try:
            # Logger.info(f"[device] Sending ASK_SYS_STATUS to Shimadzu (timeout: {timeout}s)")

            result = self.shimadzu_client.send_ask_sys_status(timeout=timeout)

            if result is None:
                Logger.info(f"[device] ASK_SYS_STATUS timeout after {timeout}s - No response from Shimadzu")
                return None
            #{'command': 'SYS_STATUS', 
            # 'params': {
            # 'MODE': 'A', 'RUN': 'N', 'LOAD': '000.0000', 'TEMP': '025.0'}}
            parsed_params = result.get("params")
            mode = parsed_params.get("MODE", "")
            run = parsed_params.get("RUN", "N")
            load = float(parsed_params.get("LOAD", "0.0"))
            temp = float(parsed_params.get("TEMP", "0.0"))

            bb.set("device/shimadzu/run_state", {
                "MODE": mode,
                "RUN": run,
                "LOAD": str(load),
                "TEMP": str(temp)
            })
            
            # Logger.info(f"[device] ASK_SYS_STATUS response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_ask_sys_status: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None

    def smz_ask_preload(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        '''
        Shimadzu 서버에 프리로드 상태 확인 요청을 보내고 응답을 기다립니다.

        Args:
            timeout: 응답 대기 시간 (초, 기본값 1초)

        Returns:
            성공 시 응답 데이터 {"command": "PRELOAD_STATUS", "params": {...}}
            타임아웃 또는 실패 시 None
        '''
        try:
            Logger.info(f"[device] Sending ASK_PRELOAD to Shimadzu (timeout: {timeout}s)")
            # TODO 명령 확인 필요
            result = self.shimadzu_client.send_ask_preload(timeout=timeout)

            if result is None:
                Logger.info(f"[device] ASK_PRELOAD timeout after {timeout}s - No response from Shimadzu")
                return None

            Logger.info(f"[device] ASK_PRELOAD response received: {result}")
            return result

        except Exception as e:
            Logger.error(f"[device] Error in smz_ask_preload: {e}\n{traceback.format_exc()}")
            reraise(e)
            return None
    
    def reconnect_remote_io(self) -> bool:
        """Remote I/O 재연결을 시도합니다."""
        Logger.info("[device] Attempting to reconnect to Remote IO...")
        try:
            self.iocontroller.disconnect()
            time.sleep(1)
            self.iocontroller.connect()
            # 재연결 성공 시, 에러 카운터를 리셋하여 즉시 위반 상태에서 벗어날 수 있도록 함
            self.remote_io_error_count = 0
            Logger.info("[device] Remote IO reconnected successfully.")
            return True
        except Exception as e:
            Logger.error(f"[device] Failed to reconnect Remote IO: {e}")
            return False

    def reconnect_gauge(self) -> bool:
        """두께 측정기 재연결을 시도합니다."""
        Logger.info("[device] Attempting to reconnect to Gauge...")
        try:
            # MitutoyoGauge는 별도의 connect/disconnect가 없으므로 재초기화
            self.gauge = MitutoyoGauge(connection_type=1)
            # 재연결 성공 시, 에러 카운터 리셋
            self.gauge_error_count = 0
            Logger.info("[device] Gauge re-initialized successfully.")
            return True
        except Exception as e:
            Logger.error(f"[device] Failed to re-initialize Gauge: {e}")
            return False

    def reconnect_qr(self) -> bool:
        """QR 리더기 재연결을 시도합니다."""
        Logger.info("[device] Attempting to reconnect to QR Reader...")
        try:
            self.qr_reader.disconnect()
            time.sleep(1)
            self.qr_reader.connect()
            # 재연결 성공 시, 에러 카운터 리셋
            self.qr_error_count = 0
            Logger.info("[device] QR Reader reconnected successfully.")
            return True
        except Exception as e:
            Logger.error(f"[device] Failed to reconnect QR Reader: {e}")
            return False