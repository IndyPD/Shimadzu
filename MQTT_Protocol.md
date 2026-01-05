Markdown

# 인장기 시험 자동화 Logic ↔ UI MQTT 프로토콜 정의서

## 최종 작성일 : 2026-01-02

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

본 항목은 UI(사용자 인터페이스)와 Logic(제어 시스템) 간의 주요 제어 명령과 그에 대한 응답(ACK) 메시지 형식을 JSON 예시와 함께 상세히 정의합니다. 모든 통신은 UI의 요청(Command)과 Logic의 응답(ACK) 구조를 따르며, 각 명령에 대해 성공(`status: "ok"`)과 실패(`status: "error"`) 시의 구체적인 응답 예시를 제공합니다. 특히 실패 시에는 원인 파악을 위한 `error_code`가 포함되어 안정적인 예외 처리를 지원합니다.

### 2.0. 제어 명령 요약 테이블

| **Cmd** | **Action** | **Payload (핵심 파라미터)** | **Command Msg ID 예시** | **응답 Status** | **응답 Reason (성공 / 실패)** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tensile_control` | `start` | `{"batch_id": "..."}` | `ui-tensile-cmd-001` | `ok` / `error` | Starting batch... / Batch is already running |
| `tensile_control` | `stop` | `{"batch_id": "..."}` | `ui-tensile-cmd-002` | `ok` / `error` | Emergency stop complete / Stop rejected: no active batch |
| `conty_program` | `start` / `stop` | `{"program_index": int}` | `ui-program-cmd-001` | `ok` / `error` | Program control accepted / Program control rejected |
| `system_control` | `do_control` | `{"params": {"addr": int, "value": bool}}` | `ui-manual-cmd-001` | `ok` / `error` | DO control executed / Invalid DO address |
| `comm_test` | `test` | `{"device": "..."}` | `ui-commtest-cmd-001` | `ok` / `error` | comm_test accepted / Unsupported device |
| `recover` | `error`, `auto`, `manual` | `{"action": "..."}` | `ui-recover-cmd-001` | `ok` / `error` | Recover sequence accepted / Recovery not available |
| `robot_control` | `enable`/`disable`, `open`/`close` | `{"target": "...", "action": "..."}` | `ui-robot-cmd-001` | `ok` / `error` | Robot control accepted / Robot control rejected |
| `data` | `save`, `reset` | `{}` | `ui-data-cmd-001` | `ok` / `error` | Batch plan saved / Batch data reset |
### 2.0. Conty Program Control
**Command (UI → Logic)**
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-program-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "conty_program",
    "action": "start",
    "program_index": 1
  }
}
```
**ACK (Logic → UI)** /OK
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
    "ack_of": "ui-program-cmd-001",
    "status": "ok",
    "reason": "Program control accepted",
    "data": {
      "program_index": 1
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.050"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-program-cmd-001",
    "status": "error",
    "reason": "Program control rejected",
    "error_code": "PROGRAM_CONTROL_REJECTED",
    "data": {
      "program_index": 1
    }
  }
}
```

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

**ACK (Logic → UI)** /OK
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
**ACK (Logic → UI)**  /ERROR 
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.050"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-tensile-cmd-001",
    "status": "error",
    "reason": "Batch is already running",
    "error_code": "BATCH_ALREADY_RUNNING",
    "data": {
      "batch_id": "B-20251208-001"
    }
  }
}
```

### 2.2. tensile_control/stop
*   **Command ID**: `ui-tensile-cmd-002`
*   **ACK ID**: `logic-ack-003` (Emergency stop complete)
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-003",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.100"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-tensile-cmd-002",
    "status": "ok",
    "reason": "Emergency stop complete",
    "data": {
      "batch_id": "B-20251208-001"
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.100"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-tensile-cmd-002",
    "status": "error",
    "reason": "Stop rejected: no active batch",
    "error_code": "NO_ACTIVE_BATCH"
  }
}
```

### 2.3. system_control/do_control (개별 핀 제어)

**DO Command (UI → Logic)**
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
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-m-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:01:00.030"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-manual-cmd-001",
    "status": "ok",
    "reason": "DO control executed",
    "data": {
      "addr": 5,
      "value": true
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-m-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:01:00.030"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-manual-cmd-001",
    "status": "error",
    "reason": "Invalid DO address",
    "error_code": "INVALID_ADDR"
  }
}
```
### 2.4. comm_settings_control (통신 설정 테스트 제어)
**DO Command (UI → Logic)**
* **device**: `robot`,`binpick`,`remote_io`,`tensile_tester`,`qr_reader`,`dial_gauge`
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-commtest-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "comm_test",
    "action": "test",
    "device": "robot"
  }
}
```
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.080"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-commtest-cmd-001",
    "status": "ok",
    "reason": "comm_test accepted",
    "data": {
      "device": "robot"
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.080"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-commtest-cmd-001",
    "status": "error",
    "reason": "Unsupported device",
    "error_code": "INVALID_DEVICE"
  }
}
```

### 2.5. recover_settings_control (복구 설정 제어)
**DO Command (UI → Logic)**
* **action**: `error`,`auto`,`manual`
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-recover-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "recover",
    "action": "error",
  }
}
```
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.090"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-recover-cmd-001",
    "status": "ok",
    "reason": "Recover sequence accepted",
    "data": {
      "action": "error"
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.090"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-recover-cmd-001",
    "status": "error",
    "reason": "Recovery not available",
    "error_code": "RECOVER_UNAVAILABLE"
  }
}
```
### 2.6. robot_settings_control (로봇 설정 제어)
**DO Command (UI → Logic)**
* **target**: `robot_direct_teaching_mode`,`gripper`,`robot_home`
* **target**: `disable`,`enable` / `close`,`open`
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-robot-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "robot_control",
    "action": "disable",
    "target": "robot_direct_teaching_mode",
  }
}
```
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.095"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-robot-cmd-001",
    "status": "ok",
    "reason": "Robot control accepted",
    "data": {
      "target": "robot_direct_teaching_mode",
      "action": "disable"
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.095"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-robot-cmd-001",
    "status": "error",
    "reason": "Robot control rejected",
    "error_code": "ROBOT_UNAVAILABLE"
  }
}
```
### 2.7. data_control (공정 데이터 관리)
**인장시험 공정 데이터 관리 Command (UI → Logic)**
* **action**: `save`,`reset`
```json
{
  "header": {
    "msg_type": "ui.command",
    "source": "ui",
    "target": "logic",
    "msg_id": "ui-data-cmd-001",
    "ack_required": true,
    "timestamp": "2025-11-18T12:00:00.000"
  },
  "payload": {
    "kind": "command",
    "cmd": "data",
    "action": "save",
  }
}
```
**ACK (Logic → UI)** /OK
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.100"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-data-cmd-001",
    "status": "ok",
    "reason": "Batch plan saved",
    "data": {
      "action": "save"
    }
  }
}
```
**ACK (Logic → UI)** /ERROR
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-ack-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:00:00.100"
  },
  "payload": {
    "kind": "ack",
    "ack_of": "ui-data-cmd-001",
    "status": "error",
    "reason": "Batch data reset",
    "error_code": "DATA_RESET"
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

본 항목은 Logic 시스템이 UI로 주기적으로 발행하는 상태 보고 메시지들을 정의합니다. 이 메시지들은 UI가 별도의 요청 없이 시스템의 실시간 상태를 파악할 수 있도록 하며, `system_dio_status`(디지털 입출력 상태), `system_status`(장비별 통신 상태), `process_status`(상세 공정 상태)로 구성됩니다.

### 4.0. 상태 보고 요약 테이블

| **Event Name** | **설명** | **주요 Payload 필드** |
| :--- | :--- | :--- |
| `system_dio_status` | 디지털 입/출력(DIO)의 전체 상태를 배열 형태로 보고합니다. | `di_values`, `do_values` |
| `system_status` | 로봇, 시험기 등 각 하드웨어 장비의 통신 연결 상태와 로봇의 현재 위치, 동작 등 상세 상태를 함께 보고합니다. | `process`, `system_entire_states`, `system_state` |
| `process_status` | 상세 공정 상태를 보고합니다. `system_status`(전체 공정), `tester_status`, `robot_status` 등 주요 상태 필드는 각 FSM(Logic/Device/Robot)에서 정의된 문자열 상태 값을 전달합니다. | `batch_info`, `current_specimen_info`, `tester_status`, `robot_status`, `aligner_status` |

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
    "system_state": {
      "robot": {
        "conntion_info" : "192.168.2.20",
        "state" : 1,
        "comm_state" : 1,
        "current_pos" : 0,
        "current_motion" : 100,
        "recover_motion" : 1103,
        "direct_teaching_mode" : 1,
        "program_run" : 1,
        "gripper_state" : 1,
        "msg" : ""
      },
      "shimadzu": {
        "conntion_info" : "192.168.2.100",
        "state" : 1,
        "msg" : ""
      },
      "remote_io": {
        "conntion_info" : "192.168.2.40",
        "state" : 1,
        "msg" : ""
      },
      "qr_reader": {
        "conntion_info" : "192.168.2.41",
        "state" : 1,
        "msg" : ""
      },
      "dial_gauge": {
        "conntion_info" : "COM5",
        "state" : 1,
        "msg" : ""
      },
      "binpick": {
        "conntion_info" : "192.168.2.30",
        "state" : 1,
        "msg" : ""
      }
    }
  }
}
```
### 4.3. LOGIC → UI 시스템 작업 상태 (process_status)
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
    "evt": "process_status",
    "batch_info": {
      "batch_id": "B-20251225-001",
      "status": "진행"
    },
    "runtime" : {
      "starttime" : "12:07:01.000",
      "elapsedtime" : "00:05:15.000"
    },
    "current_process_tray_info": {
      "tray_num": 3,
      "specimen_num": 2
    },
    "system_status": "시편 잡기",
    "tester_status": "대기",
    "robot_status": "모션중",
    "thickness_measurement": {
      "current": 15.01,
      "previous": 14.99,
      "registered": 15.00
    },
    "aligner_status": "정렬중"
    
  }
}
```

### 4.4. LOGIC → UI 공정 완료 상태 전달
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-proc-completed-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:20:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "process_completed",
    "reason": "All processes for the batch have been successfully completed.",
    "data": {
      "batch_id": "B-20251208-001",
      "total_completed": 10
    }
  }
}
```

### 4.5. LOGIC → UI 공정 중 정지(UI-STOP명령) 완료 상태 전달
UI의 `stop` 명령에 따라 공정이 즉시 중단된 후, Logic이 UI에게 정지가 완료되었음을 알리는 이벤트입니다.
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-proc-stopped-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:10:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "process_stopped",
    "reason": "The process was successfully stopped by user command.",
    "data": {
      "batch_id": "B-20251208-001"
    }
  }
}
```

### 4.6. LOGIC → UI 공정 중 단계정지(UI-STEP STOP명령) 완료 상태 전달
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-proc-stopped-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:10:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "process_step_stopped",
    "reason": "The process was successfully stopped by user command.",
    "data": {
      "batch_id": "B-20251208-001"
    }
  }
}
```

## 5. 시스템 오류 및 이벤트 보고 (UI 팝업)

본 항목은 Logic 시스템이 로봇, 장비 등에서 발생한 심각한 오류나 주요 이벤트를 UI에 전달하여 사용자에게 팝업으로 알릴 때 사용하는 메시지를 정의합니다. 이를 통해 운영자는 시스템의 예외 상황을 즉시 인지하고 필요한 조치를 취할 수 있습니다.

### 5.1. LOGIC → UI 오류 이벤트 (system_error_event)

Logic은 시스템의 치명적인 오류(예: 공압 공급 중단, 로봇 충돌)가 감지되면 `system_error_event`를 UI로 즉시 발행합니다. UI는 이 메시지를 수신하면 사용자에게 오류 내용과 권장 조치를 담은 팝업을 표시해야 합니다.

### 5.2. 주요 필드 설명

| 필드명 | 설명 | 예시 |
| :--- | :--- | :--- |
| `error_source` | 오류가 발생한 주요 모듈을 명시합니다. | `device`, `robot`, `logic` |
| `error_code` | `constants.py`에 정의된 `DeviceViolation` 또는 `RobotViolation`과 같은 구체적인 오류 코드입니다. | `SOL_SENSOR_ERR`, `COLLISION_VIOLATION` |
| `error_message` | UI에 표시될 사용자 친화적인 오류 메시지입니다. | "로봇 충돌이 감지되었습니다." |
| `severity` | 오류의 심각도를 나타냅니다. `critical`은 시스템 정지를 의미할 수 있습니다. | `critical`, `warning` |
| `recommended_action` | 사용자에게 권장되는 조치 사항입니다. | "주 공압 공급 라인을 확인하세요." |

### 5.3. 주요 오류 코드 및 메시지 정의

시스템에서 발생할 수 있는 주요 치명적 오류(Critical) 목록입니다.

| Error Source | Error Code | Error Message (Example) | Recommended Action |
| :--- | :--- | :--- | :--- |
| `device` | `SOL_SENSOR_ERR` | 솔레노이드 밸브 공압 공급 오류가 감지되었습니다. | 주 공압 공급 라인을 확인한 후 리셋 버튼을 누르세요. |
| `robot` | `COLLISION_VIOLATION` | 로봇 충돌이 감지되었습니다. | 로봇을 안전한 위치로 수동 이동시킨 후 복구 시퀀스를 진행하세요. |
| `robot` | `ROBOT_SINGULARITY_ERR` | 로봇이 특이점(Singularity) 자세에 도달했습니다. | 로봇 자세를 확인하고 티칭 포인트를 수정하거나 수동으로 이동시키세요. |
| `device` | `REMOTE_IO_COMM_ERR` | Remote I/O 장치와의 통신이 두절되었습니다. | Remote I/O 전원 및 LAN 케이블 연결 상태를 확인하세요. |
| `device` | `QR_COMM_ERR` | QR 리더기와의 통신이 두절되었습니다. | QR 리더기 전원 및 시리얼/LAN 연결을 확인하세요. |
| `device` | `QR_READ_FAIL` | QR 코드를 읽는데 실패했습니다. (최대 횟수 초과) | 시편의 QR 코드 상태를 확인하거나 조명을 조절해주세요. |
| `device` | `GAUGE_COMM_ERR` | 변위 측정기(Gauge)와의 통신이 두절되었습니다. | 측정기 전원 및 케이블 연결을 확인하세요. |
| `device` | `GAUGE_MEASURE_FAIL` | 측정기로부터 유효한 값을 읽어오지 못했습니다. | 측정기 디스플레이 상태를 확인하고 재시도하세요. |
| `device` | `SMZ_COMM_ERR` | 시마즈(Shimadzu) 시험기와의 통신이 두절되었습니다. | 시험기 PC 소프트웨어 실행 여부 및 통신 설정을 확인하세요. |
| `device` | `SMZ_COMM_CONTROL_ERROR` | 시마즈(Shimadzu) 시험기 제어 명령이 실패하였습니다. | 시험기 PC 소프트웨어 실행 여부 및 통신 설정을 확인하세요. |

### 5.4. 주요 오류 코드 및 메세지 예시

**오류 이벤트 메시지 예시 (COLLISION_VIOLATION)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-002",
    "ack_required": false,
    "timestamp": "2025-11-18T12:35:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "robot",
    "error_code": "COLLISION_VIOLATION",
    "error_message": "로봇 충돌이 감지되었습니다.",
    "severity": "critical",
    "recommended_action": "로봇을 안전한 위치로 수동 이동시킨 후 복구 시퀀스를 진행하세요."
  }
}
```

**오류 이벤트 메시지 예시 (ROBOT_SINGULARITY_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-003",
    "ack_required": false,
    "timestamp": "2025-11-18T12:36:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "robot",
    "error_code": "ROBOT_SINGULARITY_ERR",
    "error_message": "로봇이 특이점(Singularity) 자세에 도달했습니다.",
    "severity": "critical",
    "recommended_action": "로봇 자세를 확인하고 티칭 포인트를 수정하거나 수동으로 이동시키세요."
  }
}
```

**오류 이벤트 메시지 예시 (SOL_SENSOR_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-001",
    "ack_required": false,
    "timestamp": "2025-11-18T12:30:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "SOL_SENSOR_ERR",
    "error_message": "솔레노이드 밸브 공압 공급 오류가 감지되었습니다.",
    "severity": "critical",
    "recommended_action": "주 공압 공급 라인을 확인한 해주세요."
  }
}
```

**오류 이벤트 메시지 예시 (REMOTE_IO_COMM_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-004",
    "ack_required": false,
    "timestamp": "2025-11-18T12:40:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "REMOTE_IO_COMM_ERR",
    "error_message": "Remote I/O 장치와의 통신이 두절되었습니다.",
    "severity": "critical",
    "recommended_action": "Remote I/O 전원 및 LAN 케이블 연결 상태를 확인하세요."
  }
}
```

**오류 이벤트 메시지 예시 (QR_COMM_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-005",
    "ack_required": false,
    "timestamp": "2025-11-18T12:41:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "QR_COMM_ERR",
    "error_message": "QR 리더기와의 통신이 두절되었습니다.",
    "severity": "critical",
    "recommended_action": "QR 리더기 전원 및 시리얼/LAN 연결을 확인하세요."
  }
}
```

**오류 이벤트 메시지 예시 (QR_READ_FAIL)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-006",
    "ack_required": false,
    "timestamp": "2025-11-18T12:42:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "QR_READ_FAIL",
    "error_message": "QR 코드를 읽는데 실패했습니다. (최대 횟수 초과)",
    "severity": "warning",
    "recommended_action": "시편의 QR 코드 상태를 확인하거나 조명을 조절해주세요."
  }
}

```

**오류 이벤트 메시지 예시 (GAUGE_COMM_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-007",
    "ack_required": false,
    "timestamp": "2025-11-18T12:43:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "GAUGE_COMM_ERR",
    "error_message": "변위 측정기(Gauge)와의 통신이 두절되었습니다.",
    "severity": "critical",
    "recommended_action": "측정기 전원 및 케이블 연결을 확인하세요."
  }
}
```

**오류 이벤트 메시지 예시 (GAUGE_MEASURE_FAIL)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-008",
    "ack_required": false,
    "timestamp": "2025-11-18T12:44:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "GAUGE_MEASURE_FAIL",
    "error_message": "측정기로부터 유효한 값을 읽어오지 못했습니다.",
    "severity": "warning",
    "recommended_action": "측정기 디스플레이 상태를 확인하고 재시도하세요."
  }
}
```

**오류 이벤트 메시지 예시 (SMZ_COMM_ERR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-009",
    "ack_required": false,
    "timestamp": "2025-11-18T12:45:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "SMZ_COMM_ERR",
    "error_message": "시마즈(Shimadzu) 시험기와의 통신이 두절되었습니다.",
    "severity": "critical",
    "recommended_action": "시험기 PC 소프트웨어 실행 여부 및 통신 설정을 확인하세요."
  }
}
```

**오류 이벤트 메시지 예시 (SMZ_COMM_CONTROL_ERROR)**
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-009",
    "ack_required": false,
    "timestamp": "2025-11-18T12:45:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "system_error_event",
    "error_source": "device",
    "error_code": "SMZ_COMM_ERR",
    "error_message": "시마즈(Shimadzu) 시험기 제어 명령이 실패하였습니다.",
    "severity": "critical",
    "recommended_action": "시험기 PC 소프트웨어 실행 여부 및 통신 설정을 확인하세요."
  }
}
```

## 6. JSON 데이터 모델 명세

### 6.1. system_states 배열 (system_status)

[0]: Robot Comm (1:OK)
[1]: Shimadzu Device Comm (1:OK)
[2]: Gauge Comm
[3]: Remote IO Comm
[4]: QR Reader Comm
[5]: Vision Comm

### 6.2. robot_pose 구조

x, y, z, rx, ry, rz (단위: mm, degree)
```
