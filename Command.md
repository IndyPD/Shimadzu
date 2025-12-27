# Shimadzu Automation Command Protocol

본 문서는 `logic_context.py`에서 정의된 로봇(Robot) 및 장비(Device) 제어 명령의 데이터 구조와 블랙보드(Blackboard) 통신 규격을 정의합니다.

## 1. 로봇 명령 (Robot Command)

로봇의 모션 제어를 위해 사용되는 데이터 구조입니다.

*   **Blackboard Key**: `process/auto/robot/cmd`
*   **Data Structure**:
    ```json
    {
        "process": "string",      // Motion_command 상수 값
        "target_floor": "int",    // 작업 대상 층 (Rack)
        "target_num": "int",      // 작업 대상 번호 (Tray 내 순번)
        "position": "int",        // 세부 위치 (예: 두께 측정 포인트 1, 2, 3)
        "state": "string"         // 상태 ("": 대기, "done": 완료, "error": 에러)
    }
    ```

### 주요 모션 명령 (Motion_command)
| 상수명 | 값 (String) | 설명 |
| :--- | :--- | :--- |
| `M01_PICK_SPECIMEN` | "pick_specimen" | 랙에서 시편 취출 |
| `M02_MOVE_TO_INDICATOR` | "move_to_indigator" | 두께 측정기 앞으로 이동 |
| `M03_PLACE_AND_MEASURE` | "place_specimen_and_measure" | 측정기에 시편 거치 후 후퇴 |
| `M04_PICK_OUT_FROM_INDICATOR` | "Pick_specimen_out_from_indigator" | 측정기에서 시편 회수 |
| `M05_ALIGN_SPECIMEN` | "align_specimen" | 정렬기에 시편 거치 |
| `M06_PICK_OUT_FROM_ALIGN` | "Pick_specimen_out_from_align" | 정렬기에서 시편 회수 |
| `M07_LOAD_TENSILE_MACHINE` | "load_tensile_machine" | 인장기에 시편 진입/거치 |
| `M08_RETREAT_TENSILE_MACHINE` | "retreat_tensile_machine" | 인장기 거치 후 후퇴 |
| `M09_PICK_TENSILE_MACHINE` | "pick_tensile_machine" | 인장기에서 시편 파지 |
| `M10_RETREAT_AND_HANDLE_SCRAP` | "retreat_and_handle_scrap" | 시편 수거 후 스크랩 처리 |

---

## 2. 장비 명령 (Device Command)

시험기, 정렬기, 두께 측정기 등 하드웨어 제어를 위해 사용되는 데이터 구조입니다.

*   **Blackboard Key**: `process/auto/device/cmd`
*   **Data Structure**:
    ```json
    {
        "command": "string",      // Device_command 상수 값 (또는 "process" 키 사용)
        "result": "any",          // 측정 결과 값 (두께 등)
        "state": "string",        // 상태 ("": 대기, "error": 에러)
        "is_done": "bool"         // 완료 여부 (True/False)
    }
    ```
    *참고: 일부 함수에서는 `command` 대신 `process` 키를 사용하므로 수신 측에서 두 키를 모두 확인해야 합니다.*

### 주요 장비 명령 (Device_command)
| 상수명 | 값 (String) | 설명 |
| :--- | :--- | :--- |
| `MEASURE_THICKNESS` | "measure_thickness" | 두께 측정 실행 |
| `ALIGN_SPECIMEN` | "align_specimen" | 정렬기 동작 실행 |
| `TENSILE_GRIPPER_ON` | "tessile_gripper_on" | 인장기 그리퍼 체결 |
| `TENSILE_GRIPPER_OFF` | "tessile_gripper_off" | 인장기 그리퍼 해제 |

---

## 3. 공정별 명령 흐름 예시

1.  **목표 Tray QR 인식 (`move_to_rack_for_QRRead`)**
    *   [Robot] `M00_MOVE_TO_RACK` (QR 리딩 위치로 이동)
    *   Device: `QR_READ` (QR 코드 인식 실행) -> 결과값 `process/auto/qr_data/{Seq}` 저장

2.  **시편 가져오기 (`pick_specimen`)**
    *   [Robot] `M01_PICK_SPECIMEN` (랙에서 시편 잡기)

3.  **측정기 이동 (`move_to_indigator`)**
    *   [Robot] `M02_MOVE_TO_INDICATOR` (두께 측정기 앞으로 이동)

4.  **시편 거치 및 측정 (`place_specimen_and_measure`)**
    *   [Robot] `M03_PLACE_AND_MEASURE` (측정기 거치 후 후퇴)
    *   Device: `MEASURE_THICKNESS` (두께 측정 실행) -> 결과값 `process/auto/thickness/{Seq}` 저장

5.  **측정기 시편 반출 (`Pick_specimen_out_from_indigator`)**
    *   [Robot] `M04_PICK_OUT_FROM_INDICATOR` (측정기에서 시편 다시 잡기)

6.  **시편 정렬 (`align_specimen`)**
    *   [Robot] `M05_ALIGN_SPECIMEN` (정렬기 진입 및 거치)
    *   Device: `ALIGN_SPECIMEN` (정렬기 동작 실행)

7.  **정렬기 시편 반출 (`Pick_specimen_out_from_align`)**
    *   [Robot] `M06_PICK_OUT_FROM_ALIGN` (정렬된 시편 잡고 나오기)

8.  **인장기 장착 (`load_tensile_machine`)**
    *   [Robot] `M07_LOAD_TENSILE_MACHINE` (인장기 진입 및 거치)
    *   Device: `TENSILE_GRIPPER_ON` (인장기 그리퍼 체결)

9.  **인장기 후퇴 (`retreat_tensile_machine`)**
    *   [Robot] `M08_RETREAT_TENSILE_MACHINE` (시편 거치 후 로봇 팔 후퇴)

10. **인장 시험 시작 (`start_tensile_test`)**
    *   Device: `START_TENSILE_TEST` (인장 시험기 시험 시작 명령)
    *   *참고: 시험 중 실시간 데이터는 시험기 소프트웨어(Trapezium)에서 관리*

11. **인장기 시편 수거 (`pick_tensile_machine`)**
    *   [Robot] `M09_PICK_TENSILE_MACHINE` (파단된 시편 파지)
    *   Device: `TENSILE_GRIPPER_OFF` (인장기 그리퍼 해제)

12. **후퇴 및 스크랩 처리 (`retreat_and_handle_scrap`)**
    *   [Robot] `M10_RETREAT_AND_HANDLE_SCRAP` (인장기 후퇴 및 스크랩 박스 배출)

---

## 4. UI-Logic 공정 제어 시퀀스

### 4.1. 초기화 및 데이터 동기화
1.  **정보 등록**: UI에서 공정 정보 작성 후 '저장' 클릭.
2.  **저장 명령**: UI → Logic MQTT 메시지 전송.
3.  **응답(ACK)**: Logic에서 수신 확인 응답 전송.
4.  **데이터 로드**: Logic이 DB에서 공정 정보를 읽어 내부 배열(`processData`)에 저장.

**데이터 구조 예시 (JSON)**
```json
{
  "batch_id": "B20251225-001",
  "procedure_num": 10,
  "timestamp": "2025-12-25 10:00:00",
  "processData": [
    {
      "id": 1,
      "tray_no": 1,
      "seq_order": 1,
      "seq_status": 1,
      "test_method": "ASTM-D638",
      "batch_id": "B20251225-001",
      "lot": "LOT-A",
      "status": "READY"
    }
    // ... 최대 10개 시편 데이터
  ]
}
```

### 4.2. 공정 실행 및 루프
1.  **공정 시작**: UI '시작' 버튼 클릭 시 로드된 데이터를 기반으로 시퀀스 세팅.
2.  **상태 점검**: 로봇 및 장치 상태 확인 후 정상일 경우 ACK 전송 및 공정 개시.
3.  **순차 실행**: 1번부터 최대 10번 시편까지 순차 진행.
4.  **동적 업데이트**: 각 시편 공정 시작 전 DB를 재조회하여 변경된 공정 정보(파라미터 등)를 실시간 반영.

### 4.3. 실시간 제어 명령 (UI → Logic)
| 명령 | 동작 정의 |
| :--- | :--- |
| **Pause** | 로봇 이동 속도를 0으로 설정하여 즉시 일시정지. |
| **Stop** | 현재 진행 중인 세부 동작까지만 수행 후 중단. 인장 시험 전 단계라면 시편을 배출대에 반출하고 홈 위치로 복귀. |
| **Step Stop** | 현재 작업 중인 시편의 전체 사이클(인장 시험 및 폐기 포함)을 완료한 후 공정 정지. |
| **Reset** | Stop 또는 Step Stop 이후 공정 데이터를 초기화하고 대기 상태로 전환. |

### 4.4. 공정 종료
*   모든 시편의 공정이 완료되면 Logic에서 UI로 최종 완료 상태를 전송.

## 5. 로봇 직접 통신 규격 (Indy DCP3)

본 항목은 `logic_context.py`와 로봇 제어기(Conty) 간의 직접 통신을 위한 정수 변수(Integer Variable) 메모리 맵을 정의합니다.<br>
통신은 IndyDCP3 라이브러리를 통해 이루어집니다.<br>
아래의 정리된 내용은 Robot의 Conty Program의 기준으로 작성되어 있습니다. (W: Robot -> Logic, R: Logic -> Robot)
*   **명령 전달**: `indy.set_int_variable()` 함수를 사용하여 Logic에서 로봇 제어기로 명령 및 데이터를 전송합니다.
*   **상태 확인**: `indy.get_int_variable()` 함수를 사용하여 로봇 제어기의 상태 및 명령 실행 결과를 읽어옵니다.

### 정수 변수 메모리 맵

| 주소 (Addr) | 변수명 (Name) | 설명 | R/W |
| :--- | :--- | :--- | :--- |
| **Int100** | `gripper_state` | 그리퍼 상태. (0: 초기값, 1: 열림, 2: 파지 닫힘, 3: 완전 닫힘, 4: 파지 실패) | W |
| Int101-105 | - | (예비) | - |
| Int200-206 | - | (예비) | - |
| **Int400** | `Tensile_POS` | 인장기 위치 변수 (상단 그리퍼 관련) | R |
| **Int600** | `CMD` | Logic에서 전달하는 모션 명령 ID. | R |
| Int650 | `CMD_BACKUP` | `CMD` 값을 유지하기 위한 내부 변수. | R |
| **Int610** | `CMD_ack` | 로봇이 `CMD`를 수신했음을 알리는 응답. (예: `CMD` 값이 10이면, 수신 후 510으로 설정) | W |
| Int660 | `CMD_ack_BACKUP` | `CMD_ack` 값을 유지하기 위한 내부 변수. | W |
| **Int700** | `CMD_done` | `CMD`로 지시된 모션의 완료 상태. (1: 완료, 0: 모션 중) | W |
| Int750 | `CMD_done_BACKUP` | `CMD_done` 값을 유지하기 위한 내부 변수. | W |
| **Int770** | `CMD_Init` | 새로운 모션 시작 전 `CMD_ack`와 `CMD_done`을 초기화하기 위한 신호. (1: 초기화 요청) | R |

### 6. 로봇 모션 명령 테이블

| 구분 | 모션명 | 사용 | 모션 변수명 | Motion CMD | Motion ACK | Motion Done | 시작 위치 | 목표 위치 | 다음 모션 | 비고 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **기본 동작** | 홈-렉 앞 이동 | O | `home_rack_front` | 1 | 501 | 10001 | H | AA | - | |
| | 홈-툴 앞 이동 | O | `home_tool_front` | 2 | 502 | 10002 | H | TA | - | |
| | 홈-측정기 앞 이동 | O | `home_thick_gauge_front` | 3 | 503 | 10003 | H | BA | - | |
| | 홈-정렬기 앞 이동 | O | `home_aligner_front` | 4 | 504 | 10004 | H | CA | - | |
| | 홈-인장시험기 앞 이동 | O | `home_tensile_tester_front` | 5 | 505 | 10005 | H | DA | - | |
| | 홈-스크랩 배출 앞 이동 | O | `home_scrap_disposer_front` | 6 | 506 | 10006 | H | FA | - | |
| | 렉 앞 - 홈 이동 | O | `rack_front_home` | 21 | 521 | 10021 | AA | H | - | |
| | 툴 앞 - 홈 이동 | O | `tool_front_home` | 22 | 522 | 10022 | TA | H | - | |
| | 측정기 앞 - 홈 이동 | O | `thick_gauge_front_home` | 23 | 523 | 10023 | BA | H | - | |
| | 정렬기 앞 - 홈 이동 | O | `aligner_front_home` | 24 | 524 | 10024 | CA | H | - | |
| | 인장시험기 앞 - 홈 이동 | O | `tensile_tester_front_home` | 25 | 525 | 10025 | DA | H | - | |
| | 스크랩 배출 앞 - 홈 이동 | O | `scrap_disposer_front_home` | 26 | 526 | 10026 | FA | H | - | |
| | 그리퍼 열기 | O | `gripper_open` | 90 | 590 | 10090 | 현재 위치 | 현재 위치 | - | |
| | 그리퍼 닫기 | O | `gripper_close` | 91 | 591 | 10091 | 현재 위치 | 현재 위치 | - | |
| **복구** | 홈이동 | O | `Recovery_home` | 100 | 600 | 10100 | anywhere | H | - | 복구 개념 (후퇴, 안전위치 이동, 홈 이동) |
| **공정 중 모션** | 툴 위치 이동 (Binpicking) | | `BIN_tool_move_pos` | 101 | 601 | 10101 | H | T | 툴위치app -> 2번위치 이동 | Binpicking용 |
| | 툴 2번센서 진입 (Binpicking) | | `BIN_tool_enter_sensor_2` | 102 | 602 | 10102 | H | T | 2번위치 -> 1번위치 이동 | Binpicking용 |
| | 툴 1번센서 진입 (Binpicking) | | `BIN_tool_enter_sensor_1` | 103 | 603 | 10103 | H | T | 1번위치 -> 위로 이동(장착) | Binpicking용 |
| | 툴 삽입 후 위로 이동 (Binpicking) | | `BIN_tool_insert_move_up` | 104 | 604 | 10104 | H | T | 홈이동 | Binpicking용 |
| | 툴 위치 이동 (Process) | O | `PRO_tool_move_pos` | 105 | 605 | 10105 | H | T | 툴위치app -> 3번위치 이동 | Process용 |
| | 툴 3번센서 진입 (Process) | O | `PRO_tool_enter_sensor_3` | 106 | 606 | 10106 | H | T | 3번위치 -> 4번위치 이동 | Process용 |
| | 툴 4번센서 진입 (Process) | O | `PRO_tool_enter_sensor_4` | 107 | 607 | 10107 | H | T | 4번위치 -> 위로 이동(장착) | Process용 |
| | 툴 삽입 후 위로 이동 (Process) | O | `PRO_tool_insert_move_up` | 108 | 608 | 10108 | H | T | 홈이동 | Process용 |
| | 렉 앞 이동 | O | `rack_front_move` | 1000 | 1500 | 11000 | H | AA(approach) | 렉 n층 앞 이동 -> 렉 n층 QR인식위치 | |
| | 렉 n층 앞 이동 | O | `rack_nF_front_pos` | `1{nF}0`<br>(1010~1100) | `CMD + 500`<br>(1510~1600) | `CMD + 10000`<br>(11010~11100) | A{nF}_QR | A{nF} | 렉 n층 앞 이동 -> 렉 n층 N번 시편 위치 이동 | `nF`: 층수 (1~10)<br>예: 3층 -> 1030 |
| | 렉 n층 QR인식위치 | O | `rack_nF_QR_scan_pos` | `1{nF}0 + 300`<br>(1310~1400) | `CMD + 500`<br>(1810~1900) | `CMD + 10000`<br>(11310~11400) | AA | A{nF}_QR | 렉 n층 QR인식위치 -> 렉 n층 앞 이동 | 예: 3층 -> 1330 |
| | 렉 n층 N번 시편 위치 이동 | O | `rack_nF_sample_N_pos` | `1{nF}{N}`<br>(1011~1110) | `CMD + 500`<br>(1511~1610) | `CMD + 10000`<br>(11011~11110) | A{nF} | A{nF}_0N | 그리퍼 잡기 -> 렉 n층 앞 복귀 | `N`: 시편 순번 (1~10)<br>예: 3층 2번 -> 1032 |
| | 렉 n층 앞 복귀 | O | `rack_nF_front_return` | `2{nF}0`<br>(2010~2100) | `CMD + 500`<br>(2510~2600) | `CMD + 10000`<br>(12010~12100) | A{nF}_0N | A{nF} | 렉 앞 복귀 | 예: 3층 앞 -> 2030 |
| | 렉 앞 복귀 | O | `rack_front_return` | 2000 | 2500 | 12000 | A{nF} | AR | 두께 측정기 이동 | |
| | 두께 측정기 앞 이동 | O | `thick_gauge_front_move` | 3000 | 3500 | 13000 | AR | BA | 두께 측정기에 시편 놓기 | |
| | 두께 측정기 시편 놓기 1 | O | `thick_gauge_sample_1_place` | 3001 | 3501 | 13001 | BA | B | 그리퍼 열기 -> 앞 복귀 | 1차 측정 |
| | 두께 측정기 시편 놓기 2 | O | `thick_gauge_sample_2_place` | 3002 | 3502 | 13002 | BA | B | 그리퍼 열기 -> 앞 복귀 | 2차 측정 |
| | 두께 측정기 시편 놓기 3 | O | `thick_gauge_sample_3_place` | 3003 | 3503 | 13003 | BA | B | 그리퍼 열기 -> 앞 복귀 | 3차 측정 |
| | 두께 측정기 시편 잡기 1 | O | `thick_gauge_sample_1_pick` | 3011 | 3511 | 13011 | BA | B | 그리퍼 닫기 -> 시편 놓기 2 or 앞 복귀 | 1차 측정 후 |
| | 두께 측정기 시편 잡기 2 | O | `thick_gauge_sample_2_pick` | 3012 | 3512 | 13012 | BA | B | 그리퍼 닫기 -> 시편 놓기 3 or 앞 복귀 | 2차 측정 후 |
| | 두께 측정기 시편 잡기 3 | O | `thick_gauge_sample_3_pick` | 3013 | 3513 | 13013 | BA | B | 그리퍼 닫기 -> 앞 복귀 | 3차 측정 후 |
| | 두께 측정기 앞 복귀 (1) | O | `thick_gauge_front_return_1` | 4000 | 4500 | 14000 | B | BR | - | |
| | 두께 측정기 앞 복귀 (2) | O | `thick_gauge_front_return_2` | 4001 | 4501 | 14001 | B | BR | - | |
| | 두께 측정기 앞 복귀 (3) | O | `thick_gauge_front_return_3` | 4002 | 4502 | 14002 | B | BR | - | |
| | 정렬기 앞 이동 | O | `aligner_front_move` | 5000 | 5500 | 15000 | BR | CA | - | |
| | 정렬기 시편 놓기 | O | `aligner_sample_place` | 5001 | 5501 | 15001 | CA | C | 그리퍼 열기 -> 앞 복귀 | 시편 정렬 대기 |
| | 정렬기 앞 복귀 | O | `aligner_front_return` | 6000 | 6500 | 16000 | C | CR | - | |
| | 정렬기 시편 잡기 | O | `aligner_sample_pick` | 5011 | 5511 | 15011 | CA | C | 그리퍼 닫기 -> 앞 복귀 | |
| | 인장시험기 앞 이동 | | `tensile_front_move` | 7000 | 7500 | 17000 | CR | DA | 인장기 시편 잡는 위치 이동 | |
| | 인장기 시편 아래 놓기 | | `tensile_sample_place_pos_down` | 7001 | 7501 | 17001 | DA | D | 신호 대기 -> 그리퍼 열기 -> 앞 복귀 | 시험 시작 후 대기 |
| | 인장기 시편 위 놓기 | | `tensile_sample_place_pos_up` | 7002 | 7502 | 17002 | DA | D | 신호 대기 -> 그리퍼 열기 -> 앞 복귀 | 시험 시작 후 대기 |
| | 인장기 시편 아래 수거 | | `tensile_sample_pick_pos_down` | 7011 | 7511 | 17011 | DA | D | 대기 -> 그리퍼 닫기 -> 앞 복귀 | |
| | 인장기 시편 위 수거 | | `tensile_sample_pick_pos_up` | 7012 | 7512 | 17012 | DA | D | 대기 -> 그리퍼 닫기 -> 앞 복귀 | |
| | 인장시험기 앞 복귀 | | `tensile_front_return` | 8000 | 8500 | 18000 | D | DR | 홈 이동 or 대기 | |
| | 스크랩 배출대 앞 이동 | O | `scrap_front_move` | 7020 | 7520 | 17020 | DR | FA | 스크랩 버리기 -> 홈 이동 | |
| | 스크랩 배출대 스크랩 버리기 | O | `scrap_drop_pos` | 7021 | 7521 | 17021 | FA | F | 모션 후 -> 그리퍼 열기 -> 앞 이동 | |
| | 스크랩 배출대 앞 복귀 | O | `scrap_front_return` | 7022 | 7522 | 17022 | F | FR | 홈 이동 or 대기 | |