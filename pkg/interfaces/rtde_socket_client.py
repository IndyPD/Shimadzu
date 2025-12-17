## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

import common_msgs_pb2 as common_data
import rtde_msgs_pb2 as rtde_data
import rtde_pb2_grpc as rtde_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

import math
import sys

from google.protobuf import json_format
import grpc

import common as Common


class RTDESocketClient:
    """
    gRPC client to RTDE Server in C++ IndyFramework v3.0
    """
    PROG_IDLE = common_data.PROG_IDLE
    PROG_RUNNING = common_data.PROG_RUNNING
    PROG_PAUSING = common_data.PROG_PAUSING
    PROG_STOPPING = common_data.PROG_STOPPING
    CTRL_IDLE = common_data.OpState.OP_IDLE
    CTRL_VIOLATE = common_data.OpState.OP_VIOLATE
    CTRL_MANUAL_RECOVER = common_data.OpState.OP_MANUAL_RECOVER
    CTRL_SYSTEM_OFF = common_data.OpState.OP_SYSTEM_OFF
    CTRL_BRAKE = common_data.OpState.OP_BRAKE_CONTROL

    def __init__(self, ip_addr, port=Common.Config().RTDE_SOCKET_PORT):
        rtde_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        rtde_stub = rtde_grpc.RTDataExchangeStub(rtde_channel)
        self.__rtde_stub = Common.Utils.StubWithTimeout(stub=rtde_stub, timeout=Common.Limits.GRPCTimeOut)

    @Common.Utils.exception_handler
    def GetMotionData(self):
        """
        Motion Data:
            traj_state   -> TrajState
            traj_progress   -> int32
            is_in_motion  -> bool
            is_target_reached  -> bool
            is_pausing  -> bool
            is_stopping  -> bool
            has_motion  -> bool
            speed_ratio  -> int32
            motion_id  -> int32
            remain_distance  -> float
            motion_queue_size  -> uint32
            cur_traj_progress  -> int32
            response  -> Response
        """
        response = self.__rtde_stub.GetMotionData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetControlData(self):
        """
        Control Data:
            running_hours   -> uint32
            running_mins   -> uint32
            running_secs  -> uint32
            op_state  -> OpState
            sim_mode  -> bool
            q  -> float[6]
            qdot  -> float[6]
            p  -> float[6]
            pdot  -> float[6]
            ref_frame  -> float[6]
            tool_frame  -> float[6]
            response  -> Response
        """
        response = self.__rtde_stub.GetControlData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetControlState(self):

        response = self.__rtde_stub.GetControlState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetControlState(self):
        """
        ControlData2:
            q  -> float[6]
            qdot  -> float[6]
            qddot  -> float[6]
            qdes  -> float[6]
            qdotdes  -> float[6]
            qddotdes  -> float[6]

            p  -> float[6]
            pdot  -> float[6]
            pddot  -> float[6]
            pdes  -> float[6]
            pdotdes  -> float[6]
            pddotdes  -> float[6]

            tau  -> float[6]
            tau_act  -> float[6]
            tau_ext  -> float[6]
            tau_jts  -> float[6]
            response -> Response
        """
        response = self.__rtde_stub.GetControlState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetIOData(self):
        """
        IO Data:
            di   -> DigitalSignal[]
            do   -> DigitalSignal[]
            ai  -> AnalogSignal[]
            ao  -> AnalogSignal[]
            end_di  -> EndtoolSignal[]
            end_do  -> EndtoolSignal[]
            end_ai  -> AnalogSignal[]
            end_ao  -> AnalogSignal[]
            response  -> Response
        """
        response = self.__rtde_stub.GetIOData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetServoData(self):
        """
        Servo Data:
            status_codes   -> string[]
            temperatures   -> float[]
            voltages  -> float[]
            currents  -> float[]
            servo_actives  -> bool[]
            brake_actives  -> bool[]
            response  -> Response
            torques -> float[]
        """
        response = self.__rtde_stub.GetServoData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetControlState(self):
        """
         Control Data:
             q  -> float[]
             qdot  -> float[]
             qddot  -> float[]
             qdes  -> float[]
             qdotdes  -> float[]
             qddotdes  -> float[]
             p  -> float[]
             pdot  -> float[]
             pddot  -> float[]
             pdes  -> float[]
             pdotdes  -> float[]
             pddotdes  -> float[]
             tau  -> float[]
             tau_act  -> float[]
             tau_ext  -> float[]
             tau_jts  -> float[]
         """
        response = self.__rtde_stub.GetControlState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetViolationData(self):
        """
        Violation Data:
            violation_code   -> uint64
            j_index   -> uint32
            i_args  -> int32[]
            f_args  -> float[]
            violation_str  -> string
            response  -> Response
        """
        response = self.__rtde_stub.GetViolationData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetViolationMessageQueue(self):
        """
        Violation Data:
            violation_code   -> uint64
            j_index   -> uint32
            i_args  -> int32[]
            f_args  -> float[]
            violation_str  -> string
            response  -> Response
        """
        response = self.__rtde_stub.GetViolationMessageQueue(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetProgramData(self):
        """
        Program Data:
            program_state   -> ProgramState
            cmd_id   -> int32
            sub_cmd_id  -> int32
            running_hours  -> int32
            running_mins  -> int32
            running_secs  -> int32
            program_name  -> string
            program_alarm  -> string
            program_annotation  -> string
            response  -> Response
        """
        response = self.__rtde_stub.GetProgramData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetStopState(self):
        response = self.__rtde_stub.GetStopState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCollisionModelState(self):
        response = self.__rtde_stub.GetCollisionModelState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    def TestFunction(self, code: int, msg: str):
        try:
            response = self.__rtde_stub.TestFunction(rtde_data.TestRequest(
                intVal=code, strVal=msg
            ))
            return json_format.MessageToDict(response,
                                             including_default_value_fields=True,
                                             preserving_proto_field_name=True,
                                             use_integers_for_enums=True)
        except grpc.RpcError as ex:
            print('GRPC Exception: code ' + str(ex.code()) + ' - details: ' + str(ex.details()))
            return None

    @Common.Utils.exception_handler
    def GetReservedData(self):
        """
        Reserved Data:
            qres1   -> float[6]
            qres2   -> float[6]
            qdotres1  -> float[6]
            qdotres2  -> float[6]
            eres1  -> float[6]
            eres2  -> float[6]
            edotres1  -> float[6]
            edotres2  -> float[6]
            taures1  -> float[6]
            taures2  -> float[6]
        """
        response = self.__rtde_stub.GetReservedData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


############################
# Main
############################
if __name__ == "__main__":
    rtde_client = RTDESocketClient(Common.Config().CONTROLLER_IP_ADDRESS, Common.Config().RTDE_SOCKET_PORT)
    control_data = rtde_client.GetControlData()
    print(control_data)
    # rtde_data = rtde_client.GetMotionData()
    # print(rtde_data)
    print('Test 0: ' + str(rtde_client.TestFunction(code=0, msg='Test 0')))
    print('Test 1: ' + str(rtde_client.TestFunction(code=1, msg='Test 1')))
    print('Test 2: ' + str(rtde_client.TestFunction(code=2, msg='Test 2')))
    print('Test 3: ' + str(rtde_client.TestFunction(code=3, msg='Test 3')))
