## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

import common_msgs_pb2 as common_data
import device_msgs_pb2 as device_data
import ethercat_msgs_pb2 as ecat_data

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

from .boot_socket_client import BootSocketClient as BootClient
from .config_socket_client import ConfigSocketClient as ConfigClient
from .control_socket_client import ControlSocketClient as ControlClient
from .device_socket_client import DeviceSocketClient as DeviceClient
from .rtde_socket_client import RTDESocketClient as RTDEClient
from .ethercat_client import EtherCATClient as EcatClient
from .linear_control_client import LinearControlClient as LinearClient

import math
import time
import threading
import socket
from struct import pack, unpack
import common as Common
from common.dcp_addr import *
import managers as Managers


class IndyDcpServicer(metaclass=Common.SingletonMeta):
    def __init__(self, boot_client: BootClient,
                 device_client: DeviceClient,
                 config_client: ConfigClient,
                 control_client: ControlClient,
                 rtde_client: RTDEClient,
                 ecat_client: EcatClient,
                 linear_client: LinearClient):
        super().__init__()
        self._boot_client = boot_client
        self._device_client = device_client
        self._config_client = config_client
        self._control_client = control_client
        self._rtde_client = rtde_client
        self._ecat_client = ecat_client
        self._linear_client = linear_client
        self._logger = Managers.LogManager()
        self._device = Managers.HRIManager()

        self._running = False
        self._server_frequency = 500  # Hz
        self._server_thread = threading.Thread(target=self._run_server, args=((1 / self._server_frequency),))
        self._task_move_type = 0
        self._joint_waypoint = []
        self._task_waypoint = []

        self._joint_speed = 3  # vel_level : 1 ~ 9
        self._task_speed = 3  # vel_level : 1 ~ 9
        self._joint_accel = 2
        self._task_accel = 2
        self._movec_angle = 0
        self._joint_time = 0.0
        self._joint_blend_radius = 0.0  # blend_radius: mm
        self._task_blend_radius = 0.0  # blend radius: mm
        self._movec_accel = 10
        self._movec_speed = 10
        self._joint_blend_type = 0  
        self._task_blend_type  = 0  

        self._tele_mode = 0  

        self._joint_waypoint_time = 0.0
        self._task_waypoint_time = 0.0

        self.tele_method_joint_absolute = 10
        self.tele_method_joint_relative = 11
        self.tele_method_task_relative = 1
        self.tele_method_task_absolute = 0
        self._wp_thread_lock = False

    ############################
    # Server Thread
    ############################
    def startServer(self) -> bool:
        if self._running:
            self._warn('An existed server is running')
            return False

        self._info('Start DCP Server...')
        device_info = None
        reduced_ratio = None

        start_time = time.time()
        while ((device_info is None)
               or (reduced_ratio is None)
        ):
            if time.time() - start_time > 30:  # timeout
                self._warn('Robot is not ready')
                return False

            time.sleep(1)
            boot_status = self._boot_client.GetBootStatus()
            if boot_status is not None and "control_on" in boot_status and boot_status["control_on"]:
                time.sleep(2)
                device_info = self._device_client.GetDeviceInfo()
                reduced_ratio = self._config_client.GetReducedRatio()

        Common.Config().configure_robot(robot_name=device_info['robot_name'], robot_dof=device_info['robot_dof'])
        Common.Config().configure_controller(use_safety_io=device_info['use_safety_io'],
                                             use_npad=device_info['use_npad'], use_indykey=device_info['use_indykey'],
                                             use_auto_mode=device_info['use_auto_mode'])
        Common.Config().configure_conversion(reduced_ratio=reduced_ratio['ratio'])

        # Create server thread
        self._running = True
        self._server_thread.start()
        return True

    def stopServer(self):
        self._running = False
        if self._server_thread.is_alive():
            self._server_thread.join()

    def _run_server(self, interval):
        _sock = []
        HOST = []
        PORT = 6066
        while self._running:
            _sock, HOST = self._bind_socket(_sock, HOST, PORT)
            for n in range(len(_sock)):
                try:
                    connection, client_address = _sock[n].accept()
                    self._info("Connection established with {}".format(client_address))
                    client_handler = threading.Thread(target=self._run_client,
                                                      args=(connection, str(client_address),))
                    client_handler.daemon = True
                    client_handler.start()

                except socket.timeout as ex:
                    # self._error('Connection failed from {}'.format(HOST[n]))
                    pass  # No new client

            time.sleep(interval)

    def _bind_socket(self, sock, HOST, PORT):
        NEW_HOST = Common.Utils.get_all_ip()
        if set(NEW_HOST) != set(HOST):
            host_to_connect = set(NEW_HOST) - set(HOST)
            host_to_disconnect = set(HOST) - set(NEW_HOST)

            if host_to_connect:
                self._info("Open DCP on address: ", host_to_connect)
                ip_list = list(host_to_connect)
                for i in range(len(ip_list)):
                    # _show_message(ip_list[i])
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.2)
                    # s.setblocking(0)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((ip_list[i], PORT))
                    s.listen(1)
                    sock.append(s)
                    HOST.append(ip_list[i])

            if host_to_disconnect:
                self._info("Close DCP on address: ", host_to_disconnect)
                ip_list = list(host_to_disconnect)
                for i in range(len(ip_list)):
                    # _show_message(ip_list[i])
                    index = HOST.index(ip_list[i])
                    sock[index].close()
                    sock.pop(index)
                    HOST.pop(index)

        return sock, HOST

    ############################
    # Client Thread
    ############################
    def _run_client(self, connection, client_address):
        self._info('Start client thread............')
        while self._running:
            try:
                data = connection.recv(1024)
                if data:
                    if len(data) < HEADER_CMD_SIZE:
                        self._debug("-------------- Missing header ")
                        self._debug("Received header: ", data)
                        self._debug("Header size: ", len(data))
                        self._response_data(CMD_ERROR, data[HEADER_INVOKE_ID[0]:HEADER_INVOKE_ID[1]], ERR_PARSE_FAILED)
                    else:
                        data_length = unpack('i', data[HEADER_DATA_LENGTH[0]:HEADER_DATA_LENGTH[1]])[0]
                        cmd = unpack('i', data[HEADER_CMD[0]:HEADER_CMD[1]])[0]

                        try:
                            self._debug('cmd id: ', cmd)
                            timeout = time.time()
                            while self._running:
                                if cmd == CMD_FOR_EXTENDED:
                                    if len(data) >= (HEADER_CMD_SIZE + data_length):
                                        ext_frame_length = unpack('i', data[HEADER_CMD_SIZE + 4:HEADER_CMD_SIZE + 8])[0]
                                        if len(data) == (HEADER_CMD_SIZE + data_length + ext_frame_length):
                                            break
                                else:
                                    if len(data) == (HEADER_CMD_SIZE + data_length):
                                        break

                                if (time.time() - timeout) > TIMEOUT:
                                    invoke_id = data[HEADER_INVOKE_ID[0]:HEADER_INVOKE_ID[1]]
                                    self._response_data(CMD_ERROR, invoke_id, ERR_CONNECTION_TIMEOUT)
                                    break

                                data += connection.recv(1024)

                            connection.sendall(self._command_analysis(data))
                            data = None

                        except Exception as ex:
                            self._warn("Exception: ", ex)
                            invoke_id = data[HEADER_INVOKE_ID[0]:HEADER_INVOKE_ID[1]]
                            self._response_data(CMD_ERROR, invoke_id, ERR_PROCESS_FAILED)
                            pass
                else:
                    self._info("Client disconnected from ", client_address)
                    break

            except Exception as ex:
                self._warn('Client disconnected due to ', ex)
                break
        self._info('Close client thread.........')
        connection.close()

    def _command_analysis(self, data):
        robot_name = data[HEADER_ROBOT_NAME[0]:HEADER_ROBOT_NAME[1]]
        step_info = data[HEADER_STEP_INFO[0]:HEADER_STEP_INFO[1]]
        # source_of_frame = data[HEADER_SOURCE_OF_FRAME[0]:HEADER_SOURCE_OF_FRAME[1]]
        invoke_id = data[HEADER_INVOKE_ID[0]:HEADER_INVOKE_ID[1]]
        data_length = unpack('i', data[HEADER_DATA_LENGTH[0]:HEADER_DATA_LENGTH[1]])[0]
        cmd_id = unpack('i', data[HEADER_CMD[0]:HEADER_CMD[1]])[0]

        """
        Check error
        """
        if robot_name[:len(Common.Config().ROBOT_MODEL)].decode("utf-8") != Common.Config().ROBOT_MODEL:
            # ERR_NO_MATCHED_ROBOT
            # _show_message("ERR_NO_MATCHED_ROBOT")
            self._error('ERR_NO_MATCHED_ROBOT')
            return self._response_data(CMD_ERROR, invoke_id, ERR_NO_MATCHED_ROBOT)
        elif step_info != STEP_INFO_byte:
            # ERR_NO_MATCHED_STEP
            # _show_message("ERR_NO_MATCHED_STEP")
            self._error("ERR_NO_MATCHED_STEP")
            return self._response_data(CMD_ERROR, invoke_id, ERR_NO_MATCHED_STEP)
        elif data_length > MAX_DATA_LENGTH:  # TODO: extended???
            # ERR_OVER_DATA_SIZE
            # _show_message("data length: ", data_length)
            self._error("data length: ", data_length)
            return self._response_data(CMD_ERROR, invoke_id, ERR_OVER_DATA_SIZE)

        """
        if no error => try to return value
        """
        # control_data = self._rtde_client.GetControlData()
        # motion_data = self._rtde_client.GetMotionData()
        # io_data = self._rtde_client.GetIOData()
        # servo_data = self._rtde_client.GetServoData()
        # program_data = self._rtde_client.GetProgramData()
        # violation_data = self._rtde_client.GetViolationData()

        if cmd_id == CMD_CHECK:
            return self._response_data(cmd_id, invoke_id)
        elif cmd_id == CMD_IS_ROBOT_RUNNING:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][0], '?')
        elif cmd_id == CMD_IS_READY:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][1], '?')
        elif cmd_id == CMD_IS_EMG:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][2], '?')
        elif cmd_id == CMD_IS_COLLIDED:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][3], '?')
        elif cmd_id == CMD_IS_ERR:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][4], '?')
        elif cmd_id == CMD_IS_BUSY:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][5], '?')
        elif cmd_id == CMD_IS_MOVE_FINISHED:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][6], '?')
        elif cmd_id == CMD_IS_HOME:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][7], '?')
        elif cmd_id == CMD_IS_ZERO:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][8], '?')
        elif cmd_id == CMD_IS_IN_RESETTING:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][9], '?')
        elif cmd_id == CMD_IS_DIRECT_TEACHING:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][10], '?')
        elif cmd_id == CMD_IS_TEACHING:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][11], '?')
        elif cmd_id == CMD_IS_PROGRAM_RUNNING:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][12], '?')
        elif cmd_id == CMD_IS_PROGRAM_PAUSED:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][13], '?')
        elif cmd_id == CMD_IS_CONTY_CONNECTED:
            return self._response_data(cmd_id, invoke_id, self._grpc_state_to_dcp_state()[0][14], '?')

        elif cmd_id == CMD_GET_DEFAULT_TCP:            
            control_data = self._rtde_client.GetControlData()
            return self._response_data(cmd_id, invoke_id, [i for i in control_data.tool_frame])

        elif cmd_id == CMD_GET_COMP_TCP:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)

        elif cmd_id == CMD_GET_REFFRAME:
            control_data = self._rtde_client.GetControlData()
            return self._response_data(cmd_id, invoke_id, [i for i in control_data.ref_frame])

        elif cmd_id == CMD_GET_COLLISION_LEVEL:
            return self._response_data(cmd_id, invoke_id, self._config_client.GetCollSensLevel()['level'])

        elif cmd_id == CMD_GET_JOINT_BOUNDARY:  # get joint speed
            return self._response_data(cmd_id, invoke_id, self._joint_speed)
        


        elif cmd_id == CMD_GET_TASK_BOUNDARY:  # get task speed
            return self._response_data(cmd_id, invoke_id, self._task_speed)

        elif cmd_id == CMD_GET_JOINT_ACCELERATION:  # get joint accel
            return self._response_data(cmd_id, invoke_id, self._joint_accel)

        elif cmd_id == CMD_GET_TASK_ACCELERATION:  # get task accel
            return self._response_data(cmd_id, invoke_id, self._task_accel)

        elif cmd_id == CMD_GET_JOINT_WTIME:
            return self._response_data(cmd_id, invoke_id, self._joint_waypoint_time)

        elif cmd_id == CMD_GET_TASK_WTIME:
            return self._response_data(cmd_id, invoke_id, self._task_waypoint_time)

        elif cmd_id == CMD_GET_TASK_CMODE:
            return self._response_data(cmd_id, invoke_id, self._rtde_client.GetControlData()['op_state'])

        elif cmd_id == CMD_GET_JOINT_BLEND_RADIUS:
            return self._response_data(cmd_id, invoke_id, self._joint_blend_radius)

        elif cmd_id == CMD_GET_TASK_BLEND_RADIUS:
            return self._response_data(cmd_id, invoke_id, self._task_blend_radius)

        elif cmd_id == CMD_GET_RUNNING_TIME:
            control_data = self._rtde_client.GetControlData()
            # h, m, s = control_data.running_time.split(':')
            h = control_data['running_hours']
            m = control_data['running_mins']
            s = control_data['running_secs']
            # time_to_seconds = float(h[:-1]) * 3600 + float(m[:-1]) * 60 + float(s[:-1])  # get all except last char
            time_to_seconds = float(h) * 3600 + float(m) * 60 + float(s)
            return self._response_data(cmd_id, invoke_id, time_to_seconds)

        elif cmd_id == CMD_GET_CMODE:
            return self._response_data(cmd_id, invoke_id, self._rtde_client.GetControlData()['op_state'])

        elif cmd_id == CMD_GET_JOINT_STATE:
            servo_data = self._rtde_client.GetServoData()
            servo_states = servo_data['servo_actives'] + servo_data['brake_actives']
            return self._response_data(cmd_id, invoke_id, servo_states)

        elif cmd_id == CMD_GET_JOINT_POSITION:
            control_data = self._rtde_client.GetControlData()
            return self._response_data(cmd_id, invoke_id, control_data['q'])

        elif cmd_id == CMD_GET_JOINT_VELOCITY:
            control_data = self._rtde_client.GetControlData()
            return self._response_data(cmd_id, invoke_id, control_data['qdot'])

        elif cmd_id == CMD_GET_TASK_POSITION:
            task_pos = self._rtde_client.GetControlData()['p']
            # convert mm to m
            for i in range(3):
                task_pos[i] = task_pos[i] / 1000
            return self._response_data(cmd_id, invoke_id, task_pos)

        elif cmd_id == CMD_GET_TASK_VELOCITY:
            control_data = self._rtde_client.GetControlData()
            return self._response_data(cmd_id, invoke_id, control_data['pdot'])

        elif cmd_id == CMD_GET_TORQUE:
            servo_data = self._rtde_client.GetServoData()
            return self._response_data(cmd_id, invoke_id, servo_data['currents'])

        elif cmd_id == CMD_GET_INV_KIN:
            unpack_type = str(Common.Config().ROBOT_DOF + 6) + 'd'  # dof + task space(6)
            val = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            get_inverse_kinematic = self._control_client.Calculate_IK(init_jpos=val[:len(val) // 2],
                                                                      tpos=val[len(val) // 2:])
            return self._response_data(cmd_id, invoke_id, [i for i in get_inverse_kinematic['jpos']])

        elif cmd_id == CMD_GET_TORQUE_JTS:
            data = self._rtde_client.GetControlState()
            return self._response_data(cmd_id, invoke_id, data['tau_jts'])

        elif cmd_id == CMD_GET_TORQUE_JTS_RAW1:
            data = self._rtde_client.GetControlState()
            return self._response_data(cmd_id, invoke_id, data['tau_jts_raw1'])

        elif cmd_id == CMD_GET_TORQUE_JTS_RAW2:
            data = self._rtde_client.GetControlState()
            return self._response_data(cmd_id, invoke_id, data['tau_jts_raw2'])

        elif cmd_id == CMD_GET_LAST_EMG_INFO:
            violation_data = self._rtde_client.GetViolationData()
            # _show_message(data=violation_data)
            event_list = [violation_data['violation_code'],
                          violation_data['j_index'], violation_data['i_args'][0], 0,
                          violation_data['f_args'][0], 0.0, 0.0]
            return self._response_data(cmd_id, invoke_id, event_list)

        elif cmd_id == CMD_GET_SMART_DI:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['di'][idx])

        elif cmd_id == CMD_GET_SMART_DIS:
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['di'])
        
        elif cmd_id == CMD_GET_INT_VAL:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            int_data = self._control_client.GetIntVariable()
            for i in int_data:
                if i['addr'] ==idx:
                    return self._response_data(cmd_id, invoke_id, int(i['value']))
            return self._response_data(cmd_id, invoke_id, 0)
        
        elif cmd_id == CMD_GET_FLOAT_VAL:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            float_data = self._control_client.GetFloatVariable()
            for i in float_data:
                if i['addr'] ==idx:
                    return self._response_data(cmd_id, invoke_id, float(i['value']))
            return self._response_data(cmd_id, invoke_id, 0.0)
        
        elif cmd_id == CMD_GET_BOOL_VAL:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            bool_data = self._control_client.GetBoolVariable()
            for i in bool_data:
                if i['addr'] ==idx:
                    return self._response_data(cmd_id, invoke_id, bool(i['value']))
            return self._response_data(cmd_id, invoke_id, 0)


        elif cmd_id == CMD_GET_SERVO_NUM:
            print('CMD_GET_SERVO_NUM: ', data)
            return self._response_data(cmd_id, invoke_id, self._ecat_client.get_slave_type_num().num_servo)

        elif cmd_id == CMD_GET_SERVO_TX: 
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]     
            raw_data = self._ecat_client.get_servo_tx_raw(idx)
            return self._response_data(cmd_id, invoke_id, [raw_data.statusWord,raw_data.modeOpDisp,raw_data.actualPosition,raw_data.actualVelocity, raw_data.actualTorque])

        elif cmd_id == CMD_GET_SERVO_RX:            
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id, self._ecat_client.get_servo_rx(idx))

        elif cmd_id == CMD_SET_SERVO_RX:
            rx_data = list(unpack('6I', data[HEADER_CMD_SIZE:len(data)]))
            print("servo_idx: " ,rx_data[0])
            print("set_rx: " ,rx_data[1:6])
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_GET_INDY7_SERBO_TX:
            indy7_tx_data =[]
            for i in (0,6):
                indy7_tx_data+= self._ecat_client.get_servo_tx(i)
            return self._response_data(cmd_id, invoke_id,indy7_tx_data)
        
        elif cmd_id == CMD_GET_INDY7_SERBO_RX:
            indy7_rx_data =[]
            for i in (0,6):
                indy7_rx_data+= self._ecat_client.get_servo_rx(i)
            return self._response_data(cmd_id, invoke_id,indy7_rx_data)
        
        elif cmd_id == CMD_SET_INDY7_SERBO_RX:
            rx_data = list(unpack('30I', data[HEADER_CMD_SIZE:len(data)]))
            for i in range(6):
                self._ecat_client.set_servo_rx(i,rx_data[i*5:(i+1)*5])           
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_ACTIVE_SDK:
            receive_date = list(unpack('74b', data[HEADER_CMD_SIZE:HEADER_CMD_SIZE+74]))
            expire_date = ''.join(chr(date) for date in receive_date[64:74])
            license_key = ''.join(chr(date) for date in receive_date[0:64])
            self._control_client.ActivateIndySDK(license_key,expire_date)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_CUSTOM_CONTROL_MOD:
            control_mod = list(unpack('i', data[HEADER_CMD_SIZE:len(data)]))
            self._control_client.SetCustomControlMode(control_mod)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_GET_CUSTOM_CONTROL_MOD:
            return self._response_data(cmd_id, invoke_id, self._control_client.GetCustomControlMode())

        elif cmd_id == CMD_GET_TPOS_VAL:
            tpos_data = self._control_client.GetTPosVariable()
            return_data = []
            for i in tpos_data:
                return_data.append(float(i['addr']))
                return_data.extend((i['tpos']))
            return self._response_data(cmd_id, invoke_id, return_data)

        
        elif cmd_id == CMD_GET_JPOS_VAL:
            int_data = self._control_client.GetJPosVariable()
            return_data = []
            for i in int_data:
                return_data.append(float(i['addr']))
                return_data.extend((i['jpos']))
            return self._response_data(cmd_id, invoke_id, return_data)

        elif cmd_id == CMD_SET_SMART_DO:
            idx = unpack('I', data[HEADER_CMD_SIZE:(len(data) - 1)])[0]
            value = unpack('?', data[(len(data) - 1):len(data)])[0]
            result = self._device_client.SetDO([dict(address=idx, state=value)])
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_SMART_DOS:  # 32 DOs
            values = list(unpack('32?', data[HEADER_CMD_SIZE:len(data)]))
            signals = [dict(address=i, state=values[i]) for i in range(32)]
            result = self._device_client.SetDO(signals)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_GET_SMART_AI:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['ai'][idx])

        elif cmd_id == CMD_SET_SMART_AO:
            smart_ao = list(unpack('2I', data[HEADER_CMD_SIZE:len(data)]))
            # result = self._robot_client.set_ao([(smart_ao[0], smart_ao[1])])
            signals = [dict(address=smart_ao[0], voltage=smart_ao[1])]
            result = self._device_client.SetAO(signals)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_GET_SMART_DO:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['do'][idx])

        elif cmd_id == CMD_GET_SMART_DOS:
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['do'])

        elif cmd_id == CMD_GET_SMART_AO:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            io_data = self._rtde_client.GetIOData()
            return self._response_data(cmd_id, invoke_id, io_data['ao'][idx])

        elif cmd_id == CMD_SET_ENDTOOL_DO:  # 5bytes
            idx = unpack('I', data[HEADER_CMD_SIZE:(len(data) - 1)])[0]
            value = unpack('?', data[(len(data) - 1):len(data)])[0]
            # result = self._robot_client.set_end_do([(idx, value)])
            if idx == 2:
                port = 'A'
            elif idx == 1:
                port = 'B'
            else:
                port = 'C'
            result = self._device_client.SetEndDO([dict(port=port, states=[value])])
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_GET_ENDTOOL_DO:
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            end_do = self._rtde_client.GetIOData()['end_do']
            return self._response_data(cmd_id, invoke_id, end_do[0]['states'][idx])
            # return self._response_data(cmd_id, invoke_id, io_data['end_do'][idx])

        elif cmd_id == CMD_GET_ENDTOOL_DI:
            end_di = self._rtde_client.GetIOData()['end_di']
            if end_do[0]['port']=='C':
                endtool_di_data = end_di[0]['states']
            else:
                endtool_di_data = end_di[0]['states']+end_do[1]['states']
            return self._response_data(cmd_id, invoke_id, endtool_di_data)

        elif cmd_id == CMD_GET_ENDTOOL_AI:
            end_ai = self._rtde_client.GetIOData()['end_ai']
            endtool_ai_data = [end_ai[0]['voltage'],end_ai[1]['voltage']]

            return self._response_data(cmd_id, invoke_id, endtool_ai_data)

        elif cmd_id == CMD_GET_EXTIO_FTCAN_ROBOT_RAW:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)
        elif cmd_id == CMD_GET_EXTIO_FTCAN_ROBOT_TRANS:            
            return self._response_data(CMD_ERROR, invoke_id, self._device_client.GetFTSensorData)
        elif cmd_id == CMD_GET_EXTIO_FTCAN_CB_RAW:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)
        elif cmd_id == CMD_GET_EXTIO_FTCAN_CB_TRANS:
            return self._response_data(CMD_ERROR, invoke_id, self._device_client.GetFTSensorData)

        elif cmd_id == CMD_WRITE_DIRECT_VARIABLE or cmd_id == CMD_WRITE_DIRECT_VARIABLES:
            _variable_request = data[HEADER_CMD_SIZE:len(data)]
            _type = unpack('i', _variable_request[:4])[0]
            _addr = unpack('i', _variable_request[4:8])[0]
            _data_length = unpack('i', _variable_request[8:12])[0] if cmd_id == CMD_WRITE_DIRECT_VARIABLES else 1

            # if cmd_id == CMD_WRITE_DIRECT_VARIABLES:
            #     _data_length = unpack('i', _variable_request[8:12])[0]
            # else:
            #     _data_length = 1

            # _show_message("type: ", _type)
            # _show_message("address: ", _addr)
            # _show_message("data length: ", _data_length)
            # _show_message("value: ", _value)
            if _addr < 0 or (_addr + _data_length) > (DIRECT_VARIABLE_ADDRESS_LIMIT + 1):
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_INVALID_ADDRESS)
            if _data_length > NUMBER_OF_ACCESS_DIRECT_VARIABLE:
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_REFNUM_LIMIT)

            if _type == DIRECT_VAR_TYPE_BYTE:
                if cmd_id == CMD_WRITE_DIRECT_VARIABLES:
                    _value = list(unpack((str(_data_length) + '?'), _variable_request[12:len(_variable_request)]))
                else:
                    _value = unpack('?', _variable_request[8:len(_variable_request)])
                # result = [self._m_variable.set_bool_variable(_addr + i, _value[i]) for i in range(_data_length)]
                m_vars = [dict(addr=_addr + i, value=_value[i]) for i in range(_data_length)]
                result = self._control_client.SetBoolVariable(m_vars)
                return self._response_data(cmd_id, invoke_id)

            elif _type in [DIRECT_VAR_TYPE_WORD, DIRECT_VAR_TYPE_DWORD, DIRECT_VAR_TYPE_LWORD]:
                # TODO: 3 types int but same address
                if _type == DIRECT_VAR_TYPE_WORD:
                    unpack_type = 'h'
                elif _type == DIRECT_VAR_TYPE_DWORD:
                    unpack_type = 'i'
                else:
                    unpack_type = 'q'
                # unpack_type = 'q'
                if cmd_id == CMD_WRITE_DIRECT_VARIABLES:
                    _value = list(
                        unpack((str(_data_length) + unpack_type), _variable_request[12:len(_variable_request)]))
                else:
                    _value = unpack(unpack_type, _variable_request[8:len(_variable_request)])
                i_vars = [dict(addr=_addr + i, value=_value[i]) for i in range(_data_length)]
                result = self._control_client.SetIntVariable(i_vars)
                return self._response_data(cmd_id, invoke_id)

            elif _type in [DIRECT_VAR_TYPE_FLOAT, DIRECT_VAR_TYPE_DFLOAT]:
                # TODO: float and double => same address
                unpack_type = 'f' if _type == DIRECT_VAR_TYPE_FLOAT else 'd'
                if cmd_id == CMD_WRITE_DIRECT_VARIABLES:
                    _value = list(
                        unpack((str(_data_length) + unpack_type), _variable_request[12:len(_variable_request)]))
                else:
                    _value = unpack(unpack_type, _variable_request[8:len(_variable_request)])
                # result = [self._m_variable.set_float_variable(_addr + i, _value[i]) for i in range(_data_length)]
                f_vars = [dict(addr=_addr + i, value=_value[i]) for i in range(_data_length)]
                result = self._control_client.SetFloatVariable(f_vars)
                return self._response_data(cmd_id, invoke_id)

            elif _type == DIRECT_VAR_TYPE_MODBUS_REG:
                if cmd_id == CMD_WRITE_DIRECT_VARIABLES:
                    _value = list(unpack((str(_data_length) + 'H'), _variable_request[12:len(_variable_request)]))
                else:
                    _value = unpack('H', _variable_request[8:len(_variable_request)])
                # result = [self._m_variable.set_modbus_variable(_addr + i, _value[i]) for i in range(_data_length)]
                # _show_message(_value)
                # _show_message(_addr)
                # for i in range(_data_length):
                #     self._m_variable.set_modbus_variable(_addr + i, _value[i])
                m_vars = [dict(name='dcp_' + str(i), addr=_addr + i, value=_value[i]) for i in range(_data_length)]
                result = self._control_client.SetModbusVariable(m_vars)
                return self._response_data(cmd_id, invoke_id)

            else:
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_INVALID_FORMAT)

        elif cmd_id == CMD_READ_DIRECT_VARIABLE or cmd_id == CMD_READ_DIRECT_VARIABLES:
            _variable_request = data[HEADER_CMD_SIZE:len(data)]
            _type = unpack('i', _variable_request[:4])[0]
            _addr = unpack('i', _variable_request[4:8])[0]
            # if cmd_id == CMD_READ_DIRECT_VARIABLES:
            #     _data_length = unpack('i', _variable_request[-4:])[0]  # last 4 items in array
            # else:
            #     _data_length = 1
            _data_length = unpack('i', _variable_request[-4:])[0] if cmd_id == CMD_READ_DIRECT_VARIABLES else 1

            # _show_message("type: ", _type)
            # _show_message("address: ", _addr)
            # _show_message("data length: ", _data_length)
            if _addr < 0 or (_addr + _data_length) > (DIRECT_VARIABLE_ADDRESS_LIMIT + 1):
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_INVALID_ADDRESS)
            if _data_length > NUMBER_OF_ACCESS_DIRECT_VARIABLE:
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_REFNUM_LIMIT)

            if _type == DIRECT_VAR_TYPE_BYTE:
                b_vars = self._control_client.GetBoolVariable()
                _data = []
                for b_var in b_vars:
                    if b_var['addr'] in range(_addr, _addr + _data_length):
                        _data.append(b_var['value'])
                return self._response_data(cmd_id, invoke_id, (_data[0] if _data_length == 1 else _data), '?')
            elif _type in [DIRECT_VAR_TYPE_WORD, DIRECT_VAR_TYPE_DWORD, DIRECT_VAR_TYPE_LWORD]:
                i_vars = self._control_client.GetIntVariable()
                _data = []
                for i_var in i_vars:
                    if i_var['addr'] in range(_addr, _addr + _data_length):
                        _data.append(int(i_var['value']))
                if _type == DIRECT_VAR_TYPE_WORD:
                    pack_type = 'h'
                elif _type == DIRECT_VAR_TYPE_DWORD:
                    pack_type = 'i'
                else:
                    pack_type = 'q'
                # _data = [self._m_variable.get_int_variable(_addr + i) for i in range(_data_length)]
                return self._response_data(cmd_id, invoke_id, (_data[0] if _data_length == 1 else _data), pack_type)
            elif _type in [DIRECT_VAR_TYPE_FLOAT, DIRECT_VAR_TYPE_DFLOAT]:
                f_vars = self._control_client.GetFloatVariable()
                _data = []
                for f_var in f_vars:
                    if f_var['addr'] in range(_addr, _addr + _data_length):
                        _data.append(f_var['value'])
                pack_type = 'f' if _type == DIRECT_VAR_TYPE_FLOAT else 'd'
                return self._response_data(cmd_id, invoke_id, (_data[0] if _data_length == 1 else _data), pack_type)
            elif _type == DIRECT_VAR_TYPE_MODBUS_REG:
                m_vars = self._control_client.GetModbusVariable()
                _data = []
                for m_var in m_vars:
                    if m_var['addr'] in range(_addr, _addr + _data_length):
                        _data.append(m_var['value'])
                # _data = [self._m_variable.get_modbus_variable(_addr + i) for i in range(_data_length)]
                return self._response_data(cmd_id, invoke_id, (_data[0] if _data_length == 1 else _data), 'H')
            else:
                return self._response_data(CMD_ERROR, invoke_id, ERR_DIRECT_VARIABLE_INVALID_FORMAT)

        elif cmd_id == CMD_EMERGENCY_STOP:
            # result = self._robot_client.stop_motion(stop_category=common.common_msgs.STOP_CAT_IMMEDIATE_BRAKE)
            result = self._control_client.StopMotion(stop_category=ControlClient.STOP_IMMEDIATE_BRAKE)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_RESET_[Robot]
            # result = self._robot_client.recover()  # reboot()
            result = self._control_client.Recover()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_SERVO:
            unpack_type = str(Common.Config().ROBOT_DOF) + '?'
            servo_state = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            value = False if not all(servo_state) else True  # if not all value equal to True
            # _show_message(value)
            result = self._device_client.SetServoAll(enable=value)
            return self._response_data(cmd_id, invoke_id)


        elif cmd_id == CMD_SET_BRAKE:
            unpack_type = str(Common.Config().ROBOT_DOF) + '?'
            brake_state = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            result = self._device_client.SetBrakes(brake_state_list=brake_state)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_STOP:
            result = self._control_client.StopMotion(stop_category=ControlClient.STOP_SMOOTH_ONLY)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_MOVE:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)

        elif cmd_id == CMD_MOVE_HOME:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            control_data = self._rtde_client.GetControlData()
            if control_data['op_state'] == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            home_pos = self._config_client.GetHomePos()['jpos']
            # result = self._robot_client.movej(jpos=home_pos, vel_level=self._joint_speed)
            if math.isclose(self._joint_blend_radius, 0.0, rel_tol=1e-3):  # default 1e-9
                _blending_type = ControlClient.NO_BLENDING
            else:
                _blending_type = ControlClient.DUPLICATE_BLENDING

            vel_level = self._joint_speed
            acc_level = self._joint_accel

            vel_ratio = Common.Config().to_vel_ratio(vel_level)
            acc_ratio = Common.Config().to_acc_ratio(acc_level)

            jstart = control_data['q']
            result = self._control_client.MoveJ(jstart=jstart, jtarget=home_pos,
                                                blending_type=_blending_type,
                                                base_type=ControlClient.ABSOLUTE_JOINT,
                                                blending_radius=self._joint_blend_radius,
                                                vel_ratio=vel_ratio,
                                                acc_ratio=acc_ratio)

            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_MOVE_ZERO:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            control_data = self._rtde_client.GetControlData()
            if control_data['op_state'] == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            zero_pos = [0] * Common.Config().ROBOT_DOF
            # result = self._robot_client.movej(jpos=zero_pos, vel_level=self._joint_speed)
            if math.isclose(self._joint_blend_radius, 0.0, rel_tol=1e-3):  # default 1e-9
                _blending_type = ControlClient.NO_BLENDING
            else:
                _blending_type = ControlClient.DUPLICATE_BLENDING

            vel_level = self._joint_speed
            acc_level = self._joint_accel

            vel_ratio = Common.Config().to_vel_ratio(vel_level)
            acc_ratio = Common.Config().to_acc_ratio(acc_level)

            jstart = control_data['q']
            result = self._control_client.MoveJ(jstart=jstart, jtarget=zero_pos,
                                                blending_type=_blending_type,
                                                base_type=ControlClient.ABSOLUTE_JOINT,
                                                blending_radius=self._joint_blend_radius,
                                                vel_ratio=vel_ratio,
                                                acc_ratio=acc_ratio)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_JOINT_MOVE_TO or cmd_id == CMD_JOINT_MOVE_BY:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            control_data = self._rtde_client.GetControlData()
            if control_data['op_state'] == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            unpack_type = str(Common.Config().ROBOT_DOF) + 'd'
            joint_pos = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            if cmd_id == CMD_JOINT_MOVE_TO:
                _base_type = ControlClient.ABSOLUTE_JOINT
            else:
                _base_type = ControlClient.RELATIVE_JOINT

            # if math.isclose(self._joint_blend_radius, 0.0, rel_tol=1e-3):  # default 1e-9
                
            # else:
            #     _blending_type = ControlClient.DUPLICATE_BLENDING
            _blending_type = self._joint_blend_type
            vel_level = self._joint_speed
            acc_level = self._joint_accel

            vel_ratio = Common.Config().to_vel_ratio(vel_level)
            acc_ratio = Common.Config().to_acc_ratio(acc_level)

            jstart = control_data['q']
            if self._joint_waypoint_time == 0:
                result = self._control_client.MoveJ(jstart=jstart, jtarget=joint_pos,
                                                blending_type=_blending_type,
                                                base_type=_base_type,
                                                blending_radius=self._joint_blend_radius,
                                                vel_ratio=vel_ratio,
                                                acc_ratio=acc_ratio)
            else:
                result = self._control_client.MoveJT(jstart=jstart, jtarget=joint_pos,
                                                blending_type=_blending_type,
                                                base_type=_base_type,
                                                blending_radius=self._joint_blend_radius,
                                                move_time= self._joint_waypoint_time)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_TASK_MOVE_TO or cmd_id == CMD_TASK_MOVE_BY:  # or cmd_id == CMD_TASK_MOVE_VELOCITY:
            # if cmd_id != CMD_TASK_MOVE_VELOCITY and self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            control_data = self._rtde_client.GetControlData()
            if control_data['op_state'] == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            # unpack_type = str(Common.Config().ROBOT_DOF) + 'd'
            # task_pos = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            task_pos = list(unpack('6d', data[HEADER_CMD_SIZE:len(data)]))

            if (self._task_move_type):
                _base_type = ControlClient.TCP_TASK
            elif cmd_id == CMD_TASK_MOVE_TO:
                _base_type = ControlClient.ABSOLUTE_TASK
            # elif cmd_id == CMD_TASK_MOVE_BY:
            else:
                _base_type = ControlClient.RELATIVE_TASK            
            # else:
            #     _base_type = common.common_msgs.TASK_BASE_TYPE_TCP

            # if math.isclose(self._task_blend_radius, 0.0, rel_tol=1e-3):  # default 1e-9
            #     _blending_type = ControlClient.NO_BLENDING
            # else:
            #     _blending_type = ControlClient.DUPLICATE_BLENDING
            _blending_type = self._task_blend_type
            # if cmd_id == CMD_TASK_MOVE_VELOCITY:
            #     _blending_type = common.common_msgs.BLENDING_TYPE_OVERRIDE

            vel_level = self._task_speed
            acc_level = self._task_accel

            vel_ratio = Common.Config().to_vel_ratio(vel_level)
            acc_ratio = Common.Config().to_acc_ratio(acc_level)

            tstart = control_data['p']
            result = self._control_client.MoveL(tstart=tstart, ttarget=task_pos,
                                                blending_type=_blending_type,
                                                blending_radius=self._task_blend_radius,
                                                base_type=_base_type,
                                                vel_ratio=vel_ratio,
                                                acc_ratio=acc_ratio)
            return self._response_data(cmd_id, invoke_id)


        elif cmd_id == CMD_MOVE_C :
            control_data = self._rtde_client.GetControlData()
            if control_data['op_state'] == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)            
            task_pos = list(unpack('12d', data[HEADER_CMD_SIZE:len(data)]))
            # convert m to mm            
            _blending_type = self._task_blend_type

            tpos_0 = task_pos[:6]
            tpos_1 = task_pos[6:12]
            vel_level = self._movec_speed
            acc_level = self._movec_accel
            if cmd_id == CMD_TASK_MOVE_TO:
                _base_type = ControlClient.ABSOLUTE_TASK
            # elif cmd_id == CMD_TASK_MOVE_BY:
            else:
                _base_type = ControlClient.RELATIVE_TASK
            tstart = control_data['p']
            result = self._control_client.MoveC(tstart=tstart, tpos0=tpos_0,
                                                tpos1=tpos_1,
                                                blending_type=0,
                                                blending_radius=0,
                                                base_type=0,
                                                vel_ratio=vel_level,
                                                acc_ratio=acc_level,
                                                angle= self._movec_angle)
            return self._response_data(cmd_id, invoke_id)

        # elif cmd_id == CMD_JOG_JOINT:  # deg
        #     unpack_type = str(Common.Config().ROBOT_DOF) + 'd'
        #     joint_pos = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
        #     result = self._robot_client.jogj_ros(3, joint_pos)
        #     return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_START_CURRENT_PROGRAM:
            # result = self._program_manager.start_program()
            self._control_client.PlayProgram(prog_name='', prog_idx=-1)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_PAUSE_CURRENT_PROGRAM:
            # self._program_manager.control_request = self._program_manager.CTRL_PAUSE
            self._control_client.PauseProgram()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_RESUME_CURRENT_PROGRAM:
            self._control_client.ResumeProgram()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_STOP_CURRENT_PROGRAM:
            # self._program_manager.control_request = self._program_manager.CTRL_STOP
            self._control_client.StopProgram()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_START_DEFAULT_PROGRAM:
            on_start_program_index = self._config_client.GetOnStartProgramConfig()
            self._control_client.PlayProgram(prog_name='', prog_idx=on_start_program_index['index'])
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_REGISTER_DEFAULT_PROGRAM_IDX:
            auto_run = self._config_client.GetOnStartProgramConfig()['auto_run']
            idx = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            self._config_client.SetOnStartProgramConfig(auto_run=auto_run, index=idx)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_GET_REGISTERED_DEFAULT_PROGRAM_IDX:
            return self._response_data(cmd_id, invoke_id, self._config_client.GetOnStartProgramConfig()['index'])

        elif cmd_id == CMD_CHANGE_DIRECT_TEACHING:
            self._control_client.SetDirectTeaching(enable=True)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_FINISH_DIRECT_TEACHING:
            self._control_client.SetDirectTeaching(enable=False)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_JOINT_PUSH_BACK_WAYPOINT_SET:
            unpack_type = str(Common.Config().ROBOT_DOF + 2) + 'd'  # wp-type, blend_radius, q
            # wp_type: 0 (absolute), 1 (relative joint)
            # blend_radius: mm
            self._joint_waypoint.append(list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)])))
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_JOINT_POP_BACK_WAYPOINT_SET:
            if self._joint_waypoint:
                self._joint_waypoint.pop()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_JOINT_CLEAR_WAYPOINT_SET:
            self._joint_waypoint.clear()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_JOINT_EXECUTE_WAYPOINT_SET and not self._wp_thread_lock:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            op_state = self._rtde_client.GetControlData()['op_state']
            if op_state == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            self._wp_thread_lock = True
            conditions = list(unpack('2d', data[HEADER_CMD_SIZE:len(data)]))
            # _show_message(conditions)
            # _show_message("DEMO DCP Only run joint waypoint one time")
            # _show_message("DEMO DCP Only run joint waypoint one time")
            waypoint_execute = threading.Thread(target=self._joint_waypoint_execute)
            waypoint_execute.daemon = True
            waypoint_execute.start()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_TASK_PUSH_BACK_WAYPOINT_SET:
            unpack_type = str(Common.Config().ROBOT_DOF + 2) + 'd'  # wp-type, blend_radius, q
            # wp_type: 0 (absolute), 1 (relative joint)
            # task_base = 0 (base reference), 1 (base tcp)
            # blend radius: mm
            task_wp = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            # convert m to mm
            for i in range(3):
                task_wp[i + 2] = task_wp[i + 2] * 1000
            self._task_waypoint.append(task_wp)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_TASK_POP_BACK_WAYPOINT_SET:
            if self._task_waypoint:
                self._task_waypoint.pop()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_TASK_CLEAR_WAYPOINT_SET:
            self._task_waypoint.clear()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_TASK_EXECUTE_WAYPOINT_SET and not self._wp_thread_lock:
            # if self._robot_client.get_control_state_data().state == common.common_msgs.OP_MOVING:
            #     return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)
            op_state = self._rtde_client.GetControlData()['op_state']
            if op_state == common_data.OpState.OP_MOVING:
                return self._response_data(CMD_ERROR, invoke_id, ERR_ROBOT_MOVING_STATE)

            self._wp_thread_lock = True
            conditions = list(unpack('2d', data[HEADER_CMD_SIZE:len(data)]))
            # _show_message(conditions)
            # _show_message("DEMO DCP Only run task waypoint one time")
            # _show_message("DEMO DCP Only run task waypoint one time")
            waypoint_execute = threading.Thread(target=self._task_waypoint_execute)
            waypoint_execute.daemon = True
            waypoint_execute.start()
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_DEFAULT_TCP:
            unpack_type = str(Common.Config().ROBOT_DOF) + 'd'
            tcp_frame = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            # result = self._robot_client.set_tcp_frame(tcp_frame)
            result = self._config_client.SetToolFrame(fpos=tcp_frame)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_RESET_DEFAULT_TCP:
            result = self._config_client.SetToolFrame(fpos=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_COMP_TCP:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)

        elif cmd_id == CMD_RESET_COMP_TCP:
            return self._response_data(CMD_ERROR, invoke_id, ERR_NOT_SUPPORT_COMMAND)

        elif cmd_id == CMD_SET_REFFRAME:
            unpack_type = str(Common.Config().ROBOT_DOF) + 'd'
            ref_frame = list(unpack(unpack_type, data[HEADER_CMD_SIZE:len(data)]))
            result = self._config_client.SetRefFrame(fpos=ref_frame)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_RESET_REFFRAME:
            # _show_message("REF FRAME LIST")
            # _show_message(self._m_config.load_ref_frame_list())
            # self._response_data(cmd_id, invoke_id)
            result = self._config_client.SetRefFrame(fpos=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_COLLISION_LEVEL:
            collision_level = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            result = self._config_client.SetCollSensLevel(level=collision_level)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_JOINT_BOUNDARY:  # joint speed
            self._joint_speed = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_SET_MOVE_C_VEL:  # get movec speed
            self._movec_speed = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)
        elif cmd_id == CMD_SET_MOVE_C_ACC:  # get movec speed
            self._movec_acc = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)


        elif cmd_id == CMD_SET_MOVE_C_ANGLE:  # joint speed
            self._movec_angle = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_START_TELEOP:  # Teleop
            teleop_method = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            self._tele_mode = teleop_method
            self._control_client.StartTeleOp(method= teleop_method)
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_STOP_TELEOP:  # Teleop
            self._tele_mode = 99999
            self._control_client.StopTeleOp()
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_TELE_MOVEJ:  # Teleop
            joint_pos = list(unpack('6d', data[HEADER_CMD_SIZE:len(data)]))
            if self._tele_mode == self.tele_method_joint_absolute:
                self._control_client.MoveTeleJAbs(joint_pos)
            elif self._tele_mode == self.tele_method_joint_relative:
                self._control_client.MoveTeleJRel(joint_pos)
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_TELE_MOVEL:  # Teleop
            task_pos = list(unpack('6d', data[HEADER_CMD_SIZE:len(data)]))
            if self._tele_mode == self.tele_method_task_absolute:
                self._control_client.MoveTeleLAbs(task_pos)
            elif self._tele_mode == self.tele_method_task_relative:
                self._control_client.MoveTeleLRel(task_pos)
            return self._response_data(cmd_id, invoke_id)


        elif cmd_id == CMD_SET_JOINT_BLEND_TYPE:  # blend radius
            self._joint_blend_type = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)
        elif cmd_id == CMD_SET_TASK_BLEND_TYPE:  # blend radius
            self._task_blend_type = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_TASK_BOUNDARY:  # task speed
            self._task_speed = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_JOINT_ACCELERATION:  # joint accel
            self._joint_accel = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_TASK_ACCELERATION:  # task accel
            self._task_accel = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_JOINT_WTIME:
            self._joint_waypoint_time = unpack('d', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_TASK_WTIME:
            self._task_waypoint_time = unpack('d', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_TASK_CMODE:  # TODO: reference axis of TaskMove control
            self._task_move_type = unpack('I', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_JOINT_BLEND_RADIUS:
            self._joint_blend_radius = unpack('d', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)

        elif cmd_id == CMD_SET_TASK_BLEND_RADIUS:
            self._task_blend_radius = unpack('d', data[HEADER_CMD_SIZE:len(data)])[0]
            return self._response_data(cmd_id, invoke_id)
        
        elif cmd_id == CMD_SET_REDUCED_SPEED_RATIO:  
            speed_ratio = unpack('d', data[HEADER_CMD_SIZE:len(data)])[0]
            self._config_client.SetSpeedRatio(speed_ratio=speed_ratio)
            return self._response_data(cmd_id, invoke_id)    
        elif cmd_id == CMD_GET_REDUCED_SPEED_RATIO:
            cur_ratio = self._config_client.GetSpeedRatio()['ratio']
            return self._response_data(cmd_id, invoke_id, cur_ratio)
        

    def _joint_waypoint_execute(self):

        vel_level = self._joint_speed
        acc_level = self._joint_accel
        if vel_level > 2:
            vel_ratio = Common.Limits.VelAutoLevelValue * (vel_level - 1)
        else:
            vel_ratio = Common.Limits.JogVelRatioMin + Common.Limits.VelManualLevelValue * (vel_level - 1)
        acc_ratio = Common.Limits.JogAccRatioDefault * Common.Limits.JogAccLevelDefault

        _wp_time = False if math.isclose(self._joint_waypoint_time, 0.0, rel_tol=1e-3) else True
        for i in self._joint_waypoint:
            if int(i[0]):  # if True => if = 1
                _wp_type = ControlClient.RELATIVE_JOINT
            else:
                _wp_type = ControlClient.ABSOLUTE_JOINT
            if math.isclose(i[1], 0.0, rel_tol=1e-3):  # default 1e-9
                _blending_type = ControlClient.NO_BLENDING
            else:
                _blending_type = ControlClient.DUPLICATE_BLENDING

            if _wp_time:
                self._control_client.MoveJT(jpos=i[2:],
                                            blending_type=_blending_type,
                                            base_type=_wp_type,
                                            blending_radius=i[1],
                                            move_time=self._joint_waypoint_time)
            else:
                self._control_client.MoveJ(jpos=i[2:],
                                           blending_type=_blending_type,
                                           base_type=_wp_type,
                                           blending_radius=i[1],
                                           vel_ratio=vel_ratio,
                                           acc_ratio=acc_ratio)
            time.sleep(0.2)

        while self._running:
            op_state = self._rtde_client.GetControlData()['op_state']
            if op_state != common_data.OpState.OP_MOVING:
                break
            time.sleep(0.1)
        self._joint_waypoint.clear()
        self._wp_thread_lock = False

    def _task_waypoint_execute(self):
        vel_level = self._task_speed
        acc_level = self._task_accel

        _wp_time = False if math.isclose(self._task_waypoint_time, 0.0, rel_tol=1e-3) else True

        for i in self._task_waypoint:
            if (self._task_move_type):
                _wp_type = ControlClient.TCP_TASK
            elif int(i[0]):
                _wp_type = ControlClient.RELATIVE_TASK
            else:
                _wp_type = ControlClient.ABSOLUTE_TASK
            if math.isclose(i[1], 0.0, rel_tol=1e-3):  # default 1e-9
                _blending_type = ControlClient.NO_BLENDING
            else:
                _blending_type = ControlClient.DUPLICATE_BLENDING

            if _wp_time:
                self._control_client.MoveLT(tpos=i[2:],
                                            blending_type=_blending_type,
                                            blending_radius=i[1],
                                            base_type=_wp_type,
                                            move_time=self._task_waypoint_time)
            else:
                self._control_client.MoveL(tpos=i[2:],
                                           blending_type=_blending_type,
                                           blending_radius=i[1],
                                           base_type=_wp_type,
                                           vel_level=vel_level,
                                           acc_level=acc_level)
            time.sleep(0.2)
        while self._running:
            op_state = self._rtde_client.GetControlData()['op_state']
            if op_state != common_data.OpState.OP_MOVING:
                break
            time.sleep(0.1)
        self._task_waypoint.clear()
        self._wp_thread_lock = False

    def _grpc_state_to_dcp_state(self):
        """
            running
            ready
            emergency
            collision
            error
            busy
            movedone
            home
            zero
            resetting
            teaching
            direct_teaching
            program_running
            program_paused
            conty_connected
        """

        control_data = self._rtde_client.GetControlData()
        motion_data = self._rtde_client.GetMotionData()

        status_value = [0] * 15
        # is robot running
        if control_data is not None:
            status_value[0] = 1
        else:
            status_value[0] = 0

        # is robot ready
        servo_data = self._rtde_client.GetServoData()
        status_value[1] = 1
        for servo_active in servo_data['servo_actives']:
            if not servo_active:
                status_value[1] = 0
                break

        if control_data['op_state'] == common_data.OpState.OP_COLLISION:
            status_value[3] = 1
        elif control_data['op_state'] == common_data.OP_VIOLATE:
            status_value[4] = 1
        elif motion_data['is_in_motion']:
            status_value[5] = 1
        elif control_data['op_state'] == common_data.OP_RECOVER_HARD or \
                control_data['op_state'] == common_data.OP_RECOVER_SOFT:
            status_value[9] = 1
        elif control_data['op_state'] == common_data.OP_TEACHING:
            status_value[10] = 1

        # is emergency pushed
        violation_data = self._rtde_client.GetViolationData()
        if violation_data['violation_code'] == 0x01 << (7 + 11):  # "EMG Button Activated":
            status_value[2] = 1

        # is move done => target reach
        status_value[6] = int(motion_data['is_target_reached'])

        # is home and is zero
        # compare current pos with home pos and zero pos, error 0.05 deg
        _home = self._config_client.GetHomePos()['jpos']
        _current_pos = control_data['q']
        if max([abs(a_i - b_i) for a_i, b_i in zip(_home, _current_pos)]) < 0.05:
            status_value[7] = 1
        if max([abs(i - 0) for i in _current_pos]) < 0.05:
            status_value[8] = 1

        # teaching: when robot is moving but program not running
        program_data = self._rtde_client.GetProgramData()
        if control_data['op_state'] == common_data.OP_MOVING and \
                program_data['program_state'] != common_data.PROG_RUNNING:
            status_value[11] = 1

        if program_data['program_state'] == common_data.PROG_RUNNING:
            status_value[12] = 1
        elif program_data['program_state'] == common_data.PROG_PAUSING:
            status_value[13] = 1

        # is conty connected
        status_value[14] = int(self._device.has_conty())

        status_position = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 24, 25, 26, 27, 28]
        status_frame = ['0'] * 32
        for i in range(len(status_position)):
            if status_value[i] == 1:
                status_frame[status_position[i]] = '1'
        status_byte = int(''.join(map(str, status_frame)), 2).to_bytes(10, 'little')

        return status_value, status_byte

    def _response_data(self, cmd_id, invoke_id, data=None, convert_type=None):
        self._debug('Response data: ', str(data))
        data_length = 0
        converted_data = b''
        if data is not None:
            # Check if data is an array or not
            input_len = 1
            if type(data) == list:
                input_len = len(data)
                # _show_message("data len: ", input_len)
            for n in range(input_len):
                # convert data
                if input_len > 1:
                    input_value = data[n]
                else:
                    input_value = data
                # _show_message("data value: ", input_value)
                if convert_type is None:
                    if type(input_value) == float:
                        converted_data += pack('d', input_value)  # 8 bytes
                    elif type(input_value) == bool:
                        converted_data += pack('?', input_value)  # 1 byte
                    elif type(input_value) == int:
                        converted_data += pack('i', input_value)  # 4 bytes
                else:
                    converted_data += pack(convert_type, input_value)
            data_length = len(converted_data)

        response_data = bytearray(HEADER_CMD_SIZE + data_length)
        response_data[HEADER_ROBOT_NAME[0]:HEADER_ROBOT_NAME[1]] = Common.Config().ROBOT_MODEL.encode("utf-8")
        response_data[HEADER_SW_VERSION[0]:HEADER_SW_VERSION[1]] = SW_VERSION_byte
        response_data[HEADER_STEP_INFO[0]:HEADER_STEP_INFO[1]] = STEP_INFO_byte
        response_data[HEADER_SOURCE_OF_FRAME[0]:HEADER_SOURCE_OF_FRAME[1]] = SOURCE_OF_FRAME_byte
        response_data[HEADER_INVOKE_ID[0]:HEADER_INVOKE_ID[1]] = invoke_id
        response_data[HEADER_DATA_LENGTH[0]:HEADER_DATA_LENGTH[1]] = data_length.to_bytes(4, 'little')
        response_data[HEADER_RESERVED[0]:HEADER_RESERVED[1]] = self._grpc_state_to_dcp_state()[1]  # status
        response_data[HEADER_CMD[0]:HEADER_CMD[1]] = cmd_id.to_bytes(4, 'little')  # 56

        if data_length > 0:
            response_data[HEADER_CMD[1]:(HEADER_CMD[1] + data_length)] = converted_data
        # print("response_data: ",response_data)
        return bytes(response_data)

    ############################
    # Console Logging
    ############################
    def _info(self, content, data=None):
        if data is not None:
            self._logger.info(content=content + str(data), source='IndyDCP')
        else:
            self._logger.info(content=content, source='IndyDCP')

    def _debug(self, content, data=None):
        if data is not None:
            self._logger.debug(content=content + str(data), source='IndyDCP')
        else:
            self._logger.debug(content=content, source='IndyDCP')

    def _warn(self, content, data=None):
        if data is not None:
            self._logger.warn(content=content + str(data), source='IndyDCP')
        else:
            self._logger.warn(content=content, source='IndyDCP')

    def _error(self, content, data=None):
        if data is not None:
            self._logger.error(content=content + str(data), source='IndyDCP')
        else:
            self._logger.error(content=content, source='IndyDCP')
