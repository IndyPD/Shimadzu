## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from ethercat_pb2_grpc import EtherCATStub
from common_msgs_pb2 import *
from ethercat_msgs_pb2 import *

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

import subprocess
import common as Common
import grpc
import time

OP_MODE_NO_MODE = 0x00
OP_MODE_PROFILE_POSITION = 0x01
OP_MODE_VELOCITY = 0x02
OP_MODE_PROFILE_VELOCITY = 0x03
OP_MODE_TORQUE_PROFILE = 0x04
OP_MODE_HOMING = 0x06
OP_MODE_INTERPOLATED_POSITION = 0x07
OP_MODE_CYCLIC_SYNC_POSITION = 0x08
OP_MODE_CYCLIC_SYNC_VELOCITY = 0x09
OP_MODE_CYCLIC_SYNC_TORQUE = 0x0a

##TODO
# make it Config
EXT_SERVO_IDX = 0
def status2string(statusword):
    if (((statusword) & 0x004f) == 0x0000):   # x0xx 0000
        return "NOT_READY"
    elif (((statusword) & 0x004f) == 0x0040): # x1xx 0000
        return "SWITCH_DISABLED"
    elif (((statusword) & 0x006f) == 0x0021): # x01x 0001
        return "READY_SWITCH"
    elif (((statusword) & 0x006f) == 0x0023): # x01x 0011
        return "SWITCHED_ON"
    elif (((statusword) & 0x006f) == 0x0027): # x01x 0111
        return "OPERATION_ENABLED"
    elif (((statusword) & 0x006f) == 0x0007): # x00x 0111
        return "QUICK_STOP"
    elif (((statusword) & 0x004f) == 0x000f): # x0xx 1111
        return "FAULT_REACTION"
    elif (((statusword) & 0x004f) == 0x0008): # x0xx 1000
        return "FAULT"
    else:
        return "UNKNOWN"
    
    
def modeop2string(modeop):
    if modeop == 0x00:
        return "None"
    elif modeop == 0x01:
        return "PP"
    elif modeop == 0x03:
        return "PV"
    elif modeop == 0x04:
        return "TP"
    elif modeop == 0x06:
        return "Homing"
    elif modeop == 0x08:
        return "CSP"
    elif modeop == 0x09:
        return "CSV"
    elif modeop == 0x0a:
        return "CST"


def error_code(mode_op, status_word):
    string_out = []
    if mode_op ==  OP_MODE_PROFILE_POSITION:
        if (status_word & 0x2000):
            string_out.append("Following error")
        if (status_word & 0x1000):
            string_out.append("Set-point acknowledge")
        if (status_word & 0x0400):
            string_out.append("Target reached")

    elif mode_op ==  OP_MODE_PROFILE_VELOCITY:
        if (status_word & 0x2000):
            string_out.append("Max slippage error")
        if (status_word & 0x1000):
            string_out.append("Speed")
        if (status_word & 0x0400):
            string_out.append("Target reached")

    elif mode_op ==  OP_MODE_CYCLIC_SYNC_POSITION:
        if (status_word & 0x2000):
            string_out.append("Following error")
        if (status_word & 0x1000):
            string_out.append("Drive follows command value")

    elif mode_op ==  OP_MODE_CYCLIC_SYNC_VELOCITY:
        if (status_word & 0x1000):
            string_out.append("Drive follows command value")

    elif mode_op ==  OP_MODE_CYCLIC_SYNC_TORQUE:
        if (status_word & 0x1000):
            string_out.append("Drive follows command value")
    return string_out


class EtherCATClient(metaclass=Common.SingletonMeta):
    """
    gRPC client to EtherCAT Server in C++ IndyFramework v3.0
    """

    def __init__(self, ip_addr, port=20000):
        ecat_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
        ecat_stub = EtherCATStub(ecat_channel)
        
        self.__ethercat_stub = Common.Utils.StubWithTimeout(stub=ecat_stub, timeout=Common.Limits.GRPCTimeOut)

    @Common.Utils.exception_handler
    def set_master_status(self, status):
        """
        Master status
            status -> int
        """
        if status == "INIT":
            status = 1
        elif status == "PRE-OP":
            status = 2
        elif status == "SAFE-OP":
            status = 4
        elif status == "OP":
            status = 8
        else:
            status = 0
        self.__ethercat_stub.SetMasterStatus(MasterStatus(status=status))

    @Common.Utils.exception_handler
    def get_master_status(self):
        """
        Master status
            status -> int
        """
        status = self.__ethercat_stub.GetMasterStatus(Empty()).status
        if status == 1:
            return "INIT"
        elif status == 2:
            return "PRE-OP"
        elif status == 4:
            return "SAFE-OP"
        elif status == 8:
            return "OP"
        else:
            return "None"

    @Common.Utils.exception_handler
    def get_slave_status(self):
        """
        Slave status

        """
        status = (self.__ethercat_stub.GetSlaveStatus(Empty()).status)
        slave_status = []
        for stat in status:
            if stat == 1:
                slave_status.append("INIT")
            elif stat == 2:
                slave_status.append("PRE-OP")
            elif stat == 4:
                slave_status.append("SAFE-OP")
            elif stat == 8:
                slave_status.append("OP")
            else:
                slave_status.append("None")
        return slave_status

    @Common.Utils.exception_handler
    def get_txdomain_status(self):
        """
        PDO Tx Domain status
        """
        status = self.__ethercat_stub.GetTxDomainStatus(Empty()).status
        if status == 0:
            return "ZERO"
        elif status == 1:
            return "INCOMPLETE"
        elif status == 2:
            return "COMPLETE"
        else:
            return "None"

    @Common.Utils.exception_handler
    def get_rxdomain_status(self):
        """
        PDO Rx Domain status
        """
        status = self.__ethercat_stub.GetRxDomainStatus(Empty()).status
        if status == 0:
            return "ZERO"
        elif status == 1:
            return "INCOMPLETE"
        elif status == 2:
            return "COMPLETE"
        else:
            return "None"

    @Common.Utils.exception_handler
    def is_system_ready(self):
        """
        System ready state
        """
        return list(self.__ethercat_stub.IsSystemReady(Empty()).ready)

    @Common.Utils.exception_handler
    def is_servo_on(self):
        """
        Servo on state
        """
        return list(self.__ethercat_stub.IsServoOn(Empty()).servo)

    @Common.Utils.exception_handler
    def get_slave_type_num(self):
        """
        Servo on state
        """
        return self.__ethercat_stub.GetSlaveTypeNum(Empty())

    @Common.Utils.exception_handler
    def reset_overflow_count(self):
        """
        Reset and save overflow count
        """
        return self.__ethercat_stub.ResetOverflowCount(Empty())

    @Common.Utils.exception_handler
    def set_servo(self, servo_idx, on):
        """
        Servo on state
        """
        if on:
            self.__ethercat_stub.SetServoOn(ServoIndex(servoIndex=servo_idx))
        else:
            self.__ethercat_stub.SetServoOff(ServoIndex(servoIndex=servo_idx))

    @Common.Utils.exception_handler
    def get_servo_tx(self, servo_idx):
        """
        Get Servo driver's Tx PDO values
        """
        res = self.__ethercat_stub.GetServoTx(ServoIndex(servoIndex=servo_idx))
        return [status2string(res.statusWord), modeop2string(res.modeOpDisp), res.actualPosition, res.actualVelocity, res.actualTorque]
    
    @Common.Utils.exception_handler
    def get_servo_tx_raw(self, servo_idx):
        """
        Get Servo driver's Tx PDO values
        """
        return self.__ethercat_stub.GetServoTx(ServoIndex(servoIndex=servo_idx))
    
    @Common.Utils.exception_handler
    def get_servo_tx_keba(self, servo_idx):
        """
        Get Servo (Keba) driver's Tx PDO values
        """
        res = self.__ethercat_stub.GetServoTxKeba(ServoIndex(servoIndex=servo_idx))
        res1 = [status2string(res.statusWord), res.actualPosition, res.actualVelocity]
        res2 = [status2string(res.statusWord2), res.actualPosition2, res.actualVelocity2]
        res3 = [status2string(res.statusWord3), res.actualPosition3, res.actualVelocity3]
        return [res1, res2, res3]
    
    @Common.Utils.exception_handler
    def get_servo_rx_keba(self, servo_idx):
        """
        Get Servo (Keba) driver's Rx PDO values
        """
        res = self.__ethercat_stub.GetServoRxKeba(ServoIndex(servoIndex=servo_idx))
        res1 = [res.controlWord, res.targetPosition, res.targetTorque]
        res2 = [res.controlWord2, res.targetPosition2, res.targetTorque2]
        res3 = [res.controlWord3, res.targetPosition3, res.targetTorque3]
        return [res1, res2, res3] 

    @Common.Utils.exception_handler
    def get_servo_rx(self, servo_idx):
        """
        Get Servo driver's Rx PDO values
        """
        res = self.__ethercat_stub.GetServoRx(ServoIndex(servoIndex=servo_idx))
        return [res.controlWord, res.modeOp, res.targetPosition, res.targetVelocity, res.targetTorque]

    @Common.Utils.exception_handler
    def set_servo_rx(self, servo_idx, control_word, mode_op, target_pos, target_vel, target_tor):
        """
        Set Servo driver's Rx PDO values
        """
        # print(servo_idx, control_word, mode_op, target_pos, target_vel, target_tor)
        servo_rx = ServoRx(controlWord=control_word, modeOp=mode_op, targetPosition=target_pos, targetVelocity=target_vel, targetTorque=target_tor)
        return self.__ethercat_stub.SetServoRx(ServoRxIndex(servoIndex=servo_idx, rx=servo_rx))
    
    @Common.Utils.exception_handler
    def set_servo_rx_keba(self, servo_idx, rx1, rx2, rx3):
        """
        Set Servo (Keba) driver's Rx PDO values
        """        
        control_word = rx1[0]
        control_word2 = rx2[0]
        control_word3 = rx3[0]
        
        target_pos = rx1[1]
        target_pos2 = rx2[1]
        target_pos3 = rx3[1]
        
        target_tor = rx1[2]
        target_tor2 = rx2[2]
        target_tor3 = rx3[2]
        servo_rx = ServoRxKeba(controlWord=control_word, controlWord2=control_word2, controlWord3=control_word3, 
                               targetPosition=target_pos, targetPosition2=target_pos2, targetPosition3=target_pos3,
                               targetTorque=target_tor, targetTorque2=target_tor2, targetTorque3=target_tor3)
        return self.__ethercat_stub.SetServoRx(ServoRxIndexKeba(servoIndex=servo_idx, rx=servo_rx))

    @Common.Utils.exception_handler
    def get_servo_temperature(self, servo_idx):
        """
        Get Servo SDO temperatures
        """
        return self.__ethercat_stub.GetServoTemperature(ServoIndex(servoIndex=servo_idx)).temperature

    @Common.Utils.exception_handler
    def get_servo_errorcode(self, servo_idx):
        """
        Get Servo SDO error code
        """
        return self.__ethercat_stub.GetServoErrorCode(ServoIndex(servoIndex=servo_idx)).errorCode

    @Common.Utils.exception_handler
    def reset_servo(self, servo_idx):
        """
        Reset servo error
        """
        return self.__ethercat_stub.ResetServo(ServoIndex(servoIndex=servo_idx))
    
    @Common.Utils.exception_handler
    def set_brake(self, ecat_idx, onoff):
        """
        Manual brake by SDO
        """
        return self.__ethercat_stub.SetCOREManualBrake(ServoBrake(ecatIndex=ecat_idx, onoff=onoff))

    @Common.Utils.exception_handler
    def set_endtool_rx(self, endtool_rx):
        """
        Set endtool Rx data
        """
        eqc = endtool_rx["eqc"]
        gripper = endtool_rx["gripper"]
        ft_param = endtool_rx["ft_param"]
        led_mode = endtool_rx["led_mode"]
        led_g = endtool_rx["led_g"]
        led_r = endtool_rx["led_r"]
        led_b = endtool_rx["led_b"]
        return self.__ethercat_stub.SetEndtoolRx(EndtoolRx(eqc=eqc, gripper=gripper, ft_param=ft_param, led_mode=led_mode, led_g=led_g, led_r=led_r, led_b=led_b))

    @Common.Utils.exception_handler
    def get_endtool_rx(self):
        """
        Get endtool Rx data
        """
        endtool_rx = {}
        data = self.__ethercat_stub.GetEndtoolRx(Empty())
        endtool_rx["eqc"] = data.eqc
        endtool_rx["gripper"] = data.gripper
        endtool_rx["ft_param"] = data.ft_param
        endtool_rx["led_mode"] = data.led_mode
        endtool_rx["led_g"] = data.led_g
        endtool_rx["led_r"] = data.led_r
        endtool_rx["led_b"] = data.led_b
        return endtool_rx

    def set_endtool_rs485_rx(self, word1, word2):
        return self.__ethercat_stub.SetEndtoolRS485Rx(EndtoolRS485Rx(word1=word1, word2=word2))

    def get_endtool_rs485_rx(self):
        return self.__ethercat_stub.GetEndtoolRS485Rx(Empty())

    def get_endtool_rs485_tx(self):
        return self.__ethercat_stub.GetEndtoolRS485Tx(Empty())

    def set_endtool_srkey_rx(self, srkey_endtool_rx):
        """
        Set endtool SRKey Rx data
        """
        dout = srkey_endtool_rx["dout"]
        tool_Id = srkey_endtool_rx["tool_Id"]
        set_Tool = srkey_endtool_rx["set_Tool"]
        tool_Closing_Force = srkey_endtool_rx["tool_Closing_Force"]
        tool_Opening_Force = srkey_endtool_rx["tool_Opening_Force"]
        tool_Force_Location = srkey_endtool_rx["tool_Force_Location"]
        return self.__ethercat_stub.SetSRKeyEndtoolRx(SRKeyEndtoolRx(dout = dout, tool_Id = tool_Id, set_Tool = set_Tool, tool_Closing_Force = tool_Closing_Force, tool_Opening_Force = tool_Opening_Force, tool_Force_Location = tool_Force_Location))

    def get_endtool_srkey_rx(self):
        """
        Get endtool SRKey Rx data
        """
        endtool_srkey_rx = {}
        data = self.__ethercat_stub.GetSRKeyEndtoolRx(Empty())
        endtool_srkey_rx["dout"] = data.dout
        endtool_srkey_rx["tool_Id"] = data.tool_Id
        endtool_srkey_rx["set_Tool"] = data.set_Tool
        endtool_srkey_rx["tool_Closing_Force"] = data.tool_Closing_Force
        endtool_srkey_rx["tool_Opening_Force"] = data.tool_Opening_Force
        endtool_srkey_rx["tool_Force_Location"] = data.tool_Force_Location
        return endtool_srkey_rx

    def get_endtool_srkey_tx(self):
        """
        Get endtool SRKey Tx data
        """
        endtool_srkey_tx = {}
        data = self.__ethercat_stub.GetSRKeyEndtoolTx(Empty())
        endtool_srkey_tx["din"] = data.din
        endtool_srkey_tx["tool_Status"] = data.tool_Status
        endtool_srkey_tx["tool_Location"] = data.tool_Location
        endtool_srkey_tx["analog0"] = data.analog0
        endtool_srkey_tx["analog1"] = data.analog1
        endtool_srkey_tx["version"] = data.version
        return endtool_srkey_tx

    @Common.Utils.exception_handler
    def get_endtool_tx(self):
        """
        Get endtool Tx data
        """
        endtool_tx = {}
        data = self.__ethercat_stub.GetEndtoolTx(Empty())
        endtool_tx["status"] = data.status
        endtool_tx["button"] = data.button
        endtool_tx["ft_sensor"] = data.ft_sensor
        endtool_tx["ft_state"] = data.ft_state
        endtool_tx["ft_error"] = data.ft_error
        return endtool_tx

    @Common.Utils.exception_handler
    def get_ioboard_tx(self):
        """
        Get ioboard Tx data
        """
        ioboard_tx = {}
        data = self.__ethercat_stub.GetIOBoardTx(Empty())
        ioboard_tx["di5v"] = data.di5v
        ioboard_tx["di24v1"] = data.di24v1
        ioboard_tx["di24v2"] = data.di24v2
        ioboard_tx["ai1"] = data.ai1
        ioboard_tx["ai2"] = data.ai2
        return ioboard_tx

    @Common.Utils.exception_handler
    def get_ioboard_rx(self):
        """
        Get ioboard Rx data
        """
        ioboard_rx = {}
        data = self.__ethercat_stub.GetIOBoardRx(Empty())
        ioboard_rx["do5v"] = data.do5v
        ioboard_rx["do24v1"] = data.do24v1
        ioboard_rx["do24v2"] = data.do24v2
        ioboard_rx["ao1"] = data.ao1
        ioboard_rx["ao2"] = data.ao2
        ioboard_rx["ft_param"] = data.ft_param
        return ioboard_rx

    @Common.Utils.exception_handler
    def set_ioboard_rx(self, ioboard_rx):
        """
        Set ioboard Rx data
        """
        do5v = ioboard_rx["do5v"]
        do24v1 = ioboard_rx["do24v1"]
        do24v2 = ioboard_rx["do24v2"]
        ao1 = ioboard_rx["ao1"]
        ao2 = ioboard_rx["ao2"]
        ft_param = ioboard_rx["ft_param"]
        return self.__ethercat_stub.SetIOBoardRx(
            EndtoolRx(do5v=do5v, do24v1=do24v1, do24v2=do24v2, ao1=ao1, ao2=ao2, ft_param=ft_param))


    @Common.Utils.exception_handler
    def get_di(self, dio_index):
        """
        Get DIO Tx data
        """
        return self.__ethercat_stub.GetDI(DIOIndex(dioIndex=dio_index)).di_list

    @Common.Utils.exception_handler
    def get_do(self, dio_index):
        """
        Set ioboard Rx data
        """
        return self.__ethercat_stub.GetDO(DIOIndex(dioIndex=dio_index)).do_list
    
    @Common.Utils.exception_handler
    def set_do(self, dio_index, dio):
        """
        Set ioboard Rx data
        """
        return self.__ethercat_stub.SetDO(DIODigitalOutput(dioIndex=dio_index, do_list=dio))

    @Common.Utils.exception_handler
    def get_ai(self, aio_index):
        """
        Get AIO Tx data
        """
        return self.__ethercat_stub.GetAI(AIOIndex(aioIndex=aio_index)).ai_list

    @Common.Utils.exception_handler
    def get_ao(self, aio_index):
        """
        Get AIO Rx data
        """
        return self.__ethercat_stub.GetAO(AIOIndex(aioIndex=dio_index)).ao_list

    @Common.Utils.exception_handler
    def set_ao(self, aio_index, aio):
        """
        Set AIO Rx data
        """
        return self.__ethercat_stub.SetAO(AIOAnalogOutput(aioIndex=aio_index, ao_list=aio))

    @Common.Utils.exception_handler
    def set_maxTorque(self, slave_idx, value):
        """
        Set Maximum Torque [ecat idx, torq]
        """
        return self.__ethercat_stub.SetMaxTorqueSDO(ServoParam(slaveIdx=slave_idx, val=value))

    @Common.Utils.exception_handler
    def set_profileVel(self, slave_idx, value):
        """
        Set Profile Velocity [ecat idx, vel]
        """
        return self.__ethercat_stub.SetProfileVelSDO(ServoParam(slaveIdx=slave_idx, val=value))

    @Common.Utils.exception_handler
    def set_profileAcc(self, slave_idx, value):
        """
        Set Profile Acceleration [ecat idx, acc]
        """
        return self.__ethercat_stub.SetProfileAccSDO(ServoParam(slaveIdx=slave_idx, val=value))

    @Common.Utils.exception_handler
    def set_profileDec(self, slave_idx, value):
        """
        Set Profile Deceleration [ecat idx, dec]
        """
        return self.__ethercat_stub.SetProfileDecSDO(ServoParam(slaveIdx=slave_idx, val=value))

    @Common.Utils.exception_handler
    def get_maxTorque(self, slave_idx):
        """
        Get Maximum Torque [ecat idx]
        """
        return self.__ethercat_stub.GetMaxTorqueSDO(EcatIndex(ecatIndex=slave_idx)).val

    @Common.Utils.exception_handler
    def get_profileVel(self, slave_idx):
        """
        Get Profile Velocity [ecat idx]
        """
        return self.__ethercat_stub.GetProfileVelSDO(EcatIndex(ecatIndex=slave_idx)).val

    @Common.Utils.exception_handler
    def get_profileAcc(self, slave_idx):
        """
        Get Profile Acceleration [ecat idx]
        """
        return self.__ethercat_stub.GetProfileAccSDO(EcatIndex(ecatIndex=slave_idx)).val

    @Common.Utils.exception_handler
    def get_profileDec(self, slave_idx):
        """
        Get Profile Deceleration [ecat idx]
        """
        return self.__ethercat_stub.GetProfileDecSDO(EcatIndex(ecatIndex=slave_idx)).val

    @Common.Utils.exception_handler
    def get_robot_zero_count(self, servo_idx):
        """
        Get robot zero count
        """
        return self.__ethercat_stub.GetRobotZeroCount(ServoIndex(servoIndex=servo_idx))

    @Common.Utils.exception_handler
    def set_robot_zero_as_current(self, servo_idx):
        """
        Set robot zero as current
        """
        return self.__ethercat_stub.SetRobotZeroAsCurrent(ServoIndex(servoIndex=servo_idx))

    ## Conty Linear Ext Servo
    @Common.Utils.exception_handler
    def get_axis_data(self):
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
        """
        axis_data_dict = {}
        servo_tx = self.get_servo_tx(EXT_SERVO_IDX)
        servo_rx = self.get_servo_rx(EXT_SERVO_IDX)

        #active
        try:
            if servo_tx[0] == 'OPERATION_ENABLED':
                active = [True]
            else:
                active = [False]

            ##TODO
            # make it Config
            # make Code extensibility (now, only 1 axis)
            convert = 1/72000 # 1rev per 0.5cm  , 1rev per 360000feed
            num_axes = 1

            pos_cnt = servo_tx[2] # actualPos
            pos_mm = [pos_cnt * convert]

            vel_cnt = servo_tx[3] # actualVel
            vel_mm = [vel_cnt * convert]

            despos_cnt = servo_rx[2]
            despos_mm = despos_cnt * convert

            desvel_mm = 0.0 # ethertoolslave -p0 upload -t uint32 0x6081 0  (profiled velocity)
            desacc_mm = 0.0 # ethertoolslave -p0 upload -t uint32 0x6083 0  (profiled velocity)
            # ethertoolslave -p0 upload -t uint32 0x6084 0  (profiled velocity)

            if self.is_servo_on()[EXT_SERVO_IDX]:
                op_state = 1 # SYSTEM_ON
                if self.is_system_ready()[EXT_SERVO_IDX]:
                    op_state = 5 # IDLE
                elif self.is_system_ready()[EXT_SERVO_IDX] & servo_rx[2] != 0:
                    op_state = 6 # MOVING
            else:
                op_state = 0 # SYSTEM_OFF


            traj_state: TrajState = TrajState.TRAJ_NONE

            axis_data_dict = {
                "active" : active,
                "pos_mm" : pos_mm,
                "vel_mm" : vel_mm,
                "despos_mm" : despos_mm,
                "desvel_mm" : desvel_mm,
                "desacc_mm" : desacc_mm,
                "num_axes" : num_axes,
                "op_state" : op_state,
                "traj_state" : traj_state
            }
        except:
            pass
        # print('Linear Axis Data: ' + str(axis_data_dict))
        return axis_data_dict

    @Common.Utils.exception_handler
    def move_axis(self,
                  start_mm,
                  target_mm,
                  is_absolute=True,
                  vel_ratio=Common.Limits.JogVelRatioDefault,
                  acc_ratio=Common.Limits.JogAccRatioDefault,
                  teaching_mode=False,
                  sync_mode = False):
        ##TODO
        # make it Config
        convert = 1/72000

        vel = Common.Limits.ExternalMotorSpeedMaxCnt * vel_ratio / 100
        acc = vel * acc_ratio / 100

        command = f"ethercattool -p{EXT_SERVO_IDX} download -t uint32 0x6081 0 {vel}"
        subprocess.run(command, shell=True, stdout=subprocess.PIPE)
        command = f"ethercattool -p{EXT_SERVO_IDX} download -t uint32 0x6083 0 {acc}"
        subprocess.run(command, shell=True, stdout=subprocess.PIPE)
        command = f"ethercattool -p{EXT_SERVO_IDX} download -t uint32 0x6084 0 {acc}"
        subprocess.run(command, shell=True, stdout=subprocess.PIPE)

        res = {}
        if self.is_servo_on()[EXT_SERVO_IDX] & self.is_system_ready()[EXT_SERVO_IDX]:
            res = {
                "start_mm" : start_mm,
                "target_mm": target_mm,
                "is_absolute" : is_absolute,
                "vel_ratio" : vel_ratio,
                "acc_ratio" : acc_ratio,
                "teaching_mode" : teaching_mode
            }
            if teaching_mode:
                ##TODO if more then 1 Axis. Change [0] to [0],[1]...
                curr_pos = list(start_mm)[0]
                tar_pos = list(target_mm)[0]
                if is_absolute==False: # jog
                    tar_pos_cnt = (curr_pos + tar_pos) / convert
                else: # HoldtoMOVE
                    tar_pos_cnt = tar_pos / convert

                if sync_mode:
                    self.set_servo_rx(EXT_SERVO_IDX, 0x1f, 0x01, int(tar_pos_cnt), 0, 0)
                else:
                    self.set_servo_rx(EXT_SERVO_IDX, 0x3f, 0x01, int(tar_pos_cnt), 0, 0)
                    time.sleep(0.01)
                    self.set_servo_rx(EXT_SERVO_IDX, 0x2f, 0x01, int(tar_pos_cnt), 0, 0)
        else:
            res = None

        return res

    @Common.Utils.exception_handler
    def stop_motion(self, stop_category):
        time.sleep(0.1)
        self.set_servo_rx(EXT_SERVO_IDX, 15, 10, 0, 0, 0)
        pass
############################
# Main
############################
if __name__ == "__main__":
    ip = '192.168.0.91'
    ecat = EtherCATClient(ip)
    print("Master status: ", ecat.get_master_status())
    print("Slave status: ", ecat.get_slave_status())
    print("TxPDO domain: ", ecat.get_txdomain_status())
    print("RxPDO domain: ", ecat.get_rxdomain_status())
    print("System ready: ", ecat.is_system_ready())
    print("Servo state: ", ecat.is_servo_on())
    print("")
    print(ecat.get_slave_type_num())

    time.sleep(1)
