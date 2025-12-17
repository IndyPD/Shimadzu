## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from google.protobuf import json_format

import common_msgs_pb2 as common_data
import boot_msgs_pb2 as boot_data
import boot_pb2_grpc as boot_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

import common as Common
import grpc
import time


class BootSocketClient:
    """
    gRPC client to Boot Server in C++ IndyFramework v3.0
    """

    def __init__(self, ip_addr, port=Common.Config().BOOT_SOCKET_PORT):
        boot_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        boot_stub = boot_grpc.BootStub(boot_channel)
        self.__boot_stub = Common.Utils.StubWithTimeout(stub=boot_stub, timeout=Common.Limits.GRPCTimeOut)

    @Common.Utils.exception_handler
    def GetBootStatus(self):
        response = self.__boot_stub.GetBootStatus(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
