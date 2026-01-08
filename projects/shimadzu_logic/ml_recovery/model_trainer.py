"""
Model Trainer for State Prediction

LightGBM을 사용한 경량 고성능 모델 학습
- 빠른 추론 속도 (< 1ms)
- 높은 정확도 목표 (95%+)
- 간단한 학습 파이프라인
"""

import json
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, Tuple
import logging

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    lgb = None  # Define lgb as None for type hints
    LIGHTGBM_AVAILABLE = False
    logging.warning("LightGBM not installed. Will use sklearn RandomForest as fallback.")

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.ensemble import RandomForestClassifier

Logger = logging.getLogger(__name__)


class ModelTrainer:
    """모델 학습 및 평가 클래스"""

    def __init__(self, model_dir: str = None):
        """
        Args:
            model_dir: 학습된 모델 저장 경로
        """
        if model_dir is None:
            current_dir = Path(__file__).parent
            self.model_dir = current_dir / "models"
        else:
            self.model_dir = Path(model_dir)

        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model = None
        self.metadata = None

        Logger.info(f"[ML Trainer] Initialized with model directory: {self.model_dir}")

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        metadata: Dict,
        test_size: float = 0.2,
        use_lgb: bool = True
    ) -> Dict:
        """
        모델 학습 및 평가

        Args:
            X: Feature 배열 (N, 6)
            y: Label 배열 (N,)
            metadata: 데이터 메타정보
            test_size: 테스트 데이터 비율
            use_lgb: LightGBM 사용 여부 (False면 RandomForest)

        Returns:
            학습 결과 딕셔너리 (정확도, 분류 보고서 등)
        """
        # Train/Test Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        Logger.info(f"[ML Trainer] Train samples: {len(X_train)}, Test samples: {len(X_test)}")

        # 모델 선택 및 학습
        if use_lgb and LIGHTGBM_AVAILABLE:
            self.model = self._train_lightgbm(X_train, y_train, X_test, y_test)
            model_type = "LightGBM"
        else:
            self.model = self._train_random_forest(X_train, y_train)
            model_type = "RandomForest"

        # 평가
        if model_type == "LightGBM":
            # LightGBM Booster는 확률을 반환하므로 argmax로 클래스 추출
            y_pred_proba = self.model.predict(X_test)
            y_pred = np.argmax(y_pred_proba, axis=1)
        else:
            y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        Logger.info(f"[ML Trainer] {model_type} Test Accuracy: {accuracy * 100:.2f}%")

        # 상세 분류 보고서
        class_names = [metadata["cmd_to_name"].get(cmd, f"CMD_{cmd}") for cmd in sorted(set(y))]
        report = classification_report(y_test, y_pred, target_names=class_names, output_dict=True)

        # 혼동 행렬
        conf_matrix = confusion_matrix(y_test, y_pred)

        # 메타데이터 저장
        self.metadata = metadata
        self.metadata["model_type"] = model_type
        self.metadata["test_accuracy"] = float(accuracy)

        results = {
            "model_type": model_type,
            "accuracy": float(accuracy),
            "classification_report": report,
            "confusion_matrix": conf_matrix.tolist(),
            "train_samples": len(X_train),
            "test_samples": len(X_test)
        }

        # 상태별 정확도 출력
        Logger.info("\n[ML Trainer] Per-state Accuracy:")
        for state_name in class_names:
            if state_name in report:
                f1 = report[state_name]["f1-score"]
                Logger.info(f"  {state_name}: {f1 * 100:.2f}% F1-score")

        return results

    def _train_lightgbm(self, X_train, y_train, X_val, y_val):
        """LightGBM 모델 학습"""
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        params = {
            'objective': 'multiclass',
            'num_class': len(np.unique(y_train)),
            'metric': 'multi_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1
        }

        Logger.info("[ML Trainer] Training LightGBM model...")
        model = lgb.train(
            params,
            train_data,
            num_boost_round=200,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
        )

        return model

    def _train_random_forest(self, X_train, y_train) -> RandomForestClassifier:
        """Random Forest 모델 학습 (fallback)"""
        Logger.info("[ML Trainer] Training RandomForest model...")
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)
        return model

    def save_model(self, filename: str = "state_predictor_model.pkl"):
        """모델 저장"""
        if self.model is None:
            raise ValueError("No model to save. Train a model first.")

        model_path = self.model_dir / filename
        metadata_path = self.model_dir / "model_metadata.json"

        # 모델 저장
        with open(model_path, 'wb') as f:
            pickle.dump(self.model, f)

        # 메타데이터 저장 (NumPy 타입을 Python 기본 타입으로 변환)
        metadata_serializable = self._convert_to_serializable(self.metadata)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_serializable, f, indent=2, ensure_ascii=False)

        Logger.info(f"[ML Trainer] Model saved to {model_path}")
        Logger.info(f"[ML Trainer] Metadata saved to {metadata_path}")

    def _convert_to_serializable(self, obj):
        """NumPy 타입을 Python 기본 타입으로 변환"""
        if isinstance(obj, dict):
            return {key: self._convert_to_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_serializable(item) for item in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj

    def load_model(self, filename: str = "state_predictor_model.pkl"):
        """저장된 모델 로드"""
        model_path = self.model_dir / filename
        metadata_path = self.model_dir / "model_metadata.json"

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        # 모델 로드
        with open(model_path, 'rb') as f:
            self.model = pickle.load(f)

        # 메타데이터 로드
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)

        Logger.info(f"[ML Trainer] Model loaded from {model_path}")
        return self.model, self.metadata


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)

    from data_preprocessor import MotionDataPreprocessor

    # 데이터 로드
    preprocessor = MotionDataPreprocessor()
    X, y, metadata = preprocessor.load_all_data()

    # 모델 학습
    trainer = ModelTrainer()
    results = trainer.train(X, y, metadata)

    print(f"\n=== Training Results ===")
    print(f"Model Type: {results['model_type']}")
    print(f"Accuracy: {results['accuracy'] * 100:.2f}%")
    print(f"Train Samples: {results['train_samples']}")
    print(f"Test Samples: {results['test_samples']}")

    # 모델 저장
    trainer.save_model()
