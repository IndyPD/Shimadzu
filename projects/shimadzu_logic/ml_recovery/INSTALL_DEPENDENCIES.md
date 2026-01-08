# ML 학습 의존성 설치 가이드

## 필수 패키지 설치

TENSILE 포함 ML 모델을 학습하려면 다음 패키지가 필요합니다.

### 1. 기본 패키지 설치 (필수)

```bash
pip install scikit-learn numpy
```

또는 conda 환경이라면:

```bash
conda install scikit-learn numpy
```

### 2. LightGBM 설치 (선택, 권장)

LightGBM은 RandomForest보다 빠르고 정확합니다:

```bash
pip install lightgbm
```

또는:

```bash
conda install -c conda-forge lightgbm
```

## 설치 확인

```bash
python -c "import sklearn; import numpy; print('✅ 기본 패키지 설치 완료')"
python -c "import lightgbm; print('✅ LightGBM 설치 완료')"
```

## 환경별 설치 방법

### Windows (Anaconda 환경)

```bash
# 현재 환경 활성화
conda activate NRMK

# 패키지 설치
conda install scikit-learn numpy
conda install -c conda-forge lightgbm

# 또는 pip으로
pip install scikit-learn numpy lightgbm
```

### Linux / macOS

```bash
pip3 install scikit-learn numpy lightgbm
```

## 설치 후 학습 실행

```bash
cd c:\Users\S\Documents\GitHub\Shimadzu

# TENSILE 포함 학습
python -m projects.shimadzu_logic.ml_recovery.train_zone_model_v2
```

## 문제 해결

### Q: "No module named 'sklearn'"

**해결**:
```bash
pip install scikit-learn
```

### Q: LightGBM 설치 실패

**해결**: LightGBM 없이도 학습 가능 (RandomForest 사용)
```bash
# scikit-learn만 설치
pip install scikit-learn numpy
```

학습 시 자동으로 RandomForest로 fallback됩니다.

### Q: Conda 환경에서 설치 안됨

**해결**:
```bash
# pip 업그레이드
python -m pip install --upgrade pip

# 재시도
pip install scikit-learn numpy lightgbm
```

## 패키지 버전 확인

```bash
pip list | grep -E "scikit-learn|numpy|lightgbm"
```

예상 출력:
```
lightgbm              4.1.0
numpy                 1.24.3
scikit-learn          1.3.0
```

---

설치 완료 후 [QUICKSTART_TENSILE.md](QUICKSTART_TENSILE.md)로 이동하세요!
