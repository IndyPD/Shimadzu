import json


class ConfigManager:
    def __init__(self, config_path="projects/frying_template/configs/app_config.json"):
        self.config_path = config_path
        self._config = {}
        self.load_config()

    def load_config(self, config_path=None):
        if config_path is None:
            config_path = self.config_path
        else:
            self.config_path = config_path

        with open(config_path, 'r') as file:
            self._config = json.load(file)

    def save_config(self, config_path=None):
        if config_path is None:
            config_path = self.config_path
        else:
            self.config_path = config_path

        with open(config_path, "w") as json_file:
            json.dump(self._config, json_file)

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value

    def delete(self, key):
        del self._config[key]
