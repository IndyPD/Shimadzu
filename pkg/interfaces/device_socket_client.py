## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from google.protobuf import json_format
import grpc
import common as Common
import managers as Managers
import common_msgs_pb2 as common_data
import device_msgs_pb2 as device_data
import device_pb2_grpc as device_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect


class DeviceSocketClient:
    """
    gRPC client to Device Server in C++ IndyFramework v3.0
    """

    def __init__(self, ip_addr, port=Common.Config().DEVICE_SOCKET_PORT):
        device_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        device_stub = device_grpc.DeviceStub(device_channel)
        self.__device_stub = Common.Utils.StubWithTimeout(stub=device_stub, timeout=Common.Limits.GRPCTimeOut)
        self._logger = Managers.LogManager()

    @Common.Utils.exception_handler
    def SetBrakes(self, brake_state_list: list):
        """
        brake_state_list -> bool[6]
        """
        motor_list = []
        motor_idx = 0
        for brake_state in brake_state_list:
            motor_list.append(device_data.Motor(index=motor_idx, enable=brake_state))
            motor_idx += 1

        response = self.__device_stub.SetBrakes(device_data.MotorList(
            motors=list(motor_list)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetGripperControl(self,command,gripper_type,pvt_data):
        """
        brake_state_list -> bool[6]
        """
        response = self.__device_stub.SetGripperCommand(device_data.GripperCommand(gripper_command = command, gripper_type = gripper_type, gripper_pvt_data =pvt_data))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)                                         
    @Common.Utils.exception_handler
    def set_endtool_led_dim(self, led_dim):
        """
        Set endtool Rx data
        """
        return self.__device_stub.SetEndLedDim(device_data.EndLedDim(led_dim=led_dim))



    @Common.Utils.exception_handler
    def SetServoAll(self, enable=True):
        """
        enable -> bool
        """
        response = self.__device_stub.SetServoAll(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetServo(self, index, enable=True):
        """
        index -> int
        enable -> bool
        """
        response = self.__device_stub.SetServo(device_data.Servo(index=index, enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDI(self, di_signal_list: list):
        response = self.__device_stub.SetDI(device_data.DigitalList(
            signals=di_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDO(self, do_signal_list: list):
        response = self.__device_stub.SetDO(device_data.DigitalList(
            signals=do_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndDI(self, end_di_signal_list: list):
        response = self.__device_stub.SetEndDI(device_data.EndtoolSignalList(
            signals=end_di_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndDO(self, end_do_signal_list: list):
        self._debug('SetEndDO: ' + str(end_do_signal_list))
        response = self.__device_stub.SetEndDO(device_data.EndtoolSignalList(
            signals=end_do_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetAI(self, ai_signal_list: list):
        response = self.__device_stub.SetAI(device_data.AnalogList(
            signals=ai_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetAO(self, ao_signal_list: list):
        response = self.__device_stub.SetAO(device_data.AnalogList(
            signals=ao_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndAI(self, end_ai_signal_list: list):
        response = self.__device_stub.SetEndAI(device_data.AnalogList(
            signals=end_ai_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndAO(self, end_ao_signal_list: list):
        response = self.__device_stub.SetEndAO(device_data.AnalogList(
            signals=end_ao_signal_list,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def SetEnd485Comm(self, txWord1, txWord2):
        response = self.__device_stub.SetEnd485Comm(device_data.Endtool485CommTxList(
            TxWord1=txWord1,
            TxWord2=txWord2,
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndRS485Rx(self, word1: int, word2: int):
        response = self.__device_stub.SetEndRS485Rx(common_data.EndtoolRS485Rx(
            word1=word1, word2=word2
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDI(self) -> list:
        response = self.__device_stub.GetDI(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetGripperData(self) -> list:
        response = self.__device_stub.GetGripperData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDO(self) -> list:
        response = self.__device_stub.GetDO(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetEndDI(self) -> list:
        response = self.__device_stub.GetEndDI(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetEndDO(self) -> list:
        response = self.__device_stub.GetEndDO(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetAI(self) -> list:
        response = self.__device_stub.GetAI(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetAO(self) -> list:
        response = self.__device_stub.GetAO(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetEndAI(self) -> list:
        response = self.__device_stub.GetEndAI(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetEndAO(self) -> list:
        response = self.__device_stub.GetEndAO(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['signals']

    @Common.Utils.exception_handler
    def GetEndRS485Rx(self) -> dict:
        response = self.__device_stub.GetEndRS485Rx(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetEndRS485Tx(self) -> dict:
        response = self.__device_stub.GetEndRS485Tx(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetEL5001(self):
        response = self.__device_stub.GetEL5001(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetEL5101(self):
        response = self.__device_stub.GetEL5101(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetBrakeControlStyle(self):
        response = self.__device_stub.GetBrakeControlStyle(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetDeviceInfo(self):
        """
        Device Info:
            num_joints   -> uint32
            robot_serial   -> string
            io_board_fw_ver  -> string
            core_board_fw_vers  -> string[6]
            endtool_board_fw_ver  -> string
            endtool_port_type  -> EndToolPortType
            response  -> {code: int64, msg: string}
        """
        response = self.__device_stub.GetDeviceInfo(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetFTSensorData(self):
        response = self.__device_stub.GetFTSensorData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetConveyor(self):
        response = self.__device_stub.GetConveyor(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorName(self, name: str):
        response = self.__device_stub.SetConveyorName(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorByName(self, name: str):
        response = self.__device_stub.SetConveyorByName(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorEncoder(self, encoder_type, channel1: int, channel2: int, sample_num: int,
                           mm_per_tick: float, vel_const_mmps: float, reversed: bool):
        response = self.__device_stub.SetConveyorEncoder(
            device_data.Encoder(type=encoder_type,
                                channel1=channel1, channel2=channel2, sample_num=sample_num,
                                mm_per_tick=mm_per_tick, vel_const_mmps=vel_const_mmps,
                                reversed=reversed)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorTrigger(self, trigger_type, channel: int, detect_rise: bool):
        response = self.__device_stub.SetConveyorTrigger(
            device_data.Trigger(type=trigger_type, channel=channel, detect_rise=detect_rise)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorOffset(self, offset_mm):
        response = self.__device_stub.SetConveyorOffset(common_data.Float(value=offset_mm))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorLockedJoint(self, locked_joint: int):
        response = self.__device_stub.SetConveyorLockedJoint(
            common_data.Int(value=int(locked_joint))
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorToolLink(self, tool_link: int):
        response = self.__device_stub.SetConveyorToolLink(
            common_data.Int(value=int(tool_link))
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorStartingPose(self, jpos, tpos):
        response = self.__device_stub.SetConveyorStartingPose(
            common_data.PosePair(q=jpos, p=tpos)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetConveyorTerminalPose(self, jpos, tpos):
        response = self.__device_stub.SetConveyorTerminalPose(
            common_data.PosePair(q=jpos, p=tpos)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetConveyorState(self):
        response = self.__device_stub.GetConveyorState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetConveyorObjectDistances(self):
        response = self.__device_stub.GetConveyorObjectDistances(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSanderCommand(self, sander_type, ip, speed, state):
        response = self.__device_stub.SetSanderCommand(
            device_data.SanderCommand(type=sander_type, ip=ip, speed=speed, state=state))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSanderCommand(self):
        response = self.__device_stub.GetSanderCommand(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def AddPhotoneoCalibPoint(self, vision_name, px, py, pz):
        response = self.__device_stub.AddPhotoneoCalibPoint(
            device_data.AddPhotoneoCalibPointReq(vision_name=vision_name, px=px, py=py, pz=pz))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetPhotoneoDetection(self, vision_server, object, frame_type, solution_id, vision_id):
        response = self.__device_stub.GetPhotoneoDetection(
            device_data.VisionRequest(vision_server=vision_server, object=object, frame_type=frame_type, solution_id=solution_id, vision_id=vision_id))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetPhotoneoRetrieval(self, vision_server, object, frame_type, solution_id, vision_id):
        response = self.__device_stub.GetPhotoneoRetrieval(
            device_data.VisionRequest(vision_server=vision_server, object=object, frame_type=frame_type, solution_id=solution_id, vision_id=vision_id))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetLoadFactors(self):
        """
        Device Info:
            num_joints   -> uint32
            robot_serial   -> string
            io_board_fw_ver  -> string
            core_board_fw_vers  -> string[6]
            endtool_board_fw_ver  -> string
            endtool_port_type  -> EndToolPortType
            response  -> {code: int64, msg: string}
        """
        response = self.__device_stub.GetLoadFactors(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ExecuteTool(self, name: str):
        response = self.__device_stub.ExecuteTool(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetAutoMode(self, on: bool):
        response = self.__device_stub.SetAutoMode(device_data.SetAutoModeReq(on=on))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CheckAutoMode(self):
        response = self.__device_stub.CheckAutoMode(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CheckReducedMode(self):
        response = self.__device_stub.CheckReducedMode(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSafetyFunctionState(self):
        response = self.__device_stub.GetSafetyFunctionState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def RequestSafetyFunction(self, id, state):
        response = self.__device_stub.RequestSafetyFunction(
            device_data.SafetyFunctionState(id = id, state = state))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetSafetyControlData(self):
        response = self.__device_stub.GetSafetyControlData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetRTTaskTimes(self):
        response = self.__device_stub.GetRTTaskTimes(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CommitViolation(self,
                        violation_type: int,
                        stop_category: int,
                        source: int,
                        axis_idx: int,
                        misc_fvalue: float,
                        misc_ivalue: int,
                        misc_min: float,
                        misc_max: float,
                        misc_text: str):
        response = self.__device_stub.CommitViolation(
            device_data.ViolationRequest(violation_type=violation_type,
                                         stop_category=stop_category,
                                         source=source,
                                         axis_idx=axis_idx,
                                         misc_fvalue=misc_fvalue,
                                         misc_ivalue=misc_ivalue,
                                         misc_min=misc_min,
                                         misc_max=misc_max,
                                         misc_text=misc_text))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Console Logging
    ############################
    def _info(self, content=''):
        self._logger.info(content=content, source='DeviceClient')

    def _debug(self, content='', source=''):
        self._logger.debug(content=content, source='DeviceClient')

    def _warn(self, content='', source=''):
        self._logger.warn(content=content, source='DeviceClient')

    def _error(self, content='', source=''):
        self._logger.error(content=content, source='DeviceClient')

