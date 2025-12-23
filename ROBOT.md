# 모션 통신 프로토콜 상세 가이드

## 🔄 안전한 통신 흐름

### 전체 시퀀스
```
┌─────────────────────────────────────────────────────────────┐
│ 1단계: 초기화                                                │
│ - ACK = 0, DONE = 0 설정                                     │
│ - 초기화 확인 (0인지 체크)                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2단계: 명령 전송 (최대 3번 재시도)                            │
│ - CMD = motion (예: 100)                                     │
│ - Conty가 읽어감                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3단계: ACK 대기 (5초 타임아웃)                                │
│ - Conty → Python: ACK = motion + 500 (예: 600)               │
│ - ACK 못 받으면 2단계로 재시도                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4단계: CMD 리셋                                              │
│ - CMD = 0 (Conty가 명령 받았으니 안전)                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5단계: 모션 실행 중                                           │
│ - Conty가 로봇 동작 수행                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6단계: DONE 대기 (30초 타임아웃)                              │
│ - Conty → Python: DONE = motion + 10000 (예: 10100)          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7단계: 정리                                                  │
│ - ACK = 0, DONE = 0 (다음 모션 준비)                         │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Blackboard 변수

### 모션 제어 변수
```json
{
    "int_var/cmd/val": 0,          // 모션 명령 (Python → Conty)
    "int_var/motion_ack/val": 0,   // 명령 수신 확인 (Conty → Python)
    "int_var/motion_done/val": 0   // 동작 완료 신호 (Conty → Python)
}
```

### 값의 의미
| 변수 | 값 | 의미 |
|------|-----|------|
| cmd | 100 | 홈 위치로 이동 명령 |
| motion_ack | 600 | cmd=100을 받았다는 확인 (100+500) |
| motion_done | 10100 | cmd=100 동작 완료 (100+10000) |

## 🔒 안전장치

### 1. 초기화 확인
```python
# ACK/DONE을 0으로 설정
bb.set("int_var/motion_ack/val", 0)
bb.set("int_var/motion_done/val", 0)

# 실제로 0이 되었는지 확인
time.sleep(0.05)
if bb.get("int_var/motion_ack/val") != 0:
    Logger.error("Failed to reset ACK")
    return False
```

**왜 필요한가?**
- 이전 모션의 ACK/DONE 값이 남아있으면 잘못된 판단
- 예: motion 100 완료 후 motion 1 시작 시, DONE=10100이 남아있으면 DONE=10001로 오판 가능

### 2. ACK 재시도
```python
for attempt in range(1, 4):  # 최대 3번
    bb.set("int_var/cmd/val", motion_cmd)
    
    if wait_ack_success:
        return True
    
    # 재시도 전 CMD 리셋
    bb.set("int_var/cmd/val", 0)
    time.sleep(0.5)
```

**왜 필요한가?**
- 일시적인 통신 지연이나 Conty 처리 지연 대응
- 3번까지 재시도로 안정성 확보

### 3. 완료 후 정리
```python
# DONE 받은 후
bb.set("int_var/motion_ack/val", 0)
bb.set("int_var/motion_done/val", 0)
```

**왜 필요한가?**
- 다음 모션이 깨끗한 상태에서 시작
- 이전 값 간섭 방지

## 💡 사용 예시

### 기본 사용
```python
# 간단한 방법 (권장)
if context.wait_motion_complete(100):
    Logger.info("Motion completed successfully")
else:
    Logger.error("Motion failed")
```

### 내부 동작
```python
def wait_motion_complete(motion_cmd):
    # 1. ACK/DONE 초기화
    bb.set("int_var/motion_ack/val", 0)
    bb.set("int_var/motion_done/val", 0)
    
    # 2. 초기화 확인
    if bb.get("int_var/motion_ack/val") != 0:
        return False
    
    # 3. CMD 전송 (최대 3번 재시도)
    for attempt in range(1, 4):
        bb.set("int_var/cmd/val", motion_cmd)
        
        # ACK 대기
        if wait_ack(motion_cmd + 500):
            # ACK 받음 - CMD 리셋
            bb.set("int_var/cmd/val", 0)
            break
        
        # 재시도
        bb.set("int_var/cmd/val", 0)
        time.sleep(0.5)
    else:
        return False  # 3번 모두 실패
    
    # 4. DONE 대기
    if not wait_done(motion_cmd + 10000):
        return False
    
    # 5. 정리
    bb.set("int_var/motion_ack/val", 0)
    bb.set("int_var/motion_done/val", 0)
    
    return True
```

## 🐛 문제 해결

### Case 1: ACK 타임아웃
**증상**: "Motion ACK timeout: expected 600 (cmd=100), current 0"

**원인**:
- Conty 프로그램이 실행 중이 아님
- Conty에서 ACK 전송 로직 누락
- 통신 지연

**해결**:
1. Conty 프로그램 상태 확인: `context.check_program_running()`
2. Conty 코드에서 ACK 전송 확인: `bb.set("int_var/motion_ack/val", cmd + 500)`
3. 재시도 횟수 증가: `wait_motion_complete(100, max_retries=5)`

### Case 2: DONE 타임아웃
**증상**: "Motion timeout: expected 10100, current 0"

**원인**:
- 모션이 실제로 완료되지 않음
- Conty에서 DONE 전송 누락
- 타임아웃이 너무 짧음

**해결**:
1. 로봇 상태 확인: `context.robot_state()`
2. Conty 코드에서 DONE 전송 확인: `bb.set("int_var/motion_done/val", cmd + 10000)`
3. 타임아웃 증가: `wait_motion_complete(100, done_timeout=60.0)`

### Case 3: 이전 값 간섭
**증상**: 모션 시작하자마자 완료됨

**원인**:
- 이전 모션의 DONE 값이 남아있음
- 초기화 실패

**해결**:
- 초기화 로직이 자동으로 처리하므로 이제 발생 안 함
- 만약 발생하면 `motion_command_reset()` 수동 호출

## 📈 성능 고려사항

### 타임아웃 설정
```python
# 짧은 모션 (그리퍼 등)
wait_motion_complete(90, done_timeout=5.0)   # 그리퍼 열기

# 중간 모션 (이동)
wait_motion_complete(100, done_timeout=20.0)  # 홈 이동

# 긴 모션 (복잡한 경로)
wait_motion_complete(1032, done_timeout=30.0) # 랙 3층 2번 픽업
```

### 재시도 횟수
```python
# 일반적인 경우
max_retries=3  # 기본값 (권장)

# 통신이 불안정한 경우
max_retries=5

# 빠른 실패가 필요한 경우
max_retries=1
```

## 🔧 Conty 구현 가이드

Conty 프로그램에서 구현해야 할 부분:

```python
# Conty Tree (의사코드)
while True:
    cmd = bb.get("int_var/cmd/val")
    
    if cmd != 0:
        # 1. ACK 전송
        bb.set("int_var/motion_ack/val", cmd + 500)
        
        # 2. 모션 실행
        execute_motion(cmd)
        
        # 3. DONE 전송
        bb.set("int_var/motion_done/val", cmd + 10000)
        
        # 4. CMD 읽었으니 내부적으로 처리 완료
        # (CMD=0은 Python에서 ACK 받은 후 처리)
```

## ✅ 체크리스트

구현 전 확인사항:
- [ ] blackboard.json에 `int_var/motion_ack/val` 추가됨
- [ ] Conty 프로그램이 ACK 전송 (cmd + 500)
- [ ] Conty 프로그램이 DONE 전송 (cmd + 10000)
- [ ] 타임아웃 값이 실제 모션 시간에 맞게 설정됨
- [ ] 재시도 로직이 적절함

테스트 시나리오:
- [ ] 정상 통신 (CMD → ACK → DONE)
- [ ] ACK 타임아웃 → 재시도 → 성공
- [ ] DONE 타임아웃 → 에러 처리
- [ ] 연속 모션 (이전 값 간섭 없음)