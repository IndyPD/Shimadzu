## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from device_pb2_grpc import *
from config_pb2_grpc import *
from control_pb2_grpc import *
from rtde_pb2_grpc import *
from ethercat_pb2_grpc import *
from hri_pb2_grpc import *
from linear_pb2_grpc import *
from ethercat_pb2_grpc import *
from cri_pb2_grpc import *

import common_msgs_pb2 as common_data
import hri_msgs_pb2 as conty_data
import device_msgs_pb2 as device_data
import control_msgs_pb2 as control_data
import rtde_msgs_pb2 as rtde_data
import config_msgs_pb2 as config_data
import cri_msgs_pb2 as cri_data
import hri_msgs_pb2 as conty_data
import hri_pb2_grpc as conty_grpc
import common as Common
import managers as Managers

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

from .boot_socket_client import BootSocketClient as BootClient
from .config_socket_client import ConfigSocketClient as ConfigClient
from .control_socket_client import ControlSocketClient as ControlClient
from .device_socket_client import DeviceSocketClient as DeviceClient
from .rtde_socket_client import RTDESocketClient as RTDEClient
from .ethercat_client import EtherCATClient as EcatClient
from .cri_client import CRIClient
from .linear_control_client import LinearControlClient as LinearClient
from .ethercat_client import EtherCATClient as EcatClient
from .conty_servicer import ContySocketServicer as ContyServicer
from .indydcp_servicer import IndyDcpServicer as IndyDCP
