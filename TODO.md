🎯 Project To-Do List (State-Based Implementation)

이 문서는 `LogicFSM`, `DeviceFSM`, `RobotFSM`의 상태(State) 구현을 기준으로 작성된 작업 목록입니다.

1. Logic FSM (Main Sequence Controller)
전체 공정의 흐름을 제어하는 상위 로직 구현

1.1 CONNECTING
# [ ] 1.1.1 모든 서브 모듈(Device, Robot) 연결 상태 확인 로직 구현
1.2 IDLE
# [ ] 1.2.1 작업자 시작 명령 대기 및 초기 위반(Violation) 감시
1.3 PREPARING_BATCH
# [ ] 1.3.1 배치 시작 전 초기화 (Device Ready 확인)
# [ ] 1.3.2 Robot 툴 교체/확인 명령 하달
1.4 SUPPLYING_SPECIMEN
# [ ] 1.4.1 시편 공급 시퀀스 제어 (QR 리딩 -> 두께 측정 -> 정렬 -> 장착)
# [ ] 1.4.2 Robot/Device 간 핸드쉐이킹 로직 구현
1.5 TESTING_SPECIMEN
# [ ] 1.5.1 인장 시험 수행 제어 (초기 하중 제거 -> 시험 시작 -> 파단 감지)
1.6 COLLECTING_SPECIMEN
# [ ] 1.6.1 시편 회수 및 폐기 시퀀스 제어 (신율계 후진 -> 그립 해제 -> 로봇 회수)
1.7 BATCH_COMPLETE
# [ ] 1.7.1 배치 완료 처리 및 다음 시편 존재 여부 확인 (Loop 결정)
1.8 ERROR / RECOVERING / STOP_AND_OFF
# [ ] 1.8.1 시스템 전역 에러 전파 및 복구 시퀀스 구현

2. Device FSM (Shimadzu & Extensometer)
시험기 및 신율계 장치 제어 로직 구현

2.1 CONNECTING
# [ ] 2.1.1 Shimadzu Client 및 Remote I/O 연결 초기화
2.2 READY
# [ ] 2.2.1 시험기 대기 상태 유지 및 명령 수신 대기
2.3 GRIPPING_SPECIMEN
# [ ] 2.3.1 시편 그립(Chuck Close) 신호 제어 및 완료 확인
2.4 EXT_FORWARD
# [ ] 2.4.1 신율계 전진(Ext Forward) 신호 제어 및 센서 확인
2.5 PRELOADING
# [ ] 2.5.1 초기 하중 제거(Preload) 명령 전송 및 완료 확인
2.6 TESTING
# [ ] 2.6.1 시험 시작(Start Analysis) 명령 및 진행 상태 모니터링
2.7 EXT_BACK
# [ ] 2.7.1 신율계 후진(Ext Backward) 신호 제어 및 센서 확인
2.8 UNGRIPPING_SPECIMEN
# [ ] 2.8.1 시편 그립 해제(Chuck Open) 신호 제어 및 완료 확인
2.9 ERROR / RECOVERING
# [ ] 2.9.1 장비 에러 상태 감지 및 리셋(Reset) 로직

3. Robot FSM (Indy7 Handling)
로봇 모션 및 그리퍼 제어 로직 구현

3.1 CONNECTING
# [ ] 3.1.1 IndyDCP3 연결 및 상태 확인
3.2 READY
# [ ] 3.2.1 홈 위치 이동 및 명령 대기
3.3 TOOL_CHANGING
# [ ] 3.3.1 그리퍼/툴 교체 모션 및 확인 로직
3.4 READING_QR
# [ ] 3.4.1 QR 리딩 위치 이동 및 스캐너 트리거
3.5 PICKING
# [ ] 3.5.1 트레이 시편 픽업 모션 (Approach -> Grip -> Retract)
3.6 PLACING
# [ ] 3.6.1 시편 장착 모션 (시험기/정렬기/두께측정기)
3.7 ALIGNING
# [ ] 3.7.1 정렬 장치 연동 모션 수행
3.8 MOVING_TO_WAIT
# [ ] 3.8.1 안전 대기 위치 이동
3.9 DISPOSING
# [ ] 3.9.1 파단 시편 폐기 모션 수행
3.10 ERROR / RECOVERING
# [ ] 3.10.1 충돌 감지 및 로봇 에러 복구(Direct Teaching 등)

4. Common / Infrastructure
4.1 Signal Mapping
# [ ] 4.1.1 `constants.py`의 DigitalInput/Output 매핑 검증
4.2 Communication
# [ ] 4.2.1 MQTT 통신 (UI <-> Logic) 인터페이스 안정화
