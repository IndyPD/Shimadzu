import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'impl'))

import grpc
from concurrent import futures
from config_socket_client import ConfigSocketClient
from rtde_socket_client import RTDESocketClient
from control_socket_client import ControlSocketClient, control_data

from time import sleep
import numpy as np
from vive import triad_openvr
import time
import sys
import os
import math
import matplotlib.pyplot as plt
from scipy.spatial.transform import Rotation as R

robot_ip = "192.168.0.144"
DEVICE_NAME = "controller_1"


config = ConfigSocketClient(robot_ip)
control = ControlSocketClient(robot_ip)
rtde = RTDESocketClient(robot_ip)

def reset_and_go_home():
    print("### Reset 후 home position으로 이동합니다.")
    control.Recover()
    sleep(2)
    control.MoveJ(config.GetHomePos()['jpos'])
    sleep(2)
    
def task_move_by(relative_displacement):
    control.MoveL(np.multiply(1000, relative_displacement).tolist(), base_type=control_data.RELATIVE_TASK)
    sleep(2.5)
    
def get_tracker_position():
    # pos = []
    # for i in range(50):
    #     while True:
    #         this_pos = device.get_pose_euler()
    #         if this_pos != None:
    #             pos.append(device.get_pose_euler())
    #             break
    #         else:
    #             print("err")
    #             sleep(0.05)
    # pos = np.mean(np.array(pos),axis=0)
    # sleep(1)
    # return pos
    pos = []
    for i in range(50):
        pos.append(device.get_pose_euler())
    pos = np.mean(np.array(pos),axis=0)
    sleep(1)
    return pos

def get_displacement_vive(indy_disp):
    
    pre_tracker_pos = get_tracker_position()
    task_move_by(indy_disp)
    cur_trakcer_pos = get_tracker_position()
       
            
    return cur_trakcer_pos-pre_tracker_pos

v = triad_openvr.triad_openvr()
v.print_discovered_objects()
device = v.devices[DEVICE_NAME]

for i in range(200):
    v.devices[DEVICE_NAME].trigger_haptic_pulse()
    time.sleep(0.01)
    
a = 0.1 # meter
# a = 0.05 # meter
x_p = [ a, 0, 0, 0, 0, 0]
x_m = [-a, 0, 0, 0, 0, 0]
y_p = [ 0, a, 0, 0, 0, 0]
y_m = [ 0,-a, 0, 0, 0, 0]
z_p = [ 0, 0, a, 0, 0, 0]
z_m = [ 0, 0,-a, 0, 0, 0]
zero = [0]*6

time.sleep(5)

while True:
    print('### vive tracker를 base station에서 잘보이게, 6번 joint 아무곳에 흔들리지 않도록 고정해주세요')
    reset_and_go_home()
    print('### 로봇이 변의 길이가 %.2f m인 정육면체를 그리면서 움직입니다. 주변에 있는물체를 치워주세요' %a)
    displacement_vive = []
    displacement_indy = np.array([x_p, y_p, z_m, x_m, y_m, z_p])

    for disp in displacement_indy:
        displacement_vive.append(get_displacement_vive(disp))
    displacement_vive = np.array(displacement_vive)
    displacement_vive = displacement_vive[:, :3]
    displacement_vive = (displacement_vive[:3,:] - displacement_vive[3:,:])/2
    displacement_vive[2,:] = -displacement_vive[2,:]
    rot_mat = (displacement_vive/a).T
    print('indy to vive tracker rotation matrix')
    print(rot_mat)
    print('normalize with axis=1')
    print(np.linalg.norm(rot_mat,axis=1))
    
    check=np.linalg.norm(rot_mat,axis=1)
    
    if check[0]<0.95 or check[0]>1.05 or check[1]<0.95 or check[1]>1.05 or check[2]<0.95 or check[2]>1.05 :
    # if check[0]<0.99 or check[0]>1.01 or check[1]<0.99 or check[1]>1.01 or check[2]<0.99 or check[2]>1.01 :
        print("calibration 정확도를 위해서 다시 calibration 시작합니다.")
    else :
        break


np.savez('rot_mat.npz',R=rot_mat)

print("rot_mat 생성 완료")
print("callibration 종료")

