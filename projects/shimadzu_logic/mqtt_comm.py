import paho.mqtt.client as mqtt
import json
import time
import os
import random 
import threading 
from uuid import uuid4
from pkg.fsm.base import *

# ==============================================================================
# [Blackboard] 외부 상태 공유를 위한 글로벌 객체 정의 (최상단)
# ==============================================================================
# 이 코드를 통해 다른 모듈에서도 동일한 GlobalBlackboard 인스턴스를 공유합니다.
from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

# ==============================================================================
# 1. 프로토콜 데이터 정의 (Constants)
# ==============================================================================

# MQTT 토픽 정의
TOPIC_UI_CMD = "/ui/cmd"          # UI -> Logic 명령 (구독)
TOPIC_LOGIC_EVT = "/logic/evt"    # Logic -> UI 이벤트/ACK (발행)
TOPIC_BINPICK_EVT = "/binpick/evt" # BinPicking System -> Logic 이벤트 (구독)
TOPIC_BINPICK_CMD = "/logic/cmd" # [추가] Logic -> BinPicking System 명령 (발행)

# DIO 크기 정의
DI_SIZE = 48
DO_SIZE = 32

# 인장기 액션에 대한 정수 값 매핑 (self.tensile_command 용)
ACTION_MAP_TENSIL = {
    "start": 1, 
    "stop": 2, 
    "step_stop": 3, 
    "pause": 4, 
    "resume": 5, 
    "reset": 6, 
    "go_home": 7, # tensile_control go_home
}

# Bin Picking 액션에 대한 정수 값 매핑 (self.binpick_command 용)
ACTION_MAP_BINPICK = {
    "start": 1,
    "pause": 2,
    "resume": 3,
    "step_stop": 4,
    "stop": 5,
    "reset": 6,
    "go_home": 7,
    "shake": 8,
}


# Blackboard 키 상수 정의 (blackboard.json 기반)
BB_KEY_TENSILE = "ui/cmd/auto/tensile"
BB_KEY_DO_CONTROL = "ui/cmd/manual/do_control"
BB_KEY_RECOVER = "ui/cmd/manual/robot/recover"
BB_KEY_GRIPPER = "ui/cmd/manual/gripper"
BB_KEY_DT = "ui/cmd/manual/direct_teaching"
BB_KEY_GO_HOME = "ui/cmd/manual/hold_go_home"
BB_KEY_MANUAL_COMPLETE = "ui/cmd/manual/manual_recover_complete"
BB_KEY_BINPICK = "ui/cmd/auto/binpicking" # Bin Picking 키


# Blackboard 상태 확인용 상수 (실제 장비 상태를 Blackboard에서 읽어오는 키)
BB_STATUS_DO_DONE = "device/do_control/is_done"
BB_STATUS_ROBOT_RECOVER_DONE = "robot/recover/is_done"
BB_STATUS_PROC_RECOVER_DONE = "process/auto_recover/is_done"
BB_STATUS_DT_MODE = "robot/dt/mode" # 0=base, 1=active
BB_STATUS_GRIPPER_HOLDING = "gripper/is_hold" # 0=base, 1=hold
BB_STATUS_GRIPPER_RELEASE = "gripper/is_release" # 0=base, 1=released (파일명 오타 수정 반영)
BB_STATUS_ROBOT_HOME_POS = "robot/is_home_pos"
BB_STATUS_MANUAL_COMPLETE_DONE = "process/manual_recover/is_done"
BB_STATUS_BINPICK_DONE = "binpick/command/is_done" # Bin Picking 완료 플래그

# DIO 배열을 Blackboard에 통째로 전송하는 키
BB_STATUS_DI_ENTIRE = "device/remote/input/entire"
BB_STATUS_DO_ENTIRE = "device/remote/output/entire"

# 시스템 장치 상태 Blackboard 키 및 이벤트 ID
BB_KEY_ROBOT_STATE = "sys/robot/comm/state"
BB_KEY_EXT_PLC_STATE = "sys/ext/comm/state"
BB_KEY_GAUGE_STATE = "sys/gauge/comm/state"
BB_KEY_REMOTEIO_STATE = "sys/remoteio/comm/state"
EVENT_ID_SYSTEM_STATUS = "logic-evt-state-001"


# ==============================================================================
# 2. MQTT 프로토콜 통신 클래스 (NRMK Logic 역할)
# ==============================================================================

class MqttComm:
    """
    인장기 및 Bin Picking 프로토콜을 처리하는 NRMK Logic 통신 클래스입니다.
    UI로부터 명령을 수신(SUB)하고, 명령 수행을 위해 내부 변수에 상태를 할당합니다.
    ACK 발행은 이 클래스를 사용하는 외부 메인 Logic이 담당합니다.
    """
    def __init__(self, host="127.0.0.1", port=1883):
        self.host = host
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.current_batch_id = "B-TEST-20251208"
        
        self.logic_thread = None
        self.status_thread = None
        self.running = True
        
        # Logic -> Binpick 명령 ID 카운터 초기화
        self.logic_cmd_counter = 0 
        
        # 외부 Logic으로 전달할 명령 상태 변수 (0: 대기)
        self.tensile_command = 0              # (1: start, 2: stop, ...)
        self.binpick_command = 0              # (1: start, 2: pause, ...)
        self.do_control_state = 0             # (1: do_control 요청)
        self.recover_state = 0                # (1: robot_recover, 2: process_auto_recover)
        self.dt_state = 0                     # (1: DT ON, 2: DT OFF)
        self.gripper_state = 0                # (1: HOLD, 2: RELEASE)
        self.system_go_home_state = 0         # (1: system_control go_home 요청)
        self.manual_recover_complete_state = 0 # (1: manual_recover_complete 요청)
        
        self.last_command_id = None           # 마지막으로 수신된 명령의 Msg ID
        self.last_command_ack_id = None       # 해당 명령에 대한 ACK ID (성공 기준)
        self.last_command_payload = {}        # 명령 수행에 필요한 Payload (batch_id, do_values 등)
        
        # DIO 상태 초기화 (외부에서 업데이트되어야 함)
        self.current_di_values = [0] * DI_SIZE
        self.current_do_values = [0] * DO_SIZE

        # 설정 파일에서 ACK ID 로드
        self._load_config()
        
        Logger.info(f"MQTT client initialized: {self.host}:{self.port}")

    def _load_config(self):
        """config/mqtt_config.json 파일에서 ACK ID 및 기타 설정을 로드합니다."""
        config_path = "config/mqtt_config.json"
        
        # 로드 실패 시 사용할 최소한의 기본값 딕셔너리
        default_ack_ids = {
            "TENSIL_START_OK": "logic-ack-001", "TENSIL_START_REJECT": "logic-ack-002", "TENSIL_STOP": "logic-ack-003", 
            "TENSIL_STEP_STOP": "logic-ack-004", "TENSIL_PAUSE": "logic-ack-005", "TENSIL_RESUME": "logic-ack-006", 
            "TENSIL_RESET": "logic-ack-007", "TENSIL_GOHOME": "logic-ack-008", "MANUAL_CONTROL": "logic-ack-m-001",
            "ROBOT_RECOVER": "logic-ack-m-002", "PROCESS_AUTO_RECOVER": "logic-ack-m-003", "ROBOT_DT_ON": "logic-ack-m-004", 
            "ROBOT_DT_OFF": "logic-ack-m-005", "GRIPPER_HOLD": "logic-ack-m-006", "GRIPPER_RELEASE": "logic-ack-m-007", 
            "SYSTEM_GO_HOME": "logic-ack-m-008", "MANUAL_RECOVER_COMPLETE": "logic-ack-m-009",
            # Bin Picking ACK ID는 문서 3.4에 따라 logic-ack-001로 통일
            "BINPICK_GENERAL": "logic-ack-001" 
        }
        default_event_ids = {"DIO_STATUS": "logic-evt-dio-001", "SYSTEM_STATUS": "logic-evt-state-001"}
        
        ack_ids = default_ack_ids
        event_ids = default_event_ids

        if not os.path.exists(config_path):
            Logger.info(f"!!! [CRITICAL] Config file not found: {config_path} !!! (Using default values)")
        else:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 파일에서 로드에 성공하면, 기본값을 덮어씁니다.
                    ack_ids = config.get("ACK_IDS", default_ack_ids)
                    event_ids = config.get("EVENT_IDS", default_event_ids)
                Logger.info(f"→ [INFO] Config file loaded successfully: {config_path}")
            except Exception as e:
                Logger.info(f"!!! [CRITICAL] 설정 파일 로드 중 오류 발생 ({e}) !!! (기본값 사용)")

        # 클래스 속성으로 ACK ID 매핑
        self.ACK_ID_TENSIL_START_OK = ack_ids.get("TENSIL_START_OK")
        self.ACK_ID_TENSIL_START_REJECT = ack_ids.get("TENSIL_START_REJECT")
        self.ACK_ID_TENSIL_STOP = ack_ids.get("TENSIL_STOP")
        self.ACK_ID_TENSIL_STEP_STOP = ack_ids.get("TENSIL_STEP_STOP")
        self.ACK_ID_TENSIL_PAUSE = ack_ids.get("TENSIL_PAUSE")
        self.ACK_ID_TENSIL_RESUME = ack_ids.get("TENSIL_RESUME")
        self.ACK_ID_TENSIL_RESET = ack_ids.get("TENSIL_RESET")
        self.ACK_ID_TENSIL_GOHOME = ack_ids.get("TENSIL_GOHOME")
        self.ACK_ID_MANUAL_CONTROL = ack_ids.get("MANUAL_CONTROL")
        
        self.ACK_ID_ROBOT_RECOVER = ack_ids.get("ROBOT_RECOVER")
        self.ACK_ID_PROCESS_AUTO_RECOVER = ack_ids.get("PROCESS_AUTO_RECOVER")
        self.ACK_ID_ROBOT_DT_ON = ack_ids.get("ROBOT_DT_ON")
        self.ACK_ID_ROBOT_DT_OFF = ack_ids.get("ROBOT_DT_OFF")
        self.ACK_ID_GRIPPER_HOLD = ack_ids.get("GRIPPER_HOLD")
        self.ACK_ID_GRIPPER_RELEASE = ack_ids.get("GRIPPER_RELEASE")
        self.ACK_ID_SYSTEM_GO_HOME = ack_ids.get("SYSTEM_GO_HOME")
        self.ACK_ID_MANUAL_RECOVER_COMPLETE = ack_ids.get("MANUAL_RECOVER_COMPLETE")
        
        # Bin Picking ACK IDs
        self.ACK_ID_BINPICK_GENERAL = ack_ids.get("BINPICK_GENERAL") 
        
        # DIO 이벤트 ID
        self.EVENT_ID_DIO_STATUS = event_ids.get("DIO_STATUS")
        self.EVENT_ID_SYSTEM_STATUS = event_ids.get("SYSTEM_STATUS")


    def _on_connect(self, client, userdata, flags, rc):
        """브로커 연결 시 호출되는 콜백 함수"""
        if rc == 0:
            Logger.info("→ [INFO] 브로커 연결 성공!")
            
            # 1. UI 명령 구독
            self.client.subscribe(TOPIC_UI_CMD)
            Logger.info(f"→ [SUB] 토픽 구독 완료: {TOPIC_UI_CMD}")
            
            # 2. Bin Picking 이벤트 구독 (BINPICK 시스템으로부터의 이벤트)
            self.client.subscribe(TOPIC_BINPICK_EVT)
            Logger.info(f"→ [SUB] 토픽 구독 완료: {TOPIC_BINPICK_EVT}")
            
            # Logic 처리 루프와 상태 발행 루프를 별도의 스레드로 시작
            self.logic_thread = threading.Thread(target=self._logic_processing_loop, daemon=True)
            self.logic_thread.start()
            
            self.status_thread = threading.Thread(target=self._status_publishing_loop, daemon=True)
            self.status_thread.start()
            
        else:
            Logger.info(f"→ [ERROR] 브로커 연결 실패: 반환 코드 {rc}")

    def _on_message(self, client, userdata, msg):
        """구독한 토픽에서 메시지가 도착했을 때 호출되는 함수"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))
            header = payload.get("header", {})
            command = payload.get("payload", {})
            
            msg_id = header.get("msg_id")
            
            Logger.info(f"\n--- [RCV] {topic} / ID: {msg_id} ---")

            if topic == TOPIC_UI_CMD:
                # UI Command 처리 (tensile_control, system_control, binpick_control)
                cmd = command.get("cmd")
                action = command.get("action")
                
                Logger.info(f"  CMD: {cmd} / ACTION: {action}")

                if cmd == "tensile_control":
                    self._handle_tensile_control(msg_id, action, command)
                elif cmd == "system_control":
                    self._handle_manual_control(msg_id, action, command)
                elif cmd == "binpick_control":
                    self._handle_binpick_control(msg_id, action, command)
                else:
                    Logger.info(f"  [WARN] Unknown command received on {TOPIC_UI_CMD}: {cmd}")

            elif topic == TOPIC_BINPICK_EVT:
                # Bin Picking Event 처리 (ACK, status, detection, error)
                kind = command.get("kind")
                evt = command.get("evt")
                
                Logger.info(f"  Source: BINPICK / Kind: {kind} / Event: {evt}")
                
                # --- BinPicking System에서 온 이벤트 처리 ---
                if kind == "ack":
                    status = command.get("status")
                    ack_of = command.get("ack_of")
                    Logger.info(f"  BINPICK ACK RCV: Status={status}, AckOf={ack_of}. (Logic Command Success)")
                    # NOTE: 실제 Logic에서는 여기서 logic-cmd-001과 같은 명령의 완료를 확인하고 FSM 상태를 업데이트함.
                elif evt == "status":
                    phase = command.get("phase")
                    high_state = command.get("high_state")
                    Logger.info(f"  BINPICK Status RCV: Phase={phase}, HighState={high_state}. (Logic FSM update)")
                    # TODO: Blackboard에 BinPick 상태 업데이트 로직 추가
                else:
                    Logger.info(f"  Received BINPICK Event/Error: {evt or kind}")

            else:
                 Logger.info(f"  [WARN] Message received on unexpected topic: {topic}")


        except json.JSONDecodeError:
            Logger.info(f"→ [ERROR] JSON decoding error: {msg.payload.decode('utf-8')}")
        except Exception as e:
            Logger.info(f"→ [ERROR] Error processing message: {e}")

    def _on_publish(self, client, userdata, mid):
        """메시지 발행(PUB) 후 호출되는 함수"""
        pass
    
    def generate_ack(self, ack_of_id, ack_status, logic_ack_id, reason=None, data=None):
        """표준 ACK 응답 메시지 JSON을 생성합니다."""
        if data is None:
            data = {}
        
        ack_msg = {
            "header": {
                "msg_type": "logic.event",
                "source": "logic",
                "target": "ui",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "msg_id": logic_ack_id, 
                "ack_required": False
            },
            "payload": {
                "kind": "ack",
                "ack_of": ack_of_id,
                "status": ack_status,
                "reason": reason,
                "data": data
            }
        }
        return json.dumps(ack_msg, indent=2)

    def publish_ack(self, ack_json):
        """ACK 메시지를 /logic/evt 토픽으로 발행합니다."""
        self.client.publish(TOPIC_LOGIC_EVT, ack_json)
        Logger.info(f"  [PUB] ACK sent successfully: {TOPIC_LOGIC_EVT}")
        
    def publish_dio_status(self, di_values: list, do_values: list):
        """
        외부 Logic에서 현재 DIO 상태 값(DI 48개, DO 32개)을 받아 UI로 발행합니다.
        """
        if len(di_values) != DI_SIZE or len(do_values) != DO_SIZE:
            Logger.info(f"!!! [ERROR] DIO array size mismatch (DI:{len(di_values)}/{DI_SIZE}, DO:{len(do_values)}/{DO_SIZE}) !!!")
            return

        event_msg = {
            "header": {
                "msg_type": "logic.event",
                "source": "logic",
                "target": "ui",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "msg_id": self.EVENT_ID_DIO_STATUS,
                "ack_required": False
            },
            "payload": {
                "kind": "event",
                "evt": "system_dio_status",
                "di_values": di_values,
                "do_values": do_values
            }
        }
        
        try:
            self.client.publish(TOPIC_LOGIC_EVT, json.dumps(event_msg))
            # [Blackboard 동기화] DIO 상태를 Blackboard에 전송
            bb.set(BB_STATUS_DI_ENTIRE, di_values)
            bb.set(BB_STATUS_DO_ENTIRE, do_values)
        except Exception as e:
            Logger.info(f"  [ERROR] DIO status publish failed: {e}")

    def publish_system_status(self):
        """
        로봇 및 연결된 장치의 시스템 상태를 Blackboard에서 가져와 UI로 발행합니다.
        """
        # Blackboard에서 상태 값 가져오기 (새로운 키 사용)
        robot_state = bb.get(BB_KEY_ROBOT_STATE)
        ext_state = bb.get(BB_KEY_EXT_PLC_STATE)
        gauge_state = bb.get(BB_KEY_GAUGE_STATE)
        remoteio_state = bb.get(BB_KEY_REMOTEIO_STATE)
        
        # system_states 배열 구성 (5개 항목 예시를 따름)
        system_states_array = [
            robot_state, 
            ext_state, 
            gauge_state,
            remoteio_state
        ]

        event_msg = {
            "header": {
                "msg_type": "logic.event",
                "source": "logic",
                "target": "ui",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "msg_id": self.EVENT_ID_SYSTEM_STATUS,
                "ack_required": False
            },
            "payload": {
                "kind": "event",
                "evt": "system_status",
                "system_states": system_states_array # 필드명 변경 및 배열 할당
            }
        }
        self.client.publish(TOPIC_LOGIC_EVT, json.dumps(event_msg))
        # Logger.info("[PUB] System status published.")

    
    # [추가] LOGIC -> BINPICK 명령 ID 생성
    def _generate_logic_cmd_id(self):
        """LOGIC -> BINPICK 명령 ID 생성 (logic-cmd-001 형태)"""
        self.logic_cmd_counter += 1
        return f"logic-cmd-{self.logic_cmd_counter:03d}"

    # [추가] LOGIC -> BINPICK 명령 발행
    def _send_command_to_binpick(self, action, job_id, station_id="ST1"):
        """
        Bin Picking 시스템으로 Job Control 명령을 발행합니다.
        (문서 3.6 참조)
        """
        msg_id = self._generate_logic_cmd_id()
        
        cmd_msg = {
            "header": {
                "msg_type": "binpick.command",
                "source": "logic",
                "target": "binpick",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "msg_id": msg_id,
                "ack_required": True
            },
            "payload": {
                "kind": "command",
                "cmd": "job_control",
                "action": action,
                "job_id": job_id,
                "station_id": station_id
            }
        }
        
        self.client.publish(TOPIC_BINPICK_CMD, json.dumps(cmd_msg))
        Logger.info(f"  [PUB] Logic -> BINPICK Command sent to {TOPIC_BINPICK_CMD}. ID: {msg_id}")
        return msg_id


    # ==========================================================================
    # 3. CMD 핸들러: 인장기 자동 제어 (tensile_control)
    # ==========================================================================

    def _handle_tensile_control(self, msg_id, action, command):
        """
        인장기 제어 명령을 처리하고 process_command 변수에 할당합니다.
        ACK 발행 로직은 제거되었습니다.
        """
        
        if action in ACTION_MAP_TENSIL:
            self.tensile_command = ACTION_MAP_TENSIL[action]
            self.last_command_id = msg_id
            self.last_command_payload = command
            
            # ACK ID는 성공/실패 여부에 따라 외부에서 선택되어야 함.
            if action == "start":
                self.last_command_ack_id = self.ACK_ID_TENSIL_START_OK 
            else:
                ack_map_reverse = {v: k for k, v in ACTION_MAP_TENSIL.items()}
                action_name = ack_map_reverse[self.tensile_command]
                
                # 나머지 tensile_control 명령에 대한 ACK ID 매핑
                ack_id_map = {
                    "stop": self.ACK_ID_TENSIL_STOP, "step_stop": self.ACK_ID_TENSIL_STEP_STOP,
                    "pause": self.ACK_ID_TENSIL_PAUSE, "resume": self.ACK_ID_TENSIL_RESUME,
                    "reset": self.ACK_ID_TENSIL_RESET, "go_home": self.ACK_ID_TENSIL_GOHOME
                }
                self.last_command_ack_id = ack_id_map.get(action_name, "logic-ack-unknown")

            # [Blackboard 동기화]
            bb.set(BB_KEY_TENSILE, self.tensile_command)


            Logger.info(f"  [ASSIGN] tensile_command: {self.tensile_command} assigned ({action}). Waiting...")
        else:
            Logger.info(f"  [WARN] Unknown tensile_control action: {action}")

    # ==========================================================================
    # 4. CMD 핸들러: 수동/시스템 제어 (system_control)
    # ==========================================================================
    
    def _handle_manual_control(self, msg_id, action, command):
        """
        수동 및 시스템 제어 명령을 처리하고 상태 변수에 할당합니다.
        ACK 발행 로직은 제거되었습니다.
        """
        self.last_command_id = msg_id
        self.last_command_payload = command
        
        # 시스템 제어 명령에 대한 상태, ACK ID, BB Key 매핑
        manual_map = {
            "do_control": [1, self.ACK_ID_MANUAL_CONTROL, "do_control_state", BB_KEY_DO_CONTROL],
            "robot_recover": [1, self.ACK_ID_ROBOT_RECOVER, "recover_state", BB_KEY_RECOVER],
            "process_auto_recover": [2, self.ACK_ID_PROCESS_AUTO_RECOVER, "recover_state", BB_KEY_RECOVER],
            "robot_direct_teaching_on": [1, self.ACK_ID_ROBOT_DT_ON, "dt_state", BB_KEY_DT],
            "robot_direct_teaching_off": [2, self.ACK_ID_ROBOT_DT_OFF, "dt_state", BB_KEY_DT],
            "gripper_hold": [1, self.ACK_ID_GRIPPER_HOLD, "gripper_state", BB_KEY_GRIPPER],
            "gripper_release": [2, self.ACK_ID_GRIPPER_RELEASE, "gripper_state", BB_KEY_GRIPPER],
            "go_home": [1, self.ACK_ID_SYSTEM_GO_HOME, "system_go_home_state", BB_KEY_GO_HOME],
            "manual_recover_complete": [1, self.ACK_ID_MANUAL_RECOVER_COMPLETE, "manual_recover_complete_state", BB_KEY_MANUAL_COMPLETE]
        }
        
        if action in manual_map:
            state_value, ack_id, attr_name, bb_key = manual_map[action]            
            # 해당 상태 변수에 값 할당
            setattr(self, attr_name, state_value)
            self.last_command_ack_id = ack_id
            
            # [Blackboard 동기화]
            bb.set(bb_key, state_value)            
            Logger.info(f"  [ASSIGN] {attr_name}: {state_value} assigned ({action}). Waiting...")

        else:
            Logger.info(f"  [WARN] Unknown system_control action: {action}")

    # ==========================================================================
    # 5. Bin Picking 제어 (binpick_control)
    # ==========================================================================
    
    def _handle_binpick_control(self, msg_id, action, command):
        """
        Bin Picking 제어 명령을 처리하고 상태 변수에 할당합니다.
        ACK 발행 로직은 제거되었습니다.
        """
        if action in ACTION_MAP_BINPICK:
            self.binpick_command = ACTION_MAP_BINPICK[action]
            self.last_command_id = msg_id
            self.last_command_payload = command
            
            # [수정] Bin Picking ACK ID는 logic-ack-001로 고정
            self.last_command_ack_id = self.ACK_ID_TENSIL_START_OK
            
            # [Blackboard 동기화]
            bb.set(BB_KEY_BINPICK, self.binpick_command)

            # [추가] Logic -> Binpick 명령 발행 (문서 3.6 참조)
            job_id = command.get("job_id", "BP20251118-001")
            self._send_command_to_binpick(action, job_id)
            Logger.info(f"  [ASSIGN] binpick_command: {self.binpick_command} assigned ({action}). Waiting...")
        else:
            Logger.info(f"  [WARN] Unknown binpick_control action: {action}")

    # ==========================================================================
    # 6. Logic 처리 루프 (Main Logic 역할 수행)
    # ==========================================================================
    
    def _get_manual_action_info(self, state_value, state_attr):
        """상태 값과 속성 이름을 바탕으로 액션 이름, ACK ID, Reason을 반환합니다."""
        # (액션 이름, ACK ID, 성공 Reason, 실패 Reason, BB Key)
        ack_map = {
            "do_control_state": {1: ("do_control", self.ACK_ID_MANUAL_CONTROL, "Digital output control executed successfully.", "Failed to communicate with DO module. Hardware error.", BB_KEY_DO_CONTROL)},
            "recover_state": {
                1: ("robot_recover", self.ACK_ID_ROBOT_RECOVER, "Robot recovery sequence started.", "Failed to initialize robot recovery. Check robot state.", BB_KEY_RECOVER),
                2: ("process_auto_recover", self.ACK_ID_PROCESS_AUTO_RECOVER, "Automatic process recovery started.", "Recovery not possible in current state.", BB_KEY_RECOVER)
            },
            "dt_state": {
                1: ("robot_direct_teaching_on", self.ACK_ID_ROBOT_DT_ON, "Direct Teaching ON.", "Failed to enter DT mode.", BB_KEY_DT),
                2: ("robot_direct_teaching_off", self.ACK_ID_ROBOT_DT_OFF, "Direct Teaching OFF.", "Failed to exit DT mode.", BB_KEY_DT)
            },
            "gripper_state": {
                1: ("gripper_hold", self.ACK_ID_GRIPPER_HOLD, "Gripper successfully holding the item.", "Gripper operation failed: HOLD.", BB_KEY_GRIPPER),
                2: ("gripper_release", self.ACK_ID_GRIPPER_RELEASE, "Gripper successfully released the item.", "Gripper operation failed: RELEASE.", BB_KEY_GRIPPER)
            },
            "system_go_home_state": {1: ("go_home", self.ACK_ID_SYSTEM_GO_HOME, "Robot returned to system home position.", "Go Home failed.", BB_KEY_GO_HOME)},
            "manual_recover_complete_state": {1: ("manual_recover_complete", self.ACK_ID_MANUAL_RECOVER_COMPLETE, "Manual recovery sequence marked complete.", "State transition failed.", BB_KEY_MANUAL_COMPLETE)}
        }
        
        info = ack_map.get(state_attr, {}).get(state_value, ("UNKNOWN", "logic-ack-unknown", "Unknown system command.", "Unknown Error", "ui/cmd/error"))
        return info

    def _get_binpick_action_info(self, command_value):
        """Bin Picking 명령에 대한 ACK 정보를 반환합니다."""
        action_name = {v: k for k, v in ACTION_MAP_BINPICK.items()}.get(command_value, "UNKNOWN")
        
        # [수정] Bin Picking ACK ID는 logic-ack-001로 고정
        ack_id_fixed = self.ACK_ID_TENSIL_START_OK 
        
        if action_name == "start":
            # 문서 3.4.1에 따라 reason=null, data에 job_id가 포함됨
            return action_name, ack_id_fixed, None, "Job initialization failed." 
        elif action_name == "stop":
            return action_name, ack_id_fixed, "Bin Picking job stopped.", "Failed to stop job gracefully."
        elif action_name == "pause":
            return action_name, ack_id_fixed, "Bin Picking action pause executed.", "Bin Picking action pause failed."
        else:
            return action_name, ack_id_fixed, f"Bin Picking action {action_name} executed.", f"Bin Picking action {action_name} failed."
            
    
    def _logic_processing_loop(self):
        """
        MqttComm 클래스 내에서 실행되는 Logic 처리 스레드입니다.
        내부 상태 변수를 Blackboard에 동기화하고, 명령을 처리한 후 ACK를 발행합니다.
        """
        TENSIL_ACTIONS_REVERSE = {v: k for v, k in ACTION_MAP_TENSIL.items()}
        
        SYSTEM_CONTROL_STATE_ATTRS = [
            "do_control_state", "recover_state", "dt_state", "gripper_state", 
            "system_go_home_state", "manual_recover_complete_state"
        ]

        Logger.info("\n[LogicProcessingThread]: Starting internal logic processing loop.")
        
        while self.running:
            
            # ----------------------------------------------------
            # 1. TENSIL_CONTROL 명령 확인 및 처리
            # ----------------------------------------------------
            if self.tensile_command != 0:
                # [Blackboard 동기화]
                bb.set(BB_KEY_TENSILE, self.tensile_command)

                command_value = self.tensile_command
                action_name = TENSIL_ACTIONS_REVERSE.get(command_value, "UNKNOWN")
                msg_id = self.last_command_id
                ack_id = self.last_command_ack_id
                
                Logger.info(f"[LogicThread] TENSIL command detected: {action_name} ({msg_id})")
                
                # --- 장비 동작 수행 (ACK 결정) ---
                # TODO: 실제 장비 제어 로직으로 대체 필요
                for _ in range(50):
                    if not self.running: break
                    time.sleep(0.01)
                
                success = random.random() < 0.8 
                
                # --- ACK 전송 ---
                if success:
                    reason = f"{action_name} executed successfully."
                    ack_json = self.generate_ack(msg_id, "ok", ack_id, reason=reason, data=self.last_command_payload)
                else:
                    reason = f"Failed to execute {action_name}. Check limits."
                    fail_ack_id = self.ACK_ID_TENSIL_START_REJECT if action_name == "start" else ack_id
                    ack_json = self.generate_ack(msg_id, "rejected", fail_ack_id, reason=reason)
                
                self.publish_ack(ack_json)
                
                # 2. 명령 완료 후 상태 초기화 (필수)
                self.tensile_command = 0 
                bb.set(BB_KEY_TENSILE, 0) # Blackboard 상태도 초기화
                self.last_command_id = None
                self.last_command_ack_id = None
                self.last_command_payload = {}
            
            # ----------------------------------------------------
            # 2. BINPICK_CONTROL 명령 확인 및 처리
            # ----------------------------------------------------
            if self.binpick_command != 0:
                # [Blackboard 동기화]
                bb.set(BB_KEY_BINPICK, self.binpick_command)

                command_value = self.binpick_command
                msg_id = self.last_command_id
                ack_of_id = self.last_command_id # ack_of는 수신된 msg_id를 그대로 사용 (문서 3.4.1/3.4.2)
                ack_id = self.last_command_ack_id # logic-ack-001로 고정되어 있음
                
                action_name, _, ok_reason, err_reason = self._get_binpick_action_info(command_value)
                
                Logger.info(f"[LogicThread] BINPICK command detected: {action_name} ({msg_id})")
                
                # --- 장비 동작 수행 (ACK 결정) ---
                success = False
                
                if bb.get(BB_STATUS_BINPICK_DONE):
                    success = True
                    Logger.info("  [Logic] BINPICK: Done flag confirmed after device communication. Resetting Blackboard.")
                    bb.set(BB_STATUS_BINPICK_DONE, False) # 완료 플래그 초기화
                
                # [SIMULATION FALLBACK] 장비 응답이 없을 경우, 랜덤으로 성공/실패 결정
                if not success:
                    time.sleep(0.1) 
                    success = random.random() < 0.7 
                
                # --- ACK 전송 ---
                if success:
                    # 문서 3.4.1에 따라 reason=null, data={job_id}
                    data = {"job_id": self.last_command_payload.get("job_id", "BP20251118-001")} # 문서 예시 데이터 사용
                    ack_json = self.generate_ack(ack_of_id, "ok", ack_id, reason=ok_reason, data=data)
                else:
                    # 문서 3.4.2에 따라 status="error", reason={error_context}, data={}
                    data = {}
                    ack_json = self.generate_ack(ack_of_id, "error", ack_id, reason=err_reason, data=data)

                self.publish_ack(ack_json)

                # 2. 명령 완료 후 상태 초기화 (필수)
                self.binpick_command = 0
                bb.set(BB_KEY_BINPICK, 0) # Blackboard 상태도 초기화
                self.last_command_id = None
                self.last_command_ack_id = None
                self.last_command_payload = {}


            # ----------------------------------------------------
            # 3. SYSTEM_CONTROL 명령 확인 및 처리 (통합 루프)
            # ----------------------------------------------------
            for attr_name in SYSTEM_CONTROL_STATE_ATTRS:
                state_value = getattr(self, attr_name)
                
                if state_value != 0:
                    # 1. 명령 정보, ACK ID, Reason, BB Key 가져오기
                    action_name, ack_id, ok_reason, err_reason, bb_key = self._get_manual_action_info(state_value, attr_name)
                    msg_id = self.last_command_id
                    
                    # [Blackboard 동기화]
                    bb.set(bb_key, state_value)
                    
                    Logger.info(f"[LogicThread] SYSTEM command detected: {action_name} ({msg_id})")

                    # 2. 실제 장비 명령 구동 후 성공여부에 따른 값 결정
                    
                    success = False
                    
                    if action_name == "do_control":
                        if bb.get(BB_STATUS_DO_DONE):
                            success = True
                            Logger.info("  [Logic] DO_CONTROL: Done flag confirmed after device communication. Resetting Blackboard.")
                            bb.set(BB_STATUS_DO_DONE, False) # 완료 플래그 초기화
                    elif action_name == "robot_recover":
                        if bb.get(BB_STATUS_ROBOT_RECOVER_DONE):
                            success = True
                            Logger.info("  [Logic] ROBOT_RECOVER: Robot recovery done flag confirmed. Resetting Blackboard.")
                            bb.set(BB_STATUS_ROBOT_RECOVER_DONE, False)
                    elif action_name == "process_auto_recover":
                        if bb.get(BB_STATUS_PROC_RECOVER_DONE):
                            success = True
                            Logger.info("  [Logic] PROCESS_AUTO_RECOVER: Process auto recovery done flag confirmed. Resetting Blackboard.")
                            bb.set(BB_STATUS_PROC_RECOVER_DONE, False)
                    elif action_name == "robot_direct_teaching_on":
                        if bb.get(BB_STATUS_DT_MODE) == 1:
                            success = True
                            Logger.info("  [Logic] DT ON: DT mode entry status confirmed.")
                            # NOTE: DT Mode는 상태 변수이므로 상태 플래그를 초기화할 필요 없음.
                    elif action_name == "robot_direct_teaching_off":
                        if bb.get(BB_STATUS_DT_MODE) == 0:
                            success = True
                            Logger.info("  [Logic] DT OFF: DT mode exit status confirmed.")
                            # NOTE: DT Mode는 상태 변수이므로 상태 플래그를 초기화할 필요 없음.
                    elif action_name == "gripper_hold":
                        if bb.get(BB_STATUS_GRIPPER_HOLDING) == 1:
                            success = True
                            Logger.info("  [Logic] GRIPPER HOLD: Hold status confirmed.")
                            # NOTE: Holding 상태는 유지되므로 플래그 초기화 불필요.
                    elif action_name == "gripper_release":
                        if bb.get(BB_STATUS_GRIPPER_RELEASE) == 1: 
                            success = True
                            Logger.info("  [Logic] GRIPPER RELEASE: Release status confirmed. Resetting Blackboard.")
                            bb.set(BB_STATUS_GRIPPER_RELEASE, False) # 릴리즈 성공 플래그 초기화
                    elif action_name == "go_home":
                        if bb.get(BB_STATUS_ROBOT_HOME_POS):
                            success = True
                            Logger.info("  [Logic] GO HOME: Robot home position confirmed. Resetting Blackboard.")
                            bb.set(BB_STATUS_ROBOT_HOME_POS, False) # 가정: 홈 위치는 임시 플래그로 확인 후 리셋
                    elif action_name == "manual_recover_complete":
                        if bb.get(BB_STATUS_MANUAL_COMPLETE_DONE):
                            success = True
                            Logger.info("  [Logic] MANUAL RECOVER COMPLETE: Done report flag confirmed. Resetting Blackboard.")
                            bb.set(BB_STATUS_MANUAL_COMPLETE_DONE, False) # 완료 플래그 초기화
                    
                    # [SIMULATION FALLBACK] 장비 응답이 없을 경우, 랜덤으로 성공/실패 결정
                    if not success:
                        time.sleep(0.1) 
                        success = random.random() < 0.9 
                    
                    if success:
                        data = {}
                        
                        # (1) DO_CONTROL: data에 applied_values 추가 및 현재 DO 상태 업데이트
                        if action_name == "do_control":
                            do_values_rcv = self.last_command_payload.get("params", {}).get("do_values", [])
                            data = {"applied_values": do_values_rcv}
                            self.current_do_values = do_values_rcv 
                        
                        # (2) 나머지 명령 (로직만 수행)
                        else:
                            pass 

                        ack_json = self.generate_ack(msg_id, "ok", ack_id, reason=ok_reason, data=data)
                    else:
                        # 실패 처리 (모든 실패는 err_reason 사용)
                        ack_json = self.generate_ack(msg_id, "error", ack_id, reason=err_reason)

                    self.publish_ack(ack_json)

                    # 3. 명령 완료 후 상태 초기화
                    setattr(self, attr_name, 0)
                    bb.set(bb_key, 0) # Blackboard 상태도 초기화
                    self.last_command_id = None
                    self.last_command_ack_id = None
                    self.last_command_payload = {}
                    break # 하나의 시스템 명령 처리 후 다음 루프로 이동

            time.sleep(0.05) # 루프 지연 (50ms)

    def _status_publishing_loop(self):
        """
        DIO 및 시스템 상태를 주기적으로 발행하는 전용 스레드 루프입니다.
        (주기: DIO 상태는 0.5초, 시스템 상태는 DIO 발행 후 0.2초 간격)
        """
        Logger.info("[StatusPublishingThread]: Starting status publishing loop.")
        
        # DIO 발행을 위한 초기 값 설정 (publish_dio_status에서 사용)
        di_values = [0] * DI_SIZE
        do_values = [0] * DO_SIZE

        while self.running:
            try:
                # 1. DIO 상태 시뮬레이션 및 발행 (0.5s 주기 시작)
                # 시뮬레이션: 값을 약간씩 변경
                di_values = [random.randint(0, 1) if random.random() < 0.02 else v for v in di_values]
                do_values = [random.randint(0, 1) if random.random() < 0.05 else v for v in do_values]
                
                # DIO 발행 및 BB 업데이트 (T=0.0s)
                self.publish_dio_status(di_values, do_values)

                # 2. 0.2초 대기
                for _ in range(20):
                    if not self.running: break
                    time.sleep(0.01)
                if not self.running: break

                # 3. 시스템 상태 발행 (T=0.2s)
                self.publish_system_status() 

                # 4. 남은 시간 대기 (0.5s - 0.2s = 0.3s)
                for _ in range(30):
                    if not self.running: break
                    time.sleep(0.01)
            
            except Exception as e:
                Logger.info(f"[ERROR] Error in status publishing thread: {e}")
                time.sleep(1)


    # ==========================================================================
    # 7. 실행 함수
    # ==========================================================================

    def start(self):
        """MQTT 클라이언트 연결 및 루프를 시작합니다 (Non-blocking)."""
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            self.running = True
            
            Logger.info("\n" + "="*50)
            Logger.info("Tensile Machine MQTT Protocol Connector Started")
            Logger.info(f"Logic connector is waiting for commands on {TOPIC_UI_CMD}.")
            Logger.info("="*50 + "\n")
        except ConnectionRefusedError:
            Logger.info(f"\n!!! [CRITICAL] Make sure MQTT broker is running on {self.host}:{self.port}. !!!")
            self.running = False

    def stop(self):
        """클라이언트 종료 처리"""
        self.running = False
        if self.logic_thread and self.logic_thread.is_alive():
            self.logic_thread.join()
        if self.status_thread and self.status_thread.is_alive():
            self.status_thread.join()
        self.client.loop_stop()
        self.client.disconnect()

    def run(self):
        """MQTT 클라이언트 연결 및 루프를 시작합니다 (Blocking)."""
        self.start()
        if not self.running:
            return

        try:
            # Ctrl+C (KeyboardInterrupt)를 포착하기 위해 메인 스레드에서 대기
            while self.running:
                time.sleep(0.1)

        except ConnectionRefusedError:
            Logger.info(f"\n!!! [CRITICAL] Make sure MQTT broker is running on {self.host}:{self.port}. !!!")
        except KeyboardInterrupt:
            Logger.info("\nTerminating connector.")
        finally:
            self.running = False
            if self.logic_thread and self.logic_thread.is_alive():
                self.logic_thread.join()
            if self.status_thread and self.status_thread.is_alive():
                self.status_thread.join()
            self.client.loop_stop()
            self.client.disconnect()
            self.stop()

# ==============================================================================
# 메인 실행 블록
# ==============================================================================

if __name__ == "__main__":
    # 1. MqttComm 인스턴스 생성 및 MQTT 통신 시작
    connector = MqttComm()
    
    # run() 메서드 내에서 MQTT 연결 성공 시, _logic_processing_loop 및 _status_publishing_loop 스레드가 자동 시작됨.
    try:
        connector.run()
    except KeyboardInterrupt:
        pass