import os
import time
import json
import py_trees

from .file_io import load_json
from .logging import Logger
from .singleton import SingletonMeta

# BB_CONFIG_DEFAULT_PATH = 'projects/frying_template/configs/blackboard.json'
# BB_CONFIG_DEFAULT_PATH = os.environ.get(
#     "BB_CONFIG_PATH", "projects/frying_template/configs/blackboard.json"
# )

def initialize_blackboard_from_json(board, json_file_path):
    board.clear()
    data = load_json(json_file_path)
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("$"):  # string starts with $ is a runtime script
            board.set(key, eval(value[1:]))
        else:
            board.set(key, value)
    Logger.info(f"Blackboard initialized from {json_file_path}")


# class GlobalBlackboard(py_trees.blackboard.Blackboard, metaclass=SingletonMeta):
#     def __init__(self):
#         super().__init__()
#         # initialize_blackboard_from_json(self, json_file_path)
#
#     def initialize(self, json_file_path):
#         initialize_blackboard_from_json(self, json_file_path)


class GlobalBlackboard(py_trees.blackboard.Blackboard, metaclass=SingletonMeta):
    def __init__(self, json_file_path=""):
        super().__init__()
        self.config_path = json_file_path
        initialize_blackboard_from_json(self, json_file_path)

def initialize_global_blackboard(json_file_path):
    """Create the singleton instance before other modules import it."""
    return GlobalBlackboard(json_file_path)

