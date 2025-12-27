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
        Logger.info(f"[device] configs : {config.get('remote_io')}")
        Logger.info(f"[device] configs : {config.get('shimadzu_ip')} : {config.get('shimadzu_port')}")

        self._io_lock = threading.Lock()

        self.dev_gauge_enable = True
        self.dev_remoteio_enable = True
        self.dev_smz_enable = False 
        self.dev_qr_enable = True
        
        # MitutoyoGauge 장치 인스턴스 생성
        if self.dev_gauge_enable :
            self.gauge = MitutoyoGauge(connection_type=1)  # 예: connection_type=1는 시리얼 통신을 의미
        # 측정, 상태 확인 명령 전송 방지 변수
        self.gauge_initial_check_done = False
        self.gauge_measurement_done = False

        # remote I/O 장치 인스턴스 생성
        if self.dev_remoteio_enable :
            self.iocontroller = AutonicsEIPClient()
            # self.th_IO_reader = self.iocontroller.connect()
        self.remote_input_data = self.iocontroller.current_di_value
        self.remote_output_data = self.iocontroller.current_do_value
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

        # UI DO 제어 핸들러 스레드 추가
        self.th_UI_DO_handler = Thread(target=self._thread_UI_DO_handler, daemon=True)
        self.th_UI_DO_handler.start()

        # 주기적으로 통신 상태를 블랙보드에 업데이트하는 스레드 추가
        self.th_comm_status_updater = Thread(target=self._thread_comm_status_updater, daemon=True)
        self.th_comm_status_updater.start()

        Logger.info(f"[device] All device Init Complete")

        # 초기 장비 설정
        # 장비 내 램프 켜기
        self.lamp_on()
        
        # 정렬기 후퇴
        self.align_stop()
        time.sleep(1)

        self.align_pull()
        time.sleep(0.1)

        # 측정기 받침 내리기
        self.indicator_down()
        time.sleep(0.1)
    
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
            time.sleep(0.5)
            self.read_IO_status()

    def _thread_UI_DO_handler(self):
        """
        Blackboard의 트리거를 감시하여 UI로부터의 DO 제어 명령을 처리하는 스레드입니다.
        """
        while True:
            try:
                if bb.get("ui/cmd/do_control/trigger") == 1:
                    data = bb.get("ui/cmd/do_control/data")
                    if isinstance(data, dict):
                        address = data.get("addr")
                        val = data.get("value")
                        Logger.info(f"[Device] DO_Control : {address} {val}")
                        self.UI_DO_Control(int(address), int(val))
                    
                    # 처리 완료 후 트리거 리셋
                    bb.set("ui/cmd/do_control/trigger", 0)
            except Exception as e:
                Logger.error(f"[device] Error in _thread_UI_DO_handler: {e}\n{traceback.format_exc()}")
            time.sleep(0.1)

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
                if self.dev_smz_enable:
                    # are_you_there는 dict를 반환하므로, 응답이 있는지 여부로 판단
                    smz_status = self.smz_are_you_there() is not None
                    bb.set("device/shimadzu/comm_status", 1 if smz_status else 0)
                
                # Robot과 Vision은 각자의 Context에서 처리될 것으로 예상됩니다.

            except Exception as e:
                Logger.error(f"[device] Error in _thread_comm_status_updater: {e}\n{traceback.format_exc()}")
            
            time.sleep(10.0) # 10초 간격으로 업데이트
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
            if self.dev_smz_enable:
                if not self.smz_are_you_there():
                    Logger.info(f"[device] Check violation : Shimadzu Communication Error Detected")
                    self.violation_code |= DeviceViolation.SMZ_COMM_ERR
                else:
                    smz_state = self.smz_ask_sys_status()
                    if smz_state is False:
                        Logger.info(f"[device] Check violation : Shimadzu Device Error Detected")
                        self.violation_code |= DeviceViolation.SMZ_COMM_ERR
                    elif smz_state.get("RUN") == "E":
                        Logger.info(f"[device] Check violation : Shimadzu Device Error Detected")
                        self.violation_code |= DeviceViolation.SMZ_DEVICE_ERR
            
            # 3. Remote I/O 장치 오류 확인 (EMO 등)
            if self.dev_remoteio_enable and self.remote_comm_state:
                # EMO 신호는 NC(Normally Closed)이므로 0일 때 트리거된 것으로 간주
                emo_triggered = (self.remote_input_data[DigitalInput.EMO_02_SI] == 0 or 
                                 self.remote_input_data[DigitalInput.EMO_03_SI] == 0 or 
                                 self.remote_input_data[DigitalInput.EMO_04_SI] == 0)
                
                sol_sensor = self.remote_input_data[DigitalInput.SOL_SENSOR]
                if sol_sensor == 0:
                    Logger.info(f"[device] Check violation : Sol Sensor Error Detected")
                    self.violation_code |= DeviceViolation.REMOTE_IO_DEVICE_ERR
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
                time.sleep(0.5)
                self.remote_output_data = self.iocontroller.read_output_data()
            
            # 데이터 읽기 실패 또는 데이터 길이 미달 시 예외 처리
            # DI는 48개, DO는 32개의 배열 길이를 기대합니다.
            if not self.remote_input_data or len(self.remote_input_data) < 48:
                raise IndexError(f"DI 데이터가 비정상입니다. 예상 길이: 48, 실제 길이: {len(self.remote_input_data) if self.remote_input_data is not None else 0}")
            
            if not self.remote_output_data or len(self.remote_output_data) < 32:
                raise IndexError(f"DO 데이터가 비정상입니다. 예상 길이: 32, 실제 길이: {len(self.remote_output_data) if self.remote_output_data is not None else 0}")

            bb.set("device/remote/input/entire", self.remote_input_data)
            bb.set("device/remote/output/entire", self.remote_output_data)
            # Logger.info(f"[Device] DI : {self.remote_input_data}")
            # Logger.info(f"[Device] DO : {self.remote_output_data}")
            
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
            # Logger.info(f"[device] Connect state : {self.remote_comm_state}")
            bb.set("device/remote/comm_status", 1 if self.remote_comm_state else 0)
            self.remote_io_error_count = 0  # 성공 시 에러 카운트 리셋
        except Exception as e:
            Logger.error(f"[device] Error in read_IO_status: {e}\n{traceback.format_exc()}")
            self.remote_comm_state = False
            bb.set("device/remote/comm_status", 0)
            self.remote_io_error_count += 1
            Logger.warn(f"[device] Remote IO read error count: {self.remote_io_error_count}")

    def UI_DO_Control(self, address: int, value: int) -> bool:
        '''
        UI로부터 요청받은 특정 주소(address)의 디지털 출력(DO)을 제어합니다.
        :param address: 제어할 DO 비트 인덱스
        :param value: 설정할 값 (0 또는 1)
        :return: 성공 여부
        '''
        try:
            if not hasattr(self, 'iocontroller') or self.iocontroller is None:
                Logger.error("[device] UI_DO_Control: iocontroller is not initialized.")
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
            Logger.error(f"[device] Error in chuck_open: {e}\n{traceback.format_exc()}")
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

    # 신율계 전후진 제어 및 확인 함수들    
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
            Logger.error(f"[device] Error in EXT_move_forword: {e}\n{traceback.format_exc()}")
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
    
    def indicator_up(self) -> bool:
        '''
        인디게이터 가이드를 위로 이동시킵니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 1
            output_data[DigitalOutput.INDICATOR_DOWN] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.INDICATOR_UP] == 1 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 0):
                Logger.info(f"[device] Indicator Up Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Indicator Up Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_up: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def indicator_down(self) -> bool:
        '''
        인디게이터 가이드를 아래로 이동시킵니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 0
            output_data[DigitalOutput.INDICATOR_DOWN] = 1
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.INDICATOR_UP] == 0 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 1):
                Logger.info(f"[device] Indicator Down Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Indicator Down Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_down: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

    def indicator_stop(self) -> bool:
        '''
        인디게이터 가이드 이동을 정지합니다.
        :return: 성공 시 True, 실패 시 False
        '''
        try:
            output_data = self.remote_output_data.copy()
            output_data[DigitalOutput.INDICATOR_UP] = 0
            output_data[DigitalOutput.INDICATOR_DOWN] = 0
            self.iocontroller.write_output_data(output_data)
            time.sleep(0.1)
            read_data = self.iocontroller.read_output_data()
            if (read_data[DigitalOutput.INDICATOR_UP] == 0 and
                read_data[DigitalOutput.INDICATOR_DOWN] == 0):
                Logger.info(f"[device] Indicator Stop Command Sent Successfully.")
                return True
            else:
                Logger.error(f"[device] Indicator Stop Command Failed. read_data: {read_data}")
                return False
        except Exception as e:
            Logger.error(f"[device] Error in indicator_stop: {e}\n{traceback.format_exc()}")
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

    def qr_read(self, max_error_count: int = 10) -> bool:
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
            Logger.error(f"[device] Error in smz_ask_register: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in smz_start_measurement: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in smz_stop_measurement: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in smz_are_you_there: {e}\n{traceback.format_exc()}")
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
            Logger.error(f"[device] Error in smz_ask_sys_status: {e}\n{traceback.format_exc()}")
            reraise(e)
            return False

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