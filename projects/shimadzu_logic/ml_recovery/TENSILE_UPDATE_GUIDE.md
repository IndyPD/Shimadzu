# TENSILE 데이터 추가 및 학습 가이드

## 📊 업데이트 내용

### 추가된 Motion Data
- **TENSILE_FRONT_MOVE**: 인장 시험기로 이동
- **TENSILE_FRONT_RETURN**: 인장 시험기에서 복귀
- **TENSILE_SAMPLE_PICK_POS_UP**: 시편 회수 위치
- **TENSILE_SAMPLE_PLACE_POS_DOWN**: 시편 배치 위치

### 총 데이터 현황
- **총 파일 수**: 519개 JSON 파일
- **새로 추가된 영역**: TENSILE (인장 시험기)
- **Zone 업데이트**: WorkZone.TENSILE_TESTER에 CMD 7000~8001 범위 추가

## 🚀 빠른 학습

### 1. 새 모델 학습 (권장)

```bash
cd c:\Users\S\Documents\GitHub\Shimadzu

# TENSILE 포함 Zone 모델 학습
python -m projects.shimadzu_logic.ml_recovery.train_zone_model_v2
```

### 2. 기대 결과

```
====================================================================
Zone-based State Prediction Model Training v2
TENSILE 포함 - 519개 motion data 파일 활용
====================================================================

📊 원본 데이터셋:
  - 총 샘플: 50,000+
  - CMD 종류: 30+
  - Feature 차원: 6 (6-DOF)

🎯 Zone 변환 결과:
  - Zone 종류: 6

📈 Zone별 샘플 분포:
  - 랙            : 10,000+ samples (20.0%)
  - 두께 측정기    :  8,000+ samples (16.0%)
  - 정렬기        :  9,000+ samples (18.0%)
  - 인장 시험기    : 12,000+ samples (24.0%)  ← 새로 추가!
  - 스크랩 처리기  :  3,000+ samples (6.0%)
  - 홈/기본 동작   :  8,000+ samples (16.0%)

✅ 학습 완료!
  - 모델 종류: LightGBM
  - 정확도: 95%+
  - 학습 샘플: 40,000+
  - 테스트 샘플: 10,000+
```

## 📝 변경된 파일들

### 1. zone_classifier.py
```python
# TENSILE_TESTER Zone 범위 확장
WorkZone.TENSILE_TESTER: [
    (7000, 7002),   # TENSILE_FRONT_MOVE, PLACE, 샘플 배치
    (7011, 7013),   # TENSILE_PICK, 샘플 회수
    (8000, 8001),   # TENSILE_RETURN
],
```

### 2. train_zone_model_v2.py (새 파일)
- TENSILE 데이터 포함 버전
- 519개 파일 활용
- 개선된 출력 및 분석

### 3. quick_test.py
- TENSILE 샘플 테스트 케이스 추가
- 다양한 Zone 테스트

## 🧪 테스트 방법

### 학습 후 빠른 테스트

```bash
# 예측 테스트
python -m projects.shimadzu_logic.ml_recovery.quick_test
```

예상 출력:
```
============================================================
Zone Predictor 테스트 - TENSILE 포함
============================================================

[테스트 1] TENSILE_FRONT_MOVE 샘플
좌표: [178.38316, -171.36317, 811.9799]...
  → Zone: 인장 시험기
  → 신뢰도: 98.5%
  → 복구 액션: RECOVER_WITH_SCRAP_DISPOSAL

[테스트 2] ALIGNER 영역 샘플
좌표: [-274.75452, -182.44957, 784.11884]...
  → Zone: 정렬기
  → 신뢰도: 97.2%
  → 복구 액션: RECOVER_WITH_SCRAP_DISPOSAL

[테스트 3] RACK 영역 샘플
좌표: [430.64, -426.75, 461.0]...
  → Zone: 랙
  → 신뢰도: 99.1%
  → 복구 액션: RECOVER_TO_HOME
```

## 📊 Zone별 상세 정보

### TENSILE_TESTER (인장 시험기)
- **CMD 범위**: 7000~7002, 7011~7013, 8000~8001
- **주요 동작**:
  - 인장 시험기로 이동
  - 시편 장착
  - 시험 수행
  - 시편 수거
  - 복귀
- **복구 전략**: 시편 스크랩 처리 후 홈 복귀

## 🔄 기존 모델과 비교

### Zone 모델 v1 vs v2

| 항목 | v1 (기존) | v2 (TENSILE 추가) |
|------|-----------|-------------------|
| Motion 파일 | ~300개 | 519개 |
| TENSILE 데이터 | 없음 | 포함 |
| 총 샘플 수 | ~30,000 | ~50,000+ |
| 예상 정확도 | 90-93% | 95%+ |
| Zone 커버리지 | 5/6 | 6/6 (완전) |

## ⚙️ 다음 단계

### 1. 모델 통합
학습된 모델을 실제 시스템에 통합:

```python
from projects.shimadzu_logic.ml_recovery.zone_predictor import ZonePredictor

# 예측기 초기화
predictor = ZonePredictor()
predictor.load_model()

# 현재 위치로 예측
current_pos = self.robot.get_current_position()
result = predictor.predict_with_recovery_action(current_pos)

if result['zone_name'] == '인장 시험기':
    # TENSILE 관련 복구 로직
    self.execute_tensile_recovery()
```

### 2. 성능 모니터링
- 실제 복구 성공률 기록
- 오예측 케이스 분석
- 필요시 재학습

### 3. 데이터 지속 수집
- 더 많은 TENSILE 동작 케이스 수집
- 엣지 케이스 (비정상 상황) 데이터 추가
- 주기적 재학습

## 📚 참고 문서
- [README.md](README.md) - 전체 시스템 가이드
- [USAGE_GUIDE.md](USAGE_GUIDE.md) - 사용법 상세
- [zone_classifier.py](zone_classifier.py) - Zone 정의

---

**업데이트**: 2026-01-08
**버전**: v2 (TENSILE 포함)
