## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

import eyetask_pb2 as EyeTask_pb2
import eyetask_pb2_grpc as EyeTask_pb2_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

import random
import grpc
import time

from google.protobuf import json_format

import numpy as np
from typing import Sequence, Tuple

import common as Common
import managers as Managers


# Connect IndyEYE GRPC Server
class IndyEyeSocketClient:
    # Run deep learning algorithm / image processing algorithm
    CMD_TASK_DETECT = 0
    # Pose refinement and post processing
    CMD_TASK_RETRIEVE = 1
    # Reset detection algorithm
    CMD_TASK_RESET = 2
    # Request list of detectable object names
    CMD_TASK_GET_LIST = 3
    # 6D task position to pick object.
    TBE_TASK_POSE_BASE = 'Tbe'
    # 6D Tool Center Position to pick object.
    TBT_GRIP_POSE_BASE = 'Tbt'
    # 6D Position of detected object.
    TBO_OBJECT_POSE_BASE = 'Tbo'
    # Request type
    COLOR_AND_DEPTH = 0
    COLOR_ONLY = 1
    DEPTH_ONLY = 2

    def __init__(self, ip=None, port=None):
        self._logger = Managers.LogManager()
        try:
            if ip is not None and port is not None:
                options = [('grpc.max_receive_message_length', 100 * 1024 * 1024)]
                self._channel = grpc.insecure_channel("{}:{}".format(ip, port), options=options)
                eye_stub = EyeTask_pb2_grpc.EyeTaskStub(self._channel)

                self._stub = Common.Utils.StubWithTimeout(stub=eye_stub, timeout=Common.Limits.GRPCTimeOut)
            else:
                self._log_error('IP Address or Port is not specified')

        except grpc.FutureTimeoutError:
            self._log_error('Make connection failed')

    def __del__(self):
        if hasattr(self, '_channel'):
            try:
                self._channel.close()
            except:
                pass

    # def get_server_info(self):
    #     request_id = random.randint(1, 1000)
    #
    #     resp = self._stub.GetServerInfo(EyeTask_pb2.ServerInfoRequest(id=request_id))
    #
    #     if resp.id != request_id:
    #         msg = "GET IMAGE: NOT MATCH ID"
    #
    #     server_info = json_format.MessageToDict(resp)
    #     print(server_info)

    def get_image(self, request_type=0):
        request_id = random.randint(1, 1000)
        # while not grpc.ChannelConnectivity.READY:
        #     time.sleep(0.2)
        resp = self._stub.GetImage(EyeTask_pb2.ImageRequest(id=request_id, type=request_type))

        if resp.id != request_id:
            msg = "GET IMAGE: NOT MATCH ID"
            return None, None, msg
        elif resp.error_state:
            msg = "GET IMAGE: ERROR STATE"
            return None, None, msg
        # plt.figure(figsize=(15, 5))
        if request_type == 0 and len(resp.color):
            color = np.frombuffer(resp.color, dtype=np.uint8).reshape((resp.height, resp.width, 3))
            return color, None, None
        elif request_type == 1 and len(resp.depth):
            depth = np.frombuffer(resp.depth, dtype=np.uint16).reshape((resp.height, resp.width))
            return None, depth, None
        elif request_type == 2 and len(resp.color) and len(resp.depth):
            color = np.frombuffer(resp.color, dtype=np.uint8).reshape((resp.height, resp.width, 3))
            depth = np.frombuffer(resp.depth, dtype=np.uint16).reshape((resp.height, resp.width))
            return color, depth, None
        else:
            return None, None, None

    def get_object_list(self):
        #     if not self.is_connected():
        #         raise Exception("Vision {} is not connected !".format(self._ip))
        request_id = random.randint(1, 1000)
        # get object list
        detected_objects = []
        resp = self._stub.GetClassList(EyeTask_pb2.Request(id=request_id))
        if resp.id != request_id:
            self._log_error('GET OBJECT LIST: NOT MATCH ID')
            return detected_objects
        elif resp.error_state:
            self._log_error('GET OBJECT LIST: ERROR STATE')
        else:
            detected_objects = list(resp.class_names)
        return detected_objects

    def detect_by_object_name(self, cls=0, vision_frame=0, pose_cmd=None, robot_ip=None):
        # cls | target class index - 0: all, specific: 1~
        # pose_cmd | current end-effector pose: x,y,z,u,v,w, (unit: m, deg)
        # robot_ip | ip of robot from the xavier side, for multi-robot case
        request_id = random.randint(1, 1000)
        try:
            resp = self._stub.Detect(
                EyeTask_pb2.DetectRequest(id=request_id, cls=cls, pose_cmd=pose_cmd, robot_ip=robot_ip))
            if resp.id != request_id:
                msg = "DETECT OBJECT: LIST NOT MATCH ID"
                return None, 0, False, False, msg
            elif resp.error_state:
                msg = "DETECT OBJECT: ERROR STATE"
                return None, 0, False, False, msg
            elif not resp.detected:
                msg = "DETECT OBJECT: not detected"
                return None, 0, resp.detected, resp.passed, msg
            if vision_frame == 0:
                return resp.tar_obj_pose, resp.cls, resp.detected, resp.passed, None
            elif vision_frame == 1:
                return resp.tar_ee_pose, resp.cls, resp.detected, resp.passed, None
            # elif vision_frame == 2:
            #     return resp.tar_tool_pose, None
        except Exception as e:
            msg = "DETECT OBJECT: ERROR STATE"
            return None, 0, False, False, msg

    def retrieve_by_object_name(self, cls=0, vision_frame=0):
        request_id = random.randint(1, 1000)
        # request_id = self.request_id
        try:
            resp = self._stub.Retrieve(EyeTask_pb2.RetrieveRequest(id=request_id, cls=cls))
            if resp.id != request_id:
                msg = "DETECT OBJECT: LIST NOT MATCH ID"
                return None, 0, False, False, msg
            elif resp.error_state:
                msg = "DETECT OBJECT: ERROR STATE"
                return None, 0, False, False, msg
            elif not resp.detected:
                msg = "DETECT OBJECT: not detected"
                return None, 0, resp.detected, resp.passed, msg
            if vision_frame == 0:
                return resp.tar_obj_pose, resp.cls, resp.detected, resp.passed, None
            elif vision_frame == 1:
                return resp.tar_ee_pose, resp.cls, resp.detected, resp.passed, None
        except Exception as e:
            msg = "DETECT OBJECT: ERROR STATE"
            return None, 0, False, False, msg

    ############################
    # Console Logging
    ############################
    def _log_info(self, content='', source='IndyEyeClient'):
        self._logger.info(content=content, source=source)

    def _log_debug(self, content='', source=''):
        self._logger.debug(content=content, source=source)

    def _log_warn(self, content='', source=''):
        self._logger.warn(content=content, source=source)

    def _log_error(self, content='', source=''):
        self._logger.error(content=content, source=source)


# wait for response
def wait_for_metadata(response_future, event):
    metadata: Sequence[Tuple[str, str]] = response_future.initial_metadata()
    for key, value in metadata:
        print('Greeter client received initial metadata: key=%s value=%s' %
              (key, value))
    event.set()


# wait for response
def check_status(response_future, wait_success):
    if wait_success:
        print("received initial metadata before time out!")
        for response in response_future:
            message = response.message
            print("Greeter client received: " + message)
    else:
        print("Timed out before receiving any initial metadata!")
        response_future.cancel()


class IndyWeldClient(object):
    def __init__(self, ip=None, port=None):
        try:
            if ip is not None and port is not None:
                options = [('grpc.max_receive_message_length', 100 * 1024 * 1024),
                           ('grpc.keepalive_time_ms', 10000),
                           ('grpc.keepalive_timeout_ms', 10000),
                           ('grpc.keepalive_permit_without_calls', 1),
                           ('grpc.http2.max_pings_without_data', 0),
                           ('grpc.http2.min_recv_ping_interval_without_data_ms', 5000),
                           ('grpc.http2.min_sent_ping_interval_without_data_ms', 10000)]
                self._channel = grpc.insecure_channel("{}:{}".format(ip, port), options=options)
                self._stub = EyeTask_pb2_grpc.EyeTaskStub(self._channel)
            else:
                print("INDYWELD CLIENT: No IP Address Or Port")

        except grpc.FutureTimeoutError:
            print("INDYWELD CLIENT: Init Error")

        self._calibration_id = -1

    def detect_welding_lines(self):
        error_state = False
        request_id = random.randint(1, 1000)
        welding_lines_info = self._stub.GetWeldingLinesInfo(EyeTask_pb2.WeldingLinesInfoRequest(id=request_id))
        print("Welding lines info: ", welding_lines_info)
        if welding_lines_info.id != request_id:
            print("GetWeldingLines: NOT MATCH ID")
            msg = "GetWeldingLines: NOT MATCH ID"
            return msg
        # elif welding_line_list.error_state:
        #     print("GetWeldingLines: ERROR STATE")
        #     msg = "GetWeldingLines: ERROR STATE"
        #     return msg
        else:
            if welding_lines_info.error_state:
                error_state = welding_lines_info.error_state
                print("GetWeldingLines: ERROR STATE {}".format(error_state))
            line_size = len(welding_lines_info.welding)
            print("==============================")
            print("Welding line size: ", line_size)
            line_info = welding_lines_info.welding
            print("Line info: " + str(line_info))
            type_info = welding_lines_info.cell_types
            print("Type info: " + str(type_info))
            print("==============================")
            for i in range(0, line_size):
                print("name: ", line_info[i].name)
                print("start point: {} {} {}".format(line_info[i].start_point.x, line_info[i].start_point.y,
                                                     line_info[i].start_point.z))
                print("end   point: {} {} {}".format(line_info[i].end_point.x, line_info[i].end_point.y,
                                                     line_info[i].end_point.z))
                print("==============================")

            return error_state, line_info, type_info

    def detect_circular_line(self):
        error_state = False
        request_id = random.randint(1, 1000)
        print("Send the msg to vision...")
        circular_line_info = self._stub.GetCircularLineInfo(EyeTask_pb2.CircularLineInfoRequest(id=request_id))
        print("Circular line info: ", circular_line_info)
        if circular_line_info.id != request_id:
            print("GetCircularLineInfo: NOT MATCH ID")
            msg = "GetCircularLineInfo: NOT MATCH ID"
            return msg
        else:
            if circular_line_info.error_state:
                error_state = circular_line_info.error_state
                print("GetCircularLineInfo: ERROR STATE {}".format(error_state))

            print("Check circular line info: ")
            circle = circular_line_info
            print("normal vector       : {} {} {}".format(circle.normal_vector.x, circle.normal_vector.y,
                                                          circle.normal_vector.z))
            print("reference vector    : {} {} {}".format(circle.reference_vector.x, circle.reference_vector.y,
                                                          circle.reference_vector.z))
            print("point method(start): {} {} {}".format(circle.point_method.start_point.x,
                                                         circle.point_method.start_point.y,
                                                         circle.point_method.start_point.z))
            print("point method (via)  : {} {} {}".format(circle.point_method.via_point.x,
                                                          circle.point_method.via_point.y,
                                                          circle.point_method.via_point.z))
            print("point method (end)  : {} {} {}".format(circle.point_method.end_point.x,
                                                          circle.point_method.end_point.y,
                                                          circle.point_method.end_point.z))
            print("vector method (center): {} {} {}".format(circle.vector_method.center_point.x,
                                                            circle.vector_method.center_point.y,
                                                            circle.vector_method.center_point.z))
            print("vector method (radius) : {}".format(circle.vector_method.radius))

            return error_state, circle

    def detect_straight_line(self):
        error_state = False
        request_id = random.randint(1, 1000)
        straight_line_info = self._stub.GetStraightLineInfo(EyeTask_pb2.StraightLineInfoRequest(id=request_id))
        print("Straight line info: ", straight_line_info)
        if straight_line_info.id != request_id:
            print("GetStraightLineInfo: NOT MATCH ID")
            msg = "GetStraightLineInfo: NOT MATCH ID"
            return msg
        else:
            if straight_line_info.error_state:
                error_state = straight_line_info.error_state
                print("GetStraightLineInfo: ERROR STATE {}".format(error_state))

            print("Check circular line info: ")
            line = straight_line_info
            print("normal vector : {} {} {}", line.normal_vector.x, line.normal_vector.y, line.normal_vector.z)
            print("start point   : {} {} {}", line.start_point.x, line.start_point.y, line.start_point.z)
            print("end point     : {} {} {}", line.end_point.x, line.end_point.y, line.end_point.z)

        return error_state, line

    def start_calibration(self):
        request_id = random.randint(1, 1000)
        self._calibration_id = request_id
        print("start calibration!")
        calibration_resp = self._stub.DoCalibration(EyeTask_pb2.CalibrationRequest(id=request_id))

        print("done calibration!")
        print("Calibration succeeded {} {} {}".format(calibration_resp.is_succeeded[0],
                                                      calibration_resp.is_succeeded[1],
                                                      calibration_resp.is_succeeded[2]))
        print("Check rms info {} {} {}".format(calibration_resp.indy_cam_rms[0],
                                               calibration_resp.indy_cam_rms[1],
                                               calibration_resp.indy_cam_rms[2]))

        if calibration_resp.id != request_id:
            msg = "DoCalibration: NOT MATCH ID"
            return msg

        return calibration_resp.is_succeeded[0] and calibration_resp.is_succeeded[1]

    def check_calibration(self):
        calibration_resp = self._stub.IsCalibrationDone(EyeTask_pb2.CalibrationDoneRequest(id=self._calibration_id))

        while not calibration_resp.is_calibrated:
            calibration_resp = self._stub.IsCalibrationDone(EyeTask_pb2.CalibrationDoneRequest(id=self._calibration_id))
            time.sleep(1)  # 1s wait

        self._calibration_id = -1

        # check only Indy~Cam1, Indy~Cam2
        return calibration_resp.is_succeeded[0] and calibration_resp.is_succeeded[1]


############################
# Main
############################
if __name__ == "__main__":
    eye_client = IndyEyeSocketClient('192.168.1.14', 10511)
    # eye_client.get_server_info()
    obj_list = eye_client.get_object_list()
    print(obj_list)

    image = eye_client.get_image()
    print(image)
