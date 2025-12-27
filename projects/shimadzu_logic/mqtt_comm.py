import paho.mqtt.client as mqtt
import json
import time
import os
import random 
import threading 
from uuid import uuid4
from datetime import datetime

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

        self.Logger = None
        self.bb = None
        if self.role == 'logic':
            from pkg.utils.logging import Logger
            from pkg.utils.blackboard import GlobalBlackboard
            from .constants import ProgramControl
            self.Logger = Logger
            self.bb = GlobalBlackboard()
            self.ProgramControl = ProgramControl

        # 1. 규칙 로드
        self.rules = self._load_rules(rule_path)
        
        # 2. 클라이언트 초기화
        self.client = mqtt.Client(client_id=f"{self.role}_{uuid4().hex[:6]}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        # 3. 상태 관리 변수
        self.running = True
        self.thread = None
        self.connected = False
        
        if self.role == 'logic':
            self.logic_thread = None
            self.status_thread = None
            # ID 생성을 위한 카운터
            self.counters = {"tensile": 0, "manual": 0, "binpick": 0, "logic_to_bp": 0}
            # 제어 상태 변수 (이전 코드 호환성 유지)
            self.tensile_command = 0
            self.binpick_command = 0
            self.do_control_state = 0
            self.last_command_id = None
            self.last_command_payload = {}
        elif self.role == 'ui':
            # ID 생성을 위한 카운터 (UI 전용)
            self.counters = {"tensile": 0, "manual": 0, "binpick": 0}

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
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] 브로커 연결 성공")
            topics = self.rules["topics"]
            
            if self.role == 'logic':
                for key in ["ui_cmd", "binpick_evt"]:
                    topic = topics[key]
                    res, _ = self.client.subscribe(topic)
                    if res == mqtt.MQTT_ERR_SUCCESS:
                        if self.Logger: self.Logger.info(f"[{self.role.upper()}] 토픽 구독 성공: {topic}")
                    else:
                        if self.Logger: self.Logger.error(f"[{self.role.upper()}] 토픽 구독 실패 (code: {res}): {topic}")

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
                    if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] 토픽 구독 성공: {topic}")
                else:
                    if self.role == 'logic' and self.Logger: self.Logger.error(f"[{self.role.upper()}] 토픽 구독 실패 (code: {res}): {topic}")
        else:
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] 연결 실패: {rc}")
            self.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            if self.role == 'logic' and self.Logger: self.Logger.info(f"received message {msg.payload.decode('utf-8')}")
            data = json.loads(msg.payload.decode('utf-8'))
            header = data.get("header", {})
            payload = data.get("payload", {})
            
            # 수신 로그
            if self.role == 'logic' and self.Logger: self.Logger.info(f"<<< [{self.role.upper()} RCV] {msg.topic} | MsgID: {header.get('msg_id')}")

            if self.role == 'logic' and msg.topic == self.rules["topics"]["ui_cmd"]:
                self._handle_ui_command(header, payload)
            elif self.role == 'ui' and msg.topic == self.rules["topics"]["logic_evt"]:
                self._handle_logic_event(header, payload)
                
        except Exception as e:
            if self.role == 'logic' and self.Logger: self.Logger.info(f"메시지 처리 에러: {e}")

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
        if self.role == 'ui':
            msg_id = f"{self.rules['id_prefixes']['tensile']}"
            payload = {"kind": "command", "cmd": "tensile_control", "action": action, "batch_id": batch_id}
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_do_control(self, address, value):
        if self.role == 'ui':
            # 카운터를 증가시키는 대신, 입력받은 address를 ID로 사용합니다.
            msg_id = f"{self.rules['id_prefixes']['manual']}"
            payload = {
                "kind": "command", "cmd": "system_control", "action": "do_control",
                "params": {"addr": address, "value": value}
            }
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_binpick_cmd(self, action, job_id):
        if self.role == 'ui':
            prefix = self.rules['id_prefixes'].get(f"binpick_{action}", "ui-binpick-cmd")
            msg_id = f"{prefix}"
            payload = {"kind": "command", "cmd": "binpick_control", "action": action, "job_id": job_id}
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_comm_test(self, device):
        """통신 설정 테스트 명령 전송 (Section 2.4)"""
        if self.role == 'ui':
            msg_id = "ui-commtest-cmd-001"
            payload = {"kind": "command", "cmd": "comm_test", "action": "test", "device": device}
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_recover_cmd(self, action):
        """복구 설정 제어 명령 전송 (Section 2.5)"""
        if self.role == 'ui':
            msg_id = "ui-recover-cmd-001"
            payload = {"kind": "command", "cmd": "recover", "action": action}
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    def send_robot_cmd(self, action, target):
        """로봇 설정 제어 명령 전송 (Section 2.6)"""
        if self.role == 'ui':
            msg_id = "ui-robot-cmd-001"
            payload = {"kind": "command", "cmd": "robot_control", "action": action, "target": target}
            frame = self._create_frame("ui.command", "logic", msg_id, payload)
            self.client.publish(self.rules["topics"]["ui_cmd"], json.dumps(frame))

    # ==========================================================================
    # Logic 역할 함수 (ACK 및 상태 보고)
    # ==========================================================================

    def _handle_ui_command(self, header:dict, payload:dict):
        if self.role == 'logic':
            cmd = payload.get("cmd")
            action = payload.get("action")
            self.last_command_id = header.get("msg_id")
            self.last_command_payload = payload

            if cmd == "tensile_control":
                if hasattr(self, 'ProgramControl') and self.bb:
                    if action == "pause":
                        if self.Logger: self.Logger.info("[LOGIC] Pause command received via MQTT.")
                        self.bb.set("ui/command/program_control", self.ProgramControl.PROG_PAUSE.value)
                    elif action == "resume":
                        if self.Logger: self.Logger.info("[LOGIC] Resume command received via MQTT.")
                        self.bb.set("ui/command/program_control", self.ProgramControl.PROG_RESUME.value)
            elif cmd == "binpick_control":
                self.binpick_command = 1
            elif cmd == "system_control":
                if action == "do_control":
                    data = payload.get("params")
                    # print(f"DO_control data : {data}")
                    if data and self.role == 'logic' and self.bb:
                        self.bb.set("ui/cmd/do_control/data", data)
                        self.bb.set("ui/cmd/do_control/trigger", 1)
            elif cmd == "comm_test":
                if self.role == 'logic' and self.bb:
                    if self.Logger: self.Logger.info(f"[LOGIC] 통신 테스트 요청 수신: {payload.get('device')}")
                    self.bb.set("ui/cmd/comm_test/data", payload)
                    self.bb.set("ui/cmd/comm_test/trigger", 1)
            elif cmd == "recover":
                if self.role == 'logic' and self.bb:
                    if self.Logger: self.Logger.info(f"[LOGIC] 복구 명령 수신: {payload.get('action')}")
                    self.bb.set("ui/cmd/recover/data", payload)
                    self.bb.set("ui/cmd/recover/trigger", 1)
            elif cmd == "robot_control":
                if self.role == 'logic' and self.bb:
                    if self.Logger: self.Logger.info(f"[LOGIC] 로봇 제어 명령 수신: {payload.get('target')} -> {payload.get('action')}")
                    self.bb.set("ui/cmd/robot_control/data", payload)
                    self.bb.set("ui/cmd/robot_control/trigger", 1)
            elif cmd == "conty_program":
                if self.role == 'logic' and self.bb:
                    program_index = payload.get("program_index")
                    if action == "start":
                        if self.Logger: self.Logger.info(f"[LOGIC] Conty Program START command received for index: {program_index}")
                        self.bb.set("indy_command/play_program_index", program_index)
                        self.bb.set("indy_command/play_program_trigger", True)
                    elif action == "stop":
                        if self.Logger: self.Logger.info(f"[LOGIC] Conty Program STOP command received.")
                        self.bb.set("indy_command/stop_program", True)
            elif cmd == "data":
                if self.role == 'logic' and self.bb:
                    if action == "save":
                        if self.Logger: self.Logger.info(f"[LOGIC] 데이터 저장 요청 수신")
                        self.bb.set("ui/cmd/data/save", 1)
                    elif action == "reset":
                        if self.Logger: self.Logger.info(f"[LOGIC] 데이터 리셋 요청 수신")
                        self.bb.set("ui/cmd/data/reset", 1)
                    else:
                        if self.Logger: self.Logger.warn(f"[LOGIC] 알 수 없는 'data' action: {action}")

            # 프로토콜에 따라, UI 명령 수신 시 Logic이 이를 수락했음을 알리는 ACK를 전송합니다.
            # 실제 성공/실패 여부는 각 로직(Strategy)이 처리한 후 별도 이벤트로 전송하거나
            # 이 MqttComm 모듈에 콜백을 등록하여 비동기적으로 전송할 수 있습니다.
            # 여기서는 '수락'의 의미로 'ok' 상태를 즉시 회신합니다.
            status = "ok"
            reason = f"Command '{cmd}/{action}' accepted for processing."
            
            self.send_response_ack(header, status=status, reason=reason, data=payload)

    def send_response_ack(self, original_header, status="ok", reason="Success", data=None, error_code=None):
        """
        요청받은 명령에 대한 ACK 메시지를 전송합니다. (MQTT_Protocol.md v2.x 준수)
        - status: 'ok' 또는 'error'
        - error_code: status가 'error'일 때 상세 원인 코드
        """
        if self.role == 'logic':
            req_id = original_header.get("msg_id")
            ack_id = f"logic-ack-{uuid4().hex[:8]}"
            
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
            if self.Logger: self.Logger.info(f">>> [SND ACK] for {req_id} | Status: {status}")

    def _logic_processing_loop(self):
        """실제 장비 제어 로직 시뮬레이션 루프"""
        if self.role == 'logic':
            while self.running:
                if self.tensile_command != 0:
                    if self.Logger: self.Logger.info(f"[LOGIC] 인장기 공정 처리 중...")
                    time.sleep(1)
                    self.tensile_command = 0
                time.sleep(0.1)

    def _status_publishing_loop(self):
        """주기적 상태 보고 (Section 4 준수)"""
        if self.role == 'logic':
            while self.running:
                try:
                    # 1. DIO Status (0.5s)
                    di_values = self.bb.get("device/remote/input/entire")
                    do_values = self.bb.get("device/remote/output/entire")
                    dio_payload = {
                        "kind": "event", "evt": "system_dio_status",
                        "di_values": di_values if di_values is not None else [],
                        "do_values": do_values if do_values is not None else []
                    }
                    self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                        self._create_frame("logic.event", "ui", self.rules["event_ids"]["dio_status"], dio_payload, False)))
                    
                    # 2. System Status (MQTT_Protocol.md Section 4.2, 5.1 준수)
                    robot_comm_ok = self.bb.get("device/robot/comm_status")
                    shimadzu_comm_ok = self.bb.get("device/shimadzu/comm_status")
                    gauge_comm_ok = self.bb.get("device/gauge/comm_status")
                    rio_comm_ok = self.bb.get("device/remote/comm_status")
                    qr_comm_ok = self.bb.get("device/qr/comm_status")
                    vision_comm_ok = self.bb.get("device/vision/comm_status")
    
                    all_states = [robot_comm_ok, shimadzu_comm_ok, gauge_comm_ok, rio_comm_ok, qr_comm_ok, vision_comm_ok]
                    system_entire_state = 1 if all(s == 1 for s in all_states) else 0
    
                    system_status_payload = {
                        "kind": "event",
                        "evt": "system_status",
                        "process": self.bb.get("logic/fsm/current_process"),
                        "system_entire_states": system_entire_state,
                        "system_state": {
                            "robot": {
                                "conntion_info": "192.168.2.20",
                                "state": 1 if robot_comm_ok else 0,
                                "current_pos": self.bb.get("int_var/robot/position/val"),
                                "current_motion": self.bb.get("int_var/cmd/val"),
                                "recover_motion": self.bb.get("robot/recover/motion/cmd"),
                                "direct_teaching_mode": self.bb.get("robot/dt/mode"),
                                "gripper_state": self.bb.get("gripper/is_hold"),
                                "msg": "OK" if robot_comm_ok else "Connection Failed"
                            },
                            "shimadzu": {
                                "conntion_info": "192.168.2.100",
                                "state": 1 if shimadzu_comm_ok else 0,
                                "msg": "OK" if shimadzu_comm_ok else "Connection Failed"
                            },
                            "remote_io": {
                                "conntion_info": "192.168.2.40",
                                "state": 1 if rio_comm_ok else 0,
                                "msg": "OK" if rio_comm_ok else "Connection Failed"
                            },
                            "qr_reader": {
                                "conntion_info": "192.168.2.41",
                                "state": 1 if qr_comm_ok else 0,
                                "msg": "OK" if qr_comm_ok else "Connection Failed"
                            },
                            "dial_gauge": {
                                "conntion_info": "COM5",
                                "state": 1 if gauge_comm_ok else 0,
                                "msg": self.bb.get("device/gauge/comm_state/value") if gauge_comm_ok else "Connection Failed"
                            },
                            "binpick": {
                                "conntion_info": "192.168.2.30",
                                "state": 1 if vision_comm_ok else 0,
                                "msg": "OK" if vision_comm_ok else "Connection Failed"
                            }
                        }
                    }

                    self.bb.set("system/setting/context",system_status_payload)
    
                    status_msg_id = self.rules["event_ids"].get("system_status", "logic-evt-state-001")
                    self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                        self._create_frame("logic.event", "ui", status_msg_id, system_status_payload, False)))
    
                    # 3. Process Status (MQTT_Protocol.md Section 4.3)
                    process_status_payload = {
                        "kind": "event",
                        "evt": "process_status",
                        "batch_info": self.bb.get("process_status/batch_info"),
                        "runtime": self.bb.get("process_status/runtime"),
                        "current_process_tray_info": self.bb.get("process_status/current_process_tray_info"),
                        "system_status": self.bb.get("process_status/system_status"),
                        "tester_status": self.bb.get("process_status/tester_status"),
                        "robot_status": self.bb.get("process_status/robot_status"),
                        "thickness_measurement": self.bb.get("process_status/thickness_measurement"),
                        "aligner_status": self.bb.get("process_status/aligner_status")
                    }
                    process_status_msg_id = self.rules["event_ids"].get("process_status", "logic-evt-proc-status-001")
                    self.client.publish(self.rules["topics"]["logic_evt"], json.dumps(
                        self._create_frame("logic.event", "ui", process_status_msg_id, process_status_payload, False)))
                
                except KeyError as e:
                    if self.Logger:
                        self.Logger.warn(f"Blackboard key not yet available in status loop, skipping one cycle: {e}")

                time.sleep(0.5)

    def _handle_logic_event(self, header, payload):
        """UI 역할에서 Logic의 이벤트를 처리하는 함수"""
        if self.role == 'ui':
            # UI에서 Logic의 이벤트를 처리하는 로직 (필요 시 Blackboard 업데이트 등 추가)
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[UI] Logic 이벤트 수신: {payload.get('evt') or payload.get('kind')}")

    # ==========================================================================
    # 실행 및 종료
    # ==========================================================================

    def run(self):
        """MQTT 통신을 별도 스레드에서 실행하여 메인 루프가 차단되지 않도록 합니다."""
        if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] MQTT 통신 스레드를 시작합니다.")
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
                if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] 외부 종료 시그널 감지. MQTT를 정지합니다.")
                self.stop()
                break
            time.sleep(0.1)

    def _run(self):
        try:
            self.client.connect(self.host, self.port, 60)
            # loop_forever는 내부적으로 재연결을 처리하며 이 스레드를 점유합니다.
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] MQTT loop_forever를 시작합니다. (Host: {self.host}:{self.port})")
            self.client.loop_forever(retry_first_connection=True)
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] MQTT loop_forever가 종료되었습니다.")
        except Exception as e:
            if self.role == 'logic' and self.Logger: self.Logger.info(f"[{self.role.upper()}] MQTT 런타임 에러: {e}")

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