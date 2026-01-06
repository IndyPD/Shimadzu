# MQTT Error Event Guide

- Topic: `/logic/evt`
- Frame: `header` + `payload` (same envelope as MQTT_Protocol.md)
- Purpose: Logic publishes error events to UI (20 codes across device/shimadzu/robot).

## Minimal Error Message
```json
{
  "header": {
    "msg_type": "logic.event",
    "source": "logic",
    "target": "ui",
    "msg_id": "logic-evt-error-001",
    "ack_required": false,
    "timestamp": "2026-01-06T12:00:00.000"
  },
  "payload": {
    "kind": "event",
    "evt": "error",
    "category": "device | shimadzu | robot",
    "code": "D-001",
    "message": "공압 공급 끊김"
  }
}
```

## Error Code List
### device
| code  | message                     | detail (optional)                         |
|-------|-----------------------------|-------------------------------------------|
| D-001 | 공압 공급 X                 | Pneumatic supply lost                     |
| D-002 | 센서 remote IO 연결 X       | Remote IO for sensor not connected        |
| D-003 | remote IO 연결 후 통신 X    | IO connected but no communication         |
| D-004 | QR 통신 연결 X              | QR reader communication lost              |
| D-005 | QR 인식 X                   | QR read failed                            |
| D-006 | 측정기 연결 X               | Measurement device not connected          |
| D-007 | 측정기 측정 X               | Measurement device read failed            |
| D-008 | 신율계 전후진 X             | Extensometer forward/backward failed      |
| D-009 | 정렬기 정렬 X               | Aligner failed to align                   |
| D-010 | 툴체인저 센서 오류 ATC1     | Tool changer sensor error ATC1            |
| D-011 | 툴체인저 센서 오류 ATC2     | Tool changer sensor error ATC2            |
| D-012 | 비상정지 버튼               | Emergency stop button pressed             |
| D-013 | 스크랩 처리기 열림 → 로봇 정지 | Scrap processor open; robot halted        |

### shimadzu
| code  | message                          | detail (optional)                           |
|-------|----------------------------------|---------------------------------------------|
| S-001 | 시마즈 통신 연결 문제            | Shimadzu connection lost                    |
| S-002 | 통신O, 데이터 송수신 오류        | Shimadzu command/response mismatch          |
| S-003 | 측정기 그리퍼 파지 실패          | Shimadzu gripper failed to hold specimen    |

### robot
| code  | message                   | detail (optional)                           |
|-------|---------------------------|---------------------------------------------|
| R-001 | 로봇 상태 이상 (opstate)  | Robot in unexpected state/opstate           |
| R-002 | 그리퍼 파지 실패          | Gripper failed to pick                      |
| R-003 | 그리퍼 제어 실패          | Gripper control command failed              |
| R-004 | 모션 타임아웃 (로봇)      | Robot motion timeout                        |
| R-005 | 모션 타임아웃 (그리퍼)    | Gripper motion timeout                      |

## Usage Notes
- `msg_id`: use prefix `logic-evt-error-###`.
- Only `code`/`message` are required; add `detail` if helpful.
- UI can map `code` to localized strings; keep `message` short and user-facing.
