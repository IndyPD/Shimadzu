# Shimadzu Logic Project Summary

이 문서는 `shimadzu_logic` 프로젝트의 시스템 아키텍처, 제어 흐름, 통신 프로토콜 및 ML 기반 복구 시스템에 대한 종합적인 요약입니다.

---

## 1. 프로젝트 개요 (Overview)

Shimadzu 인장 시험 자동화 시스템의 상위 제어 로직입니다. 로봇(Indy7), 인장 시험기(Shimadzu), 치수 측정기, 정렬기, QR 리더기 등 다양한 하드웨어를 통합 제어하여 시편 공급부터 시험, 폐기까지의 전 과정을 자동화합니다.

### 주요 구성 요소
- **Logic FSM**: 전체 공정의 상태 및 시퀀스를 관리하는 중앙 제어기 (`logic_strategy.py`)
- **Robot FSM**: 로봇의 세부 동작 및 핸드셰이크 통신 관리
- **Device FSM**: 주변 장치(인장기, 측정기 등) 제어
- **Communication**: MQTT(UI 연동), TCP/IP, Modbus 등을 통한 장치 통신

---

## 2. 자동화 공정 흐름 (Process Flow)

`Command.md` 및 `logic_strategy.py`에 정의된 10단계 표준 공정 순서입니다.

| 단계 | 동작 (Action) | 설명 | 관련 장치 |
|:---:|:---|:---|:---|
| **1** | **QR Scan** | 랙으로 이동하여 트레이/시편 QR 코드 인식 | Robot, QR Reader |
| **2** | **Pick Specimen** | 랙에서 시편 파지 (Gripping) | Robot |
| **3** | **Measure Thickness** | 두께 측정기로 이동하여 3지점 두께 측정 | Robot, Gauge |
| **4** | **Align Specimen** | 정렬기로 이동하여 시편 정렬 수행 | Robot, Aligner |
| **5** | **Pick from Aligner** | 정렬된 시편을 다시 파지 | Robot |
| **6** | **Load Tensile** | 인장 시험기에 시편 장착 (상/하단 척) | Robot, Shimadzu |
| **7** | **Start Test** | 인장 시험 시작 및 완료 대기 | Shimadzu |
| **8** | **Unload Specimen** | 파단된 시편 수거 (하단 -> 상단 순) | Robot |
| **9** | **Dispose Scrap** | 스크랩 처리기로 이동하여 시편 폐기 | Robot |
| **10** | **Next/Complete** | 다음 시편 진행 또는 공정 완료 | Logic |

---

## 3. 통신 프로토콜 (Protocols)

### 3.1 로봇 제어 프로토콜 (Handshake)
Logic과 로봇 컨트롤러(Conty) 간의 정수형 변수 기반 통신입니다.

- **CMD (600)**: Logic → Robot (명령 ID 전송)
- **CMD_ack (610)**: Robot → Logic (수신 확인, `CMD ID + 500`)
- **CMD_done (700)**: Robot → Logic (동작 완료, `CMD ID + 10000`)
- **주요 CMD ID 범위**:
  - `1000~`: 랙 (Rack)
  - `3000~`: 두께 측정기 (Thickness Gauge)
  - `5000~`: 정렬기 (Aligner)
  - `7000~`: 인장 시험기 (Tensile Tester)

### 3.2 MQTT 통신 (UI 연동)
`mqtt_comm.py`를 통해 UI 및 외부 시스템과 데이터를 교환합니다.

- **Role**: `logic` (Publisher/Subscriber)
- **Topics**:
  - `ui_cmd`: UI로부터 제어 명령 수신 (Start, Stop, Reset 등)
  - `logic_evt`: 시스템 상태, 에러, 공정 데이터 발행
- **주요 기능**:
  - 시스템 상태 주기적 보고 (0.5초 간격)
  - 에러 이벤트 발생 시 즉시 알림
  - 배치(Batch) 데이터 및 공정 현황 동기화

---

## 4. ML 기반 에러 복구 시스템 (ML Recovery)

로봇이 에러로 정지했을 때, 현재 관절 좌표(6축)만으로 로봇의 위치(Zone)를 예측하여 안전하게 복구하는 시스템입니다.

### 4.1 모델 개요
- **알고리즘**: LightGBM / RandomForest (Zone Classification)
- **입력**: 로봇 6축 관절 좌표 (`[j1, j2, j3, j4, j5, j6]`)
- **출력**: 현재 위치한 Zone (예: `TENSILE_TESTER`, `RACK`)
- **정확도**: 약 95.36% (Tensile 데이터 포함 시)

### 4.2 Zone 정의 및 복구 전략

| Zone | 포함 장비 | 복구 전략 (Recovery Action) |
|:---|:---|:---|
| **RACK** | 시편 랙 | 안전 후퇴 → 홈 복귀 |
| **THICKNESS_GAUGE** | 두께 측정기 | 후퇴 → 시편 회수(필요시) → 스크랩 → 홈 |
| **ALIGNER** | 정렬기 | 후퇴 → 시편 회수(필요시) → 스크랩 → 홈 |
| **TENSILE_TESTER** | 인장 시험기 | 후퇴 → 시편 회수(필요시) → 스크랩 → 홈 |
| **SCRAP_DISPOSER** | 스크랩 통 | 후퇴 → 홈 복귀 |
| **HOME** | 이동 경로 | 홈 복귀 |

### 4.3 파일 구성
- `state_predictor.py`: 실시간 상태 예측 및 복구 액션 제안
- `train_zone_model_v2.py`: 모델 학습 스크립트
- `zone_classifier.py`: Zone 정의 및 데이터 전처리

---

## 5. 주요 변경 이력 (History)

### v0.1.0 (Current)
- **Tensile Zone 추가**: ML 모델에 인장 시험기 영역 데이터(519개 파일) 통합
- **Logic Strategy 강화**: 공정 중단/재개(Step Stop/Resume) 로직 고도화
- **DB 연동 최적화**: 배치 데이터 로드 및 결과 저장 로직 개선
- **안전 기능**: 로봇 충돌 방지 및 수동 모션 테스트 기능 추가

---

## 6. 설치 및 실행 (Quick Start)

### 의존성 설치
```bash
pip install scikit-learn numpy lightgbm paho-mqtt
```

### ML 모델 학습
```bash
python -m projects.shimadzu_logic.ml_recovery.train_zone_model_v2
```