import json
import os
from threading import Lock

class GlobalConfig:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GlobalConfig, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        if self._initialized:
            return

        # 현재 config_manager.py 파일이 위치한 디렉토리 기준
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self._app_config_path = os.path.join(base_dir, "app_config.json")
        self._config_path = os.path.join(base_dir, "configs.json")

        self._app_config = self._load_json(self._app_config_path)
        self._config = self._load_json(self._config_path)

        self._initialized = True

    def _load_json(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get(self, key_path, default=None):
        parts = key_path.split(".")
        config = self._merged_config()

        for part in parts:
            if isinstance(config, dict) and part in config:
                config = config[part]
            else:
                return default
        return config

    def set(self, key_path, value):
        parts = key_path.split(".")
        ref = self._config
        for part in parts[:-1]:
            ref = ref.setdefault(part, {})
        ref[parts[-1]] = value

    def _merged_config(self):
        merged = dict(self._config)
        for k, v in self._app_config.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged

    def reload(self):
        self._app_config = self._load_json(self._app_config_path)
        self._config = self._load_json(self._config_path)

    def get_app_config(self):
        return self._app_config

    def get_config(self):
        return self._config

    def save(self):  # ✅ 이 부분 추가
        with open(self._config_path, "w", encoding='utf-8') as f:
            json.dump(self._config, f, indent=2)

