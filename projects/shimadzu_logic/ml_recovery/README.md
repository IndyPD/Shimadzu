# ML 기반 로봇 상태 예측 및 자동 복구 시스템

로봇이 에러로 멈췄을 때, 현재 위치를 기반으로 어떤 모션 상태로 향하고 있었는지 예측하여 안전하게 복구하는 머신러닝 시스템입니다.

## 🎯 목표

- **정확도**: 95% 이상
- **추론 속도**: 실시간 (< 1ms)
- **모델**: 경량 (LightGBM 또는 RandomForest)

## 📁 디렉토리 구조

```
ml_recovery/
├── __init__.py                 # 모듈 초기화
├── data_preprocessor.py        # 데이터 전처리
├── model_trainer.py            # 모델 학습
├── state_predictor.py          # 실시간 예측
├── recovery_integration.py     # FSM 통합
├── train_model.py              # 학습 스크립트
├── README.md                   # 이 파일
└── models/                     # 학습된 모델 저장
    ├── state_predictor_model.pkl
    └── model_metadata.json
```

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
# 기본 (RandomForest 사용)
pip install numpy scikit-learn

# 권장 (LightGBM - 더 높은 성능)
pip install lightgbm numpy scikit-learn
```

### 2. 모델 학습

현재 수집된 motion_data를 사용하여 모델을 학습합니다:

```bash
# 프로젝트 루트에서 실행
cd /Users/kite/Desktop/neuromeka/Projects/SHIMADZU/Shimadzu

# 모델 학습
python -m projects.shimadzu_logic.ml_recovery.train_model
```

또는:

```bash
cd projects/shimadzu_logic
python -m ml_recovery.train_model
```

### 3. 학습 결과 확인

학습이 완료되면 다음과 같은 정보가 출력됩니다:

```
=== 학습 결과 ===
모델 종류: LightGBM
정확도: 96.5%
학습 샘플: 1,234
테스트 샘플: 309

✅ 목표 정확도 달성! (96.5% >= 95%)
```

### 4. 예측 사용 예제

```python
from projects.shimadzu_logic.ml_recovery import StatePredictor

# 예측기 초기화
predictor = StatePredictor()
predictor.load_model()

# 현재 위치로 상태 예측
current_position = [430.64, -426.75, 461.00, 90.26, -179.47, 0.35]
result = predictor.predict_with_recovery_action(current_position)

print(f"예측 상태: {result['state_name']}")
print(f"신뢰도: {result['confidence'] * 100:.2f}%")
print(f"복구 액션: {result['recovery_action']}")
```

## 📊 데이터 수집 방법

### 현재 방식 (자동)

`indy_control.py`에서 이미 자동으로 데이터를 수집하고 있습니다:

- **시점**: 각 모션 CMD 시작 시 (`start_recording`)
- **주기**: 0.1초마다 좌표 기록
- **종료**: CMD_done 신호 수신 시 자동 저장
- **형식**: `motion_data/[상태명].json`

### 데이터 형식

```json
{
  "CMD": 24,
  "motion_trajectory": [
    [430.64, -426.75, 461.00, 90.26, -179.47, 0.35],
    [430.63, -426.74, 461.01, 90.26, -179.46, 0.34],
    ...
  ]
}
```

### 데이터 품질 향상 팁

1. **다양한 공정 테스트**: 모든 상태의 데이터를 고르게 수집
2. **반복 실행**: 같은 상태를 여러 번 실행하여 데이터 누적
3. **품질 확인**: 너무 짧은 데이터(< 3 samples)는 자동 제외됨

## 🔧 FSM 통합 방법

### robot_context.py 또는 logic_context.py에 추가

```python
from ml_recovery import get_ml_recovery_instance

class RobotContext:
    def __init__(self):
        # 기존 초기화 코드...

        # ML 복구 시스템 초기화
        self.ml_recovery = get_ml_recovery_instance(enable=True)

    def handle_error_recovery(self):
        """에러 발생 시 ML 기반 복구"""
        # 현재 로봇 위치 가져오기
        current_pos = self.get_current_position()  # [x, y, z, u, v, w]

        # ML로 상태 예측
        result = self.ml_recovery.predict_current_state(current_pos)

        if result['success']:
            Logger.info(f"예측된 상태: {result['state_name']}")
            Logger.info(f"신뢰도: {result['confidence'] * 100:.2f}%")

            # 복구 시퀀스 가져오기
            recovery_sequence = self.ml_recovery.get_recovery_motion_sequence(
                result['predicted_cmd'],
                result['recovery_action']
            )

            # 복구 모션 실행
            for motion_cmd in recovery_sequence:
                self.execute_motion(motion_cmd)
```

## 📈 성능 개선 방법

### 정확도가 목표(95%)에 못 미칠 경우:

1. **더 많은 데이터 수집**
   ```bash
   # 각 공정을 5~10회 반복 실행하여 데이터 축적
   ```

2. **데이터 증강 사용**
   ```python
   # train_model.py 실행 시 증강 옵션 선택
   # 작은 노이즈를 추가하여 데이터 2배 증가
   ```

3. **하이퍼파라미터 튜닝**
   ```python
   # model_trainer.py의 params 조정
   params = {
       'num_leaves': 50,  # 31 → 50
       'learning_rate': 0.03,  # 0.05 → 0.03
       ...
   }
   ```

## 🔍 문제 해결

### Q1: "Model not found" 에러

**해결**: 먼저 모델을 학습하세요
```bash
python -m projects.shimadzu_logic.ml_recovery.train_model
```

### Q2: 정확도가 낮음 (< 95%)

**원인**: 데이터 부족
**해결**:
- 모든 공정을 최소 5회 이상 실행하여 데이터 수집
- 학습 시 데이터 증강 옵션 활성화

### Q3: 일부 상태만 데이터가 있음

**현재 상황**: 정상 - 점진적으로 데이터 추가 가능
**권장사항**:
- 현재 데이터로 우선 학습
- 새로운 공정 테스트 후 재학습
- 모델은 새 데이터로 언제든 재학습 가능

## 📝 모델 재학습

새로운 데이터가 추가되면 언제든 재학습 가능:

```bash
# 1. 새로운 공정 실행 → motion_data에 자동 저장됨

# 2. 모델 재학습
python -m projects.shimadzu_logic.ml_recovery.train_model

# 3. 기존 모델 자동 덮어쓰기 (백업은 수동으로 필요 시)
```

## 🎓 알고리즘 설명

### 학습 과정

1. **데이터 로드**: motion_data/*.json 파일들을 읽어서 (X, y) 데이터셋 구성
2. **전처리**: 각 좌표를 독립적인 샘플로 변환
3. **Train/Test Split**: 80% 학습, 20% 테스트
4. **모델 학습**: LightGBM 또는 RandomForest
5. **평가**: 정확도, F1-score, 혼동 행렬
6. **저장**: 모델 + 메타데이터

### 예측 과정

1. **입력**: 현재 로봇 위치 [x, y, z, u, v, w]
2. **예측**: 모델이 가장 가능성 높은 CMD ID 반환
3. **신뢰도**: 확률 기반 신뢰도 계산
4. **복구 액션**: CMD ID → 복구 시퀀스 매핑

### 복구 로직

- **시편 있음** (CMD 2000~8000): 스크랩 처리 → 홈 복귀
- **시편 없음** (나머지): 안전 후퇴 → 홈 복귀

## 📚 API 문서

### StatePredictor

```python
predictor = StatePredictor()
predictor.load_model()

# 단순 예측
cmd_id, state_name, confidence = predictor.predict(position)

# 복구 액션 포함
result = predictor.predict_with_recovery_action(position)
# Returns: {
#   "success": True,
#   "predicted_cmd": 24,
#   "state_name": "ALIGNER_FRONT_HOME",
#   "confidence": 0.98,
#   "recovery_action": "RECOVER_TO_HOME"
# }
```

### MLRecoveryIntegration

```python
from ml_recovery import get_ml_recovery_instance

ml_recovery = get_ml_recovery_instance(enable=True)

# 상태 확인
status = ml_recovery.get_status()

# 복구 실행
success = ml_recovery.execute_ml_recovery(current_position, robot_context)
```

## 🤝 기여

새로운 기능 추가나 개선 제안은 언제든 환영합니다!

---

**작성일**: 2026-01-06
**버전**: 1.0.0
