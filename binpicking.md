# 빈피킹 비전–제어 통신 명세서 (v1.2)

0. 개요
본 문서는 NRMK 제어 시스템과 VISION 시스템 간의
TCP/IP 기반 1:1 소켓 통신 인터페이스를 정의한다.

1. 통신 방식

| 항목 | 내용 |
| :--- | :--- |
| 통신 방식 | TCP/IP Socket |
| 연결 형태 | 1:1 |
| 데이터 형식 | JSON (UTF-8) |
| 메시지 구분 | JSON 1라인 + `\n` |
| 연결 관리 | NRMK 주도 |

2. 역할 정의
2.1 NRMK (제어 시스템)
* 로봇 및 그리퍼 제어
* 작업 시퀀스 관리
* 재파지 / 휘젓기 / 종료 판단
* VISION에 요청(Request) 메시지 송신

2.2 VISION (비전 시스템)
* 테이블 위 시편 인식
* 시편 위치·자세·파지 순서·시료 종류 제공
* 겹침 여부 판단
* 그립 성공/실패 영상 기반 판단

3. 네이밍 규칙

| 구분 | 규칙 |
| :--- | :--- |
| 메시지 타입 | `UPPER_SNAKE_CASE` |
| 상태 값 | `UPPER_SNAKE_CASE` |
| 필드명 | `snake_case` |

* 혼용은 허용하지 않는다.

4. 공통 메시지 형식
```json
{"type":"MESSAGE_TYPE", ...}
```
모든 메시지는 type 필드를 포함한다.

5. Handshake
5.1 HELLO
[NRMK → VISION]
```json
{"type":"HELLO"}
```

5.2 HELLO_ACK
[VISION → NRMK]
```json
{"type":"HELLO_ACK", "result":"OK"}
```

6. 장면 인식 요청
6.1 검출 모드

| mode | 설명 |
| :--- | :--- |
| SINGLE | 요청 시 1회(1프레임) 검출 |
| CONTINUOUS | 연속 프레임 검출 |

6.2 CHECK_SCENE
[NRMK → VISION]
```json
{"type":"CHECK_SCENE", "mode":"SINGLE"}
```
또는
```json
{"type":"CHECK_SCENE", "mode":"CONTINUOUS"}
```

6.3 STOP_SCENE
[NRMK → VISION]
```json
{"type":"STOP_SCENE"}
```

7. 장면 인식 응답
7.1 SCENE_RESULT
[VISION → NRMK]

| status | 의미 |
| :--- | :--- |
| TASK_DONE | 시편 없음 |
| TASK_EXECUTION | 시편 있음 |
| OVERLAPPING | 겹침 발생 |

7.2 TASK_DONE
```json
{"type":"SCENE_RESULT", "status":"TASK_DONE"}
```

7.3 TASK_EXECUTION
```json
{
  "type":"SCENE_RESULT",
  "status":"TASK_EXECUTION",
  "specimens":[
    {
      "id":1,
      "sample_type":"WHITE_SAMPLE",
      "location":{
        "x":123.4,
        "y":56.7,
        "z":32.0,
        "rx":180.0,
        "ry":0.0,
        "rz":90.0,
        "theta":90.0
      },
      "grasp_order":1
    }
  ]
}
```

8. 그립 확인
8.1 CHECK_GRASP
[NRMK → VISION]
```json
{"type":"CHECK_GRASP"}
```

8.2 GRASP_RESULT
[VISION → NRMK]
```json
{"type":"GRASP_RESULT", "status":"GRASP_SUCCESS"}
```
또는
```json
{"type":"GRASP_RESULT", "status":"REGRASP"}
```

9. 에러
ERROR
[VISION → NRMK]
```json
{"type":"ERROR", "message":"camera disconnected"}
```

10. 메시지 시퀀스 예시
시나리오 1: 단일 검출 → 다수 시편 인식 → 픽 성공
[NRMK → VISION]
```json
{"type":"HELLO"}
```
[VISION → NRMK]
```json
{"type":"HELLO_ACK", "result":"OK"}
```
[NRMK → VISION]
```json
{"type":"CHECK_SCENE", "mode":"SINGLE"}
```
[VISION → NRMK]
```json
{"type":"SCENE_RESULT","status":"TASK_EXECUTION","specimens":[{"id":1,"sample_type":"WHITE_SAMPLE","location":{"x":123.4,"y":56.7,"z":32.0,"rx":180.0,"ry":0.0,"rz":90.0,"theta":90.0},"grasp_order":1},{"id":2,"sample_type":"WHITE_SAMPLE","location":{"x":145.2,"y":78.9,"z":31.8,"rx":180.0,"ry":0.0,"rz":15.0,"theta":15.0},"grasp_order":2}]}
```
[NRMK → VISION]
```json
{"type":"CHECK_GRASP"}
```
[VISION → NRMK]
```json
{"type":"GRASP_RESULT", "status":"GRASP_SUCCESS"}
```

시나리오 2: 연속 검출 → 겹침 → 중지
[NRMK → VISION]
```json
{"type":"CHECK_SCENE", "mode":"CONTINUOUS"}
```
[VISION → NRMK]
```json
{"type":"SCENE_RESULT", "status":"OVERLAPPING", "location":{"x":200.0, "y":100.0, "z":30.0, "rx":180.0, "ry":0.0, "rz":0.0, "theta":0.0}}
```
[NRMK → VISION]
```json
{"type":"STOP_SCENE"}
```

시나리오 3: 시편 없음
[NRMK → VISION]
```json
{"type":"CHECK_SCENE", "mode":"SINGLE"}
```
[VISION → NRMK]
```json
{"type":"SCENE_RESULT", "status":"TASK_DONE"}
```

11. 설계 원칙 및 확장 방침
* location 필드는 기본 위치 정보(x, y, z)에 더해 자세 확장을 고려하여 rx, ry, rz를 포함한다.
* rx, ry, rz는 로봇 툴 기준 자세 표현을 위한 값으로, 현재 단계에서는 확장성과 호환성을 위한 제공 정보로 사용한다.
