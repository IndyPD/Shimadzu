## Includes: common, interface
## Requirements: numpy scipy netifaces openvr
## Requirements: protobuf==3.19.4 grpcio==1.34.1 grpcio-tools==1.34.1
## Need to remove: condy_servicer.py

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'impl'))

import grpc
from concurrent import futures
from interfaces.control_socket_client import ControlSocketClient
import teleop_dev_pb2 as teleop_data
import teleop_dev_pb2_grpc as teleop_grpc
from interfaces.vive import triad_openvr

import time
import numpy as np
from scipy.spatial.transform import Rotation
from threading import Thread

DEVICE_NAME = "tracker_1"
TRIGGE_NAME = "menu_button"
CONTROL_PERIOD = 0.02
VEL_SCALE = 0.8
ACC_SCALE = 7.0
DEVICE_PORT = 20500
ERROR_TIME = 5.0

class TeleOpDeviceServicer(teleop_grpc.TeleOpDeviceServicer):
    ip_indy: str
    port_indy: str
    control: ControlSocketClient
    _thread: Thread
    _stop_stream: bool

    def __init__(self):
        self.ip_indy = None
        self.port_indy = None
        self.control = None
        self._stop_stream = False
        self._stream_running = False
        self.init_vive()
        self._error_lasttime = False

    def StartTeleOpStream(self, request: teleop_data.TeleOpStreamReq, context) -> teleop_data.Response:
        if self._stream_running and self._thread is not None:
            if self.ip_indy == request.ip_indy:
                print(f"StartTeleOpStream re-requested from {request.ip_indy}:{request.port}")
                return teleop_data.Response()
            self._stop_stream = True
            self._thread.join()
        print(f"StartTeleOpStream to {request.ip_indy}:{request.port}")
        self.ip_indy = request.ip_indy
        self.port_indy = request.port
        self.control = ControlSocketClient(self.ip_indy, port=self.port_indy)
        self._stop_stream = False
        self._thread = Thread(target=self._stream_fun, daemon=True)
        self._thread.start()
        return teleop_data.Response()

    def StopTeleOpStream(self, request: teleop_data.Empty, context) -> teleop_data.Response:
        print(f"StopTeleOpStream to {self.ip_indy}")
        self._stop_stream = True
        return teleop_data.Response()

    def _stream_fun(self):
        self._stream_running = True
        time_last = time.time()
        self._error_count = 0
        while not self._stop_stream:
            try:
                step_time = time.time() - time_last
                if step_time > CONTROL_PERIOD:
                    enable = self.get_vive_input()
                    value = self.get_vive_pose()
                    res = self.control.EnableTeleKey(enable)
                    if res is not None:
                        res = self.control.MoveTeleLRec(value, VEL_SCALE, ACC_SCALE)
                    if res is None:
                        raise(RuntimeError("Communication Failure"))
                else:
                    time.sleep(CONTROL_PERIOD - step_time)
                self._error_lasttime = False
                self._error_count = 0
            except Exception as e:
                if not self._error_lasttime:
                    self._error_lasttime = True
                    print(f'Error in stream {e}')
                self._error_count += 1
                if self._error_count > 10:
                    print(f'Stop Stream By Error')
                    self._stop_stream = True
        self._stream_running = False

    def init_vive(self):
        self.v = triad_openvr.triad_openvr()
        self.v.print_discovered_objects()

        for i in range(200):
            self.v.devices[DEVICE_NAME].trigger_haptic_pulse()
            time.sleep(0.01)
    
    def get_vive_input(self):
        controller_inputs = self.v.devices[DEVICE_NAME].get_controller_inputs()
        return controller_inputs[TRIGGE_NAME]

    def get_vive_pose(self):
        vivePose = self.v.devices[DEVICE_NAME].get_pose_matrix()
        pos = np.multiply(1000, [vivePose.m[0][3], vivePose.m[1][3], vivePose.m[2][3]]).tolist()
        rotMat = np.array([[vivePose.m[0][0], vivePose.m[0][1], vivePose.m[0][2]],
                           [vivePose.m[1][0], vivePose.m[1][1], vivePose.m[1][2]],
                           [vivePose.m[2][0], vivePose.m[2][1], vivePose.m[2][2]]])
        rot = np.rad2deg(Rotation.from_matrix(rotMat).as_euler("xyz")).tolist()

        return pos + rot


if __name__ == "__main__":
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10),
                         options=
                         [('grpc.max_send_message_length', 10 * 1024 * 1024),
                          ('grpc.max_receive_message_length', 10 * 1024 * 1024)]
                         )
    servicer = TeleOpDeviceServicer()
    teleop_grpc.add_TeleOpDeviceServicer_to_server(servicer=servicer, server=server)

    server.add_insecure_port('[::]:{}'.format(DEVICE_PORT))
    server.start()
