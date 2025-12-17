import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'impl'))

import grpc
from concurrent import futures
from rtde_socket_client import RTDESocketClient
from control_socket_client import ControlSocketClient
import teleop_dev_pb2 as teleop_data
import teleop_dev_pb2_grpc as teleop_grpc

import time
import numpy as np
from scipy.spatial.transform import Rotation
from threading import Thread

DEVICE_NAME = "controller_1"
CONTROL_PERIOD = 0.01
VEL_SCALE = 0.8
ACC_SCALE = 7.0
DEVICE_PORT = 20500

class TeleOpDeviceServicer(teleop_grpc.TeleOpDeviceServicer):
    ip_indy: str
    port_indy: str
    rtde: RTDESocketClient
    control: ControlSocketClient
    _thread: Thread
    _stop_stream: bool

    def __init__(self):
        self.ip_indy = None
        self.port_indy = None
        self.rtde = None
        self.control = None
        self._thread = None
        self._stop_stream = False
        self._stream_running = False
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
        self.rtde = RTDESocketClient(self.ip_indy)
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
        while not self._stop_stream:
            try:
                step_time = time.time() - time_last
                if step_time > CONTROL_PERIOD:
                    value = self.rtde.GetControlData()['p']
                    self.control.MoveTeleLRec(value, VEL_SCALE, ACC_SCALE)
                else:
                    time.sleep(CONTROL_PERIOD - step_time)
                self._error_lasttime = False
            except Exception as e:
                if not self._error_lasttime:
                    self._error_lasttime = True
                    print(f'Error in stream {e}')

        self._stream_running = False

    
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
