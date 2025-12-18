import serial
import socket
import time
import sys
import json
import os

DEBUG_MODE = False

# 설정 파일 경로
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'configs', 'MitutoyoGauge.json')

def load_config(filepath: str) -> dict:
    """
    지정된 경로에서 JSON 설정 파일을 읽어옵니다.
    """
    # configs 폴더가 없다면 생성 (파일 생성 시에는 필요 없지만 안정성을 위해 추가)
    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
    if not os.path.exists(filepath):
        if DEBUG_MODE: print(f"ERROR: 설정 파일을 찾을 수 없습니다: {filepath}")
        if DEBUG_MODE: print("configs/MitutoyoGauge.json 파일이 존재하는지 확인해 주세요.")
        # 파일이 없으면 기본 설정으로 임시 파일 생성 유도 (선택 사항이나 여기서는 종료)
        sys.exit(1)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if DEBUG_MODE: print(f"INFO: 설정 파일 로드 성공: {filepath}")
            return config
    except json.JSONDecodeError as e:
        if DEBUG_MODE: print(f"ERROR: JSON 파일 파싱 오류: {filepath}. 오류 내용: {e}")
        sys.exit(1)
    except Exception as e:
        if DEBUG_MODE: print(f"ERROR: 설정 파일을 읽는 중 알 수 없는 오류 발생: {e}")
        sys.exit(1)


class MitutoyoGauge:
    """
    미쓰도요 게이지의 RS232 통신을 처리하는 클래스입니다.
    Serial (1) 또는 Socket (2) 통신 방식을 지원합니다.
    """
    def __init__(self, connection_type: int, debug_mode: int = 0):
        """
        클래스를 초기화하고 통신 타입에 맞는 설정을 JSON 파일에서 로드합니다.

        :param connection_type: 1 (Serial) 또는 2 (Socket)
        :param debug_mode: 1로 설정 시 디버그 로그 출력, 0(기본값) 시 출력 안 함
        """
        self.connection_type = connection_type
        self.connection = None
        self.config = {}
        self.debug_mode = debug_mode
        
        # 1. 설정 파일에서 모든 설정 로드
        full_config = load_config(CONFIG_FILE_PATH)
        
        # 2. 통신 타입에 맞는 설정 선택
        if connection_type == 1:
            self.config = full_config.get('SERIAL_CONFIG', {})
            if DEBUG_MODE: print("INFO: 통신 방식이 Serial (COM/USB)로 설정되었습니다.")
        elif connection_type == 2:
            self.config = full_config.get('SOCKET_CONFIG', {})
            if DEBUG_MODE: print("INFO: 통신 방식이 Socket (TCP/IP)로 설정되었습니다.")
        else:
            if DEBUG_MODE: print(f"ERROR: 잘못된 통신 방식 입력 ({connection_type}). 1(Serial) 또는 2(Socket)를 선택하세요.")
            sys.exit(1)
            
        # 설정 로드 확인
        if not self.config:
            config_key = 'SERIAL_CONFIG' if connection_type == 1 else 'SOCKET_CONFIG'
            if DEBUG_MODE: print(f"ERROR: JSON 파일에서 '{config_key}' 설정을 찾을 수 없습니다. CONFIG_FILE_PATH를 확인하세요.")
            sys.exit(1)

        # PC -> 게이지 요청 명령어 (Carriage Return, CR)
        # 매뉴얼에 따라 1바이트 문자를 사용하며, 바이트 형태로 인코딩
        self.request_command = '\r'.encode('latin-1') 

        # 초기 연결 및 데이터 확인
        if self.connect():
            test_val = self.request_data()
            if test_val is not None:
                if DEBUG_MODE: print(f"INFO: 초기 데이터 수신 확인 완료 ({test_val})")
            else:
                if DEBUG_MODE: print("WARNING: 연결은 성공했으나 초기 데이터 수신에 실패했습니다.")
        else:
            if DEBUG_MODE: print("WARNING: 초기 연결에 실패했습니다.")

    def _log_debug(self, message: str):
        """디버그 모드가 1일 때만 메시지를 출력합니다."""
        if self.debug_mode == 1 and DEBUG_MODE:
            print(f"DEBUG: {message}")

    def _connect_serial(self):
        """pyserial을 사용하여 시리얼 포트 연결을 시도합니다."""
        port = self.config.get('port')
        if DEBUG_MODE: print(f"[{port}] 포트에 시리얼 연결 시도 중...")
        try:
            self.connection = serial.Serial(
                port=port,
                baudrate=self.config.get('baudrate'),
                bytesize=self.config.get('bytesize'),
                parity=self.config.get('parity'),
                stopbits=self.config.get('stopbits'),
                timeout=self.config.get('timeout')
            )
            if self.connection.is_open:
                if DEBUG_MODE: print(f"✅ 시리얼 포트 연결 성공: {port}")
                return True
            return False
        except serial.SerialException as e:
            if DEBUG_MODE: print(f"❌ 시리얼 포트 연결 실패: {e}")
            if DEBUG_MODE: print("포트 설정(port)이나 속도(baudrate)를 확인해 주세요.")
            return False

    def _connect_socket(self):
        """socket을 사용하여 TCP/IP 소켓 연결을 시도합니다."""
        host = self.config.get('host')
        port = self.config.get('port')
        if DEBUG_MODE: print(f"[{host}:{port}] 주소에 소켓 연결 시도 중...")
        try:
            self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connection.settimeout(self.config.get('timeout', 1))
            self.connection.connect((host, port))
            if DEBUG_MODE: print(f"✅ 소켓 연결 성공: {host}:{port}")
            return True
        except socket.error as e:
            if DEBUG_MODE: print(f"❌ 소켓 연결 실패: {e}")
            if DEBUG_MODE: print("IP 주소(host)와 포트(port) 설정을 확인하고, 컨버터가 켜져 있는지 확인하세요.")
            self.connection = None
            return False

    def connect(self) -> bool:
        """설정된 통신 타입에 따라 연결을 시작합니다."""
        if self.connection_type == 1:
            return self._connect_serial()
        elif self.connection_type == 2:
            return self._connect_socket()
        return False

    def disconnect(self):
        """통신 연결을 해제합니다."""
        if self.connection:
            self.connection.close()
            if DEBUG_MODE: print("통신 연결 해제.")
            self.connection = None

    def _request_serial_data(self):
        """시리얼 통신으로 데이터를 요청하고 수신합니다."""
        self._log_debug(f"Serial 송신 RAW (Bytes): {repr(self.request_command)}")
        try:
            # 요청 명령 전송
            self.connection.write(self.request_command)
            
            # 응답 데이터 수신 (CR(\r)까지 읽음)
            raw_response = self.connection.read_until(b'\r')
            
            # 디버깅: 수신 RAW 메시지 출력
            if raw_response:
                self._log_debug(f"Serial 수신 RAW (Bytes): {repr(raw_response)}")
            
            return raw_response
        except serial.SerialException as e:
            if DEBUG_MODE: print(f"통신 중 시리얼 오류 발생: {e}")
        return None

    def _request_socket_data(self):
        """소켓 통신으로 데이터를 요청하고 수신합니다."""
        self._log_debug(f"Socket 송신 RAW (Bytes): {repr(self.request_command)}")
        try:
            # 1. 요청 명령 전송
            self.connection.sendall(self.request_command)
            
            # 2. 응답 데이터 수신 (CR(\r)이 나올 때까지 읽음)
            buffer = b''
            start_time = time.time()
            timeout = self.config.get('timeout', 1)
            
            while time.time() - start_time < timeout:
                try:
                    # 소켓의 settimeout()이 적용되므로, 작은 버퍼로 반복 수신
                    chunk = self.connection.recv(1) # 1바이트씩 읽기
                    if chunk:
                        buffer += chunk
                        if buffer.endswith(b'\r'):
                            self._log_debug(f"Socket 수신 RAW (Bytes): {repr(buffer)}")
                            return buffer # CR 포함하여 응답 반환
                    else:
                        # 연결이 닫혔거나 데이터가 없음
                        time.sleep(0.01)
                except socket.timeout:
                    self._log_debug(f"Socket 수신 타임아웃 발생. 현재 버퍼: {repr(buffer)}")
                    break # 타임아웃 발생
                except BlockingIOError:
                    time.sleep(0.01)
                    
            if DEBUG_MODE: print("게이지로부터 응답을 받지 못했습니다. (타임아웃)")
            return None
            
        except socket.error as e:
            if DEBUG_MODE: print(f"통신 중 소켓 오류 발생: {e}")
            return None

    def parse_data(self, raw_data: bytes) -> dict:
        """
        수신된 RAW 데이터를 ASCII 문자열로 디코딩하고, 매뉴얼에 따라 실수(float)로 파싱합니다.
        정상: 01A[+ 또는 공백]000.1234<CR>
        에러: 91x<CR>
        """
        if not raw_data:
            return {"status": "ERROR", "message": "응답 데이터 없음"}
        
        # 1. 바이트를 문자열로 디코딩
        try:
            # .strip()을 사용하여 CR/LF 및 공백 제거
            data = raw_data.decode('ascii', errors='ignore').strip()
            self._log_debug(f"ASCII 디코딩된 데이터: '{data}'")
        except Exception:
            return {"status": "ERROR", "message": "데이터 디코딩 오류"}

        if len(data) < 3:
            return {"status": "ERROR", "message": f"데이터 길이 오류: {data}"}

        # 2. 매뉴얼 파싱: 에러 응답 확인 (시작이 '91'인 경우)
        if data.startswith('91'):
            error_code = data[2]
            return {"status": "ERROR", "message": f"게이지 에러 발생 (코드: {error_code})"}

        # 3. 매뉴얼 파싱: 정상 응답 확인 (시작이 '01A'인 경우)
        if data.startswith('01A'):
            value_string = data[3:] # '01A'를 제외한 실제 값 문자열 (예: '+000.1234')
            
            try:
                # value_string 전체를 float으로 변환하여 최종 값 획득
                numeric_value = float(value_string)
                
                return {
                    "status": "OK", 
                    "value": numeric_value, # float 변수에 저장된 값
                    "raw_string": data,
                    "note": f"정상적으로 매뉴얼 형식(01A...)으로 파싱되었습니다."
                }
            except ValueError:
                # 데이터 형식이 깨지거나 숫자로 변환 불가 시 오류 처리
                return {"status": "ERROR", "message": f"숫자 변환 오류: {value_string} (Raw: {data})"}

        # 4. 알 수 없는 형식의 응답
        return {"status": "ERROR", "message": f"알 수 없는 응답 형식: {data}"}


    def request_data(self) :
        """
        설정된 통신 타입으로 데이터를 요청하고 분석합니다.
        성공 시 float 값을 반환하고, 실패 시 None을 반환합니다.
        """
        if not self.connection:
            if DEBUG_MODE: print("ERROR: 통신이 연결되지 않았습니다. .connect()를 먼저 호출하세요.")
            return None

        if self.connection_type == 1:
            raw_response = self._request_serial_data()
        elif self.connection_type == 2:
            raw_response = self._request_socket_data()
        else:
            return None

        if raw_response:
            result = self.parse_data(raw_response)
            
            # 파싱된 결과 딕셔너리 전체를 디버그 모드에서 출력
            self._log_debug(f"파싱 결과 딕셔너리: {result}")
            
            if result["status"] == "OK":
                # 최종 출력은 파싱된 float 값입니다.
                value = result['value']
                # print(f"✅ 수신 성공: 측정 값 (float) = {value}")
                return value # 성공 시 float 값 반환
            elif result["status"] == "ERROR":
                if DEBUG_MODE: print(f"❌ 실패: {result['message']}")
                
        return None # raw_response가 없거나 파싱 상태가 ERROR일 경우 None 반환


def main():
    # --- 통신 방식 선택 (1: Serial, 2: Socket) ---
    CONNECTION_TYPE = 1
    
    # --- 디버그 모드 선택 (0: 비활성화, 1: 활성화) ---
    # 1로 설정하면 모든 DEBUG 로그가 출력됩니다.
    DEBUG_MODE = 0
    
    # (주의) 'pyserial' 라이브러리가 설치되어 있어야 합니다: pip install pyserial
    
    # 클래스 초기화 시, connection_type과 debug_mode를 전달합니다.
    gauge = MitutoyoGauge(CONNECTION_TYPE)
    
    if gauge.connect():
        try:
            if DEBUG_MODE: print("\n데이터 수신 대기 중... (Ctrl+C를 눌러 종료)")
            while True:
                # request_data 호출 결과가 float 또는 None으로 반환됩니다.
                measurement = gauge.request_data() 
                if measurement is not None:
                    # 실제 측정값 사용 예시
                    if DEBUG_MODE: print(f"현재 측정값: {measurement}")
                    pass
                    
                time.sleep(1) # 1초 간격으로 반복
                
        except KeyboardInterrupt:
            if DEBUG_MODE: print("\n사용자에 의해 프로그램이 종료되었습니다.")
        finally:
            gauge.disconnect()
            
    # 잘못된 타입 입력 시 (예시)
    # gauge_err = MitutoyoGauge(3) # 이 경우 오류 로그를 남기고 종료됨

if __name__ == '__main__':
    main()