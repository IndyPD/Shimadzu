import os.path
import shutil
from typing import Tuple, Dict, Any

from .file_io import *
from .logging import Logger


PATH_CONFIG_DEFAULT = "default/configs"
PATH_CONFIG = "local/configs"


##
# @class    ConfigFile
# @brief    Config file reader with default & local configs.
#           Update if new default key is added or local file is not initialized.
#           Keep other errors on local files to trace errors later.
class ConfigFile(Dict):
    def __init__(self, fname, read_fun=load_json, save_fun=save_json, local_path=PATH_CONFIG,
                 default_path=PATH_CONFIG_DEFAULT):
        super().__init__()
        self.fname = fname
        self.read_fun, self.save_fun = read_fun, save_fun
        self.local_path = os.path.join(get_proj_path(), local_path)
        self.default_path = os.path.join(get_proj_path(), default_path)
        self.fpath_local = os.path.join(self.local_path, self.fname)
        self.fpath_default = os.path.join(self.default_path, self.fname)

        # load default config first
        try:
            self.default_dict = read_fun(self.fpath_default)
        except Exception as e:
            Logger.error(f"Error in reading default config file {self.fpath_default}")
            Logger.error(str(e))
            exit(1)

        # copy default config if local file is missing
        if not os.path.isfile(self.fpath_local):
            Logger.error(f"Local config file {fname} is not set. Initialize with default")
            create_dir(os.path.dirname(self.fpath_local))
            shutil.copyfile(self.fpath_default, self.fpath_local)

        # load local config
        try:
            self.update(**read_fun(self.fpath_local))
        except Exception as e:
            # Do not overwrite local file on error to for trace errors later. Just use default config
            self.update(**self.default_dict)
            Logger.error(f"Error in reading config file {self.fpath_local} - ignore local file and use default")
            Logger.error(str(e))

        # update keys newly defined by version update
        new_keys = set(self.default_dict.keys()) - set(self.keys())
        if len(new_keys) > 0:
            for key in new_keys:
                self[key] = self.default_dict[key]
                Logger.info(f"New default parameter {key}={self[key]} is added on {fname} - update local file")
            self.save_fun(self.fpath_local, self)

    def default(self, key: Any):
        return self.default_dict[key]

    def item(self, key: Any) -> 'ConfigItem':
        return ConfigItem(self, key)


##
# @class ConfigItem
# @brief get local parameter on call, optionally get default param
class ConfigItem:
    def __init__(self, config_file: ConfigFile, key: Any):
        self.config_file = config_file
        self.key = key

    def __call__(self, default=False):
        if default:
            return self.config_file.default(self.key)
        else:
            return self.config_file[self.key]
