import paho.mqtt.client as mqtt
import json
import time
import os
import random
import threading
from uuid import uuid4
from datetime import datetime

class MqttLogicDummy:
    """
    UI 테스트를 위한 MQTT 'logic' 역할의 더미(Dummy) 클래스.
    - 실제 로직이나 Blackboard 없이 MQTT 프로토콜에 맞춰 응답하고 상태를 발행합니다.
    - UI가 'logic'의 동작을 시뮬레이션하고 테스트할 수 있도록 돕습니다.
    """
    def __init__(self, rule_path="mqtt_rule.json", host="127.0.0.1", port=1883):
        self.role = 'logic'
        self.host = host
        self.port = port
        self.rules = self._load_rules(rule_path)

        # 1. 클라이언트 초기화
        self.client = mqtt.Client(client_id=f"{self.role}_dummy_{uuid4().hex[:6]}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # 2. 상태 관리 변수
        self.running = True
        self.connected = False
        self.status_thread = None

        # 3. 더미 데이터 상태
        self.di_values = [random.choice([0, 1]) for _ in range(48)]
        self.do_values = [random.choice([0, 1]) for _ in range(32)]
        self.runtime_counter = 0

    def _load_rules(self, path):
        # mqtt_comm.py와 동일한 규칙 로드 로직
        if os.path.exists(path):
            target_path = path
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.basename(path)
            target_path = os.path.join(base_dir, "configs", filename)
            if not os.path.exists(target_path):
                # Fallback to current directory if not in configs
                target_path = filename
                if not os.path.exists(target_path):
                     raise FileNotFoundError(f"Rule file not found: {path} (Checked also: {target_path})")

        with open(target_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print(f"[{self.role.upper()}_DUMMY] 브로커 연결 성공 (Host: {self.host}:{self.port})")
            
            # UI 명령 토픽 구독
            topic = self.rules["topics"]["ui_cmd"]
            res, _ = self.client.subscribe(topic)
            if res == mqtt.MQTT_ERR_SUCCESS:
                print(f"[{self.role.upper()}_DUMMY] 토픽 구독 성공: {topic}")
            else:
                print(f"[{self.role.upper()}_DUMMY] 토픽 구독 실패 (code: {res}): {topic}")

            # 상태 발행 스레드 시작
            if self.status_thread is None or not self.status_thread.is_alive():
                self.status_thread = threading.Thread(target=self._status_publishing_loop, daemon=True)
                self.status_thread.start()
        else:
            print(f"[{self.role.upper()}_DUMMY] 연결 실패: {rc}")
            self.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            header = data.get("header", {})
            payload = data.get("payload", {})
            
            print(f"\n<<< [DUMMY RCV] {msg.topic} | MsgID: {header.get('msg_id')}")
            print(f"    Payload: {payload}")

            # UI 명령에 대한 ACK 응답 전송
            if msg.topic == self.rules["topics"]["ui_cmd"]:
                cmd = payload.get("cmd")
                action = payload.get("action")
                status = "ok"
                reason = f"Dummy command '{cmd}/{action}' accepted."
                self.send_response_ack(header, status=status, reason=reason, data=payload)

        except Exception as e:
            print(f"[DUMMY] 메시지 처리 에러: {e}")

    def _create_frame(self, msg_type, target, msg_id, payload, ack_req=True):
        return {
            "header": {
                "msg_type": msg_type,
                "source": self.role,
                "target": target,
                "timestamp": datetime.now().isoformat(),
                "msg_id": msg_id,
                "ack_required": ack_req
            },
            "payload": payload
        }

    def send_response_ack(self, original_header, status="ok", reason="Success", data=None, error_code=None):
        req_id = original_header.get("msg_id")
        ack_id = f"logic-dummy-ack-{uuid4().hex[:8]}"
        
        ack_payload = {
            "kind": "ack",
            "ack_of": req_id,
            "status": status,
            "reason": reason
        }
        if data:
            ack_payload["data"] = data
        if status == "error" and error_code:
            ack_payload["error_code"] = error_code

        frame = self._create_frame("logic.event", "ui", ack_id, ack_payload, False)
        self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(frame))
        print(f">>> [DUMMY SND ACK] for {req_id} | Status: {status}")

    def _status_publishing_loop(self):
        """주기적으로 더미 상태 정보를 발행하는 루프"""
        while self.running:
            try:
                # 1. DIO Status 발행
                # 몇 개의 값을 랜덤하게 변경하여 변화를 시뮬레이션
                for _ in range(3):
                    di_index_to_flip = random.randint(0, 47)
                    self.di_values[di_index_to_flip] = 1 - self.di_values[di_index_to_flip]
                    do_index_to_flip = random.randint(0, 31)
                    self.do_values[do_index_to_flip] = 1 - self.do_values[do_index_to_flip]

                dio_payload = {
                    "kind": "event", "evt": "system_dio_status",
                    "di_values": self.di_values,
                    "do_values": self.do_values
                }
                self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                    self._create_frame("logic.event", "ui", self.rules["event_ids"]["dio_status"], dio_payload, False)))

                # 2. System Status 발행
                comm_ok = random.choices([0, 1], weights=[0.05, 0.95], k=6)
                system_entire_state = 1 if all(s == 1 for s in comm_ok) else 0
                
                system_status_payload = {
                    "kind": "event", "evt": "system_status",
                    "process": random.choice(["IDLE", "RUNNING", "ERROR"]),
                    "system_entire_states": system_entire_state,
                    "system_state": {
                        "robot": {"state": comm_ok[0], "current_pos": random.randint(1000, 2000), "current_motion": random.randint(0, 100), "program_run": random.randint(0,2), "msg": "OK" if comm_ok[0] else "Connection Failed"},
                        "shimadzu": {"state": comm_ok[1], "msg": "OK" if comm_ok[1] else "Connection Failed"},
                        "remote_io": {"state": comm_ok[2], "msg": "OK" if comm_ok[2] else "Connection Failed"},
                        "qr_reader": {"state": comm_ok[3], "msg": "OK" if comm_ok[3] else "Connection Failed"},
                        "dial_gauge": {"state": comm_ok[4], "msg": "OK" if comm_ok[4] else "Connection Failed"},
                        "binpick": {"state": comm_ok[5], "msg": "OK" if comm_ok[5] else "Connection Failed"}
                    }
                }
                status_msg_id = self.rules["event_ids"].get("system_status", "logic-evt-state-001")
                self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                    self._create_frame("logic.event", "ui", status_msg_id, system_status_payload, False)))

                # 3. Process Status 발행
                self.runtime_counter += 1
                process_status_payload = {
                    "kind": "event", "evt": "process_status",
                    "batch_info": {"batch_id": "DUMMY_BATCH_001", "total_count": 20, "current_count": random.randint(1, 20)},
                    "runtime": str(datetime.fromtimestamp(self.runtime_counter).strftime('%H:%M:%S')),
                    "current_process_tray_info": {"tray_id": "TRAY_A", "slot_id": random.randint(1, 10)},
                    "system_status": "Running",
                    "tester_status": "Waiting for specimen",
                    "robot_status": "Moving to pickup",
                    "thickness_measurement": {"value": round(random.uniform(0.5, 2.5), 3), "status": "Measured"},
                    "aligner_status": "Aligning"
                }
                process_status_msg_id = self.rules["event_ids"].get("process_status", "logic-evt-proc-status-001")
                self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                    self._create_frame("logic.event", "ui", process_status_msg_id, process_status_payload, False)))
                
            except Exception as e:
                print(f"\n[DUMMY] 상태 발행 루프 에러: {e}")

            time.sleep(1) # 1초마다 상태 발행

    def run(self):
        """MQTT 통신 시작"""
        try:
            print(f"[{self.role.upper()}_DUMMY] 브로커에 연결을 시도합니다...")
            self.client.connect(self.host, self.port, 60)
            self.client.loop_forever(retry_first_connection=True)
        except Exception as e:
            print(f"[{self.role.upper()}_DUMMY] MQTT 런타임 에러: {e}")
        finally:
            print(f"[{self.role.upper()}_DUMMY] MQTT 루프가 종료되었습니다.")

    def stop(self):
        """MQTT 통신 종료"""
        print(f"\n[{self.role.upper()}_DUMMY] 통신을 종료합니다.")
        self.running = False
        if self.status_thread and self.status_thread.is_alive():
            self.status_thread.join(timeout=1)
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    # 이 스크립트는 'projects/shimadzu_logic/' 폴더에 위치해야 합니다.
    # 'mqtt_rule.json' 파일은 'projects/shimadzu_logic/configs/' 폴더에 있어야 합니다.
    rule_file_path = os.path.join(os.path.dirname(__file__), "configs", "mqtt_rule.json")
    
    try:
        dummy_logic = MqttLogicDummy(rule_path=rule_file_path)
        dummy_logic.run()
    except KeyboardInterrupt:
        dummy_logic.stop()
    except FileNotFoundError:
        print(f"오류: 규칙 파일({rule_file_path})을 찾을 수 없습니다.")
        print("UI 테스트를 위해서는 실제 프로젝트의 'mqtt_rule.json' 파일이 필요합니다.")
