import paho.mqtt.client as mqtt
import json
import time
import random
from uuid import uuid4

# ==============================================================================
# 1. 설정 및 상수 정의
# ==============================================================================

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
TOPIC_UI_CMD = "/ui/cmd"          # UI -> Logic 명령 (발행)
TOPIC_LOGIC_EVT = "/logic/evt"    # Logic -> UI 이벤트/ACK (구독)

# Action 이름과 Msg ID 시퀀스 번호 매핑 (문서에 정의된 규칙을 따름)
# 실제 UI에서는 이 매핑을 사용하여 명령 ID를 생성합니다.
ACTION_SEQUENCES = {
    "start": 1, "stop": 2, "step_stop": 3, "pause": 4, 
    "resume": 5, "reset": 6, "go_home": 7,
    "do_control": 1, # Manual command sequence starts from 1
}

# ==============================================================================
# 2. MQTT UI 통신 클래스
# ==============================================================================

class MqttCommUi:
    """
    UI 애플리케이션에서 Logic(NRMK Comm)으로 명령을 전송하고
    ACK 및 시스템 이벤트를 수신하기 위한 MQTT 통신 클래스입니다.
    """
    def __init__(self, host=MQTT_HOST, port=MQTT_PORT, client_id="UiClient"):
        self.host = host
        self.port = port
        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        self.tensile_cmd_counter = 0 
        self.manual_cmd_counter = 0
        self.binpick_cmd_counter = 0

    def _on_connect(self, client, userdata, flags, rc):
        """브로커 연결 시 호출되는 콜백 함수"""
        if rc == 0:
            print(f"→ [INFO] MQTT 연결 성공. 토픽 구독 시작: {TOPIC_LOGIC_EVT}")
            # Logic에서 오는 ACK/이벤트 수신 토픽 구독
            client.subscribe(TOPIC_LOGIC_EVT) 
        else:
            print(f"→ [ERROR] MQTT 연결 실패: 반환 코드 {rc}")

    def _on_message(self, client, userdata, msg):
        """구독한 토픽에서 메시지가 도착했을 때 호출되는 함수 (ACK/이벤트 수신)"""
        try:
            message = json.loads(msg.payload.decode('utf-8'))
            header = message.get("header", {})
            payload = message.get("payload", {})
            
            # 여기서 UI의 상태 업데이트 로직을 호출해야 합니다.
            print(f"\n<<< [RCV ACK/EVENT] {msg.topic} <<<")
            print(f"    상태: {payload.get('status', payload.get('evt', 'N/A'))}")
            print(f"    Reason: {payload.get('reason', 'N/A')}")
            print(f"    ACK_OF ID: {payload.get('ack_of', 'N/A')}")
            # UI에 이벤트를 전달하는 외부 함수 (예: 콜백)를 호출해야 함.
            
        except json.JSONDecodeError:
            print(f"→ [ERROR] JSON 디코딩 오류: {msg.payload.decode('utf-8')}")
        except Exception as e:
            print(f"→ [ERROR] 메시지 처리 중 오류 발생: {e}")
            
    def connect_and_loop(self):
        """MQTT 연결을 시작하고 백그라운드에서 메시지를 수신합니다."""
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            print("UI 클라이언트 루프 시작.")
        except ConnectionRefusedError:
            print(f"!!! [CRITICAL] {self.host}:{self.port}에 MQTT 브로커가 실행 중인지 확인하십시오. !!!")
        except Exception as e:
            print(f"MQTT 연결 중 알 수 없는 오류 발생: {e}")

    def disconnect(self):
        """MQTT 연결을 종료합니다."""
        self.client.loop_stop()
        self.client.disconnect()
        print("UI 클라이언트 연결 종료.")


    # ==========================================================================
    # 3. 명령 발행 함수
    # ==========================================================================
    
    def _generate_msg_id(self, cmd_type, action):
        """명령 타입에 따라 적절한 Msg ID를 생성하고 카운터를 업데이트합니다."""
        
        if cmd_type == "tensile_control":
            self.tensile_cmd_counter += 1
            counter = self.tensile_cmd_counter
            cmd_id_base = "ui-tensile-cmd"
        elif cmd_type == "system_control":
            self.manual_cmd_counter += 1
            counter = self.manual_cmd_counter
            cmd_id_base = "ui-manual-cmd"
        elif cmd_type == "binpick_control":
            self.binpick_cmd_counter += 1
            counter = self.binpick_cmd_counter
            cmd_id_base = "ui-binpick-cmd"
        else:
            # 기본 처리
            counter = int(time.time() * 1000) % 10000 
            cmd_id_base = "ui-generic-cmd"
            
        return f"{cmd_id_base}-{counter:03d}"

    def publish_command(self, cmd_type, action, payload_data=None):
        """
        일반적인 명령 발행 메서드.
        :param cmd_type: "tensile_control", "system_control", "binpick_control" 등
        :param action: "start", "stop", "do_control" 등
        :param payload_data: 추가 데이터 (batch_id, params 등)
        """
        if payload_data is None:
            payload_data = {}
            
        msg_id = self._generate_msg_id(cmd_type, action)
        
        msg = {
            "header": {
                "msg_type": "ui.command",
                "source": "ui",
                "target": "logic",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "msg_id": msg_id,
                "ack_required": True
            },
            "payload": {
                "kind": "command",
                "cmd": cmd_type,
                "action": action,
            }
        }
        
        msg["payload"].update(payload_data)

        print(f"\n>>> [CMD PUB] {cmd_type}/{action} 전송 (ID: {msg_id}) >>>")
        self.client.publish(TOPIC_UI_CMD, json.dumps(msg))
        return msg_id


    # ==========================================================================
    # 4. UI 버튼 클릭 대응 (편의 메서드)
    # ==========================================================================

    def send_tensile_command(self, action, batch_id):
        """인장기 자동 제어 명령 (UI 버튼: 시작/중지/리셋 등)"""
        payload_data = {"batch_id": batch_id}
        return self.publish_command("tensile_control", action, payload_data)
        
    def send_manual_do_control(self, do_values):
        """시스템 수동 제어 명령 (UI 버튼: DO 제어)"""
        payload_data = {"params": {"do_values": do_values}}
        return self.publish_command("system_control", "do_control", payload_data)

    def send_binpick_command(self, action, job_id):
        """Bin Picking 제어 명령 (UI 버튼: Bin Picking 시작/중지 등)"""
        payload_data = {"job_id": job_id}
        return self.publish_command("binpick_control", action, payload_data)


# ==============================================================================
# 메인 실행 블록 (테스트 예시)
# ==============================================================================

if __name__ == "__main__":
    # 이 부분은 실제 UI 환경이 아닌 테스트를 위한 단순 실행 코드입니다.
    
    ui_comm = MqttCommUi()
    ui_comm.connect_and_loop()
    
    print("\n테스트 모드 시작. 5초 후 start 명령 전송.")
    time.sleep(5)
    
    # 1. 인장기 시작 명령 시뮬레이션
    command_id = ui_comm.send_tensile_command("start", "BATCH-001")
    print(f"전송된 START 명령 ID: {command_id}")
    time.sleep(2)
    
    # 2. 수동 DO 제어 명령 시뮬레이션 (랜덤 DO 값)
    do_test_values = [random.randint(0, 1) for _ in range(16)]
    command_id = ui_comm.send_manual_do_control(do_test_values)
    print(f"전송된 DO 명령 ID: {command_id}")
    time.sleep(2)
    
    # 3. Bin Picking 명령 시뮬레이션
    command_id = ui_comm.send_binpick_command("go_home", "JOB-BP-001")
    print(f"전송된 BINPICK 명령 ID: {command_id}")
    time.sleep(5)

    ui_comm.disconnect()
    print("UI 통신 테스트 종료.")