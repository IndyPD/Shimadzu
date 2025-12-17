## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from moby_pb2_grpc import MobyStub
from moby_msgs_pb2 import *
from common_msgs_pb2 import *

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect


import common as Common
import grpc
import time


class MobyClient:
    """
    gRPC client to EtherCAT Server in C++ IndyFramework v3.0
    """

    def __init__(self, ip_addr):
        moby_channel = grpc.insecure_channel("{}:{}".format(ip_addr, 20200))
        moby_stub = MobyStub(moby_channel)

        self.__moby_stub = Common.Utils.StubWithTimeout(stub=moby_stub, timeout=Common.Limits.GRPCTimeOut)


    @Common.Utils.exception_handler
    def get_moby_state(self):
        """
        Get Moby State
        -State
        -is_ready
        -is_enable
        -is_moving
        -is_violation
        """
        state_dict = {
            0: "SYSTEM_OFF",
            1: "SYSTEM_ON",
            2: "VIOLATE",
            # 3: "RECOVER_HARD",
            4: "RECOVER_SOFT",
            # 5: "MANUAL_RECOVER",
            6: "IDLE",
            7: "MOVING",
            # 9: "COLLISION",
            # 10: "STOP_AND_OFF",
            # 12: "BRAKE_CONTROL",
            # 15: "VIOLATE_HARD",
            16: "TELE_OP",
        }
        state = self.__moby_stub.GetMobyState(Empty())
        moby_state = state_dict.get(state.status, "(UNKNOWN STATE CODE)")
        b_ready = state.is_ready
        b_enable = state.is_enable
        b_moving = state.is_moving
        b_violation = state.is_violation

        return {'state': moby_state, 'is_ready': b_ready,
                'is_enable': b_enable, 'is_moving': b_moving, 'is_violation': b_violation}

    @Common.Utils.exception_handler
    def get_moby_error_state(self):
        """
        Get Moby Error State
        """
        error_dict = {
            0x00: "NONE",
            0x01: "SW_MASTER_NOT_OP",
            0x02: "SW_SLAVES_NOT_OP",
            0x04: "SW_SERVO_NOT_ON",
            0x08: "SW_SERVO_NOT_READY",
            0x10: "SW_ENCODER_ABNORMAL",
            0x20: "SW_BUMPER_DETECT",
            # 0x40: "HW_EMG_PUSH",
            # 0x80: "HW_STEER_NOT_REACH",
            0x100: "HW_CONNECTION_LOS",
        }

        err = self.__moby_stub.GetMobyErrorState(Empty())

        return [error_dict.get(err.errorState, "(UNKNOWN ERROR CODE)"),
                err.errorIndex1, err.errorIndex2, err.errorIndex3]

    @Common.Utils.exception_handler
    def recover(self):
        return self.__moby_stub.Recover(Empty())

    @Common.Utils.exception_handler
    def get_moby_pose(self):
        """
        Get Moby pose (m): [Px, Py, Pw]
        """
        pose = self.__moby_stub.GetMobyPose(Empty())
        return [pose.px, pose.py, pose.pw]

    @Common.Utils.exception_handler
    def get_moby_vel(self):
        """
        Get Moby velocity (m/s): [Vx, Vy, Vw]
        """
        vel = self.__moby_stub.GetMobyVel(Empty())
        return [vel.vx, vel.vy, vel.vw]

    @Common.Utils.exception_handler
    def reset_moby_pose(self):
        """
        Reset Moby pose
        """
        return self.__moby_stub.ResetMobyPose(Empty())

    @Common.Utils.exception_handler
    def get_rotation_angle(self):
        """
        Get rotation angle (deg): [fl, fr, bl, br]
        """
        val = self.__moby_stub.GetRotationAngleDeg(Empty())
        return {'fl': val.fl, 'fr': val.fr, 'bl':val.bl, 'br':val.br}

    @Common.Utils.exception_handler
    def get_drive_speed(self):
        """
        Get drive speed (m/s): [fl, fr, bl, br]
        """
        val = self.__moby_stub.GetDriveSpeed(Empty())
        return {'fl': val.fl, 'fr': val.fr, 'bl':val.bl, 'br':val.br}


    @Common.Utils.exception_handler
    def get_target_vel(self):
        """
        Get Moby's target velocity
        """
        target = self.__moby_stub.GetTargetVel(Empty())
        return [target.vx, target.vy, target.vw]

    @Common.Utils.exception_handler
    def get_zero(self):
        """
        Get rotation's zero position (encoder count)
        """
        val = self.__moby_stub.GetRotationZeroCount(Empty())
        return {'fl': val.fl, 'fr': val.fr, 'bl':val.bl, 'br':val.br}

    @Common.Utils.exception_handler
    def get_gyro_data(self):
        """
        Get Gyro sensor data (yaw, yaw rate)
        """
        return self.__moby_stub.GetGyroData(Empty()).val

    @Common.Utils.exception_handler
    def get_imu_data(self):
        """
        Get Full IMU sensor data
        """
        data = self.__moby_stub.GetGyroFullData(Empty())
        angle = [data.angleX, data.angleY, data.angleZ]
        vel = [data.angleVelX, data.angleVelY, data.angleVelZ]
        acc = [data.linAccX, data.linAccY, data.linAccZ]
        return angle, vel, acc

    @Common.Utils.exception_handler
    def reset_gyro(self):
        """
        Reset gyro sensor
        """
        return self.__moby_stub.ResetGyroSensor(Empty())

    @Common.Utils.exception_handler
    def use_gyro_for_odom(self, use_gyro):
        """
        Use gyro sensor for odometry calculation
        """
        return self.__moby_stub.UseGyroForOdom(BoolVal(val=use_gyro))

    # @Common.Utils.exception_handler
    # def get_ir_data(self):
    #     """
    #     Get IR sensor data
    #     """
    #     return self.__moby_stub.GetIRSensorData(Empty())

    @Common.Utils.exception_handler
    def get_us_data(self):
        """
        Get US sensor data
        """
        value = self.__moby_stub.GetUSSensorData(Empty())
        return {'front_left1': value.us_front_left1, 'front_left2': value.us_front_left2, 'front_left3': value.us_front_left3, 'front_ground': value.us_front_ground, 'front_right1': value.us_front_right1, 'front_right2': value.us_front_right2, 'front_right3': value.us_front_right3, 'front_right4': value.us_front_right4, 'back_right1': value.us_back_right1, 'back_right2': value.us_back_right2, 'back_right3': value.us_back_right3, 'back_ground': value.us_back_ground, 'back_left1': value.us_back_left1, 'back_left2': value.us_back_left2, 'back_left3': value.us_back_left3, 'back_left4': value.us_back_left4}
    
    @Common.Utils.exception_handler
    def get_bms(self):
        """
        Get BMS data
        GreenPyzzle : 
            'BMS status-1', 'BMS status-2',
            'Pack voltage-1', 'Pack voltage-2',
            'Battery Voltage-1', 'Battery Voltage-2',
            'Pack current1-1', 'Pack current1-2', 'Pack current2-1', 'Pack current2-2',
            'Temperature-1', 'Temperature-2', 'Temperature-3', 'Temperature-4'
        CTNS : 
            'Pack voltage-1', 'Pack current1-1
            'Is Charge', 'Is Cell OverVoltage',
            'Is Cell UnderVoltage', 'Is OverCurrent Charge',
            'Is OverCurrent Discharge', 'Is Short Circuit',
            'Is OverTemperature', 'Is Pack OverVoltage',
            'SOC', 'SOH', 'Time for Charge', 'time for Discharge'
            'Remain Capacity Ah', 'Remain Capacity Wh'
            'Temperature-(1~3)', 'Cell Voltage-(1~13)'
        """
        value = self.__moby_stub.GetBMSData(Empty())
        return {'BMS status-1': value.bms_status[0] / 10, 'BMS status-2': value.bms_status[1] / 10,
                'Pack voltage-1': value.pack_volt[0] / 100, 'Pack voltage-2': value.pack_volt[1] / 100,
                'Battery Voltage-1': value.battery_volt[0] / 100, 'Battery Voltage-2': value.battery_volt[1] / 100,
                'Pack current1-1': value.pack_current1[0] / 100, 'Pack current1-2': value.pack_current1[1] / 100,
                'Pack current2-1': value.pack_current2[0] / 100, 'Pack current2-2': value.pack_current2[1] / 100,
                'Is Charge': value.isCharge, 'Is Cell OverVoltage': value.isCellOverVolt,
                'Is Cell UnderVoltage': value.isCellUnderVolt, 'Is OverCurrent Charge': value.isOverCurCharge,
                'Is OverCurrent Discharge': value.isOverCurDischrg, 'Is Short Circuit': value.isShortCircuit,
                'Is OverTemperature': value.isOverTemperature, 'Is Pack OverVoltage': value.isPackOverVolt,
                'SOC': value.SOC * 0.1, 'SOH': value.SOH, 'Time for Charge': value.time_charge,
                'time for Discharge': value.time_dcharge, 'Remain Capacity Ah': value.rem_capAh / 100,
                'Remain Capacity Wh': value.rem_capWh, 'Temperature-1': value.bms_temperature[0] * 0.1,
                'Temperature-2': value.bms_temperature[1] * 0.1, 'Temperature-3': value.bms_temperature[2] * 0.1,
                'Temperature-4': value.bms_temperature[3] * 0.1, 'Cell Voltage-1': value.cell_volt[0] * 0.001,
                'Cell Voltage-2': value.cell_volt[1] * 0.001, 'Cell Voltage-3': value.cell_volt[2] * 0.001,
                'Cell Voltage-4': value.cell_volt[3] * 0.001, 'Cell Voltage-5': value.cell_volt[4] * 0.001,
                'Cell Voltage-6': value.cell_volt[5] * 0.001, 'Cell Voltage-7': value.cell_volt[6] * 0.001,
                'Cell Voltage-8': value.cell_volt[7] * 0.001, 'Cell Voltage-9': value.cell_volt[8] * 0.001,
                'Cell Voltage-10': value.cell_volt[9] * 0.001, 'Cell Voltage-11': value.cell_volt[10] * 0.001,
                'Cell Voltage-12': value.cell_volt[11] * 0.001, 'Cell Voltage-13': value.cell_volt[12] * 0.001}

    @Common.Utils.exception_handler
    def set_target_vel(self, vx, vy, vw):
        """
        Drive control
        """
        return self.__moby_stub.SetStepControl(TargetVel(vx=vx, vy=vy, vw=vw))

    @Common.Utils.exception_handler
    def stop_motion(self):
        """
        Stop Moby motion
        """
        return self.__moby_stub.StopMotion(Empty())

    @Common.Utils.exception_handler
    def go_straight(self):
        """
        Go straight (zero rotation)
        """
        return self.__moby_stub.SetRotationAngleDeg(SwerveDoubles(fl=0, fr=0, bl=0, br=0))

    @Common.Utils.exception_handler
    def move_rotation_deg(self, fl, fr, bl, br):
        """
        Rotation control (target angle degree)
        """
        return self.__moby_stub.SetRotationAngleDeg(SwerveDoubles(fr=fr, br=br, bl=bl, fl=fl))

    @Common.Utils.exception_handler
    def move_driving_mps(self, fl, fr, bl, br):
        """
        Driving control (target speed m/s)
        """
        return self.__moby_stub.DriveWheel(SwerveDoubles(fr=fr, br=br, bl=bl, fl=fl))

    ############################
    # Set Moby parameters
    ############################

    @Common.Utils.exception_handler
    def set_zero_as_current(self):
        """
        Set current roation position as zero
        """
        return self.__moby_stub.SetZeroPosAsCurrentPos(Empty())

    @Common.Utils.exception_handler
    def set_rotation_vel_acc(self, vel, acc):
        """
        Set rotation maximum velocity, acceleration
        """
        return self.__moby_stub.SetRotationVelAcc(DoubleVals(val=[vel, acc]))

    @Common.Utils.exception_handler
    def set_rotation_interpolator(self, val):
        """
        Set rotation interpolator
        0: Ramp interpolator
        1: Streaming interpolator
        2: Velocity interpolator
        3: Trapezoidal interpolator
        """
        return self.__moby_stub.SetRotationInterpolator(IntVal(val=val))

    @Common.Utils.exception_handler
    def set_drive_acc_dec(self, acc, dec):
        """
        Set drive acc dec
        """
        return self.__moby_stub.SetDriveAccDec(DoubleVals(val=[acc, dec]))

    @Common.Utils.exception_handler
    def set_drive_interpolator_on_off(self, on):
        """
        Set drive interpolator On Off
        """
        return self.__moby_stub.SetDriveInterpolatorOnOff(BoolVal(val=on))

    @Common.Utils.exception_handler
    def set_rotation_controller_type(self, val):
        """
        Set rotation controller type
        0: HINFPID_CONTROLLER,
        1: SIMPLEPID_POS_CONTROLLER,
        2: SIMPLEPID_VEL_CONTROLLER
        """
        return self.__moby_stub.SetRotationControllerType(IntVal(val=val))

    @Common.Utils.exception_handler
    def set_rotation_gain(self, index, k, kv, kp):
        """
        Set Rotation Control Gain
        """
        return self.__moby_stub.SetControlParam(RotationGain(idx=index, k=k, kv=kv, kp=kp))
        
    @Common.Utils.exception_handler
    def get_rotation_gain(self, index):
        """
        Get Rotation Control Gain (k, kv, kp)
        """
        val = self.__moby_stub.GetControlParam(IntVal(val=index))
        return {'k': val.k, 'kv':val.kv, 'kp':val.kp}
    
    @Common.Utils.exception_handler
    def set_kinematics_forced(self, onoff, angle):
        """
        Set Kinematics Forced( on=true, off=false )
        """
        self.__moby_stub.SetForceKinematics(ForcedKinematicsData(activate=onoff, angle=angle))

    @Common.Utils.exception_handler
    def get_kinematics_forced(self):
        """
        Get Kinematics Forced( on=true, off=false )
        """
        val = self.__moby_stub.GetForceKinematics(Empty())
        return val.activate, val.angle
        

    ############################
    # Moby-Agri related commands
    ############################
        
    @Common.Utils.exception_handler
    def turn_light(self, on):
        return self.__moby_stub.TurnLightOnOff(BoolVal(val=on))
        
    @Common.Utils.exception_handler
    def turn_buzzer(self, on):
        return self.__moby_stub.TurnBuzzOnOff(BoolVal(val=on))

    @Common.Utils.exception_handler
    def pause_bumper(self, on):
        return self.__moby_stub.PauseBumper(BoolVal(val=on))

    @Common.Utils.exception_handler
    def set_extra_do(self, do_sig:list):
        if len(do_sig)>=8:
            return self.__moby_stub.SetExtraDO(BoolVals(val=do_sig))
        else:
            return False

    ############################
    # Moby Data logging
    ############################
    
    @Common.Utils.exception_handler
    def start_rt_logging(self):
        """
        Start RT logging
        """
        return self.__moby_stub.StartRTLogging(Empty())
    
    @Common.Utils.exception_handler
    def end_rt_logging(self):
        """
        End RT logging
        """
        return self.__moby_stub.EndRTLogging(Empty())
    
    # def set_logger_buffer(self, val):
    #     """
    #     Set logger buffer
    #     """
    #     return self.__moby_stub.SetLoggerBuffer(IntVal(val=val))
    
    # def rt_logger_save(self):
    #     """
    #     RT logger save
    #     """
    #     return self.__moby_stub.RTLoggerSave(Empty())


############################
# Main
############################
if __name__ == "__main__":
    ip = '192.168.0.91'
    moby = MobyClient(ip)
    time.sleep(1)
