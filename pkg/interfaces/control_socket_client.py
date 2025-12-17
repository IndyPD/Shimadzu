## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from google.protobuf import json_format

import common_msgs_pb2 as common_data
import device_msgs_pb2 as device_data
import control_msgs_pb2 as control_data
import control_pb2_grpc as control_grpc

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect


from typing import List
import time
import grpc
import common as Common
import managers as Managers


class ControlSocketClient:
    """
    gRPC client to Control Server in C++ IndyFramework v3.0
    """
    ABSOLUTE_JOINT = control_data.ABSOLUTE_JOINT
    RELATIVE_JOINT = control_data.RELATIVE_JOINT
    ABSOLUTE_TASK = control_data.ABSOLUTE_TASK
    RELATIVE_TASK = control_data.RELATIVE_TASK
    TCP_TASK = control_data.TCP_TASK
    CIRCLE_POINT_SET = control_data.POINT_SET
    CIRCLE_CENTER_AXIS = control_data.CENTER_AXIS
    CIRCLE_CONSTANT = control_data.CONSTANT
    CIRCLE_RADIAL = control_data.RADIAL
    CIRCLE_SMOOTH = control_data.SMOOTH
    STOP_IMMEDIATE_BRAKE = common_data.IMMEDIATE_BRAKE
    STOP_SMOOTH_BRAKE = common_data.SMOOTH_BRAKE
    STOP_SMOOTH_ONLY = common_data.SMOOTH_ONLY
    NO_BLENDING = 0
    OVERRIDE_BLENDING = 1
    DUPLICATE_BLENDING = 2

    def __init__(self, ip_addr, port=Common.Config().CONTROL_SOCKET_PORT):
        control_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        control_stub = control_grpc.ControlStub(control_channel)
        self.__control_stub = Common.Utils.StubWithTimeout(stub=control_stub, timeout=Common.Limits.GRPCTimeOut)
        self._logger = Managers.LogManager()

    @Common.Utils.exception_handler
    def GetControlInfo(self):
        """
        Device Info:
            control_version -> string
            robot_model -> string
            response -> {code: int64, msg: string}
        """
        response = self.__control_stub.GetControlInfo(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def PingFromConty(self):
        response = self.__control_stub.PingFromConty(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Motion
    ############################
    @Common.Utils.exception_forwarder
    def MoveJ(self, jstart, jtarget,
              blending_type=NO_BLENDING,
              base_type=ABSOLUTE_JOINT,
              blending_radius=0.0,
              vel_ratio=Common.Limits.JogVelRatioDefault,
              acc_ratio=Common.Limits.JogAccRatioDefault,
              post_condition=Common.Property.PostCondition(),
              teaching_mode=False) -> dict:
        jtarget = control_data.TargetJ(j_start=list(jstart), j_target=list(jtarget), base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveJ(control_data.MoveJReq(
            target=jtarget,
            blending=blending,
            vel_ratio=vel_ratio, acc_ratio=acc_ratio,
            post_condition=post_cond,
            teaching_mode=teaching_mode
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveJT(self, jstart, jtarget,
               blending_type=NO_BLENDING,
               base_type=ABSOLUTE_JOINT,
               blending_radius=0.0,
               move_time=2.0,
               post_condition=Common.Property.PostCondition()) -> dict:
        """
        jpos = [deg, deg, deg, deg, deg, deg]
        move_time = seconds
        """
        jtarget = control_data.TargetJ(j_start=list(jstart), j_target=list(jtarget), base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveJT(control_data.MoveJTReq(
            target=jtarget,
            blending=blending,
            time=move_time,
            post_condition=post_cond
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_forwarder
    def MoveL(self, tstart, ttarget,
              blending_type=NO_BLENDING,
              base_type=ABSOLUTE_TASK,
              blending_radius=0.0,
              vel_ratio=Common.Limits.JogVelRatioDefault,
              acc_ratio=Common.Limits.JogAccRatioDefault,
              post_condition=Common.Property.PostCondition(),
              teaching_mode=False,
              bypass_singular=False
              ) -> dict:
        ptarget = control_data.TargetP(t_start=list(tstart), t_target=list(ttarget), base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveL(control_data.MoveLReq(
            target=ptarget,
            blending=blending,
            vel_ratio=vel_ratio, acc_ratio=acc_ratio,
            post_condition=post_cond,
            teaching_mode=teaching_mode,
            bypass_singular=bypass_singular
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveAxis(self,
                  target_mm,
                  is_absolute=True,
                  vel_ratio=Common.Limits.JogVelRatioDefault,
                  acc_ratio=Common.Limits.JogAccRatioDefault):

        # vel = Common.Limits.ExternalMotorSpeedMaxCnt * vel_ratio / 100
        # acc = vel * acc_ratio / 100

        response = self.__control_stub.MoveLinearAxis(control_data.MoveAxisReq(target_mm=target_mm, vel_percentage=vel_ratio, acc_percentage=acc_ratio, is_absolute=is_absolute))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ForceMode(self, enable, des_force, direction):

        response = self.__control_stub.ForceMode(control_data.ForceModeReq(
            enable=enable,
            des_force=des_force,
            direction=direction
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def MoveLT(self, tstart, ttarget,
               blending_type=NO_BLENDING,
               base_type=ABSOLUTE_TASK,
               blending_radius=0.0,
               move_time=2.0,
               post_condition=Common.Property.PostCondition()) -> dict:
        ptarget = control_data.TargetP(t_start=list(tstart), t_target=list(ttarget), base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveLT(control_data.MoveLTReq(
            target=ptarget,
            blending=blending,
            time=move_time,
            post_condition=post_cond
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveC(self, tstart, tpos0, tpos1,
              blending_type=NO_BLENDING,
              base_type=ABSOLUTE_TASK,
              angle=90.0,
              setting_type=CIRCLE_POINT_SET,
              move_type=control_data.CONSTANT,
              blending_radius=0.0,
              vel_ratio=Common.Limits.JogVelRatioDefault,
              acc_ratio=Common.Limits.JogAccRatioDefault,
              post_condition=Common.Property.PostCondition(),
              teaching_mode=False,
              bypass_singular=False) -> dict:
        ctarget = control_data.TargetC(t_start=list(tstart), t_pos0=list(tpos0), t_pos1=list(tpos1),
                                       base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveC(control_data.MoveCReq(
            target=ctarget,
            blending=blending,
            angle=angle,
            setting_type=setting_type,
            move_type=move_type,
            vel_ratio=vel_ratio, acc_ratio=acc_ratio,
            post_condition=post_cond,
            teaching_mode=teaching_mode,
            bypass_singular=bypass_singular
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveCT(self, tstart, tpos0, tpos1,
               blending_type=NO_BLENDING,
               base_type=ABSOLUTE_TASK,
               angle=90.0,
               setting_type=CIRCLE_POINT_SET,
               move_type=control_data.CONSTANT,
               blending_radius=0.0,
               move_time=2.0,
               post_condition=Common.Property.PostCondition()) -> dict:
        ctarget = control_data.TargetC(t_start=list(tstart), t_pos0=list(tpos0), t_pos1=list(tpos1),
                                       base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveCT(control_data.MoveCTReq(
            target=ctarget,
            blending=blending,
            angle=angle,
            setting_type=setting_type,
            move_type=move_type,
            time=move_time,
            post_condition=post_cond
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Motion
    ############################
    @Common.Utils.exception_forwarder
    def MoveConveyor(self,
                     post_condition=Common.Property.PostCondition(),
                     teaching_mode=False, bypass_singular=False,
                     acc_ratio=Common.Limits.JogAccRatioDefault) -> dict:
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveConveyor(control_data.MoveConveyorReq(
            teaching_mode=teaching_mode,
            bypass_singular=bypass_singular,
            acc_ratio=acc_ratio,
            post_condition=post_cond
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ##
    # @brief move along joint trajectory
    # @remark all arguments are NxD arrays (N: number of points, D: DOF)
    # @param q_list joint values (unit: rads)
    # @param qdot_list joint velocities (unit: rads/s)
    # @param qddot_list joint accelerations (unit: rads/s^2)
    @Common.Utils.exception_handler
    def MoveJointTraj(self, q_list: List[List[float]], qdot_list: List[List[float]], qddot_list: List[List[float]]) -> dict:
        traj_req = control_data.MoveJointTrajReq(q_list=list(map(lambda x: common_data.Vector(values=x), q_list)),
                                                 qdot_list=list(map(lambda x: common_data.Vector(values=x), qdot_list)),
                                                 qddot_list=list(map(lambda x: common_data.Vector(values=x), qddot_list)))
        response = self.__control_stub.MoveJointTraj(traj_req)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ##
    # @brief move along joint trajectory
    # @remark all arguments are Nx6 arrays (N: number of points)
    # @param p_list task positions (xyzuvw), unit: m & rads
    # @param pdot_list task velocities (v, w), unit: m/s & rads/s
    # @param pddot_list task accelerations (v, w), unit: m/s^2 & rads/s^2
    @Common.Utils.exception_handler
    def MoveTaskTraj(self, p_list: List[List[float]], pdot_list: List[List[float]], pddot_list: List[List[float]]) -> dict:
        traj_req = control_data.MoveTaskTrajReq(p_list=list(map(lambda x: common_data.Vector(values=x), p_list)),
                                                pdot_list=list(map(lambda x: common_data.Vector(values=x), pdot_list)),
                                                pddot_list=list(map(lambda x: common_data.Vector(values=x), pddot_list)))
        response = self.__control_stub.MoveTaskTraj(traj_req)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ##
    # @brief move gcode file
    # @param gcode_file file name in IndyDeployment/Gcodes folder
    # @param is_smooth_mode set True to smooth the motion
    # @param smooth_radius smoothing radius, in millimeters
    # @param vel_ratio velocity ratio in percents
    # @param acc_ratio acceleration ratio in percents
    @Common.Utils.exception_handler
    def MoveGcode(self, gcode_file, is_smooth_mode, smooth_radius, vel_ratio=25, acc_ratio=100) -> dict:
        gcode_req = control_data.MoveGcodeReq(gcode_file=gcode_file,
                                              is_smooth_mode=is_smooth_mode,
                                              smooth_radius=smooth_radius,
                                              vel_ratio=vel_ratio,
                                              acc_ratio=acc_ratio)
        response = self.__control_stub.MoveGcode(gcode_req)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def WaitIO(self, di_signal_list, do_signal_list, end_di_signal_list, end_do_signal_list, conjunction=0,
               set_do_signal_list=None, set_end_do_signal_list=None,
               set_ao_signal_list=None, set_end_ao_signal_list=None):

        response = self.__control_stub.WaitIO(control_data.WaitIOReq(
            di_list=self.__to_digital_request_list__(di_signal_list),
            do_list=self.__to_digital_request_list__(do_signal_list),
            end_di_list=self.__to_digital_request_list__(end_di_signal_list),
            end_do_list=self.__to_digital_request_list__(end_do_signal_list),
            conjunction=conjunction
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def WaitTime(self, time: float,
                 set_do_signal_list=None, set_end_do_signal_list=None,
                 set_ao_signal_list=None, set_end_ao_signal_list=None):
        response = self.__control_stub.WaitTime(control_data.WaitTimeReq(
            time=time
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def WaitProgress(self, progress: int,
                     set_do_signal_list=None, set_end_do_signal_list=None,
                     set_ao_signal_list=None, set_end_ao_signal_list=None):
        response = self.__control_stub.WaitProgress(control_data.WaitProgressReq(
            progress=progress
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def WaitTraj(self, traj_condition,
                 set_do_signal_list=None, set_end_do_signal_list=None,
                 set_ao_signal_list=None, set_end_ao_signal_list=None):
        response = self.__control_stub.WaitTraj(control_data.WaitTrajReq(
            traj_condition=traj_condition
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def WaitRadius(self, radius: int,
                   set_do_signal_list=None, set_end_do_signal_list=None,
                   set_ao_signal_list=None, set_end_ao_signal_list=None):
        response = self.__control_stub.WaitRadius(control_data.WaitRadiusReq(
            radius=radius
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    # -------------------------#
    # Violation Recovery
    # -------------------------#
    @Common.Utils.exception_handler
    def Recover(self) -> dict:
        response = self.__control_stub.Recover(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetManualRecovery(self, enable=True) -> dict:
        response = self.__control_stub.SetManualRecovery(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveRecoverJoint(self, jtarget,
                         base_type=ABSOLUTE_JOINT) -> dict:
        response = self.__control_stub.MoveRecoverJoint(
            control_data.TargetJ(j_target=list(jtarget), base_type=base_type)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Command
    ############################
    @Common.Utils.exception_handler
    def StopMotion(self, stop_category=STOP_IMMEDIATE_BRAKE) -> dict:
        response = self.__control_stub.StopMotion(common_data.StopCat(category=stop_category))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetDirectTeaching(self, enable=True) -> dict:
        response = self.__control_stub.SetDirectTeaching(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetComplianceMode(self, enable=True, stiffness=[10]*6) -> dict:
        response = self.__control_stub.SetComplianceMode(control_data.ComplianceMode(enable=enable, stiffness=stiffness))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetComplianceMode(self) -> dict:
        response = self.__control_stub.GetComplianceMode(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetSimulationMode(self, enable=True) -> dict:
        response = self.__control_stub.SetSimulationMode(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ActivateIndySDK(self, license_key, expire_date) -> dict:
        response = self.__control_stub.ActivateIndySDK(
            control_data.SDKLicenseInfo(license_key=license_key, expire_date=expire_date))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetCustomControlMode(self, mode: int) -> dict:
        response = self.__control_stub.SetCustomControlMode(common_data.IntMode(mode=mode))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetCustomControlMode(self) -> dict:
        response = self.__control_stub.GetCustomControlMode(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetFrictionCompensation(self, enable=False) -> dict:
        response = self.__control_stub.SetFrictionCompensation(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetFrictionCompensationState(self) -> dict:
        response = self.__control_stub.GetFrictionCompensationState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)


    ############################
    # Program
    ############################
    @Common.Utils.exception_handler
    def PlayProgram(self, prog_name: str = '', prog_idx: int = -1):
        response = self.__control_stub.PlayProgram(control_data.Program(
            prog_name=prog_name,
            prog_idx=prog_idx
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def PlayProgramLine(self, prog_name: str = '', prog_idx: int = -1):
        response = self.__control_stub.PlayProgramLine(control_data.Program(
            prog_name=prog_name,
            prog_idx=prog_idx
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def PlayTuningProgram(self, prog_name: str = '', prog_idx: int = -1,
                          tuning_space=common_data.TUNE_ALL, precision=common_data.HIGH_PRECISION,
                          vel_level_max=9):

        tuning_prog_dict = dict(
            program=dict(
                prog_name=prog_name,
                prog_idx=prog_idx),
            tuning_space=tuning_space,
            precision=precision,
            vel_level_max=vel_level_max
        )
        tuning_req = control_data.TuningProgram()

        json_format.ParseDict(tuning_prog_dict, tuning_req)
        response = self.__control_stub.PlayTuningProgram(tuning_req, timeout=36000)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def PauseProgram(self):
        response = self.__control_stub.PauseProgram(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ResumeProgram(self):
        response = self.__control_stub.ResumeProgram(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def StopProgram(self):
        response = self.__control_stub.StopProgram(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SendAlarm(self, content):
        response = self.__control_stub.SendAlarm(
            common_data.Message(content=content)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SendAnnotation(self, content):
        response = self.__control_stub.SendAnnotation(
            common_data.Message(content=content)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Custom Variable
    ############################
    @Common.Utils.exception_handler
    def SetModbusVariableNameList(self, modbus_list: list):
        """
        modbus_list:
            [
                {
                'server_name': 'local_server',
                'ip': '127.0.0.1',
                'port': 502,
                'variable_list': [{'name': 'home', 'addr': 1017, 'signal_type': 0}]
                },
            ]
        """
        # print("SetModbusVariableNameList modbus_list: ", modbus_list)
        modbus_variables = []
        for item in modbus_list:
            # print("SetModbusVariableNameList item: ", item)
            var_list = []
            for var in item['variable_list']:
                var_list.append(control_data.ModbusVariable(name=var['name'], addr=var['addr'],
                                                            signal_type=var['signal_type']))
            modbus_variables.append(control_data.ModbusServer(server_name=item['server_name'], ip=item['ip'],
                                                              port=item['port'], variable_list=var_list))

        response = self.__control_stub.SetModbusVariableNameList(
            control_data.ModbusVariableList(modbus_variables=modbus_variables)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    # @Common.Utils.exception_handler
    # def CheckModbusConnection(self, server):
    #     """
    #     {
    #     'server_name': 'local_server',
    #     'ip': '127.0.0.1',
    #     'port': 502,
    #     'variable_list': 0
    #     }
    #     """
    #     response = self.__control_stub.CheckModbusConnection(
    #         control_data.ModbusServer(server_name=server['server_name'], ip=server['ip'],
    #                                   port=server['port'], variable_list=[])
    #     )
    #     return json_format.MessageToDict(response,
    #                                      including_default_value_fields=True,
    #                                      preserving_proto_field_name=True,
    #                                      use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetVariableNameList(self, variables: list):
        """
        Variables:
            [
                {
                    'name' -> string
                    'addr' -> int32
                    'type' -> string
                }
            ]
        """
        variable_list = []
        for var in variables:
            variable_list.append(control_data.Variable(name=var['name'], addr=var['addr'], type=var['type']))

        response = self.__control_stub.SetVariableNameList(
            control_data.AllVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetVariableNameList(self):
        """
        Variables:
            [
                {
                    'name' -> string
                    'addr' -> int32
                    'type' -> string
                    'in_watching' -> bool
                }
            ]
        """
        response = self.__control_stub.GetVariableNameList(common_data.Empty())
        # print("control_socket_client.py GetVariableNameList: ", response)
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetIntVariable(self, int_variables: list):
        """
        Integer Variables:
            [
                addr -> int32
                value -> int64
            ]
        """
        variable_list = []
        for int_var in int_variables:
            variable_list.append(control_data.IntVariable(addr=int_var['addr'], value=int_var['value']))

        response = self.__control_stub.SetIntVariable(
            control_data.IntVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetIntVariable(self):
        """
        Integer Variables:
            [
                addr -> int32
                value -> int32
            ]
        """
        response = self.__control_stub.GetIntVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetModbusVariable(self, modbus_variables: list):
        """
        Modbus Variables:
            [
                name -> string
                addr -> int32
                value -> int32
            ]
        """
        variable_list = []
        for modbus_var in modbus_variables:
            variable_list.append(control_data.ModbusVariable(name=modbus_var['name'], addr=modbus_var['addr'],
                                                             value=modbus_var['value'],
                                                             signal_type=modbus_var['signal_type']))

        response = self.__control_stub.SetModbusVariable(
            control_data.ModbusVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetModbusVariable(self):
        """
        Modbus Variables:
            [
                name -> string
                addr -> int32
                value -> int32
            ]
        """
        response = self.__control_stub.GetModbusVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetBoolVariable(self, bool_variables: list):
        """
        Bool Variables:
            [
                addr -> int32
                value -> bool
            ]
        """
        variable_list = []
        for bool_var in bool_variables:
            variable_list.append(control_data.BoolVariable(addr=bool_var['addr'], value=bool_var['value']))

        response = self.__control_stub.SetBoolVariable(
            control_data.BoolVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetBoolVariable(self):
        """
        Bool Variables:
            [
                addr -> int32
                value -> bool
            ]
        """
        response = self.__control_stub.GetBoolVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetFloatVariable(self, float_variables: list):
        """
        Float Variables:
            [
                addr -> int32
                value -> float
            ]
        """
        variable_list = []
        for float_var in float_variables:
            variable_list.append(control_data.FloatVariable(addr=float_var['addr'], value=float_var['value']))

        response = self.__control_stub.SetFloatVariable(
            control_data.FloatVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetFloatVariable(self):
        """
        Float Variables:
            [
                addr -> int32
                value -> float
            ]
        """
        response = self.__control_stub.GetFloatVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetJPosVariable(self, jpos_variables: list):
        """
        JPos Variables:
            [
                addr -> int32
                jpos -> float[]
            ]
        """
        variable_list = []
        for jpos in jpos_variables:
            variable_list.append(control_data.JPosVariable(addr=jpos['addr'], jpos=jpos['jpos']))

        response = self.__control_stub.SetJPosVariable(
            control_data.JPosVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetJPosVariable(self):
        """
        JPos Variables:
            [
                addr -> int32
                jpos -> float[]
            ]
        """
        response = self.__control_stub.GetJPosVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetTPosVariable(self, tpos_variables: list):
        """
        TPos Variables:
            [
                addr -> int32
                tpos -> float[]
            ]
        """
        variable_list = []
        for tpos in tpos_variables:
            variable_list.append(control_data.TPosVariable(addr=tpos['addr'], tpos=tpos['tpos']))

        response = self.__control_stub.SetTPosVariable(
            control_data.TPosVars(variables=variable_list)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTPosVariable(self):
        """
        TPos Variables:
            [
                addr -> int32
                tpos -> float[]
            ]
        """
        response = self.__control_stub.GetTPosVariable(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)['variables']

    @Common.Utils.exception_handler
    def SetPluginBoolVariable(self, name: str, value: bool):
        """
        NamedBool:
            [
                name -> string
                value -> bool
            ]
        """
        response = self.__control_stub.SetPluginBoolVariable(
            common_data.NamedBool(name=name, value=value)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPluginBoolVariable(self, name: str):
        """
        NamedBool:
            [
                name -> string
                value -> bool
            ]
        """
        response = self.__control_stub.GetPluginBoolVariable(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetPluginIntVariable(self, name: str, value: int):
        """
        NamedInt:
            [
                name -> string
                value -> int
            ]
        """
        response = self.__control_stub.SetPluginIntVariable(
            common_data.NamedInt(name=name, value=value)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPluginIntVariable(self, name: str):
        """
        NamedInt:
            [
                name -> string
                value -> int
            ]
        """
        response = self.__control_stub.GetPluginIntVariable(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetPluginFloatVariable(self, name: str, value: float):
        """
        NamedFloat:
            [
                name -> string
                value -> float
            ]
        """
        response = self.__control_stub.SetPluginFloatVariable(
            common_data.NamedFloat(name=name, value=value)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPluginFloatVariable(self, name: str):
        """
        NamedFloat:
            [
                name -> string
                value -> int
            ]
        """
        response = self.__control_stub.GetPluginFloatVariable(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetPluginJPosVariable(self, name: str, jpos: List[float]):
        """
        NamedJointPosition:
            [
                name -> string
                jpos -> repeated float
            ]
        """
        response = self.__control_stub.SetPluginJPosVariable(
            common_data.NamedJointPosition(name=name, jpos=jpos)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPluginJPosVariable(self, name: str):
        """
        NamedJointPosition:
            [
                name -> string
                jpos -> repeated float
            ]
        """
        response = self.__control_stub.GetPluginJPosVariable(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetPluginTPosVariable(self, name: str, tpos: List[float]):
        """
        NamedJointPosition:
            [
                name -> string
                tpos -> repeated float
            ]
        """
        response = self.__control_stub.SetPluginTPosVariable(
            common_data.NamedTaskPosition(name=name, tpos=tpos)
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPluginTPosVariable(self, name: str):
        """
        NamedTaskPosition:
            [
                name -> string
                tpos -> repeated float
            ]
        """
        response = self.__control_stub.GetPluginTPosVariable(common_data.Name(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def PushBusEvent(self, event_id: int, b_data=[], i_data=[], f_data=[], text_data=""):
        """
        BusEvent:
            uint64 event_id = 1;
            repeated bool b_data = 2;
            repeated int32 i_data = 3;
            repeated float f_data = 4;
            string text_data = 5;
        """
        response = self.__control_stub.PushBusEvent(
            control_data.BusEvent(event_id=event_id,
                                  b_data=b_data,
                                  i_data=i_data,
                                  f_data=f_data,
                                  text_data=text_data))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CatchBusEvent(self, event_id: int, timeout: float):
        """
        event_id: id to catch
        timeout: seconds to wait
        ---
        return:
        BusEvent:
            uint64 event_id = 1;
            repeated bool b_data = 2;
            repeated int32 i_data = 3;
            repeated float f_data = 4;
            string text_data = 5;
        """
        response = self.__control_stub.CatchBusEvent(common_data.CatchBusEventReq(event_id=event_id, timeout=timeout))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTactTime(self):
        """
        TactTime Data:
            [
                type -> string
                tact_time -> float
            ]
        """
        response = self.__control_stub.GetTactTime(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Utility
    ############################
    @Common.Utils.exception_handler
    def Calculate_IK(self, tpos, init_jpos) -> dict:
        """
        :param tpos:
        :param init_jpos:
        :return:
            'jpos': []
        """
        response = self.__control_stub.InverseKinematics(control_data.InverseKinematicsReq(
            tpos=list(tpos),
            init_jpos=list(init_jpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def Calculate_FK(self, jpos) -> dict:
        """
        :param tpos:
        :param init_jpos:
        :return:
            'jpos': []
        """
        response = self.__control_stub.ForwardKinematics(control_data.ForwardKinematicsReq(
            jpos=list(jpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Utility
    ############################
    @Common.Utils.exception_handler
    def Calculate_FK(self, jpos) -> dict:
        """
        :param jpos:
        :return:
            'tpos': []
        """
        response = self.__control_stub.ForwardKinematics(control_data.ForwardKinematicsReq(
            jpos=list(jpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CheckAproachRetractValid(self, tpos, init_jpos, pre_tpos, post_tpos):
        response = self.__control_stub.CheckAproachRetractValid(control_data.CheckAproachRetractValidReq(
            tpos=list(tpos),
            init_jpos=list(init_jpos),
            pre_tpos=list(pre_tpos),
            post_tpos=list(post_tpos)
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPalletPointList(self, tpos, jpos, pre_tpos, post_tpos, pallet_pattern, width, height):
        response = self.__control_stub.GetPalletPointList(control_data.GetPalletPointListReq(
            tpos=list(tpos),
            jpos=list(jpos),
            pre_tpos=list(pre_tpos),
            post_tpos=list(post_tpos),
            pallet_pattern=pallet_pattern,
            width=width,
            height=height
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CalculateRelativePose(self, start_pos, end_pos,
                              base_type=ABSOLUTE_TASK):
        response = self.__control_stub.CalculateRelativePose(control_data.CalculateRelativePoseReq(
            start_pos=list(start_pos),
            end_pos=list(end_pos),
            base_type=base_type
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def CalculateCurrentPoseRel(self, current_pos, relative_pos,
                                base_type=ABSOLUTE_TASK):
        response = self.__control_stub.CalculateCurrentPoseRel(control_data.CalculateCurrentPoseRelReq(
            current_pos=list(current_pos),
            relative_pos=list(relative_pos),
            base_type=base_type
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTeleOpDevice(self):
        response = self.__control_stub.GetTeleOpDevice(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTeleOpState(self):
        response = self.__control_stub.GetTeleOpState(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ConnectTeleOpDevice(self, name: str, type: control_data.TeleOpDevice, ip: str, port: int):
        response = self.__control_stub.ConnectTeleOpDevice(
            control_data.TeleOpDevice(name=name,type=type,ip=ip,port=port
                                      )
        )
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def DisConnectTeleOpDevice(self):
        response = self.__control_stub.DisConnectTeleOpDevice(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def ReadTeleOpInput(self):
        response = self.__control_stub.ReadTeleOpInput(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def StartTeleOp(self, method, mode=control_data.TeleMode.TELE_RAW):
        response = self.__control_stub.StartTeleOp(control_data.TeleOpState(mode=mode,method=method))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def StopTeleOp(self):
        response = self.__control_stub.StopTeleOp(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SetPlayRate(self, rate: float):
        response = self.__control_stub.SetPlayRate(control_data.TelePlayRate(rate=rate))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetPlayRate(self):
        response = self.__control_stub.GetPlayRate(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def EnableTeleKey(self, enable):
        response = self.__control_stub.EnableTeleKey(common_data.State(enable=enable))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveTeleJAbs(self, jpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleJ(
            control_data.MoveTeleJReq(jpos=jpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_JOINT_ABSOLUTE))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveTeleJRel(self, jpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleJ(
            control_data.MoveTeleJReq(jpos=jpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_JOINT_RELATIVE))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveTeleLAbs(self, tpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleL(
            control_data.MoveTeleLReq(tpos=tpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_TASK_ABSOLUTE))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveTeleLRel(self, tpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleL(
            control_data.MoveTeleLReq(tpos=tpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_TASK_RELATIVE))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def MoveTeleLTCP(self, tpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleL(
            control_data.MoveTeleLReq(tpos=tpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_TASK_TCP))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def MoveTeleLRec(self, tpos, vel_ratio=0.8, acc_ratio=7.0):
        response = self.__control_stub.MoveTeleL(
            control_data.MoveTeleLReq(tpos=tpos, vel_ratio=vel_ratio, acc_ratio=acc_ratio,
                                      method=control_data.TELE_RECORD_ABSOLUTE))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def GetTeleFileList(self):
        response = self.__control_stub.GetTeleFileList(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def SaveTeleMotion(self, name: str):
        response = self.__control_stub.SaveTeleMotion(control_data.TeleFileReq(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def LoadTeleMotion(self, name: str):
        response = self.__control_stub.LoadTeleMotion(control_data.TeleFileReq(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def DeleteTeleMotion(self, name: str):
        response = self.__control_stub.DeleteTeleMotion(control_data.TeleFileReq(name=name))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def MoveFL(self, tpos,
               blending_type=NO_BLENDING,
               base_type=ABSOLUTE_TASK,
               blending_radius=0.0,
               vel_ratio=Common.Limits.JogVelRatioDefault,
               acc_ratio=Common.Limits.JogAccRatioDefault,
               des_force=0.0,
               enable_force_control=False,
               post_condition=Common.Property.PostCondition(),
               teaching_mode=False) -> dict:
        ptarget = control_data.TargetP(tpos=list(tpos), base_type=base_type)
        blending = control_data.BlendingType(type=blending_type, blending_radius=blending_radius)
        post_cond = control_data.MotionCondition()
        if post_condition is not None:
            post_cond = control_data.MotionCondition(
                type_cond=post_condition.condition_type,
                type_react=post_condition.reaction_type,
                const_cond=post_condition.const_cond,
                io_cond=control_data.IOCondition(
                    di=self.__to_digital_request_list__(
                        [{'address': di[0], 'state': di[1]} for di in post_condition.digital_inputs]),
                    # di=self.__to_digital_request_list__(post_condition.digital_inputs),
                    # end_di=self.__to_digital_request_list__(post_condition['enddi_condition']),
                ),
            )

        response = self.__control_stub.MoveFL(control_data.MoveLReq(
            target=ptarget,
            blending=blending,
            vel_ratio=vel_ratio, acc_ratio=acc_ratio,
            des_force=des_force,
            enable_force_control=enable_force_control,
            post_condition=post_cond,
            teaching_mode=teaching_mode
        ))
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)
    @Common.Utils.exception_handler
    def GetTransformedFTSensorData(self):
        response = self.__control_stub.GetTransformedFTSensorData(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    @Common.Utils.exception_handler
    def FTZero(self):
        response = self.__control_stub.FTZero(common_data.Empty())
        return json_format.MessageToDict(response,
                                         including_default_value_fields=True,
                                         preserving_proto_field_name=True,
                                         use_integers_for_enums=True)

    ############################
    # Private
    ############################
    def __to_digital_request_list__(self, digital_signal_list) -> list:
        request_list = []
        if digital_signal_list is not None:
            for signal in digital_signal_list:
                request_list.append(device_data.DigitalSignal(address=signal['address'], state=signal['state']))
        return request_list

    def __to_analog_request_list__(self, analog_signal_list) -> list:
        request_list = []
        if analog_signal_list is not None:
            for signal in analog_signal_list:
                request_list.append(device_data.AnalogSignal(address=signal['address'], voltage=signal['voltage']))
        return request_list

    ############################
    # Console Logging
    ############################
    def _info(self, content=''):
        self._logger.info(content=content, source='ControlClient')

    def _debug(self, content='', source=''):
        self._logger.debug(content=content, source='ControlClient')

    def _warn(self, content='', source=''):
        self._logger.warn(content=content, source='ControlClient')

    def _error(self, content='', source=''):
        self._logger.error(content=content, source='ContyServicer')


############################
# Main
############################
if __name__ == "__main__":
    control_client = ControlSocketClient('192.168.1.6')

    thresholds = control_client.PlayTuningProgram(
        prog_name='test_tuning2.indy7.json',
        tuning_space=common_data.TUNE_ALL,
        precision=common_data.HIGH_PRECISION,
        vel_level_max=3
    )
    print(thresholds)
    # control_client.SetDirectTeaching(enable=True)
    # control_info = control_client.GetControlInfo()
    # print(control_info)
    # control_client.MoveJCond(
    #     jpos=[0, 90, 0, 0, 0, 0],
    #     base_type=ControlSocketClient.ABSOLUTE_JOINT,
    #     vel_ratio=20,
    #     acc_ratio=100,
    #     teaching_mode=False
    # )
    # time.sleep(1)
    # control_client.PlayProgram(prog_idx=1)
    # time.sleep(1)
    # control_client.MoveJ(
    #     jpos=[0, 90, 0, 0, 0, 0],
    #     base_type=ControlSocketClient.ABSOLUTE_JOINT,
    #     blending_type=ControlSocketClient.OVERRIDE_BLENDING,
    #     vel_ratio=20,
    #     acc_ratio=100,
    #     teaching_mode=True
    # )

    # var_list = [
    #     {'name': 'a', 'addr': 101, 'type': 'I'},
    #     {'name': 'b', 'addr': 201, 'type': 'F'},
    #     {'name': 'c', 'addr': 301, 'type': 'JPOS'},
    #     {'name': 'd', 'addr': 401, 'type': 'TPOS'},
    # ]
    # control_client.SetVariableNameList(var_list)
    # time.sleep(1)
    # print(control_client.GetVariableNameList())
    # time.sleep(1)

    # int_var_list = [
    #     {'addr': 101, 'value': 15},
    # ]
    # control_client.SetIntVariable(int_var_list)
    # time.sleep(1)
    # print(control_client.GetIntVariable())

    # control_client.PlayProgram(prog_idx=1)
    # res = control_client.SendAlarm(content="Test")
    # print(res)
