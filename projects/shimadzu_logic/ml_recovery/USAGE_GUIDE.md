# ML 복구 시스템 사용 가이드

## 📊 현재 상태

### 학습 결과
- **현재 정확도**: ~54% (목표: 95%)
- **데이터 샘플**: 1,508개 → 증강 후 3,016개
- **상태 종류**: 64개

### 문제 분석
정확도가 낮은 주요 원인:
1. **데이터 부족**: 상태당 평균 24개 샘플 (최소 100개 권장)
2. **상태 너무 많음**: 64개 상태를 구분하기에는 데이터가 부족
3. **유사한 좌표**: 일부 상태들의 궤적이 겹침

## 🚀 정확도 95% 달성 방법

### 방법 1: 데이터 수집 (권장)

**목표**: 각 상태당 최소 100개 샘플

```bash
# 현재 각 공정을 5~10회 반복 실행하여 데이터 축적
# motion_data에 자동 저장됨

# 데이터 수집 후 재학습
python -m projects.shimadzu_logic.ml_recovery.train_model
```

**예상 결과**:
- 1,500개 → 6,000개 샘플: ~70% 정확도
- 1,500개 → 10,000개 샘플: ~85% 정확도
- 1,500개 → 20,000개 샘플: **95%+ 정확도 달성**

### 방법 2: 상태 그룹화 (빠른 해결)

유사한 상태를 그룹화하여 분류 난이도 감소:

```python
# 64개 상태 → 10개 주요 그룹
- RACK_OPERATIONS (랙 관련)
- INDICATOR_OPERATIONS (측정기 관련)
- ALIGNER_OPERATIONS (정렬기 관련)
- TENSILE_OPERATIONS (인장기 관련)
- SCRAP_OPERATIONS (스크랩 관련)
- HOME_OPERATIONS (홈 관련)
- ...
```

이 방법으로 현재 데이터로도 90%+ 달성 가능

### 방법 3: LightGBM 설치

RandomForest보다 성능이 좋은 LightGBM 사용:

```bash
pip install lightgbm

# 재학습
python -m projects.shimadzu_logic.ml_recovery.train_model
```

**예상 개선**: +5~10% 정확도 향상

## 📈 단계별 실행 계획

### Phase 1: 즉시 개선 (현재 데이터로)

1. **LightGBM 설치**
   ```bash
   pip install lightgbm
   ```

2. **모델 하이퍼파라미터 튜닝**
   - RandomForest: `n_estimators=200`, `max_depth=30`
   - 예상 정확도: 60~65%

### Phase 2: 데이터 수집 (1주일)

1. **중요 상태 우선 수집**
   - 랙 픽업/리턴
   - 측정기 배치/회수
   - 정렬기 배치/회수
   - 인장기 장착/수거
   - 스크랩 처리

2. **각 상태 10회 반복**
   - 예상 데이터: ~5,000 샘플
   - 예상 정확도: 75~80%

### Phase 3: 완전 학습 (2주일)

1. **모든 공정 20회 이상 실행**
   - 예상 데이터: ~15,000 샘플
   - **예상 정확도: 95%+ 달성**

2. **실전 배포**
   - logic_context.py에 통합
   - 에러 복구 자동화

## 💡 현재 시스템 사용법

비록 정확도가 낮지만, 현재도 사용 가능합니다:

### 1. 예측 테스트

```python
from projects.shimadzu_logic.ml_recovery import StatePredictor

predictor = StatePredictor()
predictor.load_model()

# 현재 위치로 예측
position = [430.64, -426.75, 461.00, 90.26, -179.47, 0.35]
result = predictor.predict_with_recovery_action(position)

if result['confidence'] > 0.7:  # 신뢰도 70% 이상만 사용
    print(f"예측: {result['state_name']}")
    print(f"복구: {result['recovery_action']}")
else:
    print("신뢰도 낮음 - 수동 복구 필요")
```

### 2. 선택적 사용

```python
# 고신뢰도 예측만 자동 복구
if result['confidence'] > 0.8:
    # ML 기반 자동 복구
    execute_ml_recovery()
else:
    # 기존 수동 복구
    execute_manual_recovery()
```

## 🔧 모델 개선 팁

### 데이터 품질 향상

1. **일관된 실행**
   - 같은 환경에서 반복 실행
   - 속도 일정하게 유지

2. **다양성 확보**
   - 다른 층(floor) 테스트
   - 다른 시편 위치 테스트

3. **에지 케이스 포함**
   - 시작 부분 데이터
   - 종료 부분 데이터
   - 중간 지점 데이터

### 모델 파라미터 조정

```python
# model_trainer.py 수정
RandomForestClassifier(
    n_estimators=200,      # 100 → 200
    max_depth=30,          # 20 → 30
    min_samples_split=2,   # 5 → 2
    n_jobs=-1
)
```

## 📊 성능 모니터링

### 정확도 확인

```bash
# 현재 모델 평가
python -m projects.shimadzu_logic.ml_recovery.evaluate_model
```

### 상태별 성능

```bash
# 어떤 상태가 잘 예측되는지 확인
# evaluation_results.json 파일 확인
cat ml_recovery/models/evaluation_results.json
```

## 🎯 목표 달성 로드맵

| 단계 | 데이터 양 | 예상 정확도 | 소요 시간 |
|------|-----------|-------------|-----------|
| **현재** | 1,508 | 54% | - |
| Phase 1 | 3,000 | 65% | 즉시 (증강) |
| Phase 2 | 6,000 | 80% | 1주 |
| **Phase 3** | **15,000+** | **95%+** | **2주** |

## ✅ 다음 단계

1. **LightGBM 설치**
   ```bash
   pip install lightgbm
   ```

2. **데이터 수집 계획 수립**
   - 어떤 공정을 우선적으로 테스트할지 결정
   - 일일 목표 설정 (예: 하루 500 샘플)

3. **주기적 재학습**
   ```bash
   # 새 데이터 추가될 때마다
   python -m projects.shimadzu_logic.ml_recovery.train_model
   python -m projects.shimadzu_logic.ml_recovery.evaluate_model
   ```

4. **정확도 모니터링**
   - 95% 달성 시 실전 배포
   - 미달 시 추가 데이터 수집

## 🤔 FAQ

### Q: 지금 당장 사용 가능한가요?
A: 신뢰도 70% 이상일 때만 선택적으로 사용 권장. 완전 자동화는 95% 달성 후.

### Q: 얼마나 많은 데이터가 필요한가요?
A: 상태당 최소 100개, 총 15,000~20,000개 샘플 권장.

### Q: 데이터 수집에 시간이 얼마나 걸리나요?
A: 공정 1회 실행 = 평균 20개 샘플. 하루 50회 실행 = 1,000 샘플. 약 2주면 충분.

### Q: RandomForest vs LightGBM 차이는?
A: LightGBM이 5~10% 더 정확하고, 추론 속도도 빠릅니다. 설치 권장.

---

**업데이트**: 2026-01-06
**다음 목표**: 데이터 15,000개 수집, 정확도 95% 달성
