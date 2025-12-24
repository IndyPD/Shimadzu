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

1.  **시편 취출 (`pick_specimen`)**
    *   Robot: `M01_PICK_SPECIMEN` (랙에서 시편 잡기)

2.  **측정기 이동 (`move_to_indigator`)**
    *   Robot: `M02_MOVE_TO_INDICATOR` (두께 측정기 앞으로 이동)

3.  **시편 거치 및 측정 (`place_specimen_and_measure`)**
    *   Robot: `M03_PLACE_AND_MEASURE` (측정기 거치 후 후퇴)
    *   Device: `MEASURE_THICKNESS` (두께 측정 실행) -> 결과값 `process/auto/thickness/{Seq}` 저장

4.  **측정기 시편 반출 (`Pick_specimen_out_from_indigator`)**
    *   Robot: `M04_PICK_OUT_FROM_INDICATOR` (측정기에서 시편 다시 잡기)

5.  **시편 정렬 (`align_specimen`)**
    *   Robot: `M05_ALIGN_SPECIMEN` (정렬기 진입 및 거치)
    *   Device: `ALIGN_SPECIMEN` (정렬기 동작 실행)
    *   Robot: `M06_PICK_OUT_FROM_ALIGN` (정렬된 시편 잡고 나오기)

6.  **인장기 장착 (`load_tensile_machine`)**
    *   Robot: `M07_LOAD_TENSILE_MACHINE` (인장기 진입 및 거치)
    *   Device: `TENSILE_GRIPPER_ON` (인장기 그리퍼 체결)

7.  **인장기 후퇴 (`retreat_tensile_machine`)**
    *   Robot: `M08_RETREAT_TENSILE_MACHINE` (시편 거치 후 로봇 팔 후퇴)

8.  **인장 시험 시작 (`start_tensile_test`)**
    *   Device: `START_TENSILE_TEST` (인장 시험기 시험 시작 명령)
    *   *참고: 시험 중 실시간 데이터는 시험기 소프트웨어(Trapezium)에서 관리*

9.  **인장기 시편 수거 (`pick_tensile_machine`)**
    *   Robot: `M09_PICK_TENSILE_MACHINE` (파단된 시편 파지)
    *   Device: `TENSILE_GRIPPER_OFF` (인장기 그리퍼 해제)

10. **후퇴 및 스크랩 처리 (`retreat_and_handle_scrap`)**
    *   Robot: `M10_RETREAT_AND_HANDLE_SCRAP` (인장기 후퇴 및 스크랩 박스 배출)

---