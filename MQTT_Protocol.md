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
        "current_pos" : 0,
        "current_motion" : 100,
        "recover_motion" : 1103,
        "direct_teaching_mode" : 1,
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
      "sequence_info": 3,
      "status": 2,
      "test_standard": "",
      "dimensions": [300, 200]
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

## 5. JSON 데이터 모델 명세

### 5.1. system_states 배열 (system_status)
*   `[0]`: Robot Comm (1:OK)
*   `[1]`: Shimadzu Device Comm (1:OK)
*   `[2]`: Gauge Comm
*   `[3]`: RIO Comm
*   `[4]`: QR Reader Comm
*   `[5]`: Vision Comm

### 5.2. robot_pose 구조
*   `x`, `y`, `z`, `rx`, `ry`, `rz` (단위: mm, degree)