import socket
import json
import time
import threading

class VisionClient:
    """
    포스텍 비전 시스템(VISION)과 통신하기 위한 TCP/IP 클라이언트 클래스
    """
    def __init__(self, ip, port=5003, timeout=10.0):
        """
        초기화 메서드
        :param ip: 비전 시스템의 IP 주소
        :param port: 포트 번호 (기본값 5000)
        :param timeout: 소켓 통신 타임아웃
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.lock = threading.Lock()
        self.recv_buffer = b""

    def connect(self):
        """서버에 연결 시도"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))
            print(f"Connected to Vision System at {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection Error: {e}")
            self.sock = None
            return False

    def disconnect(self):
        """연결 종료"""
        if self.sock:
            self.sock.close()
            self.sock = None
            self.recv_buffer = b""
            print("Disconnected from Vision System")

    def send_data(self, message_dict):
        """데이터 전송 (sendall)"""
        if not self.sock:
            print("Not connected to server.")
            return False

        with self.lock:
            try:
                # JSON 직렬화 및 전송
                message_str = json.dumps(message_dict, separators=(",", ":")) + "\n"
                self.sock.sendall(message_str.encode('utf-8'))
                return True
            except Exception as e:
                print(f"Send Error: {e}")
                self.disconnect()
                return False

    def receive_data(self):
        """데이터 수신 (recv) - 버퍼링 처리"""
        if not self.sock:
            return None

        try:
            # 버퍼에 이미 완성된 라인이 있는지 확인
            if b'\n' in self.recv_buffer:
                line, self.recv_buffer = self.recv_buffer.split(b'\n', 1)
                decoded = line.decode('utf-8').strip()
                if not decoded:
                    return None
                return json.loads(decoded)

            # 소켓에서 읽기
            chunk = self.sock.recv(4096)
            if not chunk:
                return None
            
            self.recv_buffer += chunk
            if b'\n' in self.recv_buffer:
                line, self.recv_buffer = self.recv_buffer.split(b'\n', 1)
                decoded = line.decode('utf-8').strip()
                if not decoded:
                    return None
                return json.loads(decoded)

        except socket.timeout:
            pass  # 타임아웃은 정상이므로 무시하고 루프 계속
        except Exception as e:
            print(f"Receive Error: {e}")
        
        return None

    def handshake(self):
        """5. HELLO: 통신 연결 확인"""
        msg = {"type": "HELLO"}
        return self.send_data(msg)

    def check_scene(self, mode="CONTINUOUS"):
        """
        6. CHECK_SCENE: 장면 인식 요청
        :param mode: "SINGLE" 또는 "CONTINUOUS"
        """
        if mode not in ["SINGLE", "CONTINUOUS"]:
            raise ValueError("Mode must be SINGLE or CONTINUOUS")
            
        msg = {"type": "CHECK_SCENE", "mode": mode}
        return self.send_data(msg)

    def stop_scene(self):
        """6.3 STOP_SCENE: 연속 인식 중지 요청"""
        msg = {"type": "STOP_SCENE"}
        return self.send_data(msg)

    def check_grasp(self):
        """8. CHECK_GRASP: 그립 확인 요청"""
        msg = {"type": "CHECK_GRASP"}
        return self.send_data(msg)

# 사용 예시 (Usage Example)
if __name__ == "__main__":
    # 비전 시스템의 IP 주소 입력
    VISION_IP = "192.168.2.16" 
    
    client = VisionClient(ip=VISION_IP)

    if client.connect():
        # 1. Handshake
        if client.handshake():
            print("Handshake Success!")

            # 2. 장면 인식 요청 (SINGLE 모드)
            print("Requesting scene check...")
            scene_result = client.check_scene(mode="SINGLE")
            
            if scene_result:
                status = scene_result.get("status")
                print(f"Scene Status: {status}")
                
                if status == "TASK_EXECUTION":
                    specimens = scene_result.get("specimens", [])
                    for spec in specimens:
                        print(f"Found Specimen ID {spec['id']}: type={spec['sample_type']}, x={spec['location']['x']}, y={spec['location']['y']}")
            
            # 3. 그립 확인
            time.sleep(1) # 시뮬레이션 대기
            print("Checking grasp...")
            grasp_result = client.check_grasp()
            if grasp_result:
                print(f"Grasp Result: {grasp_result.get('status')}")

        client.disconnect()