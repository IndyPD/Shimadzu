## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

import common_msgs_pb2 as common_data
import linear_pb2 as linear_data
import linear_pb2_grpc as linear_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import time
import grpc
from google.protobuf import json_format
import threading
import common as Common


class LinearControlClient:
    def __init__(self, ip_addr, port=Common.Config().LINEAR_SOCKET_PORT):
        linear_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        linear_stub = linear_grpc.LinearControlStub(linear_channel)
        self.__linear_stub = Common.Utils.StubWithTimeout(stub=linear_stub, timeout=Common.Limits.GRPCTimeOut)
        #
        self.__axis_timer = AxisTimer(linear_client=self, interval=0.15)
        self.lock = threading.Lock()

    @Common.Utils.exception_handler
    def get_axis_data(self) -> dict:
        """
        Axis Data:
          repeated bool active = 1;
          repeated float pos_mm = 2;
          repeated float vel_mm = 3;

          repeated float despos_mm = 4;
          repeated float desvel_mm = 5;
          repeated float desacc_mm = 6;

          uint32 num_axes = 10;
          OpState op_state = 11;
          TrajState traj_state = 12;
          AxisType axis_type = 16;
          bool is_target_reached = 20;
        """
        # print("Get Linear Axis data is called here for Linear Update in Conty servicer")
        response = self.__linear_stub.GetAxesInfo(common_data.Empty())
        # print("After GetAxesInfo is called **********************")
        # print(response)
        return json_format.MessageToDict(response,
                                                   including_default_value_fields=True,
                                                   preserving_proto_field_name=True,
                                                   use_integers_for_enums=True)
        # print('Linear Axis Data: ' + str(axis_data_dict))
        # return axis_data_dict

    @Common.Utils.exception_handler
    def set_servo(self, enable=True):
        """
        enable -> bool
        """
        response = self.__linear_stub.SetServoAll(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def set_target_torque(self, torque):
        response = self.__linear_stub.SetTargetTorque(linear_data.TargetTorque(target_nm=torque))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def set_control_gain(self, index, kp, kv, ki):
        """
        enable -> bool
        """
        response = self.__linear_stub.SetControlGains(linear_data.ControlGains(index=index, kp=kp, kv=kv, ki=ki))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def get_control_gain(self, index: int) -> dict:
        """
        ControlGains:
            uint32 index = 1;
            float kp = 2;
            float kv = 3;
            float ki = 4;
        """
        response = self.__linear_stub.GetControlGains(linear_data.Index(index=index))
        axis_data_dict = json_format.MessageToDict(response,
                                                   including_default_value_fields=True,
                                                   preserving_proto_field_name=True,
                                                   use_integers_for_enums=True)
        return axis_data_dict

    # @Common.Utils.exception_handler
    # def set_zero_pose(self, index, zero_pose):
    #     """
    #     enable -> bool
    #     """
    #     response = self.__linear_stub.SetZeroPosition(linear_data.LinearAxisServoData(index=index, zero_pos=zero_pose))
    #     return json_format.MessageToDict(response,
    #                                      including_default_value_fields=True,
    #                                      preserving_proto_field_name=True,
    #                                      use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def get_zero_pose(self) -> dict:
        """
        ControlGains:
            uint32 index = 1;
            float kp = 2;
            float kv = 3;
            float ki = 4;
        """
        response = self.__linear_stub.GetZeroPosition(common_data.Empty())
        axis_data_dict = json_format.MessageToDict(response,
                                                   including_default_value_fields=True,
                                                   preserving_proto_field_name=True,
                                                   use_integers_for_enums=True)
        return axis_data_dict

    @Common.Utils.exception_handler
    def move_axis_level(self, target_mm,
                        is_absolute=True,
                        vel_level=Common.Limits.JogVelLevelDefault,
                        acc_level=Common.Limits.JogAccLevelDefault,
                        teaching_mode=False):
        """
        target_mm = [mm, mm, mm] -> pos
        vel_level : int -> vel_level
        acc_level : int -> acc_level
        is_absolute : True if target is absolute -> base_type
        """
        # print("Linear Control ====================")
        # print("target_mm ", target_mm)
        # print("is_absolute ", is_absolute)
        # print("vel_level ", vel_level)
        # print("acc_level ", acc_level)
        # print("teaching_mode ", teaching_mode)

        if vel_level < Common.Limits.LevelMin:
            vel_level = Common.Limits.LevelMin
        if vel_level > Common.Limits.LevelMax:
            vel_level = Common.Limits.LevelMax

        if vel_level > 3:
            vel_ratio = 3

        vel_ratio = vel_level * 25  # %

        if acc_level < Common.Limits.LevelMin:
            acc_level = Common.Limits.LevelMin
        if acc_level > Common.Limits.LevelMax:
            acc_level = Common.Limits.LevelMax

        acc_ratio = Common.Limits.JogAccRatioDefault * acc_level

        return self.move_axis(target_mm=target_mm,
                              is_absolute=is_absolute,
                              vel_ratio=vel_ratio,
                              acc_ratio=acc_ratio,
                              teaching_mode=teaching_mode)

    @Common.Utils.exception_forwarder
    def move_axis(self, start_mm, target_mm,
                  is_absolute=True,
                  vel_ratio=Common.Limits.JogVelRatioDefault,
                  acc_ratio=Common.Limits.JogAccRatioDefault,
                  teaching_mode=False):
        """
        start_mm = [mm, mm, mm] -> pos
        target_mm = [mm, mm, mm] -> pos
        vel_mm : int -> vel_ratio
        acc_mm : int -> acc_ratio
        is_absolute : True if target is absolute -> base_type
        """
        # print("Linear Control ====================")
        # print("target_mm ", target_mm)
        # print("is_absolute ", is_absolute)
        # print("vel_ratio ", vel_ratio)
        # print("acc_ratio ", acc_ratio)
        # print("teaching_mode ", teaching_mode)

        axisInfo = self.get_axis_data()
        if (axisInfo['axis_type'] == 1): # Prismatic
            vel = Common.Limits.TaskDispVelValueDefault * vel_ratio / 100;
        else: # Revolute
            vel = Common.Limits.TaskRotVelValueMax * vel_ratio / 100;

        # vel = 250 * vel_ratio / 100 # 250 mm/s
        acc = vel * acc_ratio / 100

        response = self.__linear_stub.MoveLinear(linear_data.LinearTarget(
            start_mm=start_mm,
            target_mm=target_mm,
            vel_mm=vel,
            acc_mm=acc,
            is_absolute=is_absolute,
            teaching_mode=teaching_mode
        ))
        # print("DEBUG move_axis HoldToAxisJ function")
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def move_linear(self, target_mm, vel_mm, acc_mm, absolute):
        """
        enable -> bool
        """
        response = self.__linear_stub.MoveLinear(linear_data.LinearTarget(target_mm=target_mm, vel_mm=vel_mm, acc_mm=acc_mm, is_absolute=absolute))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def stop_motion(self, stop_category=common_data.SMOOTH_ONLY):
        """
            is_smooth_stop : True if stop mode is smooth
        """
        response = self.__linear_stub.StopMotion(common_data.StopCat(category=stop_category))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def pause_motion(self, pause_category=common_data.SMOOTH_PAUSE):
        """
            is_smooth_stop : True if stop mode is smooth
        """
        response = self.__linear_stub.PauseMotion(common_data.PauseCat(category=pause_category))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    def resume_motion(self):
        """
            is_smooth_stop : True if stop mode is smooth
        """
        response = self.__linear_stub.ResumeMotion(common_data.Empty())


class AxisTimer:
    def __init__(self, linear_client: LinearControlClient, interval=0.5) -> None:
        self._axes_client = linear_client
        self._interval = interval
        self._is_running = False
        self._start_time = time.time()

    def start(self):

        if self._is_running:
            self.extend()
            return

        self._start_time = time.time()
        threading.Thread(target=self._thread_run).start()

    def _thread_run(self):
        self._is_running = True
        while (time.time() - self._start_time) < self._interval and self._is_running:
            time.sleep(self._interval)

        # print('motion stop')
        self._axes_client.stop_motion(is_smooth_stop=True)
        self._is_running = False

    def extend(self):
        self._start_time = time.time()

    def isRunning(self):
        return self._is_running

    def stopRunning(self):
        self._is_running = False


############################
# Main
############################
if __name__ == "__main__":
    linear_client = LinearControlClient('192.168.4.104', 20300)

    linear_client.set_servo(enable=True)
    time.sleep(2.0)

    # linear_client.move_axis(
    #     pos=[20.0, 0.0, 0.0],
    #     vel_ratio=10.0,
    #     acc_ratio=100.0,
    #     is_absolute=True
    # )
    # time.sleep(1.0)
    axis_data = linear_client.get_axis_data()
    print(axis_data)
