📜 Project History & Changelog (프로젝트 기록 및 변경 사항)

이 문서는 프로젝트의 주요 변경 사항, 릴리스, 그리고 중요한 이정표를 기록합니다. 앞으로 아래의 정해진 형식에 따라 기록을 유지합니다.

v0.1.0 - 2025-12-17 

1. 하드웨어 (Hardware)
- **Shimadzu 전장부**: I/O 신호 결선 및 동작 테스트 완료 (I/O Check Completed).
- **신율계 (Extensometer)**: 하드웨어 설치 및 물리적 세팅 진행 중.
- **제어 PC**: 기본 운영체제 및 개발 환경 세팅 완료.

2. 소프트웨어 (Software)
- **FSM 아키텍처 설계 및 초안 작성**:
    - `LogicFSM`, `DeviceFSM`, `RobotFSM`의 상태(State), 이벤트(Event), 위반(Violation) 상수 정의 (`constants.py`).
    - 각 FSM별 상태 전이 규칙 및 기본 골격 구현 완료.
- **Device 제어 모듈 구현 (`devices_context.py`)**:
    - Shimadzu 시험기, 신율계, Mitutoyo 게이지, Remote I/O 등 하위 장치 연결 로직 통합.
    - Remote I/O 통신을 위한 `AutonicsEIPClient` 연동 및 I/O 상태 모니터링(`read_IO_status`) 구현.
    - 주요 구동부 제어 함수 구현 (Chuck Open/Close, Extensometer Move, Alignment Push/Pull 등).
- **Device FSM 전략 구현 (`devices_strategy.py`, `devices_fsm.py`)**:
    - 연결(`CONNECTING`), 대기(`READY`), 에러(`ERROR`), 복구(`RECOVERING`) 등 기본 상태 전략 구현.
    - 시험 공정별 전략 클래스(`GrippingSpecimenStrategy` 등) 구조 설계.
- **Robot FSM 전략 초안 작성 (`robot_strategy.py`)**:
    - 로봇 연결, 툴 교체, QR 리딩, 픽앤플레이스 등 주요 동작에 대한 전략 클래스 초안 작성.
- **프로젝트 관리**:
    - 상태 기반 개발 계획에 맞춰 `TODO.md` 업데이트.

3. 이슈 (Issues)
- **Bin Picking**: 구현 방식 및 기술적 세부 사항 협의 진행 중.

4. 기타 (Other)
- 특이사항 없음.