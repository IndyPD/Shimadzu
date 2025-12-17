import paho.mqtt.client as mqtt
import json
import time
from uuid import uuid4
import random 

# ==============================================================================
# 1. 설정 및 상수 정의
# ==============================================================================

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
TOPIC_UI_CMD = "/ui/cmd"          # UI -> Logic 명령 (발행)
TOPIC_LOGIC_EVT = "/logic/evt"    # Logic -> UI 이벤트/ACK (구독)
DO_SIZE = 32 # DO 크기 업데이트

# 인장기 액션 이름과 메시지 ID 시퀀스 번호 매핑
TENSIL_ACTIONS = {
    1: ("start", 1), 
    2: ("stop", 2),
    3: ("step_stop", 3),
    4: ("pause", 4),
    5: ("resume", 5),
    6: ("reset", 6),
    7: ("go_home", 7),
}

# 시스템 제어 액션 (메뉴 번호 11번부터 시작)
SYSTEM_CONTROL_ACTIONS = {
    11: "do_control", 
    12: "robot_recover",
    13: "process_auto_recover",
    14: "robot_direct_teaching_on",
    15: "robot_direct_teaching_off",
    16: "gripper_hold",
    17: "gripper_release",
    18: "go_home", 
    19: "manual_recover_complete",
}

# [추가] Bin Picking 액션 (메뉴 번호 1번부터 시작)
BINPICK_ACTIONS = {
    1: ("start", 1), 
    2: ("pause", 2),
    3: ("resume", 3),
    4: ("step_stop", 4),
    5: ("stop", 5),
    6: ("reset", 6),
    7: ("go_home", 7),
    8: ("shake", 8), 
}
BINPICK_JOB_ID_DEFAULT = "BP20251118-001" # 문서 예시와 일치


# ==============================================================================
# 2. MQTT 클라이언트 클래스
# ==============================================================================

class DummyUiClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message 
        
        self.tensile_cmd_counter = 0 
        self.manual_cmd_counter = 0
        
        # Bin Picking 문서 ID 규칙을 위한 카운터 (ui-start-001, ui-pause-001 등)
        self.binpick_start_counter = 0 
        self.binpick_pause_counter = 0 
        self.binpick_shake_counter = 0 
        self.binpick_general_counter = 0
        
        self.current_batch_id = "B-TEST-20251208"

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"→ [INFO] 브로커 연결 성공: {self.host}:{self.port}")
            self.client.subscribe(TOPIC_LOGIC_EVT) 
        else:
            print(f"→ [ERROR] 브로커 연결 실패: 반환 코드 {rc}")

    def _on_message(self, client, userdata, msg):
        """Logic에서 오는 ACK 및 상태 메시지 수신"""
        try:
            message = json.loads(msg.payload.decode('utf-8'))
            payload = message.get("payload", {})
            evt = payload.get("evt")
            
            if payload.get("kind") == "ack":
                status = payload.get("status", "N/A")
                reason = payload.get("reason", "N/A")
                ack_of = payload.get("ack_of", "N/A")

                print(f"\n<<< [ACK RCV] Logic 응답 ({status}) <<<")
                print(f"    원래 명령 ID: {ack_of}")
                print(f"    상태 메시지: {reason}")
            
            elif evt == "system_dio_status":
                di_count = len(payload.get("di_values", []))
                do_count = len(payload.get("do_values", []))
                
                print(f"\n<<< [EVENT RCV] DIO 상태 (주기적) <<<")
                print(f"    DI 수신 개수: {di_count} (예상 48개)")
                print(f"    DO 수신 개수: {do_count} (예상 {DO_SIZE}개)")
            
            elif evt == "system_status":
                system_states = payload.get("system_states", [])
                
                print(f"\n<<< [EVENT RCV] 시스템 장비 상태 (주기적) <<<")
                print(f"    상태 배열 수신: {len(system_states)}개")
                print(f"    예시 값: {system_states}")
            
            else:
                 print(f"\n<<< [EVENT RCV] 기타 이벤트: {evt or 'N/A'} <<<")

            print(f"-----------------------------------\n")

        except json.JSONDecodeError:
            print(f"→ [ERROR] ACK JSON 디코딩 오류: {msg.payload.decode('utf-8')}")
        except Exception as e:
            print(f"→ [ERROR] 메시지 처리 중 오류 발생: {e}")


    def _generate_msg_id(self, cmd_type, action):
        """명령 타입과 액션에 따라 Msg ID를 생성 (프로토콜 문서 예시 반영)"""
        
        if cmd_type == "tensile_control":
            self.tensile_cmd_counter += 1
            return f"ui-tensile-cmd-{self.tensile_cmd_counter:03d}"
            
        elif cmd_type == "system_control":
            # System Init 예시 ID (ui-init-001) 반영:
            if action == "init":
                self.manual_cmd_counter = 1 
                return f"ui-init-{self.manual_cmd_counter:03d}"
            
            self.manual_cmd_counter += 1
            return f"ui-manual-cmd-{self.manual_cmd_counter:03d}"
            
        elif cmd_type == "binpick_control":
            # Bin Picking은 문서 예시와 같이 액션 기반으로 ID 생성 (ui-start-001 등)
            if action == "start":
                self.binpick_start_counter += 1
                return f"ui-start-{self.binpick_start_counter:03d}"
            elif action == "pause":
                self.binpick_pause_counter += 1
                return f"ui-pause-{self.binpick_pause_counter:03d}"
            elif action == "shake":
                self.binpick_shake_counter += 1
                return f"ui-shake-{self.binpick_shake_counter:03d}"
            # NOTE: 문서에 정의되지 않은 기타 Bin Picking 액션은 generic ID 사용
            else:
                self.binpick_general_counter += 1
                return f"ui-binpick-cmd-{self.binpick_general_counter:03d}" 


    def send_command(self, cmd_type, action, payload_data=None):
        """명령 JSON을 생성하고 발행합니다."""
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

    def run(self):
        """클라이언트 연결 및 명령 루프 시작"""
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            self._command_loop()
        except ConnectionRefusedError:
            print(f"\n!!! [CRITICAL] {self.host}:{self.port}에 MQTT 브로커가 실행 중인지 확인하십시오. !!!")
        except KeyboardInterrupt:
            print("\n클라이언트를 종료합니다.")
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def _command_loop(self):
        """키보드 입력을 받는 메인 루프"""
        while True:
            self._print_menu()
            choice = input("명령 번호를 선택하세요 (종료: q): ").strip()

            if choice.lower() == 'q':
                break
            
            try:
                choice_num = int(choice)
                
                if 1 <= choice_num <= 7:
                    # TENSIL_CONTROL 명령 처리
                    action_name, _ = TENSIL_ACTIONS[choice_num]
                    batch_id = input(f"Batch ID를 입력하세요 (기본값: {self.current_batch_id}): ") or self.current_batch_id
                    
                    payload_data = {"batch_id": batch_id}
                    self.send_command("tensile_control", action_name, payload_data)
                
                elif choice_num == 9:
                    # BINPICK_CONTROL 명령 처리
                    self._handle_binpick_control()
                
                elif choice_num in SYSTEM_CONTROL_ACTIONS:
                    action_name = SYSTEM_CONTROL_ACTIONS[choice_num]
                    
                    if action_name == "do_control":
                        self._handle_do_control()
                    else:
                        # 나머지 system_control 액션은 빈 Payload로 전송
                        self.send_command("system_control", action_name, {})

                else:
                    print("유효하지 않은 번호입니다. 다시 시도하세요.")
                    
            except ValueError:
                print("유효하지 않은 입력입니다.")
            except Exception as e:
                print(f"명령 처리 중 오류 발생: {e}")

            time.sleep(0.1) 

    def _handle_do_control(self):
        """DO 제어 명령을 위한 랜덤 배열 (32개) 생성 처리"""
        print(f"\n--- 11. 시스템 수동 제어 (DO_CONTROL - {DO_SIZE}개 랜덤) ---")
        
        # 0 또는 1로 구성된 32개 길이의 랜덤 리스트 생성
        random_do_list = [random.randint(0, 1) for _ in range(DO_SIZE)]
        
        print(f"랜덤 DO 값 생성 완료: {random_do_list[:5]}...")

        try:
            payload_data = {"params": {"do_values": random_do_list}}
            self.send_command("system_control", "do_control", payload_data)
            
        except Exception as e:
            print(f"명령 처리 중 오류 발생: {e}")

    def _handle_binpick_control(self):
        """Bin Picking 제어 명령을 위한 사용자 입력 처리"""
        while True:
            print("\n" + "~"*50)
            print("--- 9. Bin Picking 제어 (binpick_control) ---")
            for num, (action, _) in BINPICK_ACTIONS.items():
                print(f" {num}. {action.upper()}")
            print(" 0. 이전 메뉴로 돌아가기")
            print("~"*50)

            choice = input("Bin Picking 명령 번호를 선택하세요: ").strip()

            if choice == '0':
                break
            
            try:
                choice_num = int(choice)
                if choice_num in BINPICK_ACTIONS:
                    action_name, _ = BINPICK_ACTIONS[choice_num]
                    
                    # start 명령일 경우 job_id 필요
                    if action_name == "start":
                        job_id = input(f"Job ID를 입력하세요 (기본값: {BINPICK_JOB_ID_DEFAULT}): ") or BINPICK_JOB_ID_DEFAULT
                        payload_data = {"job_id": job_id}
                    else:
                         payload_data = {}
                         
                    self.send_command("binpick_control", action_name, payload_data)
                else:
                    print("유효하지 않은 번호입니다.")
            except ValueError:
                print("유효하지 않은 입력입니다.")
                
            time.sleep(0.1)


    def _print_menu(self):
        """명령 메뉴 출력"""
        print("\n" + "="*50)
        print("인장기 자동화 MQTT 명령 클라이언트")
        print("="*50)
        print("--- 1. 자동 제어 (tensile_control) ---")
        for num, (action, _) in TENSIL_ACTIONS.items():
            print(f" {num}. {action.upper()}")
        print("-----------------------------------")
        print("--- 2. 시스템/수동 제어 (system_control) ---")
        for num, action in SYSTEM_CONTROL_ACTIONS.items():
            if action == "do_control":
                 print(f" {num}. DO_CONTROL (랜덤 {DO_SIZE}개 전송)")
            else:
                print(f" {num}. {action.upper()}")
        print("-----------------------------------")
        print(" 9. BINPICK_CONTROL")
        print("-----------------------------------")


# ==============================================================================
# 메인 실행 블록
# ==============================================================================

if __name__ == "__main__":
    client = DummyUiClient(MQTT_HOST, MQTT_PORT)
    client.run()