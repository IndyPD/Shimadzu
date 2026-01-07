"""
Motion Data Preprocessor

motion_data 폴더의 JSON 파일들을 읽어서
머신러닝 학습에 적합한 형태로 변환합니다.
"""

import json
import os
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import logging

Logger = logging.getLogger(__name__)


class MotionDataPreprocessor:
    """모션 데이터 전처리 클래스"""

    def __init__(self, data_dir: str = None):
        """
        Args:
            data_dir: motion_data 폴더 경로 (기본값: 자동 탐지)
        """
        if data_dir is None:
            # 현재 파일 기준으로 motion_data 경로 자동 설정
            current_dir = Path(__file__).parent.parent
            self.data_dir = current_dir / "motion_data"
        else:
            self.data_dir = Path(data_dir)

        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

        Logger.info(f"[ML Preprocessor] Initialized with data directory: {self.data_dir}")

    def load_all_data(self, min_samples: int = 3) -> Tuple[np.ndarray, np.ndarray, Dict]:
        """
        모든 JSON 파일을 로드하여 학습 데이터로 변환

        Args:
            min_samples: 최소 샘플 수 (이보다 적은 데이터는 제외)

        Returns:
            X: Feature 배열 (N, 6) - [x, y, z, u, v, w]
            y: Label 배열 (N,) - CMD ID
            metadata: 상태명, 샘플 수 등 메타 정보
        """
        X_list = []
        y_list = []
        state_counts = {}
        cmd_to_name = {}

        json_files = list(self.data_dir.glob("*.json"))
        Logger.info(f"[ML Preprocessor] Found {len(json_files)} JSON files")

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                cmd_id = data.get("CMD")
                trajectory = data.get("motion_trajectory", [])

                # 빈 데이터나 너무 짧은 데이터는 제외
                if not trajectory or len(trajectory) < min_samples:
                    Logger.warning(f"[ML Preprocessor] Skipping {json_file.name}: insufficient samples ({len(trajectory)})")
                    continue

                # 상태명 추출 (파일명에서, 타임스탬프 제거)
                # 예: "ALIGNER_FRONT_HOME_20260106_230101.json" → "ALIGNER_FRONT_HOME"
                state_name = json_file.stem
                if '_20' in state_name:  # 타임스탬프 형식 감지
                    state_name = '_'.join(state_name.split('_')[:-2])
                cmd_to_name[cmd_id] = state_name

                # 각 좌표를 독립적인 샘플로 추가
                for coord in trajectory:
                    if len(coord) == 6:  # [x, y, z, u, v, w] 확인
                        X_list.append(coord)
                        y_list.append(cmd_id)

                # 상태별 카운트 누적
                if state_name not in state_counts:
                    state_counts[state_name] = 0
                state_counts[state_name] += len(trajectory)

                Logger.info(f"[ML Preprocessor] Loaded {json_file.name}: {len(trajectory)} samples (CMD {cmd_id})")

            except Exception as e:
                Logger.error(f"[ML Preprocessor] Error loading {json_file.name}: {e}")

        if not X_list:
            raise ValueError("No valid data loaded. Please check your motion_data directory.")

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)

        metadata = {
            "total_samples": len(X),
            "num_states": len(set(y)),
            "state_counts": state_counts,
            "cmd_to_name": cmd_to_name,
            "unique_cmds": sorted(set(y))
        }

        Logger.info(f"[ML Preprocessor] Dataset ready: {len(X)} samples, {metadata['num_states']} states")
        return X, y, metadata

    def augment_data(self, X: np.ndarray, y: np.ndarray, noise_level: float = 0.1) -> Tuple[np.ndarray, np.ndarray]:
        """
        데이터 증강: 작은 노이즈를 추가하여 데이터 부족 문제 완화

        Args:
            X: 원본 Feature
            y: 원본 Label
            noise_level: 노이즈 크기 (좌표의 표준편차 대비 비율)

        Returns:
            증강된 X, y
        """
        # 각 feature의 표준편차 계산
        std_devs = np.std(X, axis=0)

        # 노이즈 추가
        noise = np.random.randn(*X.shape) * std_devs * noise_level
        X_augmented = X + noise

        # 원본 + 증강 데이터 결합
        X_combined = np.vstack([X, X_augmented])
        y_combined = np.hstack([y, y])

        Logger.info(f"[ML Preprocessor] Data augmented: {len(X)} → {len(X_combined)} samples")
        return X_combined, y_combined

    def extract_features(self, X: np.ndarray) -> np.ndarray:
        """
        추가 특징 추출 (선택사항)
        현재 위치에서 거리, 각도 등 유용한 특징 추가 가능

        Args:
            X: 원본 6-DOF 좌표 (N, 6)

        Returns:
            확장된 특징 배열
        """
        # 현재는 원본 6개 특징만 사용
        # 추후 필요시 거리, 속도 등 추가 가능
        return X

    def get_state_name(self, cmd_id: int, metadata: Dict) -> str:
        """
        CMD ID를 상태명으로 변환

        Args:
            cmd_id: CMD ID
            metadata: load_all_data()에서 반환된 메타데이터

        Returns:
            상태명 문자열
        """
        return metadata["cmd_to_name"].get(cmd_id, f"CMD_{cmd_id}")


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)

    preprocessor = MotionDataPreprocessor()
    X, y, metadata = preprocessor.load_all_data()

    print(f"\n=== Dataset Summary ===")
    print(f"Total samples: {metadata['total_samples']}")
    print(f"Number of states: {metadata['num_states']}")
    print(f"\nState distribution:")
    for state, count in sorted(metadata['state_counts'].items(), key=lambda x: -x[1]):
        print(f"  {state}: {count} samples")
