# shimadzu_client_v2.py
# Neuromeka 측 (Client) TCP/IP 통신 클래스 - Rev.A 251225 사양 반영

import socket
import threading
import time
import logging
from typing import Dict, Any, Optional

try:
    from pkg.utils.logging import Logger
except ImportError:
    # 단독 실행 시를 위한 fallback
    class Logger:
        @staticmethod
        def info(msg): logging.info(msg)
        @staticmethod
        def warning(msg): logging.warning(msg)
        @staticmethod
        def error(msg): logging.error(msg)
 
try:
    from .message_protocol import create_message, parse_message, ENCODING, STX, ETX
except ImportError:
    # 단독 실행 시를 위한 예외 처리
    STX = chr(0x02)
    ETX = chr(0x03)
    ENCODING = 'utf-8'

    def create_message(command, params=None):
        msg = command
        if params:
            for k, v in params.items():
                msg += f"@{k}={v}"
        return f"{STX}{msg}{ETX}"

    def parse_message(raw_message):
        """문자열 메시지를 파싱하여 딕셔너리 반환"""
        try:
            # 이미 문자열인 경우 그대로 사용
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode(ENCODING)

            # STX, ETX 제거
            if not (raw_message.startswith(STX) and raw_message.endswith(ETX)):
                return None

            content = raw_message[1:-1]
            parts = content.split('@')

            if not parts:
                return None

            command = parts[0]
            params = {}
            for p in parts[1:]:
                if '=' in p:
                    k, v = p.split('=', 1)
                    params[k] = v

            return {"type": command, "params": params}
        except Exception as e:
            return None
 
# 로그 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
 
def format_float_value(value, total_chars, decimal_places):
    """사양서의 'Parameter Number of Characters'에 맞춰 숫자를 포맷팅합니다."""
    try:
        f_val = float(value)
        s_val = f'{f_val:.{decimal_places}f}'
        return s_val[:total_chars] # 지정된 길이만큼 자름
    except (ValueError, TypeError):
        return "0".zfill(total_chars)
 
class ShimadzuClient:
    """
    Neuromeka 시스템 역할을 수행하는 TCP/IP 클라이언트 (Shimadzu Server 접속).
    Rev.A 사양서의 변경사항(MTNAME 추가, 에러 처리 강화)이 반영되었습니다.
    """
    def __init__(self, host: str, port: int, ui_callback=None):
        self.host = host
        self.port = port
        self.socket = None
        self.is_connected = False
        self.receive_thread = None
        self.ui_callback = ui_callback
        self.handlers = {}
        self.running = False
        self.response_event = threading.Event()
        self.response_data = None
        self.expected_response = None
        self._comm_lock = threading.Lock()  # 통신 직렬화를 위한 Lock
 
    def log(self, message: str):
        if self.ui_callback:
            self.ui_callback(message)
        Logger.info(f"[ShimadzuClient] {message}")
 
    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))
            self.is_connected = True
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            self.log(f"Connected to Shimadzu Server at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False
 
    def disconnect(self):
        self.running = False
        if self.socket:
            self.socket.close()
        self.is_connected = False
        self.log("Disconnected from server.")
 
    def _receive_loop(self):
        self.log("[DEBUG] _receive_loop started")
        buffer = b""
        while self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    self.log("[DEBUG] No data received, breaking loop")
                    break
                # [Log Filter] Raw data log filtering
                if b"SYS_STATUS" not in data and b"I_AM_HERE" not in data:
                    self.log(f'[DEBUG] Received raw data: {data}')
                buffer += data
                while b'\x02' in buffer and b'\x03' in buffer:
                    start_idx = buffer.find(b'\x02')
                    end_idx = buffer.find(b'\x03', start_idx)
                    if end_idx != -1:
                        msg_data = buffer[start_idx:end_idx+1]
                        buffer = buffer[end_idx+1:]
                        self._handle_raw_message(msg_data)
            except Exception as e:
                if self.running:
                    self.log(f"Receive error: {e}")
                    self.log(f"{data}")
                break
        self.is_connected = False
 
    def _handle_raw_message(self, raw_data):
        try:
            # 바이트인 경우 문자열로 디코딩
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8')

            parsed = parse_message(raw_data)
            if parsed is None:
                self.log(f"Failed to parse message: {raw_data}")
                return

            command = parsed.get("type")
            params = parsed.get("params", {})

            if command not in ["SYS_STATUS", "I_AM_HERE"]:
                self.log(f"Received: {command} | Params: {params}")
                self.log(f"[DEBUG] expected_response: {self.expected_response}, command: {command}")

            # 응답 대기 중인 경우 이벤트 세트
            if self.expected_response and command == self.expected_response:
                self.log(f"[DEBUG] Match! Setting response_data and event")
                self.response_data = {"command": command, "params": params}
                self.response_event.set()
            elif self.expected_response:
                self.log(f"[DEBUG] No match: expected '{self.expected_response}' but got '{command}'")

            # 전역 핸들러 실행
            if command in self.handlers:
                self.handlers[command](params)
            # 사양서 추가 사항: ERROR 커맨드 처리 (Shimadzu -> Neuromeka)
            if command == "ERROR":
                err_type = params.get("TYPE", "Unknown")
                err_msg = params.get("MSG", "No message")
                self.log(f"!!! SHIMADZU ERROR DETECTED !!! Type: {err_type}, Msg: {err_msg}")
                # 필요 시 여기서 Neuromeka 시스템 정지 로직 호출
        except Exception as e:
            self.log(f"Message parsing error: {e}")
 
    def register_handler(self, command: str, handler_func):
        self.handlers[command] = handler_func
 
    def send_command(self, command: str, params: Dict[str, Any] = None):
        if not self.is_connected:
            self.log("Cannot send: Not connected.")
            return
        try:
            msg = create_message(command, params)
            # 문자열인 경우 바이트로 인코딩
            if isinstance(msg, str):
                msg = msg.encode('utf-8')
            self.socket.sendall(msg)
            
            if command not in ["ASK_SYS_STATUS", "ARE_YOU_THERE"]:
                self.log(f"Sent: {command} | Params: {params}")
        except Exception as e:
            self.log(f"Send error: {e}")

    def send_and_wait(self, command: str, expected_response: str, params: Dict[str, Any] = None, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        명령을 전송하고 타임아웃 내에 응답을 기다립니다.
        Lock을 사용하여 동시에 하나의 명령만 처리합니다.

        Args:
            command: 전송할 명령
            expected_response: 기대하는 응답 명령
            params: 명령 파라미터
            timeout: 타임아웃 시간 (초)

        Returns:
            응답 데이터 ({"command": str, "params": dict}) 또는 타임아웃 시 None
        """
        if not self.is_connected:
            self.log("Cannot send: Not connected.")
            return None

        # Lock을 획득하여 동시 통신 방지
        # with self._comm_lock:
        try:
            # 이전 응답 데이터 초기화
            self.response_event.clear()
            self.response_data = None
            self.expected_response = expected_response

            # 명령 전송
            msg = create_message(command, params)
            # 문자열인 경우 바이트로 인코딩
            if isinstance(msg, str):
                msg = msg.encode('utf-8')
            self.socket.sendall(msg)

            if command not in ["ASK_SYS_STATUS", "ARE_YOU_THERE"]:
                self.log(f"Sent: {command} | Params: {params} | Waiting for: {expected_response}")

            # 응답 대기
            if self.response_event.wait(timeout):
                if command not in ["ASK_SYS_STATUS", "ARE_YOU_THERE"]:
                    self.log(f"Response received within {timeout}s: {self.response_data}")
                result = self.response_data
                # 초기화
                self.expected_response = None
                self.response_data = None
                return result
            else:
                self.log(f"Timeout: No response for {expected_response} within {timeout}s")
                # 초기화
                self.expected_response = None
                self.response_data = None
                return None

        except Exception as e:
            self.log(f"Send and wait error: {e}")
            self.expected_response = None
            self.response_data = None
        return None
 
    # --- API Methods (Rev.A 사양 반영) ---
 
    def send_are_you_there(self, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        1. 접속 확인

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("ARE_YOU_THERE", "I_AM_HERE", timeout=timeout)
        
    def send_init_run(self, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        4. 자동운전 초기화
        INIT 명령 전송 후 INIT_FINISHED 응답을 기다립니다.
        (ACK_INIT는 중간 응답으로, INIT_FINISHED가 최종 응답)

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            INIT_FINISHED 응답 데이터 ({"command": "INIT_FINISHED", "params": {"CODE": "Normal"}}) 또는 실패 시 None
        """
        # INIT 전송 후 최종 응답인 INIT_FINISHED 대기
        # (ACK_INIT는 중간에 오지만 무시하고 INIT_FINISHED만 기다림)
        init_finished_result = self.send_and_wait("INIT", "INIT_FINISHED", timeout=timeout)
        if init_finished_result is None:
            return None

        # CODE 확인
        code = init_finished_result.get("params", {}).get("CODE", "")
        if code == "Normal" or code == "0":
            self.log("INIT completed successfully (CODE=Normal)")
        else:
            self.log(f"INIT completed with CODE={code}")

        return init_finished_result

    def wait_for_response(self, expected_response: str, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        특정 응답을 대기합니다 (명령 전송 없이 수신만 대기).

        Args:
            expected_response: 기대하는 응답 명령
            timeout: 타임아웃 시간 (초)

        Returns:
            응답 데이터 ({"command": str, "params": dict}) 또는 타임아웃 시 None
        """
        if not self.is_connected:
            self.log("Cannot wait: Not connected.")
            return None

        try:
            self.response_event.clear()
            self.response_data = None
            self.expected_response = expected_response

            self.log(f"Waiting for: {expected_response}")

            if self.response_event.wait(timeout):
                self.log(f"Response received: {self.response_data}")
                result = self.response_data
                self.expected_response = None
                self.response_data = None
                return result
            else:
                self.log(f"Timeout: No {expected_response} received within {timeout}s")
                self.expected_response = None
                self.response_data = None
                return None

        except Exception as e:
            self.log(f"Wait for response error: {e}")
            self.expected_response = None
            self.response_data = None
            return None

    def send_start_run(self, lotname="LOT_001", timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        3. 자동운전 개시

        Args:
            lotname: LOT 이름
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("START_RUN", "ACK_START_RUN", {"LOTNAME": lotname}, timeout=timeout)

    def send_ask_sys_status(self, timeout: float = 360.0) -> Optional[Dict[str, Any]]:
        """
        2. 시스템 상태 확인
s
        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("ASK_SYS_STATUS", "SYS_STATUS", timeout=timeout)

    def send_ask_register(self, mtname, tpname, size1="10.00", size2="4.00", gl="50.00", chuckl="115.00", isfinal="False", timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        5. 등록 요청 (ASK_REGISTER)
        사양서에 따라 MTNAME, TPNAME, SIZE1, SIZE2, GL, ChuckL, ISFinal 만 사용

        Args:
            mtname: 시험 조건명
            tpname: 시험편명
            size1: 크기1 (두께)
            size2: 크기2 (폭)
            gl: 표점거리 (GL)
            chuckl: 척간거리 (ChuckL)
            isfinal: 최종 시험 여부 (ISFinal)
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        params = {
            "MTNAME": mtname,
            "TPNAME": tpname,
            "SIZE1": format_float_value(size1, 7, 4),
            "SIZE2": format_float_value(size2, 7, 4),
            "GL": format_float_value(gl, 7, 2),
            "ChuckL": format_float_value(chuckl, 7, 2),
            "ISFinal": isfinal
        }
        return self.send_and_wait("ASK_REGISTER", "REGISTERED", params, timeout=timeout)
 
    def send_stop_ana(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        11. Neuromeka 기기 이상 알림 (Neuromeka -> Shimadzu)
        로봇, 측순기 등 이상 시 Shimadzu를 정지시키기 위해 전송

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("STOP_ANA", "ACK_STOP_ANA", timeout=timeout)

    def send_ask_preload(self, timeout: float = 300.0) :
        """
        12. 프리로드 시험 시작 요청 (ASK_PRELOAD)

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("ASK_PRELOAD", "ACK_PRELOAD", timeout=timeout)

    def send_start_ana(self, timeout: float = 300.0) -> Optional[Dict[str, Any]]:
        """
        7. 시험 시작 요청 (START_ANA)
        ASK_REGISTER -> REGISTER_RESULT 이후 시험 시작 명령
        Shimadzu에서 ANA_STARTED 응답 후 실제 시험 진행

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("START_ANA", "ACK_START_ANA", timeout=timeout)

    def send_ack_ana_result(self):
        """
        10. 시험 결과 수신 확인 (ACK_ANA_RESULT)
        ANA_RESULT 수신 후 전송
        """
        self.send_command("ACK_ANA_RESULT")
        self.log("Sent ACK_ANA_RESULT")

    def wait_for_ana_result(self, timeout: float = 900.0) -> Optional[Dict[str, Any]]:
        """
        9. 시험 결과 대기 (ANA_RESULT)
        시험이 완료될 때까지 ANA_RESULT 메시지를 대기합니다.
        시험 시간이 길 수 있으므로 기본 타임아웃은 900초(15분)입니다.

        Args:
            timeout: 응답 대기 시간 (초, 기본 900초)

        Returns:
            응답 데이터 {"command": "ANA_RESULT", "params": {...}} 또는 타임아웃 시 None
        """
        try:
            # 이전 응답 데이터 초기화
            self.response_event.clear()
            self.response_data = None
            self.expected_response = "ANA_RESULT"

            self.log(f"Waiting for ANA_RESULT (timeout: {timeout}s)...")

            # 응답 대기 (별도 명령 전송 없이 수신만 대기)
            if self.response_event.wait(timeout):
                self.log(f"ANA_RESULT received: {self.response_data}")
                result = self.response_data
                # 초기화
                self.expected_response = None
                self.response_data = None
                return result
            else:
                self.log(f"Timeout: No ANA_RESULT received within {timeout}s")
                # 초기화
                self.expected_response = None
                self.response_data = None
                return None

        except Exception as e:
            self.log(f"Wait for ANA_RESULT error: {e}")
            self.expected_response = None
            self.response_data = None
            return None

    # [Method 2] Non-blocking check functions (Commented out)
    # def start_waiting_ana_result(self):
    #     """ANA_RESULT 대기 시작 (이벤트 초기화)"""
    #     self.response_event.clear()
    #     self.response_data = None
    #     self.expected_response = "ANA_RESULT"
    #     self.log("Started waiting for ANA_RESULT (Non-blocking)...")
    #
    # def check_ana_result(self) -> Optional[Dict[str, Any]]:
    #     """ANA_RESULT 도착 여부 확인 (Non-blocking)"""
    #     if self.response_event.is_set():
    #         self.log(f"ANA_RESULT received: {self.response_data}")
    #         result = self.response_data
    #         # 초기화
    #         self.expected_response = None
    #         self.response_data = None
    #         return result
    #     return None

    def send_end_run(self, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """
        자동운전 종료 (END_RUN)
        모든 시험 완료 후 자동운전 종료 명령

        Args:
            timeout: 응답 대기 시간 (초)

        Returns:
            응답 데이터 또는 타임아웃 시 None
        """
        return self.send_and_wait("END_RUN", "RUN_ENDED", timeout=timeout)
 
# --- 사용 예시 ---
if __name__ == "__main__":
    SERVER_HOST = "192.168.2.156"
    SERVER_PORT = 5000

    def on_ui_log(msg):
        print(f"[UI LOG] {msg}")

    def handle_ana_result(params):
        print("\n=== 시험 결과 수신 (플라스틱 사양) ===")
        # VALUUEL, VALUN 항목은 금속용이므로 제외됨
        print(f"시험편: {params.get('TPNAME')}")
        print(f"인장강도: {params.get('VALUYP')} N/mm2")
        print(f"탄성률: {params.get('VALUY')} N/mm2")
        print(f"결과코드: {params.get('CODE')} (00:정상)")
        print("==================================\n")

    def handle_i_am_here(params):
        print("\n=== 접속 확인 응답 수신 ===")
        print(f"I_AM_HERE 응답: {params}")
        print("==================================\n")

    def handle_sys_status(params):
        print("\n=== 시스템 상태 응답 수신 ===")
        print(f"SYS_STATUS: {params}")
        print("==================================\n")

    client = ShimadzuClient(SERVER_HOST, SERVER_PORT, ui_callback=on_ui_log)
    client.register_handler("ANA_RESULT", handle_ana_result)
    client.register_handler("I_AM_HERE", handle_i_am_here)
    client.register_handler("SYS_STATUS", handle_sys_status)

    if client.connect():
        print("\n=== Shimadzu 통신 테스트 시작 ===\n")

        # 1. 접속 확인 (타임아웃 5초)
        print("1. ARE_YOU_THERE 전송 중...")
        result = client.send_are_you_there(timeout=5.0)
        if result:
            print(f"   ✓ 응답 수신: {result}")
        else:
            print(f"   ✗ 타임아웃 또는 실패")
        time.sleep(1)

        # 2. 시스템 상태 확인 (타임아웃 30초)
        print("\n2. ASK_SYS_STATUS 전송 중...")
        result = client.send_ask_sys_status(timeout=30.0)
        if result:
            print(f"   ✓ 응답 수신: {result}")
        else:
            print(f"   ✗ 타임아웃 또는 실패")
        time.sleep(1)

        # 3. 등록 요청 (새로운 MTNAME 파라미터 포함)
        print("\n3. ASK_REGISTER 전송 중...")
        client.send_ask_register(
            mtname="PLASTIC_TEST_01",
            tpname="SAMPLE_2025_001",
            size1="15.50",
            size2="3.20",
            SpeedType="S",
            NVPara1="5.00",
            NVPara2="15.00"
        )
        print("   → 비동기 전송 완료 (응답은 핸들러로 수신)")

        # 4. 비상 정지 테스트 (주석 처리)
        # print("\n4. STOP_ANA 전송 중...")
        # client.send_stop_ana()

        print("\n=== 프로그램 실행 중 (Ctrl+C로 종료) ===\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n=== 프로그램 종료 중 ===")
            client.disconnect()
            print("종료 완료")