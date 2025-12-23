# Shimadzu Project

Shimadzu 인장 시험 자동화 시스템 제어 소프트웨어입니다. Neuromeka Indy7 로봇과 Shimadzu 시험기, 주변 장치들을 통합하여 시편 핸들링 및 시험 공정을 자동화합니다.

## 프로젝트 개요 (Project Overview)

본 시스템은 시편 랙(Rack)에서 시편을 취출하여 QR 코드를 인식하고, 두께를 측정한 뒤 정렬 과정을 거쳐 인장 시험기에 장착합니다. 시험이 완료된 시편은 자동으로 수거하여 폐기함에 배출하는 전 과정을 FSM(Finite State Machine) 기반으로 제어합니다.

### 주요 특징
- **FSM 기반 아키텍처**: Logic(전체 공정), Robot(로봇 동작), Device(시험기 및 주변장치)로 역할을 분리하여 상태 기반 제어 수행
- **전략 패턴(Strategy Pattern) 적용**: 각 상태별 동작을 독립적인 클래스로 구현하여 유지보수 및 확장성 강화
- **통합 모니터링**: Blackboard 시스템을 통한 실시간 데이터 공유 및 MQTT 기반 UI 통신
- **안전 및 예외 처리**: 다중 비상 정지(EMO) 감시 및 하드웨어 상태 실시간 모니터링을 통한 Violation 감지

## 시스템 구조 (System Architecture)

### 1. 제어 계층
- **Logic FSM**: 전체 자동화 시퀀스를 관리하는 최상위 컨트롤러
- **Robot FSM**: Indy7 로봇의 모션 및 그리퍼 제어 (IndyDCP3 기반)
- **Device FSM**: Shimadzu 시험기, 신율계, Mitutoyo 게이지, Remote I/O 제어

### 2. 주요 공정 흐름 (Process Flow)
1. **시편 픽업**: 랙(Rack)의 특정 층/위치에서 시편 취출
2. **정보 인식**: QR 리더기를 통한 시편 정보 식별
3. **두께 측정**: Mitutoyo 게이지를 이용한 3포인트 두께 측정 및 평균값 계산
4. **시편 정렬**: 정렬기(Aligner)를 이용한 시편 중심 정렬
5. **시험기 장착**: 인장 시험기 그리퍼에 시편 안착
6. **인장 시험**: 시험기 및 신율계 제어를 통한 인장 시험 수행
7. **수거 및 폐기**: 파단된 시편 수거 후 스크랩 박스 배출

## 주요 파일 구조

```text
shimadzu_logic/
├── constants.py          # 상태(State), 이벤트(Event), I/O 매핑 정의
├── logic_context.py      # 전체 공정 제어 로직 및 상태 관리
├── robot_context_v1.py   # 로봇 제어 API 및 복합 모션 구현
├── robot_fsm_v1.py       # 로봇 상태 전이 규칙 정의
├── robot_strategy_v1.py  # 로봇 상태별 세부 동작 전략 구현
└── devices_context.py    # 하드웨어 장치(시험기, IO 등) 인터페이스
```

## 환경 설정 (Installation)

이 프로젝트는 Anaconda 환경(`NRMK`)과 Python 3.8을 기준으로 작성되었습니다.

### 1. Conda 가상환경 생성 및 활성화

Anaconda Prompt 또는 터미널에서 아래 명령어를 실행하여 가상환경을 생성하고 활성화합니다.

```bash
# 가상환경 생성 (이름: NRMK, Python 버전: 3.8)
conda create -n NRMK python=3.8

# 가상환경 활성화
conda activate NRMK
```

### 2. 라이브러리 설치

프로젝트 실행에 필요한 라이브러리들을 한 번에 설치합니다.

```bash
pip install -r requirements.txt
```

> **참고:** `requirements.txt`에는 다음 라이브러리들이 포함되어 있습니다.
> - pycomm3 (EtherNet/IP 통신)
> - pyserial (시리얼 통신)
> - paho-mqtt (MQTT 통신)
> - grpcio, protobuf (gRPC 통신)
> - requests, numpy
> - PyYAML (설정 파일 처리)
> - semver (버전 관리)
> - psutil (시스템 프로세스 관리)
> - py_trees (Behavior Tree 구현)
> - neuromeka (Indy 로봇 제어)
> - scipy (과학 계산)

## 실행 방법 (Usage)

프로젝트 루트 경로에서 `run.py`를 실행합니다.

```bash
python run.py --project shimadzu_logic
```
