import paho.mqtt.client as mqtt
import json
import time
import os
import random 
import threading 
from uuid import uuid4
from datetime import datetime
from pkg.utils.logging import Logger
from pkg.fsm.base import *

# ==============================================================================
# [Blackboard] 외부 상태 공유를 위한 글로벌 객체
# ==============================================================================
from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

class MqttComm:
    """
    MQTT 통합 통신 클래스
    - role: 'ui' 또는 'logic'
    - is_dummy: True일 경우 시뮬레이션 모드 (상태 자동 발행 및 응답)
    """
    def __init__(self, role='logic', is_dummy=False, rule_path="mqtt_rule.json", host="127.0.0.1", port=1883, stop_event=None):
        self.role = role.lower()
        self.is_dummy = is_dummy
        self.host = host
        self.port = port
        self.stop_event = stop_event

        # 1. 규칙 로드
        self.rules = self._load_rules(rule_path)
        
        # 2. 클라이언트 초기화
        self.client = mqtt.Client(client_id=f"{self.role}_{uuid4().hex[:6]}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        # 3. 상태 관리 변수
        self.running = True
        self.thread = None
        self.logic_thread = None
        self.status_thread = None
        self.connected = False
        
        # ID 생성을 위한 카운터
        self.counters = {"tensile": 0, "manual": 0, "binpick": 0, "logic_to_bp": 0}

        # 제어 상태 변수 (이전 코드 호환성 유지)
        self.tensile_command = 0
        self.binpick_command = 0
        self.do_control_state = 0
        self.last_command_id = None
        self.last_command_payload = {}

    def _load_rules(self, path):
        # 1. 입력된 경로 그대로 확인
        if os.path.exists(path):
            target_path = path
        else:
            # 2. 파일명만 추출하여 현재 파일(mqtt_comm.py)의 configs 폴더 내에서 재탐색
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.basename(path)
            target_path = os.path.join(base_dir, "configs", filename)
            if not os.path.exists(target_path):
                raise FileNotFoundError(f"Rule file not found: {path} (Checked also: {target_path})")
        
        with open(target_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            Logger.info(f"[{self.role.upper()}] 브로커 연결 성공")
            topics = self.rules["topics"]
            
            if self.role == 'logic':
                for key in ["ui_cmd", "binpick_evt"]:
                    topic = topics[key]
                    res, _ = self.client.subscribe(topic)
                    if res == mqtt.MQTT_ERR_SUCCESS:
                        Logger.info(f"[{self.role.upper()}] 토픽 구독 성공: {topic}")
                    else:
                        Logger.error(f"[{self.role.upper()}] 토픽 구독 실패 (code: {res}): {topic}")

                # 재연결 시 스레드 중복 생성 방지
                if self.logic_thread is None or not self.logic_thread.is_alive():
                    self.logic_thread = threading.Thread(target=self._logic_processing_loop, daemon=True)
                    self.logic_thread.start()
                if self.status_thread is None or not self.status_thread.is_alive():
                    self.status_thread = threading.Thread(target=self._status_publishing_loop, daemon=True)
                    self.status_thread.start()
            elif self.role == 'ui':
                topic = topics["logic_evt"]
                res, _ = self.client.subscribe(topic)
                if res == mqtt.MQTT_ERR_SUCCESS:
                    Logger.info(f"[{self.role.upper()}] 토픽 구독 성공: {topic}")
                else:
                    Logger.error(f"[{self.role.upper()}] 토픽 구독 실패 (code: {res}): {topic}")
        else:
            Logger.info(f"[{self.role.upper()}] 연결 실패: {rc}")
            self.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            Logger.info(f"received message {msg.payload.decode('utf-8')}")
            data = json.loads(msg.payload.decode('utf-8'))
            header = data.get("header", {})
            payload = data.get("payload", {})
            
            # 수신 로그
            Logger.info(f"<<< [{self.role.upper()} RCV] {msg.topic} | MsgID: {header.get('msg_id')}")

            if self.role == 'logic' and msg.topic == self.rules["topics"]["ui_cmd"]:
                self._handle_ui_command(header, payload)
            elif self.role == 'ui' and msg.topic == self.rules["topics"]["logic_evt"]:
                self._handle_logic_event(header, payload)
                
        except Exception as e:
            Logger.info(f"메시지 처리 에러: {e}")

    # ==========================================================================
    # 메시지 생성 및 전송 (Common)
    # ==========================================================================

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

    # ==========================================================================
    # UI 역할 함수 (명령 발행)
    # ==========================================================================

    def send_tensile_cmd(self, action, batch_id):
        self.counters["tensile"] += 1
        msg_id = f"{self.rules['id_prefixes']['tensile']}{self.counters['tensile']:03d}"
        payload = {"kind": "command", "cmd": "tensile_control", "action": action, "batch_id": batch_id}
        frame = self._create_frame("ui.command", "logic", msg_id, payload)
        self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_do_control(self, address, value):
        self.counters["manual"] += 1
        msg_id = f"{self.rules['id_prefixes']['manual']}{self.counters['manual']:03d}"
        payload = {
            "kind": "command", "cmd": "system_control", "action": "do_control",
            "params": {"address": address, "value": value}
        }
        frame = self._create_frame("ui.command", "logic", msg_id, payload)
        self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_binpick_cmd(self, action, job_id):
        self.counters["binpick"] += 1
        prefix = self.rules['id_prefixes'].get(f"binpick_{action}", "ui-binpick-")
        msg_id = f"{prefix}{self.counters['binpick']:03d}"
        payload = {"kind": "command", "cmd": "binpick_control", "action": action, "job_id": job_id}
        frame = self._create_frame("ui.command", "logic", msg_id, payload)
        self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    # ==========================================================================
    # Logic 역할 함수 (ACK 및 상태 보고)
    # ==========================================================================

    def _handle_ui_command(self, header, payload):
        cmd = payload.get("cmd")
        action = payload.get("action")
        self.last_command_id = header.get("msg_id")
        self.last_command_payload = payload

        if cmd == "tensile_control":
            # 가상 제어 상태 업데이트 (logic_processing_loop에서 처리)
            self.tensile_command = 1 # 예시: START
        elif cmd == "binpick_control":
            self.binpick_command = 1
        elif cmd == "system_control" and action == "do_control":
            self.do_control_state = 1

        # 더미 모드일 경우 즉시 자동 ACK
        if self.is_dummy:
            self._send_auto_ack(header, payload)

    def _send_auto_ack(self, header, payload):
        req_id = header.get("msg_id")
        cmd = payload.get("cmd")
        
        ack_id = self.rules["ack_ids"]["standard"]
        if cmd == "system_control":
            ack_id = f"{self.rules['ack_ids']['manual_prefix']}001"
        
        ack_payload = {
            "kind": "ack", "ack_of": req_id, "status": "ok", 
            "reason": "Simulated Success", "data": {}
        }
        frame = self._create_frame("logic.event", "ui", ack_id, ack_payload, False)
        self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(frame))

    def _logic_processing_loop(self):
        """실제 장비 제어 로직 시뮬레이션 루프"""
        while self.running:
            if self.tensile_command != 0:
                Logger.info(f"[LOGIC] 인장기 공정 처리 중...")
                time.sleep(1)
                self.tensile_command = 0
            time.sleep(0.1)

    def _status_publishing_loop(self):
        """주기적 상태 보고 (Section 4 준수)"""
        while self.running:
            # 1. DIO Status (0.5s)
            dio_payload = {
                "kind": "event", "evt": "system_dio_status",
                "di_values": [random.randint(0,1) for _ in range(48)],
                "do_values": [random.randint(0,1) for _ in range(32)]
            }
            self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                self._create_frame("logic.event", "ui", self.rules["event_ids"]["dio_status"], dio_payload, False)))
            
            time.sleep(0.5)

    # ==========================================================================
    # 실행 및 종료
    # ==========================================================================

    def run(self):
        """MQTT 통신을 별도 스레드에서 실행하여 메인 루프가 차단되지 않도록 합니다."""
        Logger.info(f"[{self.role.upper()}] MQTT 통신 스레드를 시작합니다.")
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        # 종료 시그널 감시 스레드 추가
        if self.stop_event is not None:
            self.monitor_thread = threading.Thread(target=self._monitor_termination, daemon=True)
            self.monitor_thread.start()

    def wait_for_connection(self, timeout=5):
        """연결될 때까지 최대 timeout초 동안 대기합니다 (테스트용)"""
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return self.connected

    def _monitor_termination(self):
        """종료 시그널(Event)을 감시하여 시스템을 종료하는 루프"""
        while self.running:
            if self.stop_event.is_set():
                Logger.info(f"[{self.role.upper()}] 외부 종료 시그널 감지. MQTT를 정지합니다.")
                self.stop()
                break
            time.sleep(0.1)

    def _run(self):
        try:
            self.client.connect(self.host, self.port, 60)
            # loop_forever는 내부적으로 재연결을 처리하며 이 스레드를 점유합니다.
            Logger.info(f"[{self.role.upper()}] MQTT loop_forever를 시작합니다. (Host: {self.host}:{self.port})")
            self.client.loop_forever(retry_first_connection=True)
            Logger.info(f"[{self.role.upper()}] MQTT loop_forever가 종료되었습니다.")
        except Exception as e:
            Logger.info(f"[{self.role.upper()}] MQTT 런타임 에러: {e}")

    def stop(self):
        self.running = False
        if self.stop_event and not self.stop_event.is_set():
            self.stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    # 로직 더미 모드로 테스트 실행
    connector = MqttComm(role='logic', is_dummy=True)
    connector.run()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        connector.stop()