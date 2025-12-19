# Autonics APIO-C-EI와의 EtherNet/IP (EIP) 통신을 위한 Python 코드 (pycomm3 라이브러리 사용)
# 이 코드는 클래스 기반으로 구조화되어 사용 편의성을 높였습니다.

# 이 코드를 실행하기 전에 다음 명령어로 pycomm3 라이브러리를 설치해야 합니다:
# pip install pycomm3

from pycomm3 import CIPDriver
import time
import struct
import json
import os
import sys
import threading

DEBUG_MODE = True

# =========================== 모듈 상수 정의 ===========================
# 설정 파일 경로
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'configs', 'remote_io.json')

# --- APIO-C-EI/ARIO-S1-DI16N/ARIO-S1-DO16N 구성을 위한 Assembly Instance ID ---
# (사용자 확인: DO 슬라이스가 Instance 100, DI 슬라이스가 Instance 101)
# DI16N (디지털 입력) 인스턴스 ID (읽기용)
INPUT_ASSEMBLY_INSTANCE = 101
# DO16N (디지털 출력) 인스턴스 ID (쓰기용/읽기용)
OUTPUT_ASSEMBLY_INSTANCE = 100

# EtherNet/IP 통신 서비스 코드 (Explicit Messaging)
SERVICE_READ_DATA = 0x0E  # Get_Attribute_Single Service (단일 속성 읽기)
SERVICE_WRITE_DATA = 0x10 # Set_Attribute_Single Service (단일 속성 쓰기)

# Assembly Object 속성 (현재 읽기/버퍼 쓰기에 성공한 경로)
CIP_CLASS_ASSEMBLY = 0x04    # Class ID for Assembly Object
CIP_ATTRIBUTE_DATA = 0x03   # Attribute ID for Data (data in the Assembly)
# ===================================================================

def load_config(file_path):
    """
    지정된 JSON 설정 파일에서 IP 주소를 읽어옵니다.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('remote_io_ip')
    except FileNotFoundError:
        if DEBUG_MODE: print(f"❌ 오류: 설정 파일 '{file_path}'를 찾을 수 없습니다.")
        if DEBUG_MODE: print("   'configs' 폴더 내에 'remote_io.json' 파일이 있는지 확인하세요.")
        return None
    except json.JSONDecodeError:
        if DEBUG_MODE: print(f"❌ 오류: 설정 파일 '{file_path}'의 JSON 형식이 잘못되었습니다.")
        return None
    except Exception as e:
        if DEBUG_MODE: print(f"❌ 설정 파일 로드 중 알 수 없는 오류 발생: {e}")
        return None

class AutonicsEIPClient:
    """
    Autonics APIO-C-EI 장치와 EtherNet/IP Explicit Messaging을 통해 통신하는 클라이언트 클래스입니다.
    CIPDriver의 연결 관리를 위해 Context Manager(with 구문)로 사용하도록 설계되었습니다.
    """
    def __init__(self):
        """
        IP 주소를 받아 CIPDriver 인스턴스를 초기화합니다.
        """
        ip_address = load_config(CONFIG_FILE_PATH)
        self.ip_address = ip_address
        self.apioc = None
        
        # 현재 IO 상태를 저장할 리스트 변수 초기화
        self.current_di_value = []
        self.current_do_value = []

        # 스레드 제어를 위한 변수
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # 초기화 시 바로 연결 시도 및 초기 데이터 읽기
        if self.ip_address:
            try:
                self.connect()
                self.current_di_value = self.read_input_data()
                self.current_do_value = self.read_output_data()
            except Exception as e:
                if DEBUG_MODE: print(f"⚠️ 초기화 중 연결 또는 데이터 읽기 실패: {e}")
    
    def connect(self):
        """
        APIO-C-EI 장치에 연결을 시도합니다.
        """
        if self.apioc and self.apioc.connected:
            # print("이미 연결되어 있습니다.")
            return True

        if DEBUG_MODE: print(f"APIO-C-EI ({self.ip_address})에 연결 시도...")
        try:
            # CIPDriver 인스턴스 생성 및 연결 시도
            self.apioc = CIPDriver(self.ip_address)
            self.apioc.open()

            if not self.apioc.connected:
                raise ConnectionError("CIPDriver 연결 실패")

            if DEBUG_MODE: print("✅ 연결 성공.")
            return True

        except Exception as e:
            if DEBUG_MODE: print(f"❌ 연결 실패. IP 주소 및 네트워크 설정을 확인하세요. ({e})")
            raise

    def disconnect(self):
        """
        APIO-C-EI 장치와의 연결을 해제합니다.
        """
        self.stop_monitoring()  # 연결 해제 시 모니터링 스레드도 중지
        if self.apioc and self.apioc.connected:
            self.apioc.close()
            # print("연결 해제됨.")
        return False # 발생한 예외가 있다면 다시 throw합니다.

    def _call_generic_message(self, service, class_id, instance_id, attribute, request_data=None, verbose=True):
        """
        pycomm3의 generic_message를 사용하여 Explicit Messaging을 수행하는 내부 메서드입니다.
        """
        if not self.apioc or not self.apioc.connected:
            raise ConnectionError("통신을 위해 CIPDriver가 연결되어 있지 않습니다.")
            
        try:
            # generic_message 호출에 필요한 인자들을 딕셔너리로 구성합니다.
            kwargs = {
                'service': service,
                'class_code': class_id, 
                'instance': instance_id,
                'attribute': attribute,
            }
            
            if request_data is not None:
                kwargs['request_data'] = request_data
            
            # --- 추가된 코드: 보내는 메시지 정보 출력 ---
            if verbose:
                if DEBUG_MODE: print(f"   -> [요청 메시지 인자] Service: {hex(service)}, Class: {hex(class_id)}, Instance: {instance_id}, Attribute: {hex(attribute)}, Data: {request_data}")
            # ---------------------------------------------
                
            response = self.apioc.generic_message(**kwargs)
            return response
        except AttributeError:
            # generic_message가 없는 경우
            raise AttributeError(
                "CIPDriver 객체에 'generic_message' 메소드가 없습니다. "
                "pycomm3 라이브러리 업데이트가 필요합니다. ('pip install --upgrade pycomm3')"
            )
        except Exception as e:
            raise e

    def _parse_to_bit_list(self, status_value, bit_count=16):
        """
        10진수 상태 값을 지정된 비트 수의 배열 ([1, 0, 0, ...])로 변환합니다.
        """
        if status_value is None:
            return None
        # bin()으로 2진 문자열을 얻고, '0b'를 제거한 후, 16비트 길이로 0을 채웁니다.
        binary_string = bin(status_value)[2:].zfill(bit_count)
        # 문자열을 역순으로 리스트에 저장합니다. (비트 0이 리스트의 첫 번째 요소가 되도록)
        # ARIO 장치는 리틀 엔디안이므로, LSB(Bit 0)가 먼저 오도록 역순으로 저장
        bit_list = [int(bit) for bit in reversed(binary_string)]
        return bit_list

    def _read_data_and_print(self, instance_id, instance_name, verbose=True):
        """
        데이터를 읽고 결과를 파싱하여 출력하는 헬퍼 함수
        """
        if verbose:
            if DEBUG_MODE: print(f"{instance_name} (Instance: {instance_id}) 읽기 시도 (Service {hex(SERVICE_READ_DATA)} - Get_Attribute_Single)...")
        
        try:
            # 읽기 요청
            response = self._call_generic_message(
                service=SERVICE_READ_DATA,
                class_id=CIP_CLASS_ASSEMBLY,
                instance_id=instance_id,
                attribute=CIP_ATTRIBUTE_DATA,
                verbose=verbose
            )
            
            if response.error:
                if verbose:
                    if DEBUG_MODE: print(f"⚠️ {instance_name} 읽기 오류: {response.error}")
                return None
            else:
                raw_data = response.value
                if verbose:
                    if DEBUG_MODE: print(f"✅ {instance_name} Raw 값 (bytes): {raw_data}")
                
                # 데이터 해석 (가변 길이 데이터)
                if isinstance(raw_data, bytes):
                    if verbose:
                        if DEBUG_MODE: print(f"   -> 수신된 데이터 크기: {len(raw_data)} 바이트")
                    if len(raw_data) > 0:
                        # little-endian으로 바이트 전체를 부호 없는 정수로 변환
                        status_int = int.from_bytes(raw_data, byteorder='little')
                        bit_list = self._parse_to_bit_list(status_int, bit_count=len(raw_data)*8)

                        if verbose:
                            if DEBUG_MODE: print(f"   -> {instance_name} 상태 (10진수): {status_int}")
                            if DEBUG_MODE: print(f"   -> {instance_name} 상태 (비트 리스트, LSB부터): {bit_list}")
                            
                            if DEBUG_MODE: print(f"   -> {instance_name} 채널별 상태:")
                            total_bits = len(bit_list)
                            
                            # 8행으로 고정하여 출력 (1, 9, 17, 25... 가로로 나열)
                            rows = 8
                            cols = (total_bits + rows - 1) // rows

                            for row in range(rows):
                                line_items = []
                                for col in range(cols):
                                    idx = col * rows + row
                                    if idx < total_bits:
                                        val = bit_list[idx]
                                        # 값이 1이면 강조 (●)
                                        val_str = f"{val}●" if val else f"{val} "
                                        line_items.append(f"{idx+1:2d}: {val_str}")
                                
                                if DEBUG_MODE: print("      " + "   ".join(line_items))
                        
                        # 상태 정수 값과 비트 리스트를 모두 반환
                        return status_int, bit_list
                    else:
                        if verbose:
                            if DEBUG_MODE: print(f"   -> 오류: 수신된 데이터가 없습니다. 인스턴스 ID({instance_id}) 확인 필요.")
                        return None

        except Exception as e:
            if verbose:
                if DEBUG_MODE: print(f"❌ {instance_name} 통신 중 예외 발생: {e}")
        
        return None # 실패 시 None 반환

    def read_input_data(self, verbose=True):
        """
        입력 데이터 (Instance: 101)를 읽어와 DI 상태를 출력하고 비트 리스트를 반환합니다.
        """
        result = self._read_data_and_print(INPUT_ASSEMBLY_INSTANCE, "입력 데이터 (DI)", verbose=verbose)
        if result is None:
            return []
            
        status_int, bit_list = result
        if verbose:
            if DEBUG_MODE: print("-" * 50)
        return bit_list

    def read_output_data(self, verbose=True):
        """
        출력 데이터 (Instance: 100)를 읽어와 DO 상태를 출력하고 비트 리스트를 반환합니다.
        """
        result = self._read_data_and_print(OUTPUT_ASSEMBLY_INSTANCE, "출력 데이터 (DO)", verbose=verbose)
        if result is None:
            return []

        status_int, bit_list = result
        if verbose:
            if DEBUG_MODE: print("-" * 50)
        return bit_list

    def start_monitoring(self, interval=0.1):
        """
        IO 상태를 주기적으로 읽어오는 스레드를 시작합니다.
        :param interval: 읽기 주기 (초 단위, 기본값 0.1초)
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_io, args=(interval,), daemon=True)
        self._monitor_thread.start()
        if DEBUG_MODE: print(f"✅ IO 모니터링 스레드 시작 (주기: {interval}초)")

    def stop_monitoring(self):
        """
        IO 모니터링 스레드를 중지합니다.
        """
        if self._monitor_thread is not None:
            self._stop_event.set()
            self._monitor_thread.join()
            self._monitor_thread = None
            if DEBUG_MODE: print("✅ IO 모니터링 스레드 중지됨")

    def _monitor_io(self, interval):
        """
        주기적으로 DI/DO 데이터를 읽어 내부 변수를 업데이트하는 스레드 함수입니다.
        """
        while not self._stop_event.is_set():
            try:
                if self.apioc and self.apioc.connected:
                    # verbose=False로 호출하여 로그 출력을 억제하고 값만 업데이트
                    di_data = self.read_input_data(verbose=False)
                    do_data = self.read_output_data(verbose=False)
                    
                    # 읽어온 데이터로 내부 변수 업데이트
                    # (통신 실패 시 빈 리스트가 반환될 수 있음)
                    self.current_di_value = di_data
                    self.current_do_value = do_data
            except Exception as e:
                if DEBUG_MODE: print(f"⚠️ 모니터링 스레드 오류: {e}")
            
            time.sleep(interval)
    
    def DO_Control(self, address: int, value: int):
        """
        특정 주소(address)의 DO를 제어합니다.
        현재 DO 상태를 읽어온 후, 해당 주소의 비트만 변경하여 다시 씁니다.
        
        :param address: 제어할 DO 비트 인덱스 (0 ~ 31)
        :param value: 설정할 값 (0 또는 1)
        """
        # 1. 현재 DO 상태 최신화 (안전장치)
        current_status = self.read_output_data()
        if current_status:
            self.current_do_value = current_status
        
        # 리스트 길이가 부족할 경우(읽기 실패 등)를 대비해 0으로 채움 (32개)
        if len(self.current_do_value) < 32:
            self.current_do_value = self.current_do_value + [0] * (32 - len(self.current_do_value))
            self.current_do_value = self.current_do_value[:32]

        # 2. 유효성 검사
        if not (0 <= address < 32):
            if DEBUG_MODE: print(f"❌ 오류: DO 주소({address})는 0~31 사이여야 합니다.")
            return

        # 3. 해당 비트 값 변경
        self.current_do_value[address] = 1 if value else 0
        
        # 4. 변경된 전체 리스트로 출력 쓰기
        if DEBUG_MODE: print(f"DO 제어 요청: Address {address} -> {value}")
        self.write_output_data(self.current_do_value)

    def write_output_data(self, input_bits: list, writing_class=CIP_CLASS_ASSEMBLY, writing_instance=OUTPUT_ASSEMBLY_INSTANCE, writing_attribute=CIP_ATTRIBUTE_DATA, writing_service=SERVICE_WRITE_DATA):
        """
        [DO(디지털 출력) 쓰기 전용 함수]
        32개의 비트 상태를 담은 리스트를 입력받아 DO 값을 쓰고, 즉시 다시 읽어 쓰기 성공 여부를 확인합니다.
        
        매개변수:
        input_bits (list): 32개의 정수 (0 또는 1)로 구성된 리스트. [DO0, DO1, ..., DO31] 순서.
        """
        if len(input_bits) != 32 or any(bit not in [0, 1] for bit in input_bits):
            if DEBUG_MODE: print("❌ 오류: input_bits는 길이가 32인 0 또는 1 값의 리스트여야 합니다.")
            return

        # 1. 비트 리스트를 10진수 정수로 변환 (LSB(input_bits[0])가 2^0 이 되도록)
        value_to_write = 0
        for i, bit in enumerate(input_bits):
            if bit == 1:
                value_to_write |= (1 << i)
        
        # 값을 바이트 형식으로 변환 (DO 32개 = 4바이트 DWORD 가정)
        try:
            value_bytes = value_to_write.to_bytes(4, byteorder='little')
        except Exception as e:
            if DEBUG_MODE: print(f"❌ 출력 값 변환 오류: {e}")
            return
            
        if DEBUG_MODE: print(f"출력 데이터 (Instance: {OUTPUT_ASSEMBLY_INSTANCE})에 값 {value_to_write} (bytes: {value_bytes}) 쓰기 시도 (Service {hex(writing_service)} - Set_Attribute_Single)...")
        if DEBUG_MODE: print(f"   -> 쓰기 비트 리스트: {input_bits}")
        
        # --- ⚠️ 중요: EDS 분석 결과 및 다음 시도 안내 ---
        if DEBUG_MODE: print("   -> (매뉴얼 확인: 현재 Assembly Object 쓰기는 '통신 버퍼'만 변경하며, 실제 DO 제어는 다른 CIP 경로가 필요할 가능성이 높습니다.)")
        
        try:
            # 1. 쓰기 요청
            self._call_generic_message(
                service=writing_service,
                class_id=writing_class, 
                instance_id=writing_instance, 
                attribute=writing_attribute, 
                request_data=value_bytes # 쓸 데이터
            )
            
            if DEBUG_MODE: print("✅ 출력 데이터 쓰기 요청 완료. (장치 응답은 출력하지 않습니다.)")

            # 2. 쓰기 직후 DO 상태를 다시 읽어 확인
            if DEBUG_MODE: print("\n**[쓰기 후 즉시 DO 상태 확인]**")
            new_status_int, new_bit_list = self._read_data_and_print(OUTPUT_ASSEMBLY_INSTANCE, "출력 데이터 (DO)")

            if new_status_int == value_to_write:
                if DEBUG_MODE: print(f"✅ 쓰기 확인 성공! DO 상태가 {value_to_write}로 변경되었습니다. (통신 버퍼 변경 확인)")
                if DEBUG_MODE: print("   ⚠️ **주의:** 통신 버퍼는 변경되었으나, 실제 DO가 바뀌지 않는다면 **'DAQMaster'** 소프트웨어에서 **Output Control Mode (출력 제어 모드)**를 확인/변경하거나, **특정 CIP 제어 객체 경로**를 찾아야 합니다.")
            elif new_status_int is not None:
                if DEBUG_MODE: print(f"❌ 쓰기 확인 실패! 요청 값({value_to_write})과 현재 DO 상태({new_status_int})가 다릅니다.")
            else:
                if DEBUG_MODE: print("⚠️ 쓰기 후 DO 상태를 읽을 수 없습니다.")

        except Exception as e:
            if DEBUG_MODE: print(f"❌ 출력 데이터 통신 중 예외 발생: {e}")
        finally:
            if DEBUG_MODE: print("-" * 50)


if __name__ == '__main__':
    APIO_C_EI_IP = load_config(CONFIG_FILE_PATH)
    
    if APIO_C_EI_IP:
        try:
            client = AutonicsEIPClient()
            client.connect() # 명시적으로 연결
            
            # 백그라운드 모니터링 시작 (필요시 주석 해제)
            # client.start_monitoring(interval=0.5)

            if DEBUG_MODE: print("\n" + "=" * 50)
            if DEBUG_MODE: print("🎮 CLI 제어 모드 시작")
            if DEBUG_MODE: print("명령어 목록:")
            if DEBUG_MODE: print("  'get' : 현재 DI/DO 데이터 읽기")
            if DEBUG_MODE: print("  's'   : DO 단일 비트 제어 (Address 입력)")
            if DEBUG_MODE: print("  'q'   : 프로그램 종료")
            if DEBUG_MODE: print("=" * 50)

            client.write_output_data([0] * 32)
            
            try:
                while True:
                    cmd = input("\n명령 입력 (get/s/q) >> ").strip().lower()

                    if cmd == 'q':
                        if DEBUG_MODE: print("프로그램을 종료합니다.")
                        break
                    
                    elif cmd == 'get':
                        if DEBUG_MODE: print("\n--- [Input Data (DI)] ---")
                        client.read_input_data(verbose=True)
                        if DEBUG_MODE: print("\n--- [Output Data (DO)] ---")
                        client.read_output_data(verbose=True)
                    
                    elif cmd == 's':
                        try:
                            addr_input = input("  👉 제어할 DO Address (1~32): ")
                            if not addr_input.isdigit():
                                if DEBUG_MODE: print("  ❌ 숫자를 입력하세요.")
                                continue
                            address = int(addr_input) - 1

                            val_input = input(f"  👉 DO {addr_input}번 설정 값 (1:ON, 0:OFF): ")
                            if val_input not in ['0', '1']:
                                if DEBUG_MODE: print("  ❌ 0 또는 1을 입력하세요.")
                                continue
                            value = int(val_input)

                            client.DO_Control(address, value)
                        except Exception as e:
                            if DEBUG_MODE: print(f"  ❌ 입력 처리 중 오류: {e}")
                    
                    else:
                        if DEBUG_MODE: print("❌ 알 수 없는 명령어입니다. 'get', 's', 'q' 중 하나를 입력하세요.")

            except ConnectionError as e:
                if DEBUG_MODE: print(f"❌ 연결 오류 발생: {e}")
            except Exception as e:
                if DEBUG_MODE: print(f"❌ 프로그램 실행 중 예상치 못한 오류 발생: {e}")
            finally:
                client.disconnect() # 프로그램 종료 시 연결 해제

        except Exception as e:
            if DEBUG_MODE: print(f"❌ 초기 연결 또는 프로그램 실행 중 오류 발생: {e}")
    else:
        if DEBUG_MODE: print("IP 주소를 로드할 수 없어 프로그램을 종료합니다.")