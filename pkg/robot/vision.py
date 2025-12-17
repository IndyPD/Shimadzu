from .interfaces.indyeye_socket_client import IndyEyeSocketClient as IndyEyeClient
import numpy as np
import math

vision_ip = "192.168.0.6"
vision_port = 10511

def pos_to_transform(p):
    xyz = p[:3]
    uvw = p[3:]
    transform_matrix = np.identity(4)
    transform_matrix[:3, :3] = euler_to_rotm(uvw)
    transform_matrix[:3, 3] = xyz[:]
    return transform_matrix
def euler_to_rotm(uvw):
    rx = uvw[0]
    ry = uvw[1]
    rz = uvw[2]
    return np.matmul(np.matmul(rot_axis(3, rz), rot_axis(2, ry)), rot_axis(1, rx))
def rot_axis(axis, degree):
    th = math.radians(degree)
    if axis == 1:
        rot_matrix = np.asarray([[1, 0, 0], [0, math.cos(th), -math.sin(th)], [0, math.sin(th), math.cos(th)]])
    elif axis == 2:
        rot_matrix = np.asarray([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
    elif axis == 3:
        rot_matrix = np.asarray([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    else:
        rot_matrix = np.identity
    return rot_matrix
def transform_to_pos(transform_matrix):
    p = [0, 0, 0, 0, 0, 0]
    p[:3] = transform_matrix[:3, 3]
    p[3:] = list(rotm_to_euler(transform_matrix[:3, :3]))
    return p
def rotm_to_euler(rot_matrix):
    sy = math.sqrt(rot_matrix[0, 0] ** 2 + rot_matrix[1, 0] ** 2)

    if sy > 0.000001:
        u = math.degrees(math.atan2(rot_matrix[2, 1], rot_matrix[2, 2]))
        v = math.degrees(math.atan2(-rot_matrix[2, 0], sy))
        w = math.degrees(math.atan2(rot_matrix[1, 0], rot_matrix[0, 0]))
    else:
        u = math.degrees(math.atan2(-rot_matrix[1, 2], rot_matrix[1, 1]))
        v = math.degrees(math.atan2(-rot_matrix[2, 0], sy))
        w = 0

    return np.asarray([u, v, w])

def detect_position(control_data,robot_ip):
    
    indyeye_client = IndyEyeClient(vision_ip, vision_port)
    task_pos = pos_to_transform(control_data['p'])  # Trt (mm)
    ref_frame = pos_to_transform(control_data['ref_frame'])  # Tbr (mm)
    tool_frame = pos_to_transform(control_data['tool_frame'])
    robot_pos = np.matmul(np.matmul(ref_frame, task_pos), np.linalg.inv(tool_frame))
    robot_pos[:3, 3] /= 1000  # convert to m
    robot_pos = transform_to_pos(robot_pos)

    frame, cls, detected, passed, msg = indyeye_client.detect_by_object_name(id=0, cls=1, pose_cmd=robot_pos, robot_ip=robot_ip)
    if frame is not None:
        frame[0] *= 1000  # convert to mm
        frame[1] *= 1000  # convert to mm
        frame[2] *= 1000  # convert to mm
        
        frame = pos_to_transform(frame)  # Tbe (mm)
        # robot task pose on current frames: Trt = inv(Tbr) * Tbe * Tet
        frame = np.matmul(np.matmul(np.linalg.inv(ref_frame), frame), tool_frame)
        frame = transform_to_pos(frame)  # Trt (mm)
        return list(frame)
    else:
        return [0, 0, 0, 0, 0, 0]