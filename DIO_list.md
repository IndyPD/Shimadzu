# Shimadzu 프로젝트 DIO 매핑 리스트

본 문서는 `devices_context.py`에서 정의된 Remote I/O(Autonics EIP)의 전체 디지털 입력(DI 48ch) 및 출력(DO 32ch) 매핑 정보를 담고 있습니다.

## 1. Digital Input (DI) 매핑

| 1-8 (0-7) | 9-16 (8-15) | 17-21 (16-20) | 22-28 (21-27) | 29-35 (28-34) | 36-42 (35-41) | 43-48 (42-47) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [0] SELECT_SW | [8] ENO_01_SW | [16] GRIPPER_1_CLAMP | [21] EXT_BW_SENSOR | [28] ALIGN_2_PUSH | [35] ATC_2_1_SENSOR | [42] - |
| [1] RESET_SW | [9] EMO_02_SI | [17] - | [22] - | [29] ALIGN_2_PULL | [36] ATC_2_2_SENSOR | [43] - |
| [2] - | [10] EMO_03_SI | [18] GRIPPER_2_CLAMP | [23] - | [30] ALIGN_3_PUSH | [37] - | [44] - |
| [3] SOL_SENSOR | [11] EMO_04_SI | [19] - | [24] INDICATOR_GUIDE_DOWN | [31] ALIGN_3_PULL | [38] - | [45] - |
| [4] BCR_OK | [12] DOOR_1_OPEN | [20] EXT_FW_SENSOR | [25] INDICATOR_GUIDE_UP | [32] ATC_1_1_SENSOR | [39] - | [46] - |
| [5] BCR_ERROR | [13] DOOR_2_OPEN | | [26] ALIGN_1_PUSH | [33] ATC_1_2_SENSOR | [40] - | [47] - |
| [6] BUSY | [14] DOOR_3_OPEN | | [27] ALIGN_1_PULL | [34] SCRAPBOX_SENSOR | [41] - | |
| [7] - | [15] DOOR_4_OPEN | | | | | |

## 2. Digital Output (DO) 매핑 (Total 32 Channels)

| 1-8 (Index 0-7) | 9-16 (Index 8-15) | 17-24 (Index 16-23) | 25-32 (Index 24-31) |
| :--- | :--- | :--- | :--- |
| [0] TOWER_LAMP_RED | [8] RESET_SW_LAMP | [16] ALIGN_1_PUSH | [24] GRIPPER_2_UNCLAMP |
| [1] TOWER_LAMP_GREEN | [9] DOOR_4_LAMP | [17] ALIGN_1_PULL | [25] LOCAL_LAMP_C |
| [2] TOWER_LAMP_YELLOW | [10] - | [18] ALIGN_2_PUSH | [26] EXT_FW |
| [3] TOWER_BUZZER | [11] - | [19] ALIGN_2_PULL | [27] EXT_BW |
| [4] - | [12] - | [20] ALIGN_3_PUSH | [28] - |
| [5] BCR_TGR | [13] - | [21] ALIGN_3_PULL | [29] - |
| [6] LOCAL_LAMP_R | [14] INDICATOR_UP | [22] GRIPPER_1_UNCLAMP | [30] - |
| [7] - | [15] INDICATOR_DOWN | [23] LOCAL_LAMP_L | [31] - |

---
*참고: `Index`는 Python 코드 및 Remote I/O 통신 시 사용되는 0-based 인덱스입니다.*