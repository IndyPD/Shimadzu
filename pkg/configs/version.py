import os
from ..utils.file_io import *
from ..utils.process_control import *
from ..utils.logging import *
import semver
import importlib

CURRENT_VERSION = "0.1.0"
SEMVER = semver.parse(CURRENT_VERSION)
VERSION_LOG_FILE = os.path.join(get_proj_path(),'local','version.cfg')
create_dir(os.path.dirname(VERSION_LOG_FILE))
KEY_LIST = ['major', 'minor', 'patch', 'prerelease', 'build']


def get_version_down_to(key):
    idx_key = KEY_LIST.index(key)+1
    return ".".join([str(SEMVER[KEY_LIST[i]]) for i in range(idx_key)])


def load_prev_version():
    return try_or(load_text, args=[VERSION_LOG_FILE], default=CURRENT_VERSION, callback_error=Logger.warn)


def save_current_version():
    save_text(VERSION_LOG_FILE, CURRENT_VERSION)


def check_version_patch_local():
    Logger.info("Software version: %s"%CURRENT_VERSION)
    prev_version = load_prev_version()
    if CURRENT_VERSION != prev_version:
        Logger.warn("Software version is updated %s -> %s"%(prev_version, CURRENT_VERSION))
        Logger.warn("START VERSION PATCH PROTOCOL")
        update_local(prev_version)
    save_current_version()


def update_local(prev_version):
    PATCH_KEYS = sorted(PATCH_DICT.keys())
    for key in PATCH_KEYS:
        if prev_version < key:
            patch_module = importlib.import_module('Patches.%s' % PATCH_DICT[key])
            patch_module.run()


PATCH_DICT = {
    # '0.1.2': 'patch013'
}