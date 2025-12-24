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

