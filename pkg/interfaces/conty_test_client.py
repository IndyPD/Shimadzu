import time
import grpc
from google.protobuf import json_format

from interfaces.impl import common_msgs_pb2 as common_data
from interfaces.impl import hri_msgs_pb2 as conty_data
from interfaces.impl import hri_pb2_grpc as conty_grpc
import common as Common


class ContySocketClient(metaclass=Common.SingletonMeta):
    def __init__(self, conty_stub: conty_grpc.HRIStub):
        self.__conty_stub = conty_stub

    @Common.Utils.exception_handler
    def ContyInit(self):
        response = self.__conty_stub.ContyInit(conty_data.ContyInitReq())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def RobotUpdate(self):
        response = self.__conty_stub.RobotUpdate(conty_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSpeedRatio(self, ratio: int):
        response = self.__conty_stub.SetSpeedRatio(conty_data.SetSpeedRatioReq(ratio=ratio))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetRefFramePlanar(self, planar_frame: dict):
        request = conty_data.SetRefFramePlanarReq()
        json_format.ParseDict(planar_frame, request)
        response = self.__conty_stub.SetRefFramePlanar(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetRefFrameList(self):
        request = conty_data.GetRefFrameListReq()
        response = self.__conty_stub.GetRefFrameList(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetRefFrameList(self, refframe_list: list, default_name: str):
        request = conty_data.SetRefFrameListReq(
            ref_frames=refframe_list, default_name=default_name
        )
        response = self.__conty_stub.SetRefFrameList(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDO(self, do_list: dict):
        request = conty_data.DOSignals()
        json_format.ParseDict(do_list, request)
        response = self.__conty_stub.SetDO(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndDO(self, enddo_list: dict):
        request = conty_data.EndtoolSignalList()
        json_format.ParseDict(enddo_list, request)
        response = self.__conty_stub.SetEndDO(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetEndAO(self, ao_list: dict):
        request = conty_data.AOSignals()
        json_format.ParseDict(ao_list, request)
        response = self.__conty_stub.SetEndAO(request)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def PlayTuningProgram(self, prog_name: str = '',
                          tuning_space=common_data.TUNE_ALL, precision=common_data.HIGH_PRECISION,
                          vel_level_max=9):
        tuning_prog_dict = dict(
            file_dir=prog_name,
            tuning_space=tuning_space,
            precision=precision,
            vel_level_max=vel_level_max
        )
        tuning_req = conty_data.TuningProgram()

        json_format.ParseDict(tuning_prog_dict, tuning_req)
        response = self.__conty_stub.PlayTuningProgram(tuning_req)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def UpdateIndySW(self, file_bytes: bytes):
        def make_bytes(byte_list):
            chunk_size = 500000
            for i in range(0, len(file_bytes), chunk_size):
                yield conty_data.UpdateIndySWReq(file_buffer=file_bytes[i:i + chunk_size])

        response = self.__conty_stub.UpdateIndySW(make_bytes(file_bytes))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


############################
# Main
############################
if __name__ == '__main__':
    # conty_channel = grpc.insecure_channel("{}:{}".format(Common.Config.CONTROLLER_IP_ADDRESS, 20131))
    conty_channel = grpc.insecure_channel("{}:{}".format('192.168.1.6', 20131))
    conty_stub = conty_grpc.HRIStub(conty_channel)
    conty_client = ContySocketClient(conty_stub)

    conty_init = conty_client.ContyInit()
    print(conty_init)

    # Opening the binary file in binary mode as rb(read binary)
    f = open(Common.Config.SW_UPDATE_FILE_NAME, mode="rb")

    # Reading file data with read() method
    data = f.read()

    # Knowing the Type of our data
    print(type(data))

    # Printing our byte sequenced data
    print(data)

    # Closing the opened file
    f.close()

    update_res = conty_client.UpdateIndySW(data)
    print(update_res)

    # thresholds = conty_client.PlayTuningProgram(
    #     prog_name='test_tuning2.indy7.json',
    #     tuning_space=common_data.TUNE_ALL,
    #     precision=common_data.HIGH_PRECISION,
    #     vel_level_max=3
    # )
    # print(thresholds)

    # do_signal_test = [dict(address=16, state=1)]
    #
    # do_signals = dict(signals=do_signal_test)
    # # print(do_signal_test)
    #
    # do_res = conty_client.SetDO(do_signals)
    # print(do_res)
    # time.sleep(3)

    # enddo_signals = {'signals': [{'port': 'B', 'states': [-2, 1]}]}
    # enddo_res = conty_client.SetEndDO(enddo_signals)
    # print(enddo_res)
    # time.sleep(0.1)

    # endao_signals = {'signals': [{'voltage': 555, 'address': 1}]}
    # ao_data = conty_client.SetEndAO(endao_signals)
    # print(ao_data)
    # time.sleep(0.1)

    # robot_data = conty_client.RobotUpdate()
    # print(robot_data)

    # refframe_data = conty_client.GetRefFrameList()
    # print(refframe_data)
    # time.sleep(1.0)
    #
    # res = conty_client.SetRefFrameList(
    #     refframe_list=refframe_data['ref_frames'], default_name=refframe_data['default_name']
    # )
    # print(res)

    # planar_frame = dict(tpos0=[381.97437, -34.817627, 328.87488, -0.00999296, -179.89131, 0.14893097],
    #                     tpos1=[440.42404, -34.829037, 328.83093, -0.012917242, -179.89182, 0.12506503],
    #                     tpos2=[381.95776, 39.250782, 328.90118, -0.010483602, -179.89415, 0.22381273])
    # refframe_res = conty_client.SetRefFramePlanar(planar_frame)
    # print(refframe_res)
