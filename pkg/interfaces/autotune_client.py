import math
import time
import numpy as np

## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

import common_msgs_pb2 as common_data
import hri_msgs_pb2 as conty_data
import boot_msgs_pb2 as boot_data
import device_msgs_pb2 as device_data
import control_msgs_pb2 as control_data
import rtde_msgs_pb2 as rtde_data
import config_msgs_pb2 as config_data
import common as Common

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

def autotune_control_gain(file_name, config, control, rtde, ):
    autotune_control_gain.flag_stop = False

    GAIN_INCREMENT_DEFAULT = 100
    GAIN_CONVERGENCE_DEFAULT = 5
    ROBOT_DOF = Common.Config().ROBOT_DOF
    JERK_REF_RATIO = 1.1

    SW_JPOS_FOLLOW_ERROR = 0x1
    ISO_JVEL_LIMIT = 0x100
    ISO_JTAU_LIMIT = 0x200

    gain_set = config.GetJointControlGain()
    gain_kl2 = np.array(gain_set['kl2'])
    gain_increment = np.array([GAIN_INCREMENT_DEFAULT]*ROBOT_DOF)
    gain_convergence_threshold = GAIN_CONVERGENCE_DEFAULT;
    gain_kl2_lb = gain_kl2
    gain_kl2_ub = gain_kl2 + gain_increment

    control.SetPluginBoolVariable("autotune.reset", True)
    control.SetPluginBoolVariable("autotune.active", True)
    control.PlayProgram(file_name)
    while(rtde.GetProgramData()['program_state'] == common_data.PROG_RUNNING):
        time.sleep(0.02)
        e_rn_jerk_max = control.GetPluginJPosVariable("autotune.eRNjerkMax")['jpos']
    if rtde.GetProgramData()['program_state'] != common_data.PROG_IDLE:
        print(f"Fail: program run state fail {rtde.GetProgramData()['program_state']}")
    control.SetPluginBoolVariable("autotune.active", False)

    e_rn_jerk_max_ref = np.multiply(e_rn_jerk_max, JERK_REF_RATIO)
    print(f"error jerk ref: {e_rn_jerk_max_ref}")

    gain_log = [gain_kl2]
    jerk_log = [e_rn_jerk_max]
    time_log = [0]
    time_0= time.time()
    while not autotune_control_gain.flag_stop:
        control.SetPluginBoolVariable("autotune.reset", True)
        control.SetPluginBoolVariable("autotune.active", True)
        control.PlayProgram(file_name)

        while(rtde.GetProgramData()['program_state'] == common_data.PROG_RUNNING):
            time.sleep(0.005)
            if autotune_control_gain.flag_stop:
                control.StopProgram()
                break
            e_rn_jerk_max = control.GetPluginJPosVariable("autotune.eRNjerkMax")['jpos']
            joint_over_threshold = e_rn_jerk_max > e_rn_jerk_max_ref
            if np.any(joint_over_threshold):
                control.StopProgram()
                break

        while(rtde.GetProgramData()['program_state'] != common_data.PROG_IDLE):
            time.sleep(0.5)
            if autotune_control_gain.flag_stop:
                control.StopProgram()
                break

        violation_data = rtde.GetViolationData()
        if (int(violation_data['violation_code']) in [SW_JPOS_FOLLOW_ERROR, ISO_JVEL_LIMIT, ISO_JTAU_LIMIT]):
            joint_over_threshold[violation_data['j_index']] = True

        if rtde.GetControlData()['op_state'] != common_data.OP_IDLE:
            control.Recover()
            while rtde.GetControlData()['op_state'] != common_data.OP_IDLE:
                if autotune_control_gain.flag_stop:
                    control.StopProgram()
                    break
                time.sleep(1)

        if autotune_control_gain.flag_stop:
            control.StopProgram()
            break
        if np.any(joint_over_threshold):
            for idx, over_thresh in enumerate(joint_over_threshold):
                if over_thresh:
                    print(f"Joint {idx} Over Thresh")
                    if gain_increment[idx] < GAIN_CONVERGENCE_DEFAULT:
                        gain_kl2_ub[idx] = gain_kl2_ub[idx] - GAIN_CONVERGENCE_DEFAULT
                        gain_kl2_lb[idx] = gain_kl2_lb[idx] - GAIN_CONVERGENCE_DEFAULT
                    else:
                        gain_increment[idx] /= 2
                        if gain_increment[idx] < GAIN_CONVERGENCE_DEFAULT:
                            gain_increment[idx] = 0
                        gain_kl2_ub[idx] = gain_kl2_lb[idx] + gain_increment[idx]
        else:
            print(f"Increment All Gains")
            # increment all bounds
            gain_kl2_lb = gain_kl2_ub
            gain_kl2_ub = gain_kl2_lb + gain_increment
        gain_kl2 = gain_kl2_ub


        if rtde.GetProgramData()['program_state'] != common_data.PROG_IDLE:
            print(f"Fail: program run state fail {rtde.GetProgramData()['program_state']}")
        control.SetPluginBoolVariable("autotune.active", False)

        print(f"kl2: {gain_kl2} | jerk: {e_rn_jerk_max}")
        gain_log.append(gain_kl2)
        jerk_log.append(e_rn_jerk_max)
        time_log.append(time.time()-time_0)
        gain_set['kl2'] = gain_kl2.tolist()
        config.SetJointControlGain(**gain_set)
    
        if np.all(gain_increment < GAIN_CONVERGENCE_DEFAULT):
            print(f"Final kl2: {gain_kl2}")
            break
