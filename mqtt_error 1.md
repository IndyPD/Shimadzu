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
    "status" : "Auto | Manual",
    "category": "device | shimadzu | robot",
    "code": "D-001",
    "message": "공압 공급 이상"
  }
}
```
Status가 Auto면 시험중 / Manual이면 수동조작상태
 
## Error Code List
### device
| code  | message                     | detail (optional)                                   |
|-------|-----------------------------|-----------------------------------------------------|
| D-001 | 공압 공급 이상              | Pneumatic supply lost or insufficient               |
| D-002 | 센서 Remote IO 연결 실패    | Sensor remote IO connection failed                  |
| D-003 | Remote IO 통신 실패         | Remote IO connected but communication failed        |
| D-004 | QR 리더 통신 실패           | QR reader communication lost                        |
| D-005 | QR 인식 실패                | QR code recognition failed                          |
| D-006 | 측정기 연결 실패            | Measurement device not connected                    |
| D-007 | 측정기 측정 실패            | Measurement device read failed                      |
| D-008 | 신율계 구동 실패            | Extensometer forward/backward motion failed         |
| D-009 | 정렬기 정렬 실패            | Aligner alignment failed                            |
| D-010 | 툴체인저 1 센서 오류        | Tool changer 1 sensor error detected                |
| D-011 | 툴체인저 2 센서 오류        | Tool changer 2 sensor error detected                |
| D-012 | 비상정지 버튼 작동          | Emergency stop button activated                     |
| D-013 | 스크랩 처리기 열림 감지     | Scrap processor open detected; robot halted         |
 
### shimadzu
| code  | message                          | detail (optional)                           |
|-------|----------------------------------|---------------------------------------------|
| T-001 | 시마즈 장비 통신 끊김            | Shimadzu device communication lost          |
| T-002 | 시마즈 장비 데이터 송수신 오류   | Shimadzu device command/response error      |
| T-003 | 시마즈 장비 그리퍼 파지 실패     | Shimadzu device gripper failed to hold specimen |
 
### robot
| code  | message                   | detail (optional)                           |
|-------|---------------------------|---------------------------------------------|
| R-001 | 로봇 상태 이상            | Robot entered an unexpected operating state |
| R-002 | 로봇 그리퍼 파지 실패     | Robot gripper failed to pick specimen       |
| R-003 | 로봇 그리퍼 제어 실패     | Robot gripper control command failed        |
| R-004 | 로봇 모션 타임아웃        | Robot motion execution timeout              |
| R-005 | 로봇 그리퍼 모션 타임아웃 | Robot gripper motion timeout                |
 
 
 
## Usage Notes
- `msg_id`: use prefix `logic-evt-error-###`.
- Only `code`/`message` are required; add `detail` if helpful.
- UI can map `code` to localized strings; keep `message` short and user-facing.
 