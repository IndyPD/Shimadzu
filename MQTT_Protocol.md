Markdown

# 인장기 시험 자동화 Logic ↔ UI MQTT 프로토콜 정의서

## 1. 명령 (Command) 및 응답 (ACK) 요약

### 1.1. 통신 요약 테이블

| **Cmd** | **Action** | **Payload (핵심 파라미터)** | **Command Msg ID 접두사** | **응답 Status** | **응답 Msg ID 예시** | **응답 Reason / 데이터** | 
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| tensile_control | start | {"batch_id": "..."} | ui-tensile-cmd | ok / rejected | logic-ack-001 / logic-ack-002 | ok: Starting batch ID / rejected: Shimadzu is not ready | 
| tensile_control | stop | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-003 | Emergency stop complete. | 
| tensile_control | step_stop | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-004 | Stop scheduled after current specimen completes. | 
| tensile_control | pause | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-005 | System paused successfully. | 
| tensile_control | resume | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-006 | Operation resumed. | 
| tensile_control | reset | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-007 | Starting reset and recovery procedure. | 
| tensile_control | go_home | {"batch_id": "..."} | ui-tensile-cmd | ok | logic-ack-008 | Home movement sequence started. | 
| system_control | do_control | {"params": {"address": int, "value": bool}} | ui-manual-cmd | ok / error | logic-ack-m-001 | ok: DO control executed / error: Invalid address. | 
| system_control | robot_recover | {} | ui-manual-cmd | ok / error | logic-ack-m-002 | 로봇 복구 시퀀스 시작 | 
| system_control | gripper_hold | {} | ui-manual-cmd | ok / error | logic-ack-m-006 | 그리퍼 홀드 완료 | 
| **binpick_control** | **start / pause / shake** | **{"job_id": "..."}** | **ui-start- / ui-pause- / ui-shake-** | **ok / error** | **logic-ack-001** | **Bin Picking 제어 명령 수락** | 

### 1.2. MQTT Topic 구조

| **Topic** | **Publisher** | **Subscriber** | **설명** | 
| :--- | :--- | :--- | :--- |
| `/ui/cmd` | UI | LOGIC | UI → LOGIC 명령 (인장기, 시스템, BinPick 제어) | 
| `/logic/evt` | LOGIC | UI | ACK, 시스템 상태, BinPick 상태 보고 | 

### 1.3. Message Frame (Envelope) 정의

```json
{
  "header": {
    "msg_type": "string",
    "source": "ui | logic",
    "target": "ui | logic",
    "timestamp": "ISO8601",
    "msg_id": "UUID (or Prefixed ID)",
    "ack_required": true
  },
  "payload": {}
}
```

## 2. 인장기 및 시스템 제어 JSON 예시

### 2.1. tensile_control/start
**Command (UI → Logic)**
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-tensile-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "tensile_control",
    "action": "start",
    "batch_id": "B-20251208-001"
  }
}
```

**ACK (Logic → UI)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.050"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-tensile-cmd-001",
    "status": "ok",
    "reason": "Starting batch B-20251208-001",
    "data": {
      "batch_id": "B-20251208-001"
    }
  }
}
```

### 2.2. tensile_control/stop
*   **Command ID**: `ui-tensile-cmd-002`
*   **ACK ID**: `logic-ack-003` (Emergency stop complete)

### 2.3. system_control/do_control (개별 핀 제어)

**Command (UI → Logic)**
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-manual-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:01:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "system_control",
    "action": "do_control",
    "params": {
      "addr": 5,
      "value": true
    }
  }
}
```

## 3. Bin Picking 통신 정의 (UI ↔ LOGIC)
UI는 Logic에게 Bin Picking 동작을 명령하고, Logic은 내부적으로 Bin Picking 시스템을 제어한 뒤 결과를 UI에 보고합니다.

### 3.1. Bin Picking 상태 모델 (Logic 보고용)
*   **HighState**: `IDLE`, `READY`, `RUNNING`, `ERROR`
*   **Phase**: `DETECTING`, `RECOGNIZED`, `SHAKE`, `POSE_READY`, `PICKING`, `MOVING`, `PLACE`, `ERROR` 등

### 3.2. UI → LOGIC Bin Picking 명령 예시 (Start)

```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-start-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "binpick_control",
    "action": "start",
    "job_id": "BP20251118-001"
  }
}
```

### 3.3. LOGIC → UI Bin Picking ACK

```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.050"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-start-001",
    "status": "ok",
    "reason": "BinPicking operation started",
    "data": {
      "job_id": "BP20251118-001"
    }
  }
}
```

### 3.4. LOGIC → UI Bin Picking 상태 보고 (Status Report)
Logic은 Bin Picking 시스템으로부터 받은 데이터를 가공하여 UI에 상시 보고합니다.

```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-bp-status-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:10.000"
  },
  "payload": {
    "kind": "event",
    "evt": "binpick_status",
    "phase": "PICKING",
    "high_state": "RUNNING",
    "job_id": "BP20251118-001",
    "stats": {
      "picked": 10,
      "success": 9,
      "fail": 1
    },
    "robot_pose": {
      "x": 500.0,
      "y": 120.0,
      "z": 300.0,
      "rx": 180.0,
      "ry": 0.0,
      "rz": 90.0
    },
    "current_pick": {
      "id": "obj_01",
      "score": 0.92,
      "status": "approaching"
    }
  }
}
```

## 4. 상시 상태 보고 메시지 정의 (Periodic)
Logic에서 UI로 상시 발행되는 상태 메시지들입니다.

### 4.1. LOGIC → UI DIO 상태 (system_dio_status)

```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-dio-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:05:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_dio_status",
    "di_values": [
      0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    ],
    "do_values": [
      0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    ]
  }
}
```

### 4.2. LOGIC → UI 시스템 통합 상태 (system_status)
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-state-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:05:01.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_status",
    "process": "run",
    "system_states": [
      1, 1, 1, 0, 1
    ]
  }
}
```

## 5. JSON 데이터 모델 명세

### 5.1. system_states 배열 (system_status)
*   `[0]`: Robot Comm (1:OK)
*   `[1]`: PLC Comm
*   `[2]`: Gauge Comm
*   `[3]`: RIO Comm
*   `[4]`: Vision Comm

### 5.2. robot_pose 구조
*   `x`, `y`, `z`, `rx`, `ry`, `rz` (단위: mm, degree)

## 6. DIO 매핑 테이블

`system_dio_status` 메시지의 `di_values` 및 `do_values` 배열 인덱스에 매핑된 하드웨어 정보입니다.

### 6.1. Digital Input (DI) 매핑

| 인덱스 | 이름 | 설명 |
| :--- | :--- | :--- |
| 0 | SELECT_SW | 자동/수동 선택 스위치 |
| 1 | RESET_SW | 리셋 스위치 |
| 2 | SOL_SENSOR | 솔레노이드 센서 |
| 3 | BCR_OK | 바코드 리더 판독 성공 |
| 4 | BCR_ERROR | 바코드 리더 판독 실패 |
| 5 | BUSY | 시스템 비지 상태 |
| 6 | ENO_01_SW | 비상 정지 스위치 1 |
| 7-9 | EMO_02~04_SI | 비상 정지 신호 2, 3, 4 |
| 10-13 | DOOR_1~4_OPEN | 도어 1~4 개폐 감지 센서 |
| 14-15 | GRIPPER_1~2_CLAMP | 그리퍼 1, 2 클램프 확인 센서 |
| 16 | EXT_FW_SENSOR | 신율계 전진 완료 센서 |
| 17 | EXT_BW_SENSOR | 신율계 후진 완료 센서 |
| 18 | INDICATOR_GUIDE_UP | 인디케이터 가이드 상승 센서 |
| 19 | INDICATOR_GUIDE_DOWN | 인디케이터 가이드 하강 센서 |
| 20-21 | ALIGN_1_PUSH / PULL | 정렬기 1번 전진/후진 센서 |
| 22-23 | ALIGN_2_PUSH / PULL | 정렬기 2번 전진/후진 센서 |
| 24-25 | ALIGN_3_PUSH / PULL | 정렬기 3번 전진/후진 센서 |
| 26-27 | ATC_1_1 / 1_2_SENSOR | 툴 체인저 1번 센서류 |
| 28 | SCRAPBOX_SENSOR | 스크랩 박스 감지 센서 |
| 29-30 | ATC_2_1 / 2_2_SENSOR | 툴 체인저 2번 센서류 |

### 6.2. Digital Output (DO) 매핑

| 인덱스 | 이름 | 설명 |
| :--- | :--- | :--- |
| 0 | TOWER_LAMP_RED | 타워 램프 적색 |
| 1 | TOWER_LAMP_GREEN | 타워 램프 녹색 |
| 2 | TOWER_LAMP_YELLOW | 타워 램프 황색 |
| 3 | TOWER_BUZZER | 타워 부저 |
| 5 | BCR_TGR | 바코드 리더 트리거 신호 |
| 6 | LOCAL_LAMP_R | 로컬 램프 우측 |
| 8 | RESET_SW_LAMP | 리셋 스위치 램프 |
| 9 | DOOR_4_LAMP | 4번 도어 상태 램프 |
| 14 | INDICATOR_UP | 인디케이터 가이드 상승 솔레노이드 |
| 15 | INDICATOR_DOWN | 인디케이터 가이드 하강 솔레노이드 |
| 16 | ALIGN_1_PUSH | 정렬기 1번 전진 솔레노이드 |
| 17 | ALIGN_1_PULL | 정렬기 1번 후진 솔레노이드 |
| 18 | ALIGN_2_PUSH | 정렬기 2번 전진 솔레노이드 |
| 19 | ALIGN_2_PULL | 정렬기 2번 후진 솔레노이드 |
| 20 | ALIGN_3_PUSH | 정렬기 3번 전진 솔레노이드 |
| 21 | ALIGN_3_PULL | 정렬기 3번 후진 솔레노이드 |
| 22 | GRIPPER_1_UNCLAMP | 그리퍼 1번 언클램프 제어 |
| 23 | LOCAL_LAMP_L | 로컬 램프 좌측 |
| 24 | GRIPPER_2_UNCLAMP | 그리퍼 2번 언클램프 제어 |
| 25 | LOCAL_LAMP_C | 로컬 램프 중앙 |
| 26 | EXT_FW | 신율계 전진 제어 |
| 27 | EXT_BW | 신율계 후진 제어 |
