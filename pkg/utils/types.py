import json
import numpy as np


class AttributeDict(dict):
    def __getattr__(self, name):
        return self[name]


def get_class_name(obj):
    return obj.__class__.__name__


def enum2dict(enumcls):
    return {e.name:e.value for e in enumcls}


def str2bool(v, raise_unexpected=True):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        if raise_unexpected:
            raise RuntimeError('Boolean argument expected.')
        else:
            return None


def str2val(str_val, list_to_np=False):
    val = json.loads(str_val)
    if list_to_np:
        if isinstance(val, list):
            val = np.array(val)
    return val


def str2val_dict(str_dict, list_to_np=False):
    return {k: str2val(v, list_to_np=list_to_np) for k, v in str_dict.items()}
    return total, used, available


def divide_bytes_arr(uint_arr):
    num = uint_arr.astype(np.uint)
    return np.floor(num%0x10000/0x100).astype(np.uint)%0x100, num%0x100


def combine_bytes_arr(up_byte_arr, lo_byte_arr):
    return up_byte_arr*0x100 + lo_byte_arr
