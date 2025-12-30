# 로봇 모션 명령 정의 (Command.md)

이 문서는 `logic_fsm`에서 사용하는 상위 레벨 모션 명령(`MotionCommand`)과 `robot_fsm`이 실제 로봇을 구동하기 위해 사용하는 하위 레벨 정수 명령(`RobotMotionCommand`) 간의 매핑을 정의합니다.

- **Logic Command**: `logic_context.py`에서 사용하는 `MotionCommand` Enum 멤버입니다.
- **Robot Command**: `robot_context.py`의 `get_motion_cmd` 함수를 통해 변환되는 `RobotMotionCommand` Enum 멤버입니다.
- **CMD ID**: 로봇 컨트롤러(Conty)에 실제로 전송되는 정수 값입니다.
- **설명**: 해당 명령이 수행하는 동작에 대한 설명입니다.

---

### 명령 핸드셰이크 프로토콜 (Handshake Protocol)

`Logic`과 로봇 컨트롤러(`Conty`)는 정수 변수를 사용하여 명령을 주고받습니다. 이 통신은 다음과 같은 핸드셰이크 과정을 따릅니다.

1.  **명령 전송**: `Logic`이 `CMD` 변수에 실행할 모션의 `CMD ID`를 씁니다.
2.  **수신 확인 (ACK)**: `Conty`가 `CMD`를 읽고, `CMD_ack` 변수에 `CMD ID + 500` 값을 써서 수신했음을 알립니다. `Logic`은 이 `ACK`를 확인하면 `CMD` 값을 0으로 리셋합니다.
3.  **동작 완료 (Complete)**: `Conty`가 모션 실행을 완료하면, `CMD_done` 변수에 `CMD ID + 10000` 값을 씁니다.
4.  **초기화**: `Logic`은 `CMD_done`을 확인한 후, 다음 명령을 위해 `CMD_Init` 변수를 `True`로 설정하여 `Conty`가 `CMD_ack`와 `CMD_done`을 초기화하도록 요청합니다.

| 변수 (Variable) | 주소 (Address) | 방향 (Direction) | 설명 (Description) | 값 계산 (Value Calculation) |
|---|---|---|---|---|
| `CMD` | 600 | Logic → Conty | 실행할 모션의 `CMD ID`를 전달합니다. | - |
| `CMD_ack` | 610 | Conty → Logic | `CMD`를 정상적으로 수신했음을 알립니다. | `CMD ID` + 500 |
| `CMD_done` | 700 | Conty → Logic | 요청된 모션이 완료되었음을 알립니다. | `CMD ID` + 10000 |
| `CMD_Init` | 770 (Bool) | Logic → Conty | `CMD_ack`와 `CMD_done`을 0으로 초기화하도록 요청합니다. | `True` (1) |

---

### ACT01: 시편 랙 (Specimen Rack)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_RACK` | `RACK_FRONT_MOVE` | 1000 | 시편 랙의 정면으로 이동합니다. |
| `MOVE_TO_QR_SCAN_POS` | `get_rack_nF_QR_scan_pos_cmd(floor)` | 13n0 | 지정된 층(`n`)의 QR 스캔 위치로 이동합니다. |
| `PICK_SPECIMEN_FROM_RACK` | `get_rack_nF_sample_N_pos_cmd(floor, num)` | 10nN | 지정된 층(`n`)의 `N`번째 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_RACK` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_RACK` | `get_rack_nF_front_return_cmd(floor)` | 20n0 | 지정된 층(`n`)에서 작업 후 랙 정면으로 복귀합니다. |

---

### ACT02: 치수 측정기 (Indicator)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_INDICATOR` | `THICK_GAUGE_FRONT_MOVE` | 3000 | 치수 측정기 정면으로 이동합니다. |
| `PLACE_SPECIMEN_AND_MEASURE` | `THICK_GAUGE_SAMPLE_n_PLACE` | 3001~3003 | 지정된 위치(`n`)에 시편을 내려놓습니다. |
| `GRIPPER_OPEN_AT_INDICATOR` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_INDICATOR_AFTER_PLACE` | `THICK_GAUGE_FRONT_RETURN_n` | 4000~4002 | 시편을 내려놓은 후, 지정된 위치(`n`)에서 후퇴합니다. |
| `PICK_SPECIMEN_FROM_INDICATOR` | `THICK_GAUGE_SAMPLE_n_PICK` | 3011~3013 | 지정된 위치(`n`)의 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_INDICATOR` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_INDICATOR_AFTER_PICK` | `THICK_GAUGE_FRONT_RETURN_n` | 4000~4002 | 시편을 집은 후, 지정된 위치(`n`)에서 후퇴합니다. |

---

### ACT03: 시편 정렬기 (Aligner)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_ALIGN` | `ALIGNER_FRONT_MOVE` | 5000 | 시편 정렬기 정면으로 이동합니다. |
| `PLACE_SPECIMEN_ON_ALIGN` | `ALIGNER_SAMPLE_PLACE` | 5001 | 정렬기에 시편을 내려놓습니다. |
| `GRIPPER_OPEN_AT_ALIGN` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_ALIGN_AFTER_PLACE` | `ALIGNER_FRONT_RETURN` | 6000 | 시편을 내려놓은 후 정렬기에서 후퇴합니다. |
| `PICK_SPECIMEN_FROM_ALIGN` | `ALIGNER_SAMPLE_PICK` | 5011 | 정렬된 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_ALIGN` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_ALIGN_AFTER_PICK` | `ALIGNER_FRONT_RETURN` | 6000 | 시편을 집은 후 정렬기에서 후퇴합니다. |

---

### ACT04: 인장 시험기 (Tensile Machine) - 장착

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_TENSILE_MACHINE_FOR_LOAD` | `TENSILE_FRONT_MOVE` | 7000 | 인장 시험기 정면으로 이동합니다. |
| `LOAD_TENSILE_MACHINE` | `TENSILE_SAMPLE_PLACE_POS_DOWN` | 7001 | 시편을 인장 시험기 하단에 장착합니다. |
| `GRIPPER_OPEN_AT_TENSILE_MACHINE` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD` | `TENSILE_FRONT_RETURN` | 8000 | 시편 장착 후 인장 시험기에서 후퇴합니다. |

---

### ACT05: 인장 시험기 (Tensile Machine) - 수거

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_TENSILE_MACHINE_FOR_PICK` | `TENSILE_FRONT_MOVE` | 7000 | 인장 시험기 정면으로 이동합니다. |
| `PICK_FROM_TENSILE_MACHINE` | `TENSILE_SAMPLE_PICK_POS_UP/DOWN` | 7012/7011 | 인장 시험기 상단(`1`)/하단(`2`)에서 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_TENSILE_MACHINE` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK` | `TENSILE_FRONT_RETURN` | 8000 | 시편 수거 후 인장 시험기에서 후퇴합니다. |

---

### ACT06: 스크랩 처리기 (Scrap Disposer)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_SCRAP_DISPOSER` | `SCRAP_FRONT_MOVE` | 7020 | 스크랩 처리기 정면으로 이동합니다. |
| `PLACE_IN_SCRAP_DISPOSER` | `SCRAP_DROP_POS` | 7021 | 스크랩 처리기에 시편을 버립니다. |
| `GRIPPER_OPEN_AT_SCRAP_DISPOSER` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_SCRAP_DISPOSER` | `SCRAP_FRONT_RETURN` | 7022 | 스크랩 처리기에서 후퇴합니다. |

---

### ACT07: 홈 (Home)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_HOME` | `RECOVERY_HOME` | 100 | 로봇을 초기 위치(Home)로 복귀시킵니다. |