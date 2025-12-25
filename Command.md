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
    *   Robot: `M00_MOVE_TO_RACK` (QR 리딩 위치로 이동)
    *   Device: `QR_READ` (QR 코드 인식 실행) -> 결과값 `process/auto/qr_data/{Seq}` 저장

2.  **시편 가져오기 (`pick_specimen`)**
    *   Robot: `M01_PICK_SPECIMEN` (랙에서 시편 잡기)

3.  **측정기 이동 (`move_to_indigator`)**
    *   Robot: `M02_MOVE_TO_INDICATOR` (두께 측정기 앞으로 이동)

4.  **시편 거치 및 측정 (`place_specimen_and_measure`)**
    *   Robot: `M03_PLACE_AND_MEASURE` (측정기 거치 후 후퇴)
    *   Device: `MEASURE_THICKNESS` (두께 측정 실행) -> 결과값 `process/auto/thickness/{Seq}` 저장

5.  **측정기 시편 반출 (`Pick_specimen_out_from_indigator`)**
    *   Robot: `M04_PICK_OUT_FROM_INDICATOR` (측정기에서 시편 다시 잡기)

6.  **시편 정렬 (`align_specimen`)**
    *   Robot: `M05_ALIGN_SPECIMEN` (정렬기 진입 및 거치)
    *   Device: `ALIGN_SPECIMEN` (정렬기 동작 실행)

7.  **정렬기 시편 반출 (`Pick_specimen_out_from_align`)**
    *   Robot: `M06_PICK_OUT_FROM_ALIGN` (정렬된 시편 잡고 나오기)

8.  **인장기 장착 (`load_tensile_machine`)**
    *   Robot: `M07_LOAD_TENSILE_MACHINE` (인장기 진입 및 거치)
    *   Device: `TENSILE_GRIPPER_ON` (인장기 그리퍼 체결)

9.  **인장기 후퇴 (`retreat_tensile_machine`)**
    *   Robot: `M08_RETREAT_TENSILE_MACHINE` (시편 거치 후 로봇 팔 후퇴)

10. **인장 시험 시작 (`start_tensile_test`)**
    *   Device: `START_TENSILE_TEST` (인장 시험기 시험 시작 명령)
    *   *참고: 시험 중 실시간 데이터는 시험기 소프트웨어(Trapezium)에서 관리*

11. **인장기 시편 수거 (`pick_tensile_machine`)**
    *   Robot: `M09_PICK_TENSILE_MACHINE` (파단된 시편 파지)
    *   Device: `TENSILE_GRIPPER_OFF` (인장기 그리퍼 해제)

12. **후퇴 및 스크랩 처리 (`retreat_and_handle_scrap`)**
    *   Robot: `M10_RETREAT_AND_HANDLE_SCRAP` (인장기 후퇴 및 스크랩 박스 배출)

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