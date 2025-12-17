import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'impl'))

import grpc
from concurrent import futures
from config_socket_client import ConfigSocketClient
from rtde_socket_client import RTDESocketClient
from control_socket_client import ControlSocketClient, control_data

import triad_openvr
import time
import sys
import os
import numpy as np
import math 
import matplotlib.pyplot as plt

import pandas as pd

from scipy.spatial.transform import Rotation as R

robot_ip="192.168.0.144"
DEVICE_NAME = "controller_1"
VEL_SCALE = 1.0
ACC_SCALE = 1.0


config = ConfigSocketClient(robot_ip)
control = ControlSocketClient(robot_ip)
rtde = RTDESocketClient(robot_ip)


def indy_get_task_pos():
    tpos = rtde.GetControlData()['p']
    tpos = np.array(tpos)
    tpos[:3] /= 1000
    tpos[3:] *= np.pi/180
    return tpos.tolist()

def indy_go_home():
    control.MoveJ(config.GetHomePos()['jpos'])
    
def indy_get_di(i):
    return rtde.GetIOData()['di'][i]['state']
    
def indy_start_teleoperation():
    control.StartTeleOp(method=control_data.TeleMethod.TELE_TASK_RELATIVE,
                        mode=control_data.TeleMode.TELE_RAW)
    
def indy_stop_teleoperation():
    control.StopTeleOp()
    
def indy_update_teleoperation_traj(tpos):
    tpos = np.array(tpos)
    tpos[:3] *= 1000
    tpos[3:] *= 180/np.pi
    control.MoveTeleL(tpos.tolist(), VEL_SCALE, ACC_SCALE)

def reset():
    indy_stop_teleoperation()
    time.sleep(1)
    control.Recover()
    time.sleep(1)
    while not all(rtde.GetServoData()['servo_actives']):
        print("Wait Robot Ready")
        time.sleep(1)   
    time.sleep(2)

def get_vive_pose():
    vivePose = v.devices[DEVICE_NAME].get_pose_matrix()
    rotMat = np.array([[vivePose.m[0][0], vivePose.m[0][1], vivePose.m[0][2]],
                       [vivePose.m[1][0], vivePose.m[1][1], vivePose.m[1][2]],
                       [vivePose.m[2][0], vivePose.m[2][1], vivePose.m[2][2]]])
    rot = R.from_matrix(np.dot(T.T, rotMat))
    pos = np.dot(T.T, np.array([vivePose.m[0][3], vivePose.m[1][3], vivePose.m[2][3]]))
    rotVec = rot.as_rotvec()
    return [pos, rotVec]

def get_vive():
    v = triad_openvr.triad_openvr()
    v.print_discovered_objects()

    if use_vive:
        for i in range(200):
            v.devices[DEVICE_NAME].trigger_haptic_pulse()
            time.sleep(0.01)            
    return v
    

def movement_limit_by(before_command,command):
    moveby_flag = True
    
    #except rotation
    for i in range(3):
        if 0.02 < abs(before_command[i]-command[i]):
            print("i = ",i,"gap = ",before_command[i]-command[i])
            moveby_flag = False            
    return moveby_flag            

def movement_limit_to():
    moveto_flag = True
    current = indy_get_task_pos()

    if current[2] >= 0.7565399408340454 :
        moveto_flag = False
        print("z axix +")   
    return moveto_flag

def command_limit(command):
    command_limit_flag = True
    for i in range(3):
        if 0.5 < abs(command[i]):
            print("command_limit filter!!!!!!!!!!!")
            time.sleep(3)
            indy_stop_teleoperation()
            indy_go_home()

#variables 
global flag
flag = 1
global v
use_vive = True
interval = 1/50
offset = []
npz_file = np.load('rot_mat.npz')
T = npz_file['R']
start_time = time.time()
operation_time = 0
operation_time_save = 0
grip_button_down = False
menu_button_down = False
recording = False
isTeleoperating = False
record_flag = 0
tele_time_flag = True
command = indy_get_task_pos()
before_command = command
magnification = 1.0
print("magnification: {}".format(magnification))
isConstraint = False

v = get_vive()

indy_stop_teleoperation()
reset()

# check robot cmode
if rtde.GetControlData()['op_state'] != 5:
    print("robot is running")
    time.sleep(1)
    operation_time = 1000000.0

while True:
    try:
        loopStart = time.time()
        controller_inputs = v.devices[DEVICE_NAME].get_controller_inputs()

        if indy_get_di(0)==True:  #recording play
            indy_stop_teleoperation()
            isTeleoperating = False
            
            for i in range(30):
                v.devices[DEVICE_NAME].trigger_haptic_pulse()
                time.sleep(0.01)
            
            print("start exteranl trajectory move")
            
            time.sleep(1)

            print("start exteranl trajectory move not implemented this version")
            # ext = ext_test.ext_client()
            # ext.external_move()
            # print("start exteranl trajectory move done")

        if indy_get_di(0)==False:
            if tele_time_flag == True:
                tele_start_time = time.time()
                tele_time_flag = False
            tele_operation_time = time.time()-tele_start_time
            # print("tele_operation_time: {0}".format(tele_operation_time))

            if controller_inputs['trigger']:
                # print("trigerrrrrr")
                if get_vive_pose() == 0:
                    isTeleoperating = False
                    isTeleoperating_constraint = False
                else:
                    [current_vive_position, current_vive_rotvec] = get_vive_pose()

                #not constraint teleoperation
                if not isTeleoperating:
                    rows = 1
                    cols = 6
                    data = [[0 for j in range(cols)] for i in range(rows)]
                    #set vive haptic pulse
                    for i in range(30):
                        v.devices["controller_1"].trigger_haptic_pulse()
                        time.sleep(0.01)
                
                    indy_start_teleoperation()
                    print("start teleoperation")
                    time.sleep(0.3)

                    record_flag = 1
                    
                    # set current controller position as robot position (orientation is not implemented yet)
                    current_robot_pose = indy_get_task_pos()
                    print("current_robot_pose at start : ",current_robot_pose)
                    print("robot pose", current_robot_pose)
                    robot_position_offset = - np.array(current_robot_pose[0:3])
                    robot_orientation_offset = R.identity()
                    controller_position_offset = - np.array(current_vive_position)
                    controller_orientation_offset = R.identity()
                    vive_rotmat = R.from_rotvec(current_vive_rotvec)
                    controller_orientation_offset = vive_rotmat.inv()       #*identity()
                    robot_rotmat = R.from_euler("xyz", current_robot_pose[3:6])
                    robot_orientation_offset = robot_rotmat.inv()
                    isTeleoperating = True

                    #init
                    init_command_position = np.array(current_vive_position) + controller_position_offset
                    init_command = init_command_position.tolist()
                    print(init_command)
                    print("pass init command")
                    
                else:
                    command_position = np.array(current_vive_position) + controller_position_offset
                    vive_rotmat = R.from_rotvec(current_vive_rotvec)
                    command_rotmat = vive_rotmat * controller_orientation_offset
                    command_orientation = command_rotmat.as_euler("xyz")          
                    before_command = command
                    command = command_position.tolist() + command_orientation.tolist()

                    for j in range(6):
                        command[j] = command[j]*(1/5)
                        
                    # limit function
                    moveto_flag = movement_limit_to()    
                    # moveby_flag = movement_limit_by(before_command,command)   
                    command_limit(command)

                    data.append(command)
                    
                    if moveto_flag==True :
                        # START_T = time.time()
                        indy_update_teleoperation_traj(command)  
                        # print("gap = ",time.time()-START_T)
                    else : 
                        time.sleep(3)
                        record_flag = 0
                        tele_time_flag = True
                        indy_stop_teleoperation()
                        isTeleoperating = False
                        indy_go_home()           
            else:
                if record_flag == 1:
                    record_flag = 0
                    tele_time_flag = True
                    indy_stop_teleoperation()
                    isTeleoperating = False
                    indy_go_home()
                    df = pd.DataFrame(data)
                    # print(len(data))
                    # df.to_csv("teleoperation_button.csv", index = False)
                    # print('record finish')
                    
        # sleep_time = interval - (time.time() - loopStart) - 0.0005
        # if sleep_time > 0:
        #     time.sleep(sleep_time)
        # else:
        #     print("update loop time exceeded")

        operation_time = time.time()-start_time
        if operation_time-operation_time_save > 1.0:
            operation_time_save = operation_time

    except Exception as e:
        print("error")
        print(e)
        indy_stop_teleoperation()
        isTeleoperating = False
        
    