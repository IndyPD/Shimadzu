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

### 명령 ACK 기반 로봇 위치 판단 (Robot Position based on ACK)

`Logic` 모듈이 로봇으로부터 `CMD_ack`를 수신하면, 이는 로봇이 해당 명령을 인지하고 동작을 시작했음을 의미합니다. 아래 표는 각 `CMD ID`에 대한 `ACK` 수신 시점의 로봇의 예상 위치 또는 상태를 정의합니다. 이 정보를 통해 `Logic`은 로봇의 현재 상태를 추정하고 다음 단계를 준비할 수 있습니다.

| ID | 정지 시 시편 버리기 | `CMD ID` 범위 (Range) | `CMD_ack` 값 (Value) | 로봇 위치/상태 (Robot Position/State) | 설명 (Description) |
|:---|:---|:---|:---|:---|:---|
| M1 | X | 1000 | 1500 | 랙 정면으로 이동 중 | 홈 또는 다른 위치에서 시편 랙 정면으로 이동을 시작합니다. |
| M2 | X | 1310 ~ 1400 | 1810 ~ 1900 | QR 스캔 위치로 이동 중 | 랙 정면에서 지정된 층의 QR 코드를 스캔하기 위한 위치로 이동합니다. |
| M3 | X | 1010 ~ 1100 | 1510 ~ 1600 | 작업 대상 랙 층으로 이동 | 랙 정면에서 지정된 층의 시편을 집기 위해 접근합니다. |
| M4 | X | 1011 ~ 1105 | 1511 ~ 1605 | 특정 시편으로 접근 중 | 랙 정면에서 지정된 층/번호의 시편을 집기 위해 접근합니다. |
| M5 | O | 2000 | 2500 | 랙 앞 복귀 위치로 이동 중 | 랙의 특정 층에서 작업 후, 랙 앞 중간 지점으로 복귀합니다. |
| M6 | O | 2010 ~ 2100 | 2510 ~ 2600 | 랙의 특정 층에서 후퇴 중 | 시편을 집은 후, 해당 층에서 랙 정면 위치로 후퇴합니다. |
| M7 | O | 3000 | 3500 | 두께 측정기 정면으로 이동 중 | 랙 앞 복귀 위치에서 두께 측정기 정면으로 이동합니다. |
| M8 | O | 3001 ~ 3003 | 3501 ~ 3503 | 두께 측정기에 시편을 놓는 중 | 두께 측정기 정면에서 지정된 측정 포인트(1~3)로 이동하여 시편을 내려놓습니다. |
| M9 | O | 3011 ~ 3013 | 3511 ~ 3513 | 두께 측정기에서 시편을 집는 중 | 두께 측정기 정면에서 지정된 측정 포인트(1~3)에 놓인 시편을 집기 위해 접근합니다. |
| M10 | O | 4000 ~ 4002 | 4500 ~ 4502 | 두께 측정기에서 후퇴 중 | 시편을 놓거나 집은 후, 두께 측정기 정면 위치로 후퇴합니다. (시편 회수 필요) |
| M11 | O | 5000 | 5500 | 정렬기 정면으로 이동 중 | 두께 측정기 앞 복귀 위치에서 정렬기 정면으로 이동합니다. |
| M12 | O | 5001 | 5501 | 정렬기에 시편을 놓는 중 | 정렬기 정면에서 시편을 내려놓기 위한 위치로 이동합니다. |
| M13 | O | 5011 | 5511 | 정렬기에서 시편을 집는 중 | 정렬기 정면에서 정렬된 시편을 집기 위해 접근합니다. |
| M14 | O | 5012 | 5512 | 정렬기 앞에서 대기 위치로 이동 중 | 시편을 정렬기에 놓은 후, 인장기가 사용 중일 때 정렬기 앞 대기 위치로 이동합니다. (시편 회수 필요) |
| M15 | O | 6000 | 6500 | 정렬기에서 후퇴 중 | 시편을 놓거나 집은 후, 정렬기 정면 위치로 후퇴합니다. (시편 회수 필요) |
| M16 | O | 7000 | 7500 | 인장 시험기 정면으로 이동 중 | 정렬기 앞 복귀 위치에서 인장 시험기 정면으로 이동합니다. |
| M17 | O | 7001, 7002 | 7501, 7502 | 인장 시험기에 시편을 장착하는 중 | 인장 시험기 정면에서 시편을 하단/상단 척에 장착하기 위해 접근합니다. |
| M18 | O | 7011, 7012 | 7511, 7512 | 인장 시험기에서 시편을 수거하는 중 | 인장 시험기 정면에서 파단된 시편을 하단/상단 척에서 수거하기 위해 접근합니다. |
| M19 | O | 7020 | 7520 | 스크랩 처리기로 이동 중 | 인장 시험기 앞 복귀 위치에서 스크랩 처리기 정면으로 이동합니다. |
| M20 | O | 7021 | 7521 | 스크랩 처리기에 시편을 버리는 중 | 스크랩 처리기 정면에서 시편을 버리기 위한 위치로 이동합니다. |
| M21 | X | 7022 | 7522 | 스크랩 처리기에서 후퇴 중 | 시편을 버린 후, 스크랩 처리기 정면 위치로 후퇴합니다. |
| M22 | O | 8000 | 8500 | 인장 시험기에서 후퇴 중 | 시편을 장착하거나 수거한 후, 인장 시험기 정면 위치로 후퇴합니다. (수거 후에는 회수 필요) |

---

### ACT00: 기본 이동 명령 (Basic Movement Commands)

| 모션명 | 사용 | 모션 변수명 | Motion CMD | Motion ACK | Motion Done | 시작 위치 | 목표 위치 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 홈-렉 앞 이동 | O | home_rack_front | 1 | 501 | 10001 | H | AA |
| 홈-툴 앞 이동 | O | home_tool_front | 2 | 502 | 10002 | H | TA |
| 홈-측정기 앞 이동 | O | home_thick_gauge_front | 3 | 503 | 10003 | H | BA |
| 홈-정렬기 앞 이동 | O | home_aligner_front | 4 | 504 | 10004 | H | CA |
| 홈-인장시험기 앞 이동 | O | home_tensile_tester_front | 5 | 505 | 10005 | H | DA |
| 홈-스크랩 배출 앞 이동 | O | home_scrap_disposer_front | 6 | 506 | 10006 | H | FA |
| 렉 앞 - 홈 이동 | O | rack_front_home | 21 | 521 | 10021 | AA | H |
| 툴 앞 - 홈 이동 | O | tool_front_home | 22 | 522 | 10022 | TA | H |
| 측정기 앞 - 홈 이동 | O | thick_gauge_front_home | 23 | 523 | 10023 | BA | H |
| 정렬기 앞 - 홈 이동 | O | aligner_front_home | 24 | 524 | 10024 | CA | H |
| 인장시험기 앞 - 홈 이동 | O | tensile_tester_front_home | 25 | 525 | 10025 | DA | H |
| 스크랩 배출 앞 - 홈 이동 | O | scrap_disposer_front_home | 26 | 526 | 10026 | FA | H |

---

### 후퇴 및 홈 복귀 시퀀스 (Retreat and Home Sequence)

로봇이 특정 위치에서 작업을 중단하고 안전하게 홈 위치로 복귀해야 할 때 사용되는 개념적인 시퀀스입니다. "후퇴" 동작은 로봇의 현재 위치에 따라 달라지며, 후퇴 후에는 `MOVE_TO_HOME` (CMD ID: 100) 명령을 통해 홈으로 복귀합니다. 이 로직은 `logic_context.py`의 `execute_controlled_stop` 함수에서 관리됩니다.

| 현재 위치 (Current Position) | 후퇴 명령 (Retreat Command) | CMD ID | 다음 동작 (Next Action) |
| :--- | :--- | :--- | :--- |
| 랙 (시편 취급 중) | `RETREAT_FROM_RACK` | 20n0 | `rack_front_home` |
| 두께 측정기 | `RETREAT_FROM_INDICATOR_AFTER_PICK` | 4000~4002 | `thick_gauge_front_home` |
| 정렬기 | `RETREAT_FROM_ALIGN_AFTER_PICK` | 6000 | `home_aligner_front` |
| 인장 시험기 | `RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK` | 8000 | `tensile_tester_front_home` |
| 스크랩 처리기 | `RETREAT_FROM_SCRAP_DISPOSER` | 7022 | `scrap_disposer_front_home` |

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

### ACT06: STOP 명령 후 이동 시퀀스 (Stop Command Sequence)

`STOP` 명령 수신 시, 로봇의 현재 상태에 따라 안전하게 시편을 회수 및 폐기하고 홈 위치로 복귀하는 제어된 정지 시퀀스입니다. 이 시퀀스는 `logic_context.py`의 `execute_controlled_stop` 함수에 의해 관리됩니다.

#### 1. 시편 회수 (두께 측정기)
로봇이 시편을 두께 측정기에 내려놓은 상태에서 `STOP` 명령을 받으면 다음 순서로 시편을 회수합니다.

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `PICK_SPECIMEN_FROM_INDICATOR` | `THICK_GAUGE_SAMPLE_n_PICK` | 3011~3013 | 두께 측정기의 지정된 위치(`n`)에서 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_INDICATOR` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_INDICATOR_AFTER_PICK` | `THICK_GAUGE_FRONT_RETURN_n` | 4000~4002 | 시편을 집은 후, 지정된 위치(`n`)에서 후퇴합니다. |

#### 2. 시편 회수 (정렬기)
로봇이 시편을 정렬기에 내려놓은 상태에서 `STOP` 명령을 받으면 다음 순서로 시편을 회수합니다.

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `PICK_SPECIMEN_FROM_ALIGN` | `ALIGNER_SAMPLE_PICK` | 5011 | 정렬된 시편을 집기 위해 접근합니다. |
| `GRIPPER_CLOSE_FOR_ALIGN` | `GRIPPER_CLOSE` | 91 | 로봇 그리퍼를 닫습니다. |
| `RETREAT_FROM_ALIGN_AFTER_PICK` | `ALIGNER_FRONT_RETURN` | 6000 | 시편을 집은 후 정렬기에서 후퇴합니다. |

#### 3. 스크랩 처리
로봇이 시편을 들고 있는 상태(회수 포함)에서 `STOP` 명령을 받으면 다음 순서로 스크랩을 처리합니다. 이 시퀀스는 아래 `ACT07`과 동일합니다.

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_SCRAP_DISPOSER` | `SCRAP_FRONT_MOVE` | 7020 | 스크랩 처리기 정면으로 이동합니다. |
| `PLACE_IN_SCRAP_DISPOSER` | `SCRAP_DROP_POS` | 7021 | 스크랩 처리기에 시편을 버립니다. |
| `GRIPPER_OPEN_AT_SCRAP_DISPOSER` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_SCRAP_DISPOSER` | `SCRAP_FRONT_RETURN` | 7022 | 스크랩 처리기에서 후퇴합니다. |

#### 4. 홈 복귀
모든 정지 시퀀스가 완료되거나, 로봇이 시편을 들고 있지 않은 상태에서 `STOP` 명령을 받으면 홈 위치로 복귀합니다. 이 시퀀스는 아래 `ACT08`과 동일합니다.

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_HOME` | `RECOVERY_HOME` | 100 | 로봇을 초기 위치(Home)로 복귀시킵니다. |

---

### ACT07: 스크랩 처리기 (Scrap Disposer)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_SCRAP_DISPOSER` | `SCRAP_FRONT_MOVE` | 7020 | 스크랩 처리기 정면으로 이동합니다. |
| `PLACE_IN_SCRAP_DISPOSER` | `SCRAP_DROP_POS` | 7021 | 스크랩 처리기에 시편을 버립니다. |
| `GRIPPER_OPEN_AT_SCRAP_DISPOSER` | `GRIPPER_OPEN` | 90 | 로봇 그리퍼를 엽니다. |
| `RETREAT_FROM_SCRAP_DISPOSER` | `SCRAP_FRONT_RETURN` | 7022 | 스크랩 처리기에서 후퇴합니다. |

---

### ACT08: 홈 (Home)

| Logic Command (MotionCommand) | Robot Command (RobotMotionCommand) | CMD ID | 설명 |
| --- | --- | --- | --- |
| `MOVE_TO_HOME` | `RECOVERY_HOME` | 100 | 로봇을 초기 위치(Home)로 복귀시킵니다. |

---
