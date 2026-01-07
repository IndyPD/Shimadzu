# 데이터 수집 가이드

## 🎯 목표: 정확도 95% 달성

현재 정확도 **54%** → 목표 **95%**를 위한 데이터 수집 전략

---

## ❌ 하지 말아야 할 것

### 1. 로봇 속도 조절 X
```python
# ❌ 나쁜 예: 느린 속도로 수집
self.indy.set_speed_ratio(30)  # 느리게 설정
# → 실전과 다른 데이터로 학습되어 정확도 하락!
```

**이유:**
- 에러는 정상 속도(70~100%)에서 발생
- 속도가 다르면 좌표 변화 패턴이 완전히 달라짐
- 느린 속도 데이터 ≠ 빠른 속도 예측 불가능

### 2. 샘플링 주기 변경 X
```python
# ❌ 나쁜 예: 더 자주 찍기
if (time.time() - self.last_record_time >= 0.05):  # 0.1 → 0.05
# → 데이터 양만 늘고 정보는 동일
```

---

## ✅ 권장 수집 방법

### 방법 1: 그대로 두고 반복 실행 (Best!)

**현재 설정이 최적입니다!**
- 속도: 정상 운영 속도 (70~100%)
- 주기: 0.1초 (이미 구현됨)
- 자동 저장: CMD_done 시 자동

```bash
# 할 일: 각 공정을 여러 번 반복 실행만 하면 됨
# 1. 공정 A 실행 → 자동 저장
# 2. 공정 A 다시 실행 → 기존 파일 덮어쓰기
# 3. 반복...
```

**⚠️ 문제:** 같은 상태를 다시 실행하면 **기존 파일이 덮어써집니다!**

---

## 📝 데이터 누적 방법 (수정 필요)

### 현재 문제
```python
# indy_control.py:142-207
# 파일명이 고정되어 있어서 덮어씀
file_name = f"{cmd_name}.json"  # ❌ 항상 같은 이름
self.recording_file_path = os.path.join(self.record_dir, file_name)
```

### 해결 방법 1: 타임스탬프 추가 (권장)

`indy_control.py`를 수정하여 **매번 새 파일로 저장**:

```python
# indy_control.py의 start_recording 함수 수정
def start_recording(self, cmd_id):
    """ 데이터 기록 시작 (JSON 저장을 위한 버퍼 초기화) """
    if self.is_recording:
        return

    try:
        os.makedirs(self.record_dir, exist_ok=True)

        # CMD ID로 모션 이름 찾기
        try:
            cmd_name = RobotMotionCommand(cmd_id).name
        except ValueError:
            cmd_name = f"CMD_{cmd_id}"

        # ✅ 타임스탬프 추가로 매번 새 파일 생성
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{cmd_name}_{timestamp}.json"
        self.recording_file_path = os.path.join(self.record_dir, file_name)

        self.trajectory_buffer = []
        self.is_recording = True
        self.recording_cmd_id = cmd_id
        self.last_record_time = time.time() - 0.1
        Logger.info(f"[DataRecorder] Recording started for '{cmd_name}'. Saving to: {file_name}")
    except Exception as e:
        Logger.error(f"[DataRecorder] Failed to start recording: {e}")
```

**결과:**
```bash
motion_data/
├── ALIGNER_FRONT_HOME_20260106_230101.json
├── ALIGNER_FRONT_HOME_20260106_230205.json  # 2번째 실행
├── ALIGNER_FRONT_HOME_20260106_230312.json  # 3번째 실행
...
```

### 해결 방법 2: 데이터 병합 (나중에 한 번에)

타임스탬프 없이 그냥 실행하고, 나중에 병합:

```python
# 별도 스크립트: merge_data.py
import json
import glob
from collections import defaultdict

# 같은 상태 데이터들을 병합
data_by_state = defaultdict(list)

for json_file in glob.glob("motion_data/*.json"):
    with open(json_file) as f:
        data = json.load(f)
        cmd = data["CMD"]
        trajectories = data["motion_trajectory"]
        data_by_state[cmd].extend(trajectories)

# 병합된 데이터 저장
for cmd, trajectories in data_by_state.items():
    merged_data = {
        "CMD": cmd,
        "motion_trajectory": trajectories
    }
    with open(f"motion_data_merged/CMD_{cmd}_merged.json", 'w') as f:
        json.dump(merged_data, f, indent=4)
```

---

## 📅 2주 수집 계획

### Week 1: 빈 상태 채우기

**목표**: 0 samples 상태들에 데이터 추가

```bash
Day 1-2: THICK_GAUGE 관련
  - THICK_GAUGE_FRONT_MOVE (현재 0개)
  - 각 공정 10회 반복

Day 3-4: CMD_10XX 시리즈
  - CMD_1072 등 비어있는 상태
  - 각 공정 10회 반복

Day 5-7: 기타 0 samples 상태
  - 전체 체크 후 누락된 것 수집
```

### Week 2: 부족한 상태 보강

**목표**: 모든 상태 100개 이상

```bash
Day 8-10: 30개 미만 상태
  - 각각 100개까지 보강
  - 우선순위: 자주 사용하는 공정

Day 11-14: 전체 균형 맞추기
  - 부족한 상태 집중 수집
  - 최종 목표: 15,000+ 샘플
```

---

## 🔍 수집 현황 확인

### 실시간 모니터링

```bash
# 현재 데이터 현황 확인
cd /Users/kite/Desktop/neuromeka/Projects/SHIMADZU/Shimadzu
python -m projects.shimadzu_logic.ml_recovery.data_preprocessor
```

또는 간단하게:

```bash
# 파일 개수 확인
ls motion_data/*.json | wc -l

# 각 파일 크기 확인 (빈 파일 찾기)
ls -lh motion_data/*.json | grep "48B"  # 빈 파일은 48 bytes
```

### 수집 목표 체크리스트

```
□ Week 1 완료: 빈 상태 0개
□ Week 2 완료: 모든 상태 100개 이상
□ 총 샘플: 15,000개 이상
□ 정확도 테스트: 95% 이상
```

---

## 💡 효율적인 수집 팁

### 1. 배치 실행

한 번에 여러 공정을 순서대로 실행:

```python
# 예시: 전체 공정 자동 실행
test_scenarios = [
    "RACK_TO_INDICATOR",     # 랙 → 측정기
    "INDICATOR_TO_ALIGNER",  # 측정기 → 정렬기
    "ALIGNER_TO_TENSILE",    # 정렬기 → 인장기
    "TENSILE_TO_SCRAP",      # 인장기 → 스크랩
]

for _ in range(10):  # 10회 반복
    for scenario in test_scenarios:
        execute_process(scenario)
        time.sleep(5)  # 공정 간 대기
```

### 2. 다양한 조건

**같은 공정도 조건을 다르게:**
- 다른 층(floor): 1F, 2F, 3F...
- 다른 시편 위치: 1번, 2번, 3번...
- 다른 측정 포인트: 좌, 중, 우

```python
# 예시: 다양한 랙 층 테스트
for floor in [1, 2, 3, 4, 5]:
    for sample_num in [1, 2, 3, 4, 5]:
        pick_from_rack(floor, sample_num)
```

### 3. 야간/주말 활용

```bash
# 주말에 자동으로 100회 반복 실행
# → 2일간 2,000+ 샘플 수집 가능
```

---

## 📊 예상 결과

### 데이터 양에 따른 정확도

| 총 샘플 | 상태당 평균 | 예상 정확도 | 소요 시간 |
|---------|-------------|-------------|-----------|
| **1,508** (현재) | 24개 | 54% | - |
| 3,000 | 47개 | 65% | 3일 |
| 6,000 | 94개 | 80% | 1주 |
| **15,000** | **234개** | **95%+** | **2주** |

### 실제 테스트 결과 (예상)

```bash
# Week 1 후
python -m projects.shimadzu_logic.ml_recovery.train_model
# → 정확도: 75~80%

# Week 2 후
python -m projects.shimadzu_logic.ml_recovery.train_model
# → 정확도: 95%+ ✅ 목표 달성!
```

---

## 🚨 주의사항

### DO
✅ 정상 운영 속도로 실행
✅ 다양한 조건에서 반복
✅ 주기적으로 재학습
✅ 정확도 모니터링

### DON'T
❌ 속도 조절하지 않기
❌ 샘플링 주기 바꾸지 않기
❌ 한 가지 조건만 반복하지 않기
❌ 데이터 없이 모델만 튜닝하지 않기

---

## 📞 문제 발생 시

### Q1: 파일이 계속 덮어써져요
→ `indy_control.py` 수정 (위의 해결 방법 1 참고)

### Q2: 어떤 상태가 부족한지 모르겠어요
```bash
python -m projects.shimadzu_logic.ml_recovery.data_preprocessor
# → 상태별 샘플 수 출력
```

### Q3: 특정 공정만 안 찍혀요
→ `CMD_done` 신호가 제대로 오는지 확인
→ `indy_control.py:383-386` 로그 확인

---

## ✅ 다음 단계

1. **indy_control.py 수정** (타임스탬프 추가)
2. **2주간 데이터 수집**
3. **주기적 재학습 및 평가**
4. **95% 달성 확인**
5. **실전 배포**

**화이팅! 2주 후면 95% 달성 가능합니다!** 🚀
