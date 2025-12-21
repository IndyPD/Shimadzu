# shimadzu_client.py
# Neuromeka 측 (Client) TCP/IP 통신 클래스

import socket
import threading
import time
from typing import Dict, Any, Optional
try:
    from .message_protocol import create_message, parse_message, ENCODING, STX, ETX
except ImportError:
    from message_protocol import create_message, parse_message, ENCODING, STX, ETX

DEBUG_MODE = False

def format_float_string(value, total_chars, decimal_places):
    """지정된 전체 길이와 소수점 자릿수로 숫자 문자열을 포맷합니다 (오른쪽 공백 패딩)."""
    try:
        # 문자열로 변환하고 소수점 자릿수 조정
        f_val = float(value)
        s_val = f'{f_val:.{decimal_places}f}'
        
        # 총 길이 패딩 (오른쪽 공백)
        return s_val.ljust(total_chars)[:total_chars]
    except (ValueError, TypeError):
        # 유효하지 않은 값의 경우 0 등으로 대체
        default_val = '0.' + '0' * decimal_places
        return default_val.ljust(total_chars)[:total_chars]


class ShimadzuClient:
    """
    Neuromeka 시스템 역할을 수행하는 TCP/IP 클라이언트 클래스 (ShimadzuClient 클래스명 사용).
    Shimadzu Server에 연결하고, 명령을 전송하며, Server의 응답을 처리합니다.
    """
    def __init__(self, host: str = '127.0.0.1', port: int = 5000, ui_callback=None): # 포트 5000 기본값 변경
        """
        Args:
            host: 접속할 Server(Shimadzu)의 IP 주소.
            port: 접속할 Server(Shimadzu)의 포트 번호.
            ui_callback: UI 업데이트를 위한 콜백 함수 (예: UI에 로그 출력).
        """
        self.host = host
        self.port = port
        self.client_socket: Optional[socket.socket] = None
        self.running = False
        self.receiver_thread: Optional[threading.Thread] = None
        self.ui_callback = ui_callback or self._default_callback
        self.is_connected = False
        self.response_handlers: Dict[str, callable] = {} # 응답 처리 함수 등록 딕셔너리
        self.lock = threading.Lock() # 스레드 안전성 확보를 위한 락
        self.debug_mode = False

    def _default_callback(self, message):
        """기본 콜백 함수 (UI 콜백이 없을 경우 콘솔 출력)."""
        if self.debug_mode and DEBUG_MODE:
            print(f"[SHIMADZU-CLIENT-DEBUG] {message}")
            
        

    def connect(self) -> bool:
        """Server에 연결을 시도하고 성공 시 수신 스레드를 시작합니다."""
        with self.lock:
            if self.is_connected:
                self.ui_callback("Already connected.")
                return True
            
            # 연결 시도 전에 이전 스레드 정리 (안전한 재연결 보장)
            if self.receiver_thread and self.receiver_thread.is_alive():
                 self.running = False
                 self.receiver_thread.join(timeout=1)
                 self.receiver_thread = None

            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                connect_host = self.host if self.host else '127.0.0.1'
                
                self.client_socket.connect((connect_host, self.port))
                self.client_socket.settimeout(0.5) # 수신 타임아웃 설정
                self.is_connected = True
                self.running = True
                self.ui_callback(f"Successfully connected to Server at {connect_host}:{self.port}")

                # 응답 수신 처리를 위한 별도 스레드 시작
                self.receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
                self.receiver_thread.start()
                return True
                
            except ConnectionRefusedError:
                self.ui_callback(f"[ERROR] Connection refused by Server at {connect_host}:{self.port}")
                self.client_socket = None
                return False
            except Exception as e:
                self.ui_callback(f"[ERROR] Connection error: {e}")
                self.client_socket = None
                return False

    def disconnect(self):
        """연결을 끊고 수신 스레드를 중지합니다."""
        with self.lock:
            if not self.is_connected:
                return

            self.running = False
            
            # 1. 소켓 종료
            if self.client_socket:
                try:
                    self.client_socket.close()
                    self.ui_callback("Disconnected from Server.")
                except Exception as e:
                    self.ui_callback(f"Error closing client socket: {e}")
                finally:
                    self.client_socket = None
                    self.is_connected = False

            # 2. 스레드 종료 대기 (자기 자신은 join 하지 않음)
            if self.receiver_thread and self.receiver_thread.is_alive():
                if self.receiver_thread != threading.current_thread():
                    self.receiver_thread.join(timeout=1)
                
            self.receiver_thread = None

    def _receive_loop(self):
        """Server로부터 데이터를 수신하고 처리하는 스레드의 메인 루프."""
        buffer = "" # 메시지 조립을 위한 버퍼
        try:
            while self.running and self.client_socket:
                try:
                    data = self.client_socket.recv(1024)
                    if not data:
                        self.ui_callback("Server disconnected.")
                        break
                    
                    received_str = data.decode(ENCODING)
                    buffer += received_str

                    while STX in buffer and ETX in buffer:
                        stx_index = buffer.find(STX)
                        etx_index = buffer.find(ETX, stx_index + 1)

                        if stx_index != -1 and etx_index != -1:
                            full_message = buffer[stx_index : etx_index + len(ETX)]
                            
                            # RAW 데이터 수신 로깅: STX, ETX를 \x02, \x03 형태로 출력
                            self.ui_callback(f"[RX-RAW] {full_message.encode('unicode_escape').decode()}")

                            buffer = buffer[etx_index + len(ETX):]
                            self._process_response(full_message)
                        else:
                            break

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.ui_callback(f"Receiver loop error: {e}")
                    break
                    
        except ConnectionResetError:
            self.ui_callback("Connection reset by server.")
        finally:
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
            self.is_connected = False
            self.running = False
            self.ui_callback("Receiver loop finished.")


    def _process_response(self, full_message: str):
        """수신된 응답 메시지를 파싱하고 등록된 핸들러를 호출합니다."""
        parsed_data = parse_message(full_message)
        
        if not parsed_data:
            self.ui_callback("[ERROR] Failed to parse response.")
            return

        response_type = parsed_data['type']
        params = parsed_data['params']

        if response_type in self.response_handlers:
            self.ui_callback(f"-> Calling handler for: {response_type}")
            try:
                self.response_handlers[response_type](params)
            except Exception as e:
                self.ui_callback(f"[ERROR] Handler for {response_type} failed: {e}")
        else:
            self.ui_callback(f"-> Unhandled response type: {response_type}. Params: {params}")

    def register_handler(self, response_type: str, handler: callable):
        """특정 응답 메시지 타입에 대한 콜백 함수를 등록합니다."""
        self.response_handlers[response_type] = handler

    def send_command(self, command_type: str, parameters: Optional[Dict[str, Any]] = None) -> bool:
        """
        Server(Shimadzu)에 명령 메시지를 전송합니다.
        """
        if not self.is_connected or not self.client_socket:
            self.ui_callback("[ERROR] Cannot send command: Not connected to Server.")
            return False

        message = create_message(command_type, parameters)
        
        try:
            self.client_socket.sendall(message.encode(ENCODING))
            # RAW 데이터 송신 로깅: STX, ETX를 \x02, \x03 형태로 출력
            self.ui_callback(f"[TX-RAW] {message.encode('unicode_escape').decode()}")
            return True
        except Exception as e:
            self.ui_callback(f"[ERROR] Failed to send command: {e}")
            self.disconnect() # 전송 실패 시 연결 끊기
            return False

    # ====================================================================
    # Command_Neuromeka->Shimadzu(例) 탭에 기반한 명령 함수들
    # ====================================================================
    
    def _send_and_wait(self, cmd: str, expected_response: str, params: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> bool:
        """명령을 전송하고 지정된 응답을 기다리는 내부 헬퍼 함수"""
        event = threading.Event()
        
        def callback(response_params):
            event.set()
            
        self.register_handler(expected_response, callback)
        
        if not self.send_command(cmd, parameters=params):
            if expected_response in self.response_handlers:
                del self.response_handlers[expected_response]
            return False
            
        result = event.wait(timeout)
        
        if expected_response in self.response_handlers:
            del self.response_handlers[expected_response]
            
        return result

    def send_are_you_there(self, timeout: float = 3.0) -> bool:
        """1. Connection Check (연결 확인)"""
        return self._send_and_wait("ARE_YOU_THERE", "I_AM_HERE", timeout=timeout)

    def send_init(self, timeout: float = 3.0) -> bool:
        """2. Initialization (장비 초기화)"""
        # TODO: 실제 프로토콜에 맞는 응답 키(예: INIT_ACK)로 수정 필요
        return self._send_and_wait("INIT", "INIT_FINISHED", timeout=timeout)

    def send_ask_sys_status(self, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        """
        3. Checking System Status (시스템 상태 요청)
        
        Returns:
            dict: {
                "MODE": "A"(Auto) or "M"(Manual),
                "RUN": "N"(Standby), "C"(Testing), "B"(Return), "F"(Stop), "R"(Ready), "E"(Error),
                "KEY": Optional status info name,
                "VALUE": Optional status info content,
                "LOAD": float,
                "TEMP": float
            }
        """
        event = threading.Event()
        result_data = {}

        def callback(params):
            result_data.update(params)
            event.set()

        self.register_handler("SYS_STATUS", callback)

        if not self.send_command("ASK_SYS_STATUS"):
            if "SYS_STATUS" in self.response_handlers:
                del self.response_handlers["SYS_STATUS"]
            return None

        if event.wait(timeout):
            if "SYS_STATUS" in self.response_handlers:
                del self.response_handlers["SYS_STATUS"]
            
            return {
                "MODE": result_data.get("MODE"), 
                "RUN": result_data.get("RUN"),
                "KEY": result_data.get("KEY"),
                "VALUE": result_data.get("VALUE"),
                "LOAD": float(result_data.get("LOAD", 0.0)), 
                "TEMP": float(result_data.get("TEMP", 0.0))
            }
        
        if "SYS_STATUS" in self.response_handlers:
            del self.response_handlers["SYS_STATUS"]
        return None

    def wait_for_ana_result(self, timeout: float = 600.0) -> Optional[Dict[str, Any]]:
        """
        시험 결과(ANA_RESULT)를 기다립니다.
        
        Returns:
            dict: 시험 결과 데이터 (VALUTS, VALUEPOS 등) 또는 None (타임아웃)
        """
        event = threading.Event()
        result_data = {}

        def callback(params):
            result_data.update(params)
            event.set()

        self.register_handler("ANA_RESULT", callback)
        
        if event.wait(timeout):
            if "ANA_RESULT" in self.response_handlers:
                del self.response_handlers["ANA_RESULT"]
            return result_data
        
        if "ANA_RESULT" in self.response_handlers:
            del self.response_handlers["ANA_RESULT"]
        return None

    def send_stop_ana(self, timeout: float = 3.0) -> bool:
        """4. Abnormality notification from other than the testing machine (자동운전 중지)"""
        return self._send_and_wait("STOP_ANA", "ACK_STOP_ANA", timeout=timeout)

    def send_start_run(self, lotname: str = "DEFAULT_LOT", timeout: float = 3.0) -> bool:
        """5. start of automatic operation (자동 운전 시작)"""
        params = {"LOTNAME": lotname}
        return self._send_and_wait("START_RUN", "ACK_START_RUN", params, timeout=timeout)

    def send_ask_register(self, 
                          tpname: str, type_p: str, size1: str, size2: str,
                          test_rate_type: str, test_rate: str,
                          detect_yp: str, detect_ys: str, detect_elastic: str, detect_lyp: str,
                          detect_ypel: str, detect_uel: str, detect_ts: str, detect_el: str, detect_nv: str,
                          ys_para: str, nv_type: str, nv_para1: str, nv_para2: str, lotname: Optional[str] = None) -> bool:
        """6. Registration Request (측정 파라미터 등록 요청) - 모든 항목 포함"""
        
        # Format SIZE1, SIZE2 (XXX.XXXX -> 9 chars total, 4 decimal)
        f_size1 = format_float_string(size1, 9, 4)
        f_size2 = format_float_string(size2, 9, 4)
        
        # Format TestRate (XXXXXX.XX -> 9 chars total, 2 decimal)
        f_test_rate = format_float_string(test_rate, 9, 2)
        
        # Format YSPara (xx.xx -> 5 chars total, 2 decimal)
        f_ys_para = format_float_string(ys_para, 5, 2)

        # Format NVPara1, NVPara2 (xx.xx -> 5 chars total, 2 decimal)
        f_nv_para1 = format_float_string(nv_para1, 5, 2)
        f_nv_para2 = format_float_string(nv_para2, 5, 2)

        params = {
            # 필수 항목
            "TPNAME": tpname.ljust(30), # 30 characters, right padded
            "TYPE": type_p,             # P/B
            "SIZE1": f_size1,           # XXX.XXXX (9 chars total)
            "SIZE2": f_size2,           # XXX.XXXX (9 chars total)
            
            # 테스트 속도 관련
            "TestRateType": test_rate_type, # S/R/T
            "TestRate": f_test_rate,        # XXXXXX.XX (9 chars total)

            # 계산 항목 T/F
            "DetectYP": detect_yp,          # T/F
            "DetectYS": detect_ys,          # T/F
            "DetectElastic": detect_elastic, # T/F
            "DetectLYP": detect_lyp,        # T/F
            "DetectYPEL": detect_ypel,      # T/F
            "DetectUEL": detect_uel,        # T/F
            "DetectTS": detect_ts,          # T/F
            "DetectEL": detect_el,          # T/F
            "DetectNV": detect_nv,          # T/F

            # 파라미터 항목
            "YSPara": f_ys_para,            # xx.xx (5 chars total)
            "NVType": nv_type,              # I/A/J
            "NVPara1": f_nv_para1,          # xx.xx (5 chars total)
            "NVPara2": f_nv_para2           # xx.xx (5 chars total)
        }
        
        if lotname:
             params["LOTNAME"] = lotname
             
        return self.send_command("ASK_REGISTER", params)


# --- 테스트 실행 예시 (Shimadzu Client) ---
if __name__ == '__main__':
    SERVER_HOST = '127.0.0.1'
    SERVER_PORT = 5000

    def client_log(message):
        if client.debug_mode and DEBUG_MODE:
            print(f"[NEURO-CLIENT-DEBUG] {message}")
        # print(f"[NEURO-CLIENT] {message}")

    def handle_i_am_here(params: Dict[str, Any]):
        client_log(f"Connection Check successful! Server Status: {params}")
        
    def handle_registered(params: Dict[str, Any]):
        code = params.get('CODE', '??')
        if code == '00':
            client_log("Test piece successfully REGISTERED (CODE: 00). Ready to START_RUN.")
        else:
            client_log(f"Registration FAILED (CODE: {code}). Check parameters.")

    def handle_ana_result(params: Dict[str, Any]):
        client_log("--- Test Result Received ---")
        client_log(f"  Sample: {params.get('TPNAME', 'N/A').strip()}")
        client_log(f"  Max Stress (VALUTS): {params.get('VALUTS', 'N/A')}")
        client_log(f"  Crosshead Pos (VALUEPOS): {params.get('VALUEPOS', 'N/A')}")
        client_log("----------------------------")


    client = ShimadzuClient(SERVER_HOST, SERVER_PORT, ui_callback=client_log)
    
    client.register_handler("I_AM_HERE", handle_i_am_here)
    client.register_handler("REGISTERED", handle_registered)
    client.register_handler("ANA_RESULT", handle_ana_result)
    
    if client.connect():
        client_log("\n--- Step 1: Connection Check ---")
        client.send_are_you_there()
        time.sleep(1)

        client_log("\n--- Step 2: Registration Request ---")
        # 모든 파라미터를 명시적으로 전달하는 예시
        client.send_ask_register(
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
        time.sleep(1)

        client_log("\n--- Step 3: Start Automatic Operation ---")
        client.send_start_run(lotname="LOT_0701_A")
        time.sleep(1)
        
        client_log("\n--- Step 4: Waiting for Test Results (ANA_RESULT) ---")
        time.sleep(7) 

    client_log("\n--- Disconnecting ---")
    client.disconnect()