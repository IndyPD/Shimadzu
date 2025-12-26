import socket
import threading
import time
import os
import json
import traceback

DEBUG_MODE = False

# 설정 파일 경로
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'configs', 'QR_comm.json')

def load_config(filepath: str) -> dict:
    """JSON 설정 파일을 로드합니다."""
    if not os.path.exists(filepath):
        if DEBUG_MODE: print(f"⚠️ Config file not found: {filepath}")
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        if DEBUG_MODE: print(f"❌ Failed to load config: {e}\n{traceback.format_exc()}")
        return {}

class QRReader:
    """
    TCP/IP를 통해 QR 리더기(Server)에 접속하여 제어 및 데이터를 수신하는 클래스입니다.
    """
    def __init__(self, host=None, port=None, timeout=2.0):
        """
        Args:
            host: QR 리더기 서버 IP 주소
            port: QR 리더기 서버 포트 번호
            timeout: 소켓 통신 타임아웃 (초)
        """
        self.config = load_config(CONFIG_FILE_PATH)
        self.host = host if host else self.config.get('host', '192.168.2.41')
        self.port = port if port else self.config.get('port', 9004)
        self.timeout = timeout
        self.client_socket = None
        self.is_connected = False
        self.running = False
        self.receiver_thread = None
        self.buffer = ""
        
        # 테스트 결과 동기화를 위한 변수
        self._test_result_event = threading.Event()
        self._test_success = False
        self._last_qr_data = None

        # 외부에서 등록 가능한 콜백 함수
        self.on_qr_data = None      # QR 데이터 수신 시 호출: func(data_str)
        self.on_heartbeat = None    # 하트비트 수신 시 호출: func()

    def connect(self) -> bool:
        """서버에 접속하고 수신 스레드를 시작합니다."""
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(self.timeout)
            self.client_socket.connect((self.host, self.port))
            
            self.is_connected = True
            self.running = True
            self.receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receiver_thread.start()
            
            if DEBUG_MODE: print(f"✅ QR Reader: Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            if DEBUG_MODE: print(f"❌ QR Reader: Connection failed - {e}\n{traceback.format_exc()}")
            return False

    def disconnect(self):
        """접속을 종료합니다."""
        self.running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        self.is_connected = False
        if DEBUG_MODE: print("🔌 QR Reader: Disconnected.")

    def _receive_loop(self):
        """데이터 수신 및 파싱 루프 (CR 기준 분리)"""
        while self.running:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    if DEBUG_MODE: print("⚠️ QR Reader: Connection closed by server.")
                    break
                
                # ASCII 디코딩 (에러 무시)
                self.buffer += data.decode('ascii', errors='ignore')
                
                # [CR] (\r) 기준으로 메시지 분리
                while '\r' in self.buffer:
                    line, self.buffer = self.buffer.split('\r', 1)
                    line = line.strip()
                    if line:
                        self._process_message(line)
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    if DEBUG_MODE: print(f"❌ QR Reader: Receive error - {e}\n{traceback.format_exc()}")
                break
        self.is_connected = False

    def parse_qr_data(self, line: str) -> dict:
        """
        수신된 문자열을 파싱하여 dict 형태로 반환합니다.
        예: "002,TEST_002:01:100%:98" -> {'index': '002', 'name': 'TEST_002', 'score': '98'}
        """
        try:
            # 수신 데이터 형식 검증 (쉼표와 콜론이 모두 포함되어야 함)
            if ',' not in line or ':' not in line:
                # HeartBeat, OK, ER 외의 비정상 포맷은 에러로 처리
                raise ValueError(f"알 수 없는 응답 형식: {line}")

            # 1. 쉼표(,) 기준으로 인덱스와 나머지 분리
            parts_comma = line.split(',', 1)
            index = parts_comma[0].strip()

            # 2. 콜론(:) 기준으로 이름과 점수(마지막 항목) 분리
            parts_colon = parts_comma[1].split(':')
            name = parts_colon[0].strip()
            score = parts_colon[-1].strip()

            return {"index": index, "name": name, "score": score}
        except Exception as e:
            # 에러 로그를 요청하신 형식과 유사하게 변경하여 디버깅을 돕습니다.
            if DEBUG_MODE: print(f"❌ 실패: {e}\n{traceback.format_exc()}")
            return {"raw": line, "error": "Parsing failed"}

    def _process_message(self, line: str):
        """수신된 라인별 처리"""
        if DEBUG_MODE: print(f"📥 [QR RX] {line}")
        
        # 1. 하트비트 확인
        if "HeartBeat" in line:
            if self.on_heartbeat:
                self.on_heartbeat()
            return

        # 2. 응답/데이터 구분
        if line.startswith("OK,"):
            # 명령 수신 확인 (Ack), 데이터가 올 때까지 기다림
            return
        elif line.startswith("ER,"):
            # 에러 응답 수신
            self._test_success = False
            self._last_qr_data = {"raw": line, "error": "Device returned ER"}
            self._test_result_event.set()
        else:
            # 실제 QR 데이터 (예: 002,TEST_002:01:100%:98)
            parsed_dict = self.parse_qr_data(line)
            self._last_qr_data = parsed_dict

            if "error" in parsed_dict:
                # 파싱 실패 시 (예: 'ERROR::0%:0') 실패로 처리하여 에러 카운트 증가 유도
                self._test_success = False
            else:
                self._test_success = True
                # 점수(score)가 80점 이상이면 QUIT 명령을 전송하여 리더기를 멈춤
                if 'score' in parsed_dict:
                    try:
                        score_val = int(parsed_dict['score'])
                        if score_val >= 80:
                            if DEBUG_MODE: print(f"🎯 점수 {score_val}점 감지 (80점 이상). QUIT 명령을 전송합니다.")
                            self.quit()
                    except (ValueError, TypeError):
                        pass

            self._test_result_event.set()

            if self.on_qr_data:
                self.on_qr_data(parsed_dict)

    def send_command(self, cmd: str) -> bool:
        """명령어 전송 (뒤에 \r 추가)"""
        if not self.is_connected:
            if DEBUG_MODE: print("❌ QR Reader: Not connected.")
            return False
        
        try:
            msg = f"{cmd}\r"
            if DEBUG_MODE: print(f"📤 [QR TX] {cmd}")
            self.client_socket.sendall(msg.encode('ascii'))
            return True
        except Exception as e:
            if DEBUG_MODE: print(f"❌ QR Reader: Send error - {e}\n{traceback.format_exc()}")
            return False

    # --- 인터페이스 메서드 ---
    def trigger_on(self):
        """LON 명령 전송 (리더기 켜기)"""
        return self.send_command("LON")

    def trigger_off(self):
        """LOFF 명령 전송 (리더기 끄기)"""
        return self.send_command("LOFF")

    def request_test(self, test_no: int, max_error_count: int = 10) -> dict:
        """
        TESTn 명령을 전송하고 결과를 확인합니다.
        연속으로 지정된 횟수(max_error_count)만큼 에러 응답이 오거나 타임아웃 시 에러 정보를 담은 dict를 반환합니다.
        """
        start_time = time.time()
        timeout_limit = max_error_count * 2.5  # 시도 횟수에 비례하여 타임아웃 설정
        error_count = 0
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout_limit:
                if DEBUG_MODE: print(f"⏰ QR Reader: request_test timed out after {elapsed:.2f}s")
                break

            self._test_result_event.clear()
            self._test_success = False
            self._last_qr_data = None
            
            if not self.send_command(f"TEST{test_no}"):
                return {"status": "error", "message": "send_command_failed"}
            
            # 응답 대기 (남은 시간 또는 최대 2초 중 작은 값)
            remaining = timeout_limit - (time.time() - start_time)
            if remaining > 0 and self._test_result_event.wait(timeout=min(2.0, remaining)):
                if self._test_success:
                    return {"status": "success", "data": self._last_qr_data}
                else:
                    # ER 응답을 받은 경우 카운트 증가
                    error_count += 1
                    if DEBUG_MODE: print(f"⚠️ QR Reader: Error response ({error_count}/{max_error_count})")
                    if error_count >= max_error_count:
                        if DEBUG_MODE: print(f"🛑 QR Reader: Stopped after {max_error_count} consecutive errors.")
                        break
            
            # 아직 시간이 남았다면 재시도 전 잠시 대기
            if time.time() - start_time < timeout_limit:
                time.sleep(0.5)
            
        self.quit()
        return {
            "status": "error", 
            "message": "max_errors_reached" if error_count >= max_error_count else "timeout",
            "last_data": self._last_qr_data
        }

    def quit(self):
        """QUIT 명령 전송 (종료)"""
        return self.send_command("QUIT")

if __name__ == "__main__":
    # 테스트용 콜백
    def on_qr_received(data):
        print(f"\n[CALLBACK] QR 데이터 파싱 결과:")
        print(data)

    def on_hb_received():
        print("\n[CALLBACK] 하트비트 수신됨 ❤️")

    # 설정 파일로부터 정보를 읽어 객체 생성
    qr = QRReader()
    qr.on_qr_data = on_qr_received
    qr.on_heartbeat = on_hb_received

    print(f"🚀 QR Reader 테스트 시작 ({qr.host}:{qr.port})")
    if qr.connect():
        try:
            while True:
                print("\n--- 명령어 선택 ---")
                print("1: LON (리더기 켬)")
                print("2: LOFF (리더기 끔)")
                print("3: TEST1 (테스트 요청)")
                print("4: QUIT (테스트 종료 요청)")
                print("q: 종료")
                
                cmd = input("입력 >> ").strip().lower()
                
                if cmd == '1': qr.trigger_on()
                elif cmd == '2': qr.trigger_off()
                elif cmd == '3': qr.request_test(1,20)
                elif cmd == '4': qr.quit()
                elif cmd == 'q':
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            qr.disconnect()