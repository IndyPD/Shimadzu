## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from google.protobuf import json_format

import common_msgs_pb2 as common_data
import device_msgs_pb2 as device_data
import config_msgs_pb2 as config_data
import config_pb2_grpc as config_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

import common as Common
import grpc
import time


class ConfigSocketClient:
    """
    gRPC client to Config Server in C++ IndyFramework v3.0
    """
    COLLISION_NO_DETECT = common_data.COLL_NO_DETECT
    COLLISION_PAUSE = common_data.COLL_PAUSE
    COLLISION_RESUME_AFTER_SLEEP = common_data.COLL_RESUME_AFTER_SLEEP
    COLLISION_STOP = common_data.COLL_STOP
    STOPCAT_IMMEDIATE_BRAKE = common_data.IMMEDIATE_BRAKE
    STOPCAT_SMOOTH_BRAKE = common_data.SMOOTH_BRAKE
    STOPCAT_SMOOTH_ONLY = common_data.SMOOTH_ONLY
    GUARD_STOP = common_data.GUARD_STOP

    def __init__(self, ip_addr, port=Common.Config().CONFIG_SOCKET_PORT):
        config_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        config_stub = config_grpc.ConfigStub(config_channel)

        self.__config_stub = Common.Utils.StubWithTimeout(stub=config_stub, timeout=Common.Limits.GRPCTimeOut)

    @Common.Utils.exception_handler
    def GetNonce(self):
        response = self.__config_stub.GetNonce(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def Login(self, digest: str):
        response = self.__config_stub.Login(config_data.Digest(digest=digest))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def ChangePassword(self, digest:str, nonce:str):
        response = self.__config_stub.ChangePassword(
            config_data.ChangePasswordReq(digest=digest, nonce=nonce))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def VerifyToken(self, token: str):
        response = self.__config_stub.VerifyToken(config_data.Token(token=token))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetRefFrame(self, fpos: list):
        """
        Ref Frame
            fpos -> float[6]
        """
        response = self.__config_stub.SetRefFrame(config_data.Frame(
            fpos=list(fpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetRefFramePlanar(self, fpos0: list, fpos1: list, fpos2: list):
        """
        Ref Frame
            fpos -> float[6]
        """
        response = self.__config_stub.SetRefFramePlanar(config_data.PlanarFrame(
            fpos0=list(fpos0), fpos1=list(fpos1), fpos2=list(fpos2)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetLockedJoint(self, locked_joint: int):
        """
        Tool Link
            locked_joint -> int
        """
        response = self.__config_stub.SetLockedJoint(common_data.Int(value=int(locked_joint)))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolLink(self, tool_link: int):
        """
        Tool Link
            tool_link -> int
        """
        response = self.__config_stub.SetToolLink(common_data.Int(value=int(tool_link)))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolFrame(self, fpos: list):
        """
        Tool Frame
            fpos -> float[6]
        """
        response = self.__config_stub.SetToolFrame(config_data.Frame(
            fpos=list(fpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolFrameList(self, tool_frame_list):
        """
        Tool Frame List
            {
              repeated NamedTaskPosition tool_frames
              string default_name
            }
        """
        tool_frame_list_request = config_data.ToolFrameList()
        json_format.ParseDict(tool_frame_list, tool_frame_list_request)

        response = self.__config_stub.SetToolFrameList(tool_frame_list_request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetToolFrameList(self):
        """
        Tool Frame List
            {
              repeated NamedTaskPosition tool_frames
              string default_name
            }
        """
        response = self.__config_stub.GetToolFrameList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetRefFrameList(self, ref_frame_list):
        """
        Ref Frame List
            {
              repeated NamedTaskPosition ref_frames
              string default_name
            }
        """
        ref_frame_list_request = config_data.RefFrameList()
        json_format.ParseDict(ref_frame_list, ref_frame_list_request)

        response = self.__config_stub.SetRefFrameList(ref_frame_list_request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetRefFrameList(self):
        """
        Ref Frame List
            {
              repeated NamedTaskPosition ref_frames
              string default_name
            }
        """
        response = self.__config_stub.GetRefFrameList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCustomPosList(self, custom_pos_list):
        """
        Custom Pos List
            {
              repeated NamedJointPosition custom_pos
            }
        """
        custom_pos_list_request = config_data.CustomPosList()
        json_format.ParseDict(custom_pos_list, custom_pos_list_request)

        response = self.__config_stub.SetCustomPosList(custom_pos_list_request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCustomPosList(self):
        """
        Custom Pos List
            {
              repeated NamedJointPosition custom_pos
            }
        """
        response = self.__config_stub.GetCustomPosList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSpeedRatio(self, speed_ratio: int):
        """
        Speed Ratio
            ratio -> uint32 {0 ~ 100}
        """
        response = self.__config_stub.SetSpeedRatio(config_data.Ratio(
            ratio=speed_ratio
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSpeedRatio(self):
        """
        Speed Ratio
            ratio -> uint32 {0 ~ 100}
        """
        response = self.__config_stub.GetSpeedRatio(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetHomePos(self, home_jpos: list):
        """
        Joint Home Position
            jpos -> double[]
        """
        response = self.__config_stub.SetHomePosition(config_data.JointPos(
            jpos=home_jpos
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetHomePos(self):
        """
        Joint Home Position
            jpos -> double[]
        """
        response = self.__config_stub.GetHomePosition(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPackPos(self):
        """
        Joint Pack Position
            jpos -> double[]
        """
        response = self.__config_stub.GetPackPosition(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetToolList(self):
        """
        Tool Configuration List
            {
                'tools': [
                    {
                      string name
                      float execute_time
                      repeated DigitalSignal do_signals
                      repeated EndtoolSignal enddo_signals
                      repeated AnalogSignal ao_signals
                      repeated AnalogSignal endao_signals
                      repeated string expression
                      repeated GripperCommand gripper_signals
                      repeated ModbusCommand modbus_signals
                    }
                ]
            }
        """
        response = self.__config_stub.GetToolList(common_data.Empty())

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolList(self, tool_list: dict):
        """
        Tool Configuration List
            {
                'tools': [
                    {
                      string name
                      float execute_time
                      repeated DigitalSignal do_signals
                      repeated EndtoolSignal enddo_signals
                      repeated AnalogSignal ao_signals
                      repeated AnalogSignal endao_signals
                      repeated string expression
                      repeated GripperCommand gripper_signals
                      repeated ModbusCommand modbus_signals
                    }
                ]
            }
        """
        tool_list_request = config_data.ToolList()
        json_format.ParseDict(tool_list, tool_list_request)
        response = self.__config_stub.SetToolList(tool_list_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetConveyorList(self):
        """
        Conveyor List
            {
                'conveyor_list': [
                    {
                      string name = 1;
                      Encoder encoder = 2;
                      Trigger trigger = 3;
                      float offset_dist = 4;
                      float working_dist = 5;
                      Nrmk.IndyFramework.Vector direction = 6;
                      PosePair starting_pose = 10;
                      PosePair terminal_pose = 11;
                    }
                ]
            }
        """
        response = self.__config_stub.GetConveyorList(common_data.Empty())

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorList(self, conveyor_list: dict):
        """
        Conveyor List
            {
                'conveyor_list': [
                    {
                      string name = 1;
                      Encoder encoder = 2;
                      Trigger trigger = 3;
                      float offset_dist = 4;
                      float working_dist = 5;
                      Nrmk.IndyFramework.Vector direction = 6;
                      PosePair starting_pose = 10;
                      PosePair terminal_pose = 11;
                    }
                ]
            }
        """
        conveyor_list_request = config_data.ConveyorList()
        json_format.ParseDict(conveyor_list, conveyor_list_request)
        response = self.__config_stub.SetConveyorList(conveyor_list_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetVisionServerList(self):
        """
        VisionServerList
            {
                'vision_servers': [
                    {
                      string name = 1;
                      VisionServerType vision_server_type = 2;
                      string ip = 3;
                      uint32 port = 4;
                    }
                ]
            }
        """
        response = self.__config_stub.GetVisionServerList(common_data.Empty())

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetVisionServerList(self, vision_servers: dict):
        """
        VisionServerList
            {
                'vision_servers': [
                    {
                      string name = 1;
                      VisionServerType vision_server_type = 2;
                      string ip = 3;
                      uint32 port = 4;
                    }
                ]
            }
        """
        vision_servers_request = config_data.VisionServerList()
        json_format.ParseDict(vision_servers, vision_servers_request)
        response = self.__config_stub.SetVisionServerList(vision_servers_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetModbusServerList(self):
        """
        ModbusServerList
            {
                'vision_servers': [
                    {
                      string name = 1;
                      VisionServerType vision_server_type = 2;
                      string ip = 3;
                      uint32 port = 4;
                    }
                ]
            }
        """
        response = self.__config_stub.GetModbusServerList(common_data.Empty())

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetModbusServerList(self, modbus_servers: dict):
        """
        ModbusServerList
            {
                'modbus_servers': [
                    {
                      string name = 1;
                      string ip = 2;
                      int32 port = 3;
                      int32 unit_id = 4;
                    }
                ]
            }
        """
        modbus_servers_request = config_data.ModbusServerList()
        json_format.ParseDict(modbus_servers, modbus_servers_request)
        response = self.__config_stub.SetModbusServerList(modbus_servers_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDefaultCollSensParam(self):
        response = self.__config_stub.GetDefaultCollSensParam(common_data.Empty())

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCollSensParam(self, col_params: dict):
        col_params_request = config_data.CollisionThresholds()
        json_format.ParseDict(col_params, col_params_request)
        response = self.__config_stub.SetCollSensParam(col_params_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDIConfigList(self, di_config_list: dict):
        """
        DI Configuration List
            {
                'di_configs': [
                    {
                        'function_code': 2,
                        'function_name': "name",
                        'triggerSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                        'successSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                        'failureSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                    }
                ]
            }
        """
        di_list_request = config_data.DIConfigList()
        json_format.ParseDict(di_config_list, di_list_request)

        response = self.__config_stub.SetDIConfigList(di_list_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDIConfigList(self):
        """
        DI Configuration List
            {
                'di_configs': [
                    {
                        'function_code': 2,
                        'function_name': "name",
                        'triggerSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}],
                        'successSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}],
                        'failureSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                    }
                ]
            }
        """
        response = self.__config_stub.GetDIConfigList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDOConfigList(self, do_config_list: dict):
        """
        DO Configuration List
            {
                'do_configs': [
                    {
                        'state_code': 2,
                        'state_name': "name",
                        'onSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}],
                        'offSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                    }
                ]
            }
        """
        do_list_request = config_data.DOConfigList()
        json_format.ParseDict(do_config_list, do_list_request)

        response = self.__config_stub.SetDOConfigList(do_list_request)

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDOConfigList(self):
        """
        DO Configuration List
            {
                'do_configs': [
                    {
                        'state_code': 2,
                        'state_name': "name",
                        'onSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}],
                        'offSignals': [{'address': 1, 'state': 1}, {'address': 2, 'state': 0}]
                    }
                ]
            }
        """
        response = self.__config_stub.GetDOConfigList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetAutoServoOff(self, enable: bool, time: float):
        """
        Auto Servo-Off Config
            enable -> bool
            time -> float
        """
        response = self.__config_stub.SetAutoServoOff(config_data.AutoServoOffConfig(
            enable=enable, time=time
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetAutoServoOff(self):
        """
        Auto Servo-Off Config
            enable -> bool
            time -> float
        """
        response = self.__config_stub.GetAutoServoOff(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetJointControlGain(self, kp: list, kv: list, kl2: list):
        """
        Joint Control Gains:
            kp   -> float[6]
            kv   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.SetJointControlGain(config_data.JointGainSet(
            kp=list(kp), kv=list(kv), kl2=list(kl2)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetJointControlGain(self):
        """
        Joint Control Gains:
            kp   -> float[6]
            kv   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.GetJointControlGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetTaskControlGain(self, kp, kv, kl2):
        """
        Task Control Gains:
            kp   -> float[6]
            kv   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.SetTaskControlGain(config_data.TaskGainSet(
            kp=list(kp), kv=list(kv), kl2=list(kl2)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTaskControlGain(self):
        """
        Task Control Gains:
            kp   -> float[6]
            kv   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.GetTaskControlGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetImpedanceControlGain(self, mass, damping, stiffness, kl2):
        """
        Impedance Control Gains:
            mass   -> float[6]
            damping   -> float[6]
            stiffness   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.SetImpedanceControlGain(config_data.ImpedanceGainSet(
            mass=list(mass), damping=list(damping), stiffness=list(stiffness), kl2=list(kl2)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetImpedanceControlGain(self):
        """
        Impedance Control Gains:
            mass   -> float[6]
            damping   -> float[6]
            stiffness   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.GetImpedanceControlGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetForceControlGain(self, kp, kv, kl2, mass, damping, stiffness, kpf, kif):
        """
        Impedance Control Gains:
            mass   -> float[6]
            damping   -> float[6]
            stiffness   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.SetForceControlGain(config_data.ForceGainSet(
            kp=list(kp), kv=list(kv), kl2=list(kl2), mass=list(mass), damping=list(damping), stiffness=list(stiffness),
            kpf=list(kpf), kif=list(kif)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetForceControlGain(self):
        """
        Impedance Control Gains:
            mass   -> float[6]
            damping   -> float[6]
            stiffness   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.GetForceControlGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetComplianceControlJointGain(self, kp, kv, kl2, kd, bd, rate, ki, ks, km):

        response = self.__config_stub.SetComplianceControlJointGain(config_data.ComplianceGainSet(
            kp=list(kp), kv=list(kv), kl2=list(kl2), kd=list(kd), bd=list(bd), rate=list(rate), ki=list(ki), ks=list(ks), km=list(km)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetComplianceControlJointGain(self):

        response = self.__config_stub.GetComplianceControlJointGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSensorlessParams(self, tau_bound):
        response =  self.__config_stub.SetSensorlessParams(config_data.SensorlessParams(
            tau_bound=list(tau_bound)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetSensorlessParams(self):

        response = self.__config_stub.GetSensorlessParams(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


    @Common.Utils.exception_handler
    def SetCustomControlGain2(self, gain0, gain1):
        return self._set_custom_control_gain(gain0, gain1, *[([0]*6) for _ in range(8)])

    @Common.Utils.exception_handler
    def SetCustomControlGain3(self, gain0, gain1, gain2):
        return self._set_custom_control_gain(gain0, gain1, gain2, *[([0]*6) for _ in range(7)])

    @Common.Utils.exception_handler
    def SetCustomControlGain6(self, gain0, gain1, gain2, gain3, gain4, gain5):
        return self._set_custom_control_gain(gain0, gain1, gain2, gain3, gain4, gain5, *[([0]*6) for _ in range(4)])

    @Common.Utils.exception_handler
    def SetCustomControlGain(self, gain0, gain1, gain2, gain3, gain4, gain5, gain6, gain7, gain8, gain9):
        return self._set_custom_control_gain(gain0, gain1, gain2, gain3, gain4, gain5, gain6, gain7, gain8, gain9)

    def _set_custom_control_gain(self, *gains):
        """
        Private method to set custom control gains with a variable number of gain arrays.

        Args:
            *gains: Up to 10 lists of gain values. Each gain should be a list of floats.
        """
        response = self.__config_stub.SetCustomControlGain(config_data.CustomGainSet(
            gain0=list(gains[0]), gain1=list(gains[1]), gain2=list(gains[2]), gain3=list(gains[3]),
            gain4=list(gains[4]), gain5=list(gains[5]), gain6=list(gains[6]), gain7=list(gains[7]),
            gain8=list(gains[8]), gain9=list(gains[9])
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


    @Common.Utils.exception_handler
    def GetCustomControlGain(self):
        """
        Impedance Control Gains:
            mass   -> float[6]
            damping   -> float[6]
            stiffness   -> float[6]
            kl2  -> float[6]
        """
        response = self.__config_stub.GetCustomControlGain(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetFrictionComp(self, control_comp: bool, control_comp_levels: list,
                        dt_comp: bool, dt_comp_levels: list):
        """
        Friction Compensation Set:
            joint_idx   -> uint32
            control_comp_enable   -> bool
            control_comp_levels   -> int32[6]
            teaching_comp_enable   -> bool
            teaching_comp_levels   -> int32[6]
        """
        response = self.__config_stub.SetFrictionComp(config_data.FrictionCompSet(
            control_comp_enable=control_comp, control_comp_levels=list(control_comp_levels),
            teaching_comp_enable=dt_comp, teaching_comp_levels=list(dt_comp_levels)
        ))

        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetFrictionComp(self):
        """
        Friction Compensation Set:
            joint_idx   -> uint32
            control_comp_enable   -> bool
            control_comp_levels   -> int32[6]
            teaching_comp_enable   -> bool
            teaching_comp_levels   -> int32[6]
        """
        response = self.__config_stub.GetFrictionComp(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetMountPos(self, rot_y=0.0, rot_z=0.0):
        """
        Mounting Angles:
            rot_y   -> float
            rot_z   -> float
        """
        response = self.__config_stub.SetMountPos(config_data.MountingAngles(
            ry=rot_y, rz=rot_z
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetMountPos(self):
        """
        Mounting Angles:
            rot_y   -> float
            rot_z   -> float
        """
        response = self.__config_stub.GetMountPos(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetFTSensorConfig(self,
                          dev_type, com_type, ip_address,
                               ft_frame_translation_offset_x=0.0,
                               ft_frame_translation_offset_y=0.0,
                               ft_frame_translation_offset_z=0.0,
                               ft_frame_rotation_offset_r=0.0,
                               ft_frame_rotation_offset_p=0.0,
                               ft_frame_rotation_offset_y=0.0):
        response = self.__config_stub.SetFTSensorConfig(config_data.FTSensorDevice(
            dev_type=dev_type, com_type=com_type,ip_address=ip_address,
            ft_frame_translation_offset_x=ft_frame_translation_offset_x,
            ft_frame_translation_offset_y=ft_frame_translation_offset_y,
            ft_frame_translation_offset_z=ft_frame_translation_offset_z,
            ft_frame_rotation_offset_r=ft_frame_rotation_offset_r,
            ft_frame_rotation_offset_p=ft_frame_rotation_offset_p,
            ft_frame_rotation_offset_y=ft_frame_rotation_offset_y))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetFTSensorConfig(self):
        response = self.__config_stub.GetFTSensorConfig(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolProperty(self, mass: float, center_of_mass: list, inertia: list):
        """
        Tool Properties:
            mass   -> float
            center_of_mass   -> float[3]
            inertia   -> float[6]
        """
        response = self.__config_stub.SetToolProperty(config_data.ToolProperties(
            mass=mass, center_of_mass=list(center_of_mass), inertia=list(inertia)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetToolProperty(self):
        """
        Tool Properties:
            mass   -> float
            center_of_mass   -> float[3]
            inertia   -> float[6]
        """
        response = self.__config_stub.GetToolProperty(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCollSensLevel(self, level: int):
        """
        Collision Sensitivity Level:
            level -> uint32
        """
        response = self.__config_stub.SetCollSensLevel(config_data.CollisionSensLevel(
            level=level
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCollSensLevel(self):
        """
        Collision Sensitivity Level:
            level -> uint32
        """
        response = self.__config_stub.GetCollSensLevel(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCollisonModelMargin(self):
        """
        Collision Sensitivity Level:
            level -> uint32
        """
        response = self.__config_stub.GetCollisonModelMargin(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCollisonModelMargin(self, collision_margin: float, recover_margin: float):
        """
        CollisionModelMargin:
            collision_margin: float, recover_margin: float
        """
        response = self.__config_stub.SetCollisonModelMargin(
            config_data.CollisionModelMargin(
                collision_margin=collision_margin, recover_margin=recover_margin
            ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetToolShapeList(self, tool_shape_list):
        """
        tool_shape_list: ToolShapeList
            - geometries: NamedGeometry[]
              - shapes: Shape[]
              - name: string
            - default_name: string
        """
        tool_shape_list_request = config_data.ToolShapeList()
        json_format.ParseDict(tool_shape_list, tool_shape_list_request)
        response = self.__config_stub.SetToolShapeList(tool_shape_list_request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetToolShapeList(self):
        """
        tool_shape_list: ToolShapeList
            - geometries: NamedGeometry[]
              - shapes: Shape[]
              - name: string
            - default_name: string
        """
        response = self.__config_stub.GetToolShapeList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEnvironmentList(self, env_list):
        """
        env_list: EnvironmentList
            - environments: NamedEnvironment[]
              - zones: Zone[]
              - name: string
            - default_name: string
        """
        env_list_request = config_data.EnvironmentList()
        json_format.ParseDict(env_list, env_list_request)
        response = self.__config_stub.SetEnvironmentList(env_list_request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetEnvironmentList(self):
        """
        env_list: EnvironmentList
            - environments: NamedEnvironment[]
              - zones: Zone[]
              - name: string
            - default_name: string
        """
        response = self.__config_stub.GetEnvironmentList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCollSensParam(self):
        """
        Collision Params:
            j_torque_bases                  -> double[6]
            j_torque_tangents               -> double[6]
            t_torque_bases                  -> double[6]
            t_torque_tangents               -> double[6]
            error_bases                     -> double[6]
            error_tangents                  -> double[6]
            t_constvel_torque_bases         -> double[6]
            t_constvel_torque_tangents      -> double[6]
            t_conveyor_torque_bases         -> double[6]
            t_conveyor_torque_tangents      -> double[6]
        """
        response = self.__config_stub.GetCollSensParam(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCollPolicy(self, policy=COLLISION_NO_DETECT,
                      sleep_time=0, gravity_time=0.1):
        """
        Collision Policies:
            policy -> uint32
            sleep_time -> float
            gravity_time -> float
        """
        response = self.__config_stub.SetCollPolicy(config_data.CollisionPolicy(
            policy=policy, sleep_time=sleep_time, gravity_time=gravity_time
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCollPolicy(self):
        """
        Collision Policy:
            policy -> uint32
            sleep_time -> float
            gravity_time -> float
        """
        response = self.__config_stub.GetCollPolicy(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetOnStartProgramConfig(self, auto_run: bool, index: int):
        """
        OnStartProgramConfig:
            auto_run -> bool
            index -> uint32
        """
        response = self.__config_stub.SetOnStartProgramConfig(
            config_data.OnStartProgramConfig(auto_run=auto_run, index=index))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetOnStartProgramConfig(self):
        """
        OnStartProgramConfig:
            auto_run -> bool
            index -> uint32
        """
        response = self.__config_stub.GetOnStartProgramConfig(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSimpleCollThreshold(self):
        response = self.__config_stub.SetSimpleCollThreshold(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSafetyLimits(self, power_limit: float, power_limit_ratio: float,
                        tcp_force_limit: float, tcp_force_limit_ratio: float,
                        tcp_speed_limit: float, tcp_speed_limit_ratio: float):
        # joint_limits: list):
        """
        Safety Limits:
            power_limit             -> float
            power_limit_ratio       -> float
            tcp_force_limit         -> float
            tcp_force_limit_ratio   -> float
            tcp_speed_limit         -> float
            tcp_speed_limit_ratio   -> float
            # joint_limits   -> float[]
        """
        response = self.__config_stub.SetSafetyLimits(config_data.SafetyLimits(
            power_limit=power_limit, power_limit_ratio=power_limit_ratio,
            tcp_force_limit=tcp_force_limit, tcp_force_limit_ratio=tcp_force_limit_ratio,
            tcp_speed_limit=tcp_speed_limit, tcp_speed_limit_ratio=tcp_speed_limit_ratio  # ,
            # joint_limits=list(joint_limits)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSafetyLimits(self):
        """
        Safety Limits:
            power_limit             -> float
            power_limit_ratio       -> float
            tcp_force_limit         -> float
            tcp_force_limit_ratio   -> float
            tcp_speed_limit         -> float
            tcp_speed_limit_ratio   -> float
            joint_limits   -> float[]
        """
        response = self.__config_stub.GetSafetyLimits(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPathConfig(self):
        """
        PathConfig:
            config_path          -> str
            program_path         -> str
            index_program_path   -> str
        """
        response = self.__config_stub.GetPathConfig(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSafetyStopConfig(self, jpos_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            jvel_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            jtau_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            tvel_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            tforce_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            power_limit_stop_cat=STOPCAT_IMMEDIATE_BRAKE,
                            safegd_stop_cat=[STOPCAT_SMOOTH_BRAKE, STOPCAT_SMOOTH_BRAKE],
                            safegd_type=[GUARD_STOP, GUARD_STOP]):
        """
        Safety Stop Category:
            jpos_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            jvel_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            jtau_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            tvel_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            tforce_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            power_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            safegd_stop_cat[2] = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            safegd_type[2] = GUARD_NONE(0) | GUARD_STOP(1) | GUARD_PAUSE(2) | GUARD_PAUSE_RESUME(3) | REDUCED_MODE(4)
        """
        response = self.__config_stub.SetSafetyStopConfig(config_data.SafetyStopConfig(
            joint_position_limit_stop_cat=jpos_limit_stop_cat,
            joint_speed_limit_stop_cat=jvel_limit_stop_cat,
            joint_torque_limit_stop_cat=jtau_limit_stop_cat,
            tcp_speed_limit_stop_cat=tvel_limit_stop_cat,
            tcp_force_limit_stop_cat=tforce_limit_stop_cat,
            power_limit_stop_cat=power_limit_stop_cat,
            safegd_stop_cat=safegd_stop_cat,
            safegd_type=safegd_type
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSafetyStopConfig(self):
        """
        Safety Stop Category:
            joint_position_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            joint_speed_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            joint_torque_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            tcp_speed_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            tcp_force_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            power_limit_stop_cat = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            safegd_stop_cat[2] = IMMEDIATE_BRAKE(0) | SMOOTH_BRAKE(1) | SMOOTH_ONLY(2)
            safegd_type[2] = GUARD_NONE(0) | GUARD_STOP(1) | GUARD_PAUSE(2) | GUARD_PAUSE_RESUME(3) | REDUCED_MODE(4)
        """
        response = self.__config_stub.GetSafetyStopConfig(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetReducedRatio(self):
        response = self.__config_stub.GetReducedRatio(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetReducedSpeed(self):
        response = self.__config_stub.GetReducedSpeed(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetReducedSpeed(self, speed):
        response = self.__config_stub.SetReducedSpeed(config_data.SetReducedSpeedReq(speed=speed))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetTeleOpParams(self, smooth_factor, cutoff_freq, error_gain):
        response = self.__config_stub.SetTeleOpParams(
            config_data.TeleOpParams(smooth_factor=smooth_factor,
                                     cutoff_freq=cutoff_freq,
                                     error_gain=error_gain))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTeleOpParams(self):
        response = self.__config_stub.GetTeleOpParams(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetKinematicsParams(self):
        response = self.__config_stub.GetKinematicsParams(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


############################
# Main
############################
if __name__ == "__main__":
    config_client = ConfigSocketClient(Common.Config().CONTROLLER_IP_ADDRESS, Common.Config().CONFIG_SOCKET_PORT)

    # di_list = [{'address': 0, 'state': 1}, {'address': 2, 'state': 0}]
    # di_config_list = config_client.GetDIConfigList()
    # print(di_config_list)
    time.sleep(1)

    fric_comp = config_client.GetFrictionComp()
    print(fric_comp)

    config_client.SetFrictionComp(control_comp=False, control_comp_levels=[1, 1, 1, 1, 1, 1],
                                  dt_comp=True, dt_comp_levels=[1, 1, 1, 1, 1, 1])
    time.sleep(1)
