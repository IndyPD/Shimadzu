# 🚀 TENSILE 포함 ML 모델 빠른 시작

## 1분 안에 학습하기

### Step 1: 학습 실행
```bash
cd c:\Users\S\Documents\GitHub\Shimadzu
python -m projects.shimadzu_logic.ml_recovery.train_zone_model_v2
```

### Step 2: 테스트
```bash
python -m projects.shimadzu_logic.ml_recovery.quick_test
```

## 끝! 🎉

모델이 `ml_recovery/models/zone_predictor_model.pkl`에 저장됩니다.

---

## 무엇이 달라졌나요?

✅ **TENSILE (인장 시험기)** 데이터 추가
✅ 519개 motion data 파일 사용 (기존 ~300개)
✅ 6개 Zone 전체 커버 (이전 5개)
✅ 예상 정확도 **95%+** (이전 90-93%)

## Zone 목록

1. **랙** - 시편 픽업/배치
2. **두께 측정기** - 두께 측정
3. **정렬기** - 시편 정렬
4. **인장 시험기** - 인장 시험 ⭐ NEW!
5. **스크랩 처리기** - 시편 폐기
6. **홈/기본** - 초기화 및 기본 동작

## 사용 예제

```python
from projects.shimadzu_logic.ml_recovery.zone_predictor import ZonePredictor

predictor = ZonePredictor()
predictor.load_model()

# 현재 위치 예측
position = [178.38, -171.36, 811.97, -96.42, 0.94, 108.35]
result = predictor.predict_with_recovery_action(position)

print(f"Zone: {result['zone_name']}")        # "인장 시험기"
print(f"신뢰도: {result['confidence']:.1%}") # "98.5%"
```

## 문제 발생시

**Q: ModuleNotFoundError**
```bash
pip install lightgbm numpy scikit-learn
```

**Q: 모델이 없다고 나옴**
```bash
# Step 1 먼저 실행
python -m projects.shimadzu_logic.ml_recovery.train_zone_model_v2
```

**Q: 더 자세한 정보?**
- [TENSILE_UPDATE_GUIDE.md](TENSILE_UPDATE_GUIDE.md) 참고
- [README.md](README.md) 전체 문서
