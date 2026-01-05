# shimadzu_client_v2.py
# Neuromeka 측 (Client) TCP/IP 통신 클래스 - Rev.A 251225 사양 반영
 
import socket
import threading
import time
import logging
from typing import Dict, Any, Optional
 
try:
    from .message_protocol import create_message, parse_message, ENCODING, STX, ETX
except ImportError:
    # 단독 실행 시를 위한 예외 처리
    def create_message(command, params=None):
        msg = command
        if params:
            for k, v in params.items():
                msg += f"@{k}={v}"
        return f"\x02{msg}\x03".encode('ascii')
 
    def parse_message(data):
        content = data.decode('ascii').strip('\x02\x03')
        parts = content.split('@')
        command = parts[0]
        params = {}
        for p in parts[1:]:
            if '=' in p:
                k, v = p.split('=', 1)
                params[k] = v
        return command, params
 
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
 
    def log(self, message: str):
        if self.ui_callback:
            self.ui_callback(message)
        logging.info(message)
 
    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
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
        buffer = b""
        while self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
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
                break
        self.is_connected = False
 
    def _handle_raw_message(self, raw_data):
        try:
            command, params = parse_message(raw_data)
            self.log(f"Received: {command} | Params: {params}")
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
            self.socket.sendall(msg)
            self.log(f"Sent: {command} | Params: {params}")
        except Exception as e:
            self.log(f"Send error: {e}")
 
    # --- API Methods (Rev.A 사양 반영) ---
 
    def send_are_you_there(self):
        """1. 접속 확인"""
        self.send_command("ARE_YOU_THERE")
 
    def send_start_run(self, lot_name="LOT_001"):
        """3. 자동운전 개시"""
        self.send_command("START_RUN", {"LOTNAME": lot_name})
 
    def send_ask_register(self, mtname, tpname, type_p="P", size1="10.00", size2="4.00", **kwargs):
        """
        5. 등록 요청 (ASK_REGISTER)
        사양서에 따라 MTNAME 추가 및 키워드 대소문자 수정
        """
        params = {
            "MTNAME": mtname,       # 시험 조건명 (추가됨)
            "TPNAME": tpname,       # 시험편명
            "TYPE": type_p,         # P:판상, R:봉상
            "SIZE1": format_float_value(size1, 7, 4),
            "SIZE2": format_float_value(size2, 7, 4),
            "SpeedType": kwargs.get("SpeedType", "S"), # S/R/T
            "DetectYP": kwargs.get("DetectYP", "T"),
            "DetectYS": kwargs.get("DetectYS", "T"),
            "DetectElastic": kwargs.get("DetectElastic", "T"),
            "DetectLYP": kwargs.get("DetectLYP", "F"),
            "DetectYPEL": kwargs.get("DetectYPEL", "F"),
            "DetectUEL": "F", # 플라스틱용이므로 고정(DetectUEL)
            "DetectTS": kwargs.get("DetectTS", "T"),
            "DetectEL": kwargs.get("DetectEL", "T"),
            "DetectNV": "F", # 플라스틱용이므로 고정(DetectNV)
            "YSPara": format_float_value(kwargs.get("YSPara", "0.20"), 5, 2),
            "NVType": kwargs.get("NVType", "I"),
            "NVPara1": format_float_value(kwargs.get("NVPara1", "10.00"), 5, 2),
            "NVPara2": format_float_value(kwargs.get("NVPara2", "20.00"), 5, 2)
        }
        self.send_command("ASK_REGISTER", params)
 
    def send_stop_ana(self):
        """
        11. Neuromeka 기기 이상 알림 (Neuromeka -> Shimadzu)
        로봇, 측순기 등 이상 시 Shimadzu를 정지시키기 위해 전송
        """
        self.send_command("STOP_ANA")
 
# --- 사용 예시 ---
if __name__ == "__main__":
    SERVER_HOST = "127.0.0.1"
    SERVER_PORT = 10000
 
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
 
    client = ShimadzuClient(SERVER_HOST, SERVER_PORT, ui_callback=on_ui_log)
    client.register_handler("ANA_RESULT", handle_ana_result)
 
    if client.connect():
        # 접속 확인
        client.send_are_you_there()
        time.sleep(1)
 
        # 등록 요청 (새로운 MTNAME 파라미터 포함)
        client.send_ask_register(
            mtname="PLASTIC_TEST_01", 
            tpname="SAMPLE_2025_001",
            size1="15.50", 
            size2="3.20",
            SpeedType="S",
            NVPara1="5.00",
            NVPara2="15.00"
        )
        # 만약 Neuromeka 로봇에 문제가 생겼다면?
        # client.send_stop_ana()
 
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            client.disconnect()