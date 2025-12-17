import math
import os
import sys
import time
import traceback
import glob
import grpc
import threading
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

from google.protobuf import json_format
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
import cri_msgs_pb2 as cri_data
import hri_msgs_pb2 as conty_data
import hri_pb2_grpc as conty_grpc
import mimic_msgs_pb2 as mimic_data
import mimic_pb2_grpc as mimic_grpc
import common as Common
import managers as Managers

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

from .boot_socket_client import BootSocketClient as BootClient
from .config_socket_client import ConfigSocketClient as ConfigClient
from .control_socket_client import ControlSocketClient as ControlClient
from .device_socket_client import DeviceSocketClient as DeviceClient
from .rtde_socket_client import RTDESocketClient as RTDEClient
from .ethercat_client import EtherCATClient as EcatClient
from .indyeye_socket_client import IndyEyeSocketClient as IndyEyeClient
from .linear_control_client import LinearControlClient as LinearClient
from .cri_client import CRIClient
from .autotune_client import autotune_control_gain

# from utils.motion_timer import MotionTimer
from common.utils import get_abs_path, load_json, write_json, try_wrap
from common.security import hash_data

import platform
if platform.system() == 'Linux':
    from common.system import get_process_resources, get_pids, get_ancestor_pids, extract_name_from_cmd, get_tree, NO_PROCESS

from pyModbusTCP.client import ModbusClient  # use for check modbus connection

UPDATE_PRINT_PERIOD = 5.0
check_token = Managers.TokenManager.check
NetworkManager = Managers.NetworkManager

class ContySocketServicer(conty_grpc.HRIServicer):
    CHUNK_SIZE = 1024 * 1024  # 1 MB
    UPDATE_PERIOD = 0.05  # 0.05  # 50 msec
    RECONNECT_PERIOD = 2  # 0.05  # 50 msec
    CONTY_UPDATE_TIMEOUT = 1.0  # 0.5 sec
    CONTY_INIT_PERIOD = 5.0  # 2 sec
    __joint_upper_limits : List[float]
    __joint_lower_limits : List[float]

    def __init__(self, boot_client: BootClient,
                 device_client: DeviceClient,
                 config_client: ConfigClient,
                 control_client: ControlClient,
                 rtde_client: RTDEClient,
                 ecat_client: EcatClient,
                 cri_client: CRIClient,
                 linear_client: LinearClient):
        self._boot_client = boot_client
        self._device_client = device_client
        self._config_client = config_client
        self._control_client = control_client
        self._rtde_client = rtde_client
        self._ecat_client = ecat_client
        self._cri_client = cri_client
        self._linear_client = linear_client
        self._pallet = Managers.PalletManager()
        self._token = Managers.TokenManager(self._config_client)
        self._device = Managers.HRIManager()
        self._logger = Managers.LogManager()

        # self._motion_timer = MotionTimer(robot_client=control_client, interval=0.15)
        self._program_data = None
        self._program_name = ''
        self._violation_data = None
        self._collision_model_state = None
        self._boot_data = None
        self._violation_queue_data = None
        self._safety_control_data = None
        self._servo_data = None
        self._control_data = None
        self._motion_data = None
        self._io_data = None
        self._linear_data = None
        self._data_id = 0
        self._device_info = None
        self._path_config = None
        self._safety_limits = None
        self._reduced_ratio = None

        self.__reboot = False
        self.__power_off = False
        self.__sw_update = False

        self.__jnt_reached_threshold = 0.03  # 0.03deg
        self.__pos_reached_threshold = 0.1  # 0.1mm
        self.__rot_reached_threshold = 0.1 / 180.0 * math.pi  # 0.1deg
        self.__is_target_disturbed = False

        self.__prev_distance = 0.0
        self.__prev_j_index = 0
        self.__prev_t_index = -1
        self.__prev_jog_frame = -1
        self.__violation_id_prev = None
        self.__violation_logged_queue = []
        self.__collision_logged = False
        self._process_resource_list = []

        self.__mimic_channel = None
        self.__mimic_stub = None

        self.ft_sensor_type = 0
        self.ft_com_type = 0
        self.ft_ip = ""

        self.__prev_base_type = -1
        self._axis_limits_max = [8150.0, 0.0, 0.0]
        self._axis_limits_min = [50.0, 0.0, 0.0]

        self._last_conty_request_time = time.time()
        self._has_framework_connected = False
        self._has_boot_server_connected = False
        self._has_linear_axis = None  # None means not determined
        self._lock_data_updating = threading.Lock()

        self._is_data_update_running = True
        self._thread_data_updating = threading.Thread(target=self._update_framework_data)
        self._thread_data_updating.start()

        self._auto_prog_starting = True
        self.auto_prog_thread = threading.Thread(target=self.__start_auto_prog_run)
        self.auto_prog_thread.start()


        self._resource_monitor_thread = threading.Thread(target=self.__resource_monitor)
        if platform.system() == 'Linux':
            self._is_resource_monitoring = True
            self._resource_monitor_thread.start()
        else:
            self._is_resource_monitoring = False

        self._autotune_thread = None

        self._update_last = time.time()
        self._info(f"Conty Service Version {Common.Config().VERSION_INFO}-{Common.Config().VERSION_DETAIL} [{Common.Config().VERSION_DATE}] Start")

    def stop(self):
        self._auto_prog_starting = False
        self._is_data_update_running = False
        self._thread_data_updating.join()
        self._is_resource_monitoring = False
        self._resource_monitor_thread.join()

        if self.auto_prog_thread.is_alive():
            self.auto_prog_thread.join()

        self._info('Conty Connection Closed')
        self._device.disable_usb_connection()

    def __start_auto_prog_run(self):
        while self._auto_prog_starting:
            time.sleep(2)
            self._info('Check Auto Start Program')
            try:
                control_data = None
                safety_control_data = None
                if self.has_framework_connected():
                    framework_data = self.get_framework_data()
                    control_data = framework_data['control_data']
                    safety_control_data = framework_data['safety_control_data']

                if (control_data is None) or (safety_control_data is None):
                    self._info('Postpone Auto Start Program - Framework Not Connected')
                    continue

                if (not ((control_data['op_state'] == common_data.OP_SYSTEM_OFF)
                         or (control_data['op_state'] == common_data.OP_SYSTEM_ON)
                         or (control_data['op_state'] == common_data.OP_IDLE))):
                    self._warn(f"Quit Auto Start Program - Boot to abnormal state {control_data['op_state']}")
                    break  # quit autostart if deviated from off-on-idle sequence

                if control_data['op_state'] == common_data.OP_IDLE:  # Ready to play auto program

                    if Common.Config().USE_AUTO_MODE is None:
                        self._info('Postpone Auto Start Program - Config Not Loaded')
                        continue

                    if Common.Config().USE_AUTO_MODE and not safety_control_data['auto_mode']:
                        self._info(f'Quit Auto Start Program - Boot to manual mode')
                        break  # quit autostart if manual mode

                    auto_prog_info = self.__get_onstart_program_info()
                    self._debug('Auto Start Program Info: ' + str(auto_prog_info))
                    if auto_prog_info is None or not auto_prog_info['auto_run']:
                        self._info(f'Quit Auto Start Program - auto_run not set')
                        break

                    if self._control_client.PlayProgram(
                            prog_name='',
                            prog_idx=auto_prog_info['index']
                    ) is None:
                        self._warn('Start Auto Program Failed')
                    else:
                        self._info('Start Auto Program Success')
                    break

            except Exception as ex:
                self._error(f"Error in starting auto-start program {ex}")
                pass

        self._auto_prog_starting = False

    def is_reboot(self) -> bool:
        return self.__reboot

    def is_power_off(self) -> bool:
        return self.__power_off

    def is_update(self) -> bool:
        return self.__sw_update

    @try_wrap
    def ContyInit(self, request, context):
        self._info('Start Initializing Conty')
        now = datetime.now(timezone.utc)
        system_time = common_data.DateTime(year=now.year, month=now.month, day=now.day,
                                           hour=now.hour, minute=now.minute, second=now.second)
        conty_init_res = conty_data.ContyInitRes(system_time=system_time)

        if self._device.has_conty():
            self._error('Another Conty had been registered!')
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            return conty_init_res

        cb_ip = Common.Utils.get_ip()

        if not self.has_framework_connected():
            context.set_code(grpc.StatusCode.NOT_FOUND)
            conty_init_res = conty_data.ContyInitRes(
                robot_name="",
                robot_dof=0,
                robot_sn="",
                cb_ip=cb_ip,
                cb_sn="",
                server_ver=Common.Config().VERSION_INFO,  # control_info['control_version'],
                server_detail=Common.Config().VERSION_DETAIL,
                server_date=Common.Config().VERSION_DATE,
                conty_ver_minimum=Common.Config().VERSION_MINIMUM,

                config_path="",
                program_path="",
                index_program_path="",
                server_log_path=Common.Config().SERVER_LOG_PATH,
                rt_log_path=Common.Config().LOG_PATH,

                system_time=system_time
            )
            return conty_init_res
        self._info('Add Conty device')
        self._info('Prepare init data for ' + str(cb_ip))
        framework_data = self.get_framework_data()
        device_info = framework_data['device_info']
        path_config = framework_data['path_config']
        safety_limits = framework_data['safety_limits']
        reduced_ratio = framework_data['reduced_ratio']

        Common.Config().configure_robot(robot_name=device_info['robot_name'], robot_dof=device_info['robot_dof'])
        Common.Config().configure_controller(use_safety_io=device_info['use_safety_io'],
                                             use_npad=device_info['use_npad'], use_indykey=device_info['use_indykey'],
                                             use_auto_mode=device_info['use_auto_mode'])
        Common.Config().configure_conversion(reduced_ratio=reduced_ratio['ratio'])
        Common.Config().configure_path(config_path=path_config['config_path'],
                                       safety_path_list=path_config["safety_path_list"])
        self.__joint_upper_limits = safety_limits['joint_upper_limits']
        self.__joint_lower_limits = safety_limits['joint_lower_limits']

        conty_init_res = conty_data.ContyInitRes(
            robot_name=Common.Config().ROBOT_MODEL,
            robot_dof=Common.Config().ROBOT_DOF,
            robot_sn=device_info['robot_serial'],
            robot_payload=device_info['payload'],
            teleop_loaded=device_info['teleop_loaded'],
            calibrated=device_info['calibrated'],
            cb_ip=cb_ip,
            cb_sn=device_info['cb_serial'],
            controller_ver=device_info['controller_ver'],  # control_info['control_version'],
            controller_detail=device_info['controller_detail'],
            controller_date=device_info['controller_date'],
            server_ver=Common.Config().VERSION_INFO,  # control_info['control_version'],
            server_detail=Common.Config().VERSION_DETAIL,
            server_date=Common.Config().VERSION_DATE,
            conty_ver_minimum=Common.Config().VERSION_MINIMUM,
            controller_type=device_info['controller_type'],
            controller_platform=device_info['controller_platform'],

            config_path=Common.Config().ROBOT_CONFIG_PATH,
            program_path=Common.Config().PROGRAM_DIR,
            index_program_path=Common.Config().INDEX_PROGRAM_DIR,
            server_log_path=Common.Config().SERVER_LOG_PATH,
            rt_log_path=Common.Config().LOG_PATH,
            io_fw_ver=device_info['io_board_fw_ver'],
            core_fw_vers=device_info['core_board_fw_vers'],
            endtool_fw_ver=device_info['endtool_board_fw_ver'],
            joint_upper_limits=self.__joint_upper_limits,
            joint_lower_limits=self.__joint_lower_limits,

            system_time=system_time
        )
        self._info('init data Prepared')
        return conty_init_res

    @try_wrap
    def GetBootStatus(self, request, context):
        framework_data = self.get_framework_data()
        response = boot_data.BootStatus()
        json_format.ParseDict(framework_data["boot_data"], response)
        return response

    @try_wrap
    def GetNonce(self, request, context):
        resp = self._config_client.GetNonce()
        response = config_data.Nonce()
        json_format.ParseDict(resp, response)
        return response

    @try_wrap
    def Login(self, request, context):
        try:
            resp = self._config_client.Login(digest=request.digest)
            response = config_data.LoginRes()
            json_format.ParseDict(resp, response)
            return response
        except:
            context.abort(grpc.StatusCode.CANCELLED, "Login failed")

    @check_token
    def ChangePassword(self, request, context):
        resp = self._config_client.ChangePassword(digest=request.digest, nonce=request.nonce)
        response = common_data.Response()
        json_format.ParseDict(resp, response)
        return response

    @check_token
    def RobotUpdate(self, request, context):
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug("RobotUpdate")

        now = datetime.now(timezone.utc)
        system_time = common_data.DateTime(year=now.year, month=now.month, day=now.day,
                                          hour=now.hour, minute=now.minute, second=now.second)

        if not self.has_framework_connected():
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            robot_data = conty_data.RobotData(
                system_time=system_time,
                response=common_data.Response(
                    code=1, msg='Robot Connection Failed!'
                )
            )
            return robot_data

        framework_data = self.get_framework_data()

        robot_state = True
        for servo_state in framework_data['servo_data']['servo_actives']:
            if not servo_state:
                robot_state = False
                break

        di_list = self.__convert_digital_bool_list__(framework_data['io_data']['di'])
        do_list = self.__convert_digital_bool_list__(framework_data['io_data']['do'])
        # end_di_list = self.__convert_digital_bool_list__(framework_data['io_data']['end_di'])
        # end_do_list = self.__convert_digital_bool_list__(framework_data['io_data']['end_do'])
        # di_list = framework_data['io_data']['di']
        # do_list = framework_data['io_data']['do']
        end_di_list = framework_data['io_data']['end_di']
        end_do_list = framework_data['io_data']['end_do']

        ai_list = self.__convert_analog_value_list__(framework_data['io_data']['ai'])
        ao_list = self.__convert_analog_value_list__(framework_data['io_data']['ao'])
        end_ai_list = self.__convert_analog_value_list__(framework_data['io_data']['end_ai'])
        end_ao_list = self.__convert_analog_value_list__(framework_data['io_data']['end_ao'])

        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._update_last = time.time()
            self._debug('\nDO: ' + str(do_list) +
                        '\nAO: ' + str(ao_list) +
                        '\nEndDI: ' + str(end_di_list) +
                        '\nEndDO: ' + str(end_do_list) +
                        '\nEndADI: ' + str(end_ai_list) +
                        '\nEndAO: ' + str(end_ao_list))
        robot_data = conty_data.RobotData(
            do=do_list,
            di=di_list,
            ao=ao_list,
            ai=ai_list,

            end_do=end_do_list,
            end_di=end_di_list,
            end_ao=end_ao_list,
            end_ai=end_ai_list,

            robot_state=robot_state,
            joint_servos=framework_data['servo_data']['servo_actives'],
            joint_brakes=framework_data['servo_data']['brake_actives'],

            temperatures=framework_data['servo_data']['temperatures'],
            voltages=framework_data['servo_data']['voltages'],
            currents=framework_data['servo_data']['currents'],
            status_codes=framework_data['servo_data']['status_codes'],
            torques=framework_data['servo_data']['torques'],

            system_time=system_time,
            data_id=int(framework_data['data_id'])
        )
        return robot_data

    @check_token
    def ProgramUpdate(self, request, context):
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug("ProgramUpdate")

        if not self.has_framework_connected():
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.ProgramData(
                response=common_data.Response(
                    code=1, msg='Robot Connection Failed!'
                )
            )

        framework_data = self.get_framework_data()

        program_time = f"{framework_data['program_data']['running_hours']:02d}" + ':' + \
                       f"{framework_data['program_data']['running_mins']:02d}" + ':' + \
                       f"{framework_data['program_data']['running_secs']:02d}"

        program_data = conty_data.ProgramData(
            program_state=framework_data['program_data']['program_state'],
            cmd_id=framework_data['program_data']['cmd_id'],
            speed_ratio=framework_data['program_data']['speed_ratio'],
            program_time=program_time,
            program_name=framework_data['program_data']['program_name'],
            program_alarm=framework_data['program_data']['program_alarm'],
            program_annotation=framework_data['program_data']['program_annotation'],
            data_id=int(framework_data['data_id'])
        )

        if framework_data['program_data']['program_alarm'] != '':
            self._debug('Alarm: ' + framework_data['program_data']['program_alarm'])
            framework_data['program_data']['program_alarm'] = ''
            self._control_client.SendAlarm(content='')  # Reset alarm

        if framework_data['program_data']['program_annotation'] != '':
            self._debug('Annotation: ' + framework_data['program_data']['program_annotation'])
            self._control_client.SendAnnotation(content='')  # Reset annotation

        return program_data

    @check_token
    def ControlUpdate(self, request, context):
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug("ControlUpdate")

        if not self.has_framework_connected():
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.ControlData(
                response=common_data.Response(
                    code=1, msg='Robot Connection Failed!'
                )
            )

        framework_data = self.get_framework_data()

        running_time = f"{framework_data['control_data']['running_hours']:02d}" + ':' + \
                       f"{framework_data['control_data']['running_mins']:02d}" + ':' + \
                       f"{framework_data['control_data']['running_secs']:02d}"

        violation_queue = framework_data['violation_queue_data']['violation_queue']
        violation_data = framework_data['violation_data']
        is_target_reached = framework_data['motion_data']['is_target_reached']
        if self._has_linear_axis:
            is_target_reached = is_target_reached and framework_data['linear_data']['is_target_reached']
            # is_target_reached = is_target_reached and (framework_data['linear_data']['op_state'] != common_data.OP_MOVING)

        collision_model_state = framework_data['collision_model_state']
        collision_model_state_resp = rtde_data.CollisionModelState()
        json_format.ParseDict(collision_model_state, collision_model_state_resp)
        control_data = conty_data.ControlData(
            jpos=framework_data['control_data']['q'],
            jvel=framework_data['control_data']['qdot'],
            tpos=framework_data['control_data']['p'],
            tvel=framework_data['control_data']['pdot'],

            ref_frame=framework_data['control_data']['ref_frame'],
            tool_frame=framework_data['control_data']['tool_frame'],
            ref_frame_name=self.__get_ref_frame_name(framework_data['control_data']['ref_frame']),
            tool_frame_name=self.__get_tool_frame_name(framework_data['control_data']['tool_frame']),

            control_time=running_time,
            control_state=framework_data['control_data']['op_state'],

            is_simulation_mode=framework_data['control_data']['sim_mode'],
            is_auto_mode=framework_data['safety_control_data']['auto_mode'],
            # is_target_reached=framework_data['motion_data']['is_target_reached'],
            is_target_reached=is_target_reached,
            is_key_connected=Common.Config().USE_INDYKEY,
            is_enabler_on=framework_data['safety_control_data']['enabler_pressed'],
            is_robot_connected=framework_data['control_data']['is_robot_connected'],

            violation=violation_data['violation_str'],
            violation_code=int(violation_data['violation_code']),
            violation_id=int(violation_data['violation_id']),
            violation_queue=[
                conty_data.ViolationMsgCode(
                    violation=violation['violation_str'],
                    violation_code=int(violation['violation_code']),
                    violation_id=int(violation['violation_id']))
                for violation in violation_queue if int(violation['violation_id']) != int(violation_data['violation_id']) ],
            collision_model_state=collision_model_state_resp,
            tool_link=framework_data['control_data']['tool_link'],
            locked_joint=framework_data['control_data']['locked_joint'],
            data_id=int(framework_data['data_id'])
        )
        return control_data

    @check_token
    def LinearUpdate(self, request, context):
        # self._debug('LinearUpdate')
        if not self.has_framework_connected():
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.ControlData(
                response=common_data.Response(
                    code=1, msg='Robot Connection Failed!'
                )
            )

        framework_data = self.get_framework_data()
        if framework_data['linear_data'] is None:
            linear_data = conty_data.LinearData()
        else:
            linear_data = conty_data.LinearData(
                num_axes=framework_data['linear_data']['num_axes'],
                axis_servos=framework_data['linear_data']['active'],
                pos_mm=framework_data['linear_data']['pos_mm'],
                vel_mm=framework_data['linear_data']['vel_mm'],
                op_state=framework_data['linear_data']['op_state'],
                axis_type=framework_data['linear_data']['axis_type'],
                is_target_reached=framework_data['linear_data']['is_target_reached'],
                data_id=int(framework_data['data_id'])
            )
        # self._debug('Linear data: ' + str(framework_data['linear_data']))
        return linear_data

    @check_token
    def HoldToMoveJ(self, request, context):
        self._debug('HoldToMoveJ')
        framework_data = self.get_framework_data()

        # if framework_data['control_data']['op_state'] == RTDEClient.CTRL_IDLE:
        self._debug('Hold to joint target from ' + str(request.j_start) +
                    ' to ' + str(request.j_target))

        jstart = request.j_start
        jtarget = request.j_target
        cur_q = framework_data['control_data']['q']

        vel_ratio = Common.Config().to_vel_ratio(request.vel_level)
        acc_ratio = Common.Config().to_acc_ratio(request.vel_level)

        res = self._control_client.MoveJ(
            jstart=jstart, jtarget=jtarget,
            base_type=request.base_type,
            vel_ratio=vel_ratio,
            acc_ratio=acc_ratio,
            teaching_mode=True
        )
        self.__unmark_target_reached()
        # if res is None:
        #     self._error('Hold to joint target: ' + str(request.jpos) + ' failed!')
        #     context.set_code(grpc.StatusCode.UNAVAILABLE)

        if isinstance(res, Common.utils.GRPCReturn):
            self._error('Hold to joint target: ' + str(request.j_target) + ' failed!')
            context.set_code(res.code)
            context.set_details(res.details)

        return common_data.Empty()

    @check_token
    def HoldToMoveL(self, request, context):
        self._debug('HoldToMoveL')
        framework_data = self.get_framework_data()

        if framework_data['control_data']['op_state'] == RTDEClient.CTRL_IDLE:
            self._debug('Hold to task target from ' + str(request.t_start) +
                        ' to ' + str(request.t_target) +
                        ', base=' + str(request.base_type))

        tstart = request.t_start
        ttarget = request.t_target
        bypass_singular = False
        if hasattr(request, 'bypass_singular'):
            bypass_singular = request.bypass_singular
        cur_p = framework_data['control_data']['p']


        vel_ratio = Common.Config().to_vel_ratio(request.vel_level)
        acc_ratio = Common.Config().to_acc_ratio(request.vel_level)

        res = self._control_client.MoveL(
            tstart=tstart, ttarget=ttarget,
            base_type=request.base_type,
            vel_ratio=vel_ratio,
            acc_ratio=acc_ratio,
            teaching_mode=True,
            bypass_singular=bypass_singular
        )
        self.__unmark_target_reached()

        if isinstance(res, Common.utils.GRPCReturn):
            self._error('Hold to task target: ' + str(request.t_target) +
                        ', base=' + str(request.base_type) + ' failed!')
            context.set_code(res.code)
            context.set_details(res.details)

        return common_data.Empty()

    @check_token
    def HoldToAxisJ(self, request, context):
        self._debug("HoldToAxisJ")
        framework_data = self.get_framework_data()

        if framework_data['linear_data']['op_state'] == common_data.OP_IDLE:
            self._debug('Hold to linear target from ' + str(request.a_start) +
                        ' to ' + str(request.a_target))
        self._debug('Hold to joint target from ' + str(request.j_start) +
                    ' to ' + str(request.j_target))

        jstart = request.j_start
        jtarget = request.j_target # in mm
        axstart = request.a_start
        axtarget = request.a_target
        # expos = request.expos

        vel_ratio = Common.Config().to_vel_ratio(request.vel_level)
        acc_ratio = Common.Config().to_acc_ratio(request.vel_level)

        if request.base_type == control_data.ABSOLUTE_JOINT:
            is_absolute = True
        else:
            is_absolute = False

        if self._has_linear_axis:
            axtarget_valid = False
            num_axes = framework_data['linear_data']['num_axes']
            pos_mm = framework_data['linear_data']['pos_mm']
            if len(axtarget) >= num_axes:
                axtarget = axtarget[:num_axes]
                if is_absolute:
                    dtarget = np.subtract(axtarget, pos_mm[:num_axes])
                else:
                    dtarget = axtarget
                axtarget_valid = (np.max(np.abs(dtarget))>1e-2)
            if axtarget_valid:
                res = self._linear_client.move_axis(start_mm=axstart,
                                                    target_mm=axtarget,
                                                    is_absolute=is_absolute,
                                                    vel_ratio=vel_ratio,
                                                    acc_ratio=acc_ratio,
                                                    teaching_mode=True)
                if isinstance(res, Common.Utils.GRPCReturn):
                    self._error('Hold to axis target: ' + str(axtarget) + ' failed!')
                    context.set_code(res.code)
                    context.set_details(res.details)
        if jtarget:
            jtarget_valid = False
            if len(jtarget) >= Common.Config().ROBOT_DOF:
                jtarget = jtarget[:Common.Config().ROBOT_DOF]
                if is_absolute:
                    dtarget = np.subtract(jtarget, framework_data['control_data']['q'][:Common.Config().ROBOT_DOF])
                else:
                    dtarget = jtarget
                jtarget_valid = (np.max(np.abs(dtarget))>1e-2)
            if jtarget_valid or not self._has_linear_axis:
                res = self._control_client.MoveJ(
                    jstart=jstart, jtarget=jtarget,
                    base_type=request.base_type,
                    vel_ratio=vel_ratio,
                    acc_ratio=acc_ratio,
                    teaching_mode=True
                )
                self.__unmark_target_reached()
                if isinstance(res, Common.Utils.GRPCReturn):
                    self._error('Hold to joint target: ' + str(jtarget) + ' failed!')
                    context.set_code(res.code)
                    context.set_details(res.details)
                    return common_data.Empty()


        return common_data.Empty()

    @check_token
    def StopMotion(self, request, context):
        self._debug("StopMotion")
        framework_data = self.get_framework_data()
        res = self._control_client.StopMotion(stop_category=ControlClient.STOP_SMOOTH_ONLY)
        if res is None:
            self._error('Stop motion failed!')
            context.set_code(grpc.StatusCode.CANCELLED)
        return conty_data.StopMotionRes()

    @check_token
    def SetHomePos(self, request, context):
        self._debug('SetHomePos = ' + str(request.jpos))
        jpos = [i for i in request.jpos]
        self._config_client.SetHomePos(home_jpos=jpos)
        return conty_data.SetHomePosRes()

    @check_token
    def GetHomePos(self, request, context):
        self._debug('GetHomePos')
        home_pos = self._config_client.GetHomePos()['jpos']
        return conty_data.GetHomePosRes(jpos=home_pos)

    @check_token
    def GetPackagingPos(self, request, context):
        self._debug('GetPackPos')
        pack_pos = self._config_client.GetPackPos()['jpos']
        return conty_data.GetPackagingPosRes(jpos=pack_pos)

    @check_token
    def SetRefFrame(self, request, context):
        self._debug('SetRefFrame')
        framework_data = self.get_framework_data()

        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            res = self._config_client.SetRefFrame(fpos=list(request.ref_frame))
            if res is None:
                self._error('Set ref_frame=' + str(request.ref_frame) + ' failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
            else:
                self._debug('Set ref_frame=' + str(request.ref_frame))
        return conty_data.SetRefFrameRes()

    @check_token
    def SetRefFramePlanar(self, request, context):
        self._debug('SetRefFramePlanar')
        res = self._config_client.SetRefFramePlanar(fpos0=list(request.tpos0),
                                                    fpos1=list(request.tpos1),
                                                    fpos2=list(request.tpos2))
        if res is None:
            self._debug('SetFramePlanar Failed')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.SetRefFramePlanarRes()
        else:
            self._debug('RefFrame: ' + str(res))
            msg = ""
            if 'response' in res:
                if 'msg' in res['response']:
                    msg = res['response']['msg']
            return conty_data.SetRefFramePlanarRes(ref_frame=res['fpos'], msg=msg)

    @check_token
    def SetLockedJoint(self, request, context):
        self._debug('SetLockedJoint')
        framework_data = self.get_framework_data()
        self._info(f'SetLockedJoint: {int(request.value)}')

        response = common_data.Response()
        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            resp = self._config_client.SetLockedJoint(locked_joint=int(request.value))
            if resp is None:
                self._error(f'Set locked_joint= {int(request.value)} failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
            else:
                self._debug(f'Set locked_joint= {int(request.value)}')
                json_format.ParseDict(resp, response)
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return response

    @check_token
    def SetToolLink(self, request, context):
        self._debug('SetToolLink')
        framework_data = self.get_framework_data()
        self._info(f'SetToolLink: {int(request.value)}')

        response = common_data.Response()
        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            resp = self._config_client.SetToolLink(tool_link=int(request.value))
            if resp is None:
                self._error(f'Set tool_link= {int(request.value)} failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
            else:
                self._debug(f'Set tcp_link= {int(request.value)}')
                json_format.ParseDict(resp, response)
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return response

    @check_token
    def SetToolFrame(self, request, context):
        self._debug('SetToolFrame')
        framework_data = self.get_framework_data()
        self._info('SetToolFrame: ' + str(list(request.tool_frame)))

        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            res = self._config_client.SetToolFrame(fpos=list(request.tool_frame))
            if res is None:
                self._error('Set tcp_frame=' + str(request.tool_frame) + ' failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
            else:
                self._debug('Set tcp_frame=' + str(request.tool_frame))
        return conty_data.SetToolFrameRes()

    @check_token
    def SetGripperCommand(self,request, context):
        self._debug('SetGripperCommand')
        gripper_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetGripperCommand: ' + str(gripper_dict))
        res = self._device_client.SetGripperControl(command=gripper_dict['gripper_command'], gripper_type = gripper_dict['gripper_type'],pvt_data = gripper_dict['gripper_pvt_data'])
        if res is None:
            self._error('SetGripperCommand: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return common_data.Response(code=1, msg='SetGripperCommand: Service unavailable')

        return common_data.Response()

    @check_token
    def GetGripperData(self,request, context):
        self._debug('GetGripperData')
        gripper_data = self._device_client.GetGripperData()
        response = device_data.GripperData()
        json_format.ParseDict(gripper_data, response)
        return response

    @check_token
    def GetToolFrameList(self, request, context):
        self._debug('GetToolFrameList')
        response = conty_data.GetToolFrameListRes()
        tool_frame_list = self._config_client.GetToolFrameList()
        if tool_frame_list is not None:
            json_format.ParseDict(tool_frame_list, response)
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return response

    @check_token
    def SetToolFrameList(self, request, context):
        frames_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._info('SetToolFrameList: ' + str(frames_dict))
        self._config_client.SetToolFrameList(frames_dict)
        return conty_data.SetToolFrameListRes()

    @check_token
    def GetRefFrameList(self, request, context):
        self._debug('GetRefFrameList')
        response = conty_data.GetRefFrameListRes()
        ref_frame_list = self._config_client.GetRefFrameList()
        if ref_frame_list is not None:
            json_format.ParseDict(ref_frame_list, response)
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return response

    @check_token
    def SetRefFrameList(self, request, context):
        self._debug('SetRefFrameList')
        frames_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._config_client.SetRefFrameList(frames_dict)
        return conty_data.SetRefFrameListRes()

    @check_token
    def SetSpeedRatio(self, request, context):
        self._debug('SetSpeedRatio')
        res = self._config_client.SetSpeedRatio(speed_ratio=request.ratio)
        if res is None:
            self._error('Set speed_ratio=' + str(request.ratio) + ' failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._debug('Set speed_ratio=' + str(request.ratio))

        return conty_data.SetSpeedRatioRes()

    @check_token
    def SetSimulationMode(self, request, context):
        self._debug('SetSimulationMode')
        res = self._control_client.SetSimulationMode(enable=request.on)
        if res is None:
            self._error('Set Simulation(' + str(request.on) + ') failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._debug('Set Simulation(' + str(request.on) + ')')
        return conty_data.SetSimulationModeRes()

    @check_token
    def SetCustomControlMode(self, request: common_data.IntMode, context):
        self._debug('SetCustomControlMode')
        resp = self._control_client.SetCustomControlMode(request.mode)
        response = common_data.Response()
        json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetCustomControlMode(self, request, context):
        self._debug('GetCustomControlMode')
        resp = self._control_client.GetCustomControlMode()
        response = common_data.IntMode()
        json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetBrakeControlStyle(self, request, context):
        self._debug('GetBrakeControlStyle')
        brake_style_res = self._device_client.GetBrakeControlStyle()
        response = device_data.BrakeControlStyle()
        json_format.ParseDict(brake_style_res, response)
        return response

    @check_token
    def SetDirectTeachingMode(self, request, context):
        self._debug('SetDirectTeachingMode')
        framework_data = self.get_framework_data()

        res = conty_data.SetDirectTeachingModeRes()
        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            if self._control_client.SetDirectTeaching(enable=request.on) is None:
                self._error('Set Direct Teaching(' + str(request.on) + ') failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._error('Direct Teaching is not available in Auto Mode')
            res = conty_data.SetDirectTeachingModeRes(msg='Direct Teaching is not available in Auto Mode')
        self._debug('Set Direct Teaching(' + str(request.on) + ')')
        return res

    @check_token
    def SetComplianceMode(self, request, context):
        self._debug('SetComplianceMode')
        framework_data = self.get_framework_data(from_conty=False)

        res = conty_data.SetComplianceModeRes()
        if framework_data['program_data']['program_state'] != RTDEClient.PROG_RUNNING:
            if self._control_client.SetComplianceMode(enable=request.on) is None:
                self._error('Set Compliance Mode(' + str(request.on) + ') failed!')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._error('Compliance Mode is not available in Auto Mode')
            res = conty_data.SetComplianceModeRes(msg='Compliance Mode is not available in Auto Mode')
        self._debug('Set Compliance Mode(' + str(request.on) + ')')
        return res

    @check_token
    def GetComplianceMode(self, request, context):
        self._debug('GetComplianceMode')
        resp = self._control_client.GetComplianceMode()
        response = conty_data.GetComplianceModeRes()
        json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetBrake(self, request, context):
        self._debug('SetBrake')
        # servo_states = True
        # for servo_state in framework_data['servo_data']['servo_actives']:
        #     if not servo_state:
        #         servo_states = False
        #         break

        servo_states = False
        if servo_states:
            self._error('Set Brake failed because servo is on')
            return conty_data.SetBrakeRes(msg="If the robot's servo is turned on,\n the brake cannot be controlled")
        else:
            if self._device_client.SetBrakes(brake_state_list=list(request.on)) is None:
                self._error('Set Brake: Service unavailable')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
            else:
                self._debug('Set Brake: ' + str(request.on))

            return conty_data.SetBrakeRes()

    @check_token
    def SetServo(self, request, context):
        self._debug('SetServo')
        framework_data = self.get_framework_data()

        err_msg = None
        if request.on is True:
            if framework_data['control_data']['op_state'] != RTDEClient.CTRL_SYSTEM_OFF and \
                    framework_data['control_data']['op_state'] != RTDEClient.CTRL_MANUAL_RECOVER and \
                    framework_data['control_data']['op_state'] != RTDEClient.CTRL_BRAKE:
                err_msg = 'Servo On is not available in current robot state (' + \
                          str(framework_data['control_data']['op_state']) + ')'
        else:  # Servo Off
            if framework_data['control_data']['op_state'] != RTDEClient.CTRL_IDLE:
                err_msg = 'Servo Off is not available in current robot state (' + \
                          str(framework_data['control_data']['op_state']) + ')' + str(RTDEClient.CTRL_IDLE)

        if err_msg is not None:
            self._error(err_msg)
            return conty_data.SetServoRes(msg=err_msg)

        if self._device_client.SetServoAll(enable=request.on) is None:
            self._error('Set Servo: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._debug('Set Servo: ' + str(request.on))
        return conty_data.SetServoRes()

    @check_token
    def CalculateRelativePose(self, request, context):
        self._debug('CalculateRelativePose')

        res = self._control_client.CalculateRelativePose(
            start_pos=list(request.start_pos),
            end_pos=list(request.end_pos),
            base_type=request.base_type)
        if res is not None:
            response = control_data.CalculateRelativePoseRes()
            json_format.ParseDict(res, response)
            return response
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return control_data.CalculateRelativePoseRes()

    @check_token
    def CalculateCurrentPoseRel(self, request, context):
        self._debug('CalculateCurrentPoseRel')

        res = self._control_client.CalculateCurrentPoseRel(
            current_pos=list(request.current_pos),
            relative_pos=list(request.relative_pos),
            base_type=request.base_type
        )
        if res is not None:
            response = control_data.CalculateCurrentPoseRelRes()
            json_format.ParseDict(res, response)
            return response
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return control_data.CalculateCurrentPoseRelRes()

    @check_token
    def PingFromConty(self, request, context):
        # self._debug('PingFromConty')
        self._last_conty_request_time = time.time()
        if not self._device.has_conty():
            self._device.update_conty(connected=True)
        res = self._control_client.PingFromConty()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return common_data.Empty()

    @check_token
    def InverseKinematics(self, request, context):
        self._debug('InverseKinematics')
        framework_data = self.get_framework_data()

        init_jpos = []
        if len(request.init_jpos) < Common.Config().ROBOT_DOF:
            init_jpos = framework_data['control_data']['q']  # Get InverseKinematics in Current Pos
        else:
            init_jpos = list(request.init_jpos)  # Get InverseKinematics in Input Pos

        # init_jpos = framework_data['control_data']['q']  # Get InverseKinematics in Current Pos
        # tpos = framework_data['control_data']['p']  # list(request.tpos)
        tpos = list(request.tpos)
        self._debug('Init IK Joint: ' + str(init_jpos))
        self._debug('tpos: ' + str(tpos))
        res = self._control_client.Calculate_IK(
            tpos=tpos, init_jpos=init_jpos
        )
        if res is not None:
            self._debug('res: ' + str(res['jpos']))
            response = control_data.InverseKinematicsRes()
            json_format.ParseDict(res, response)
            return response
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return control_data.InverseKinematicsRes()

    @check_token
    def ForwardKinematics(self, request, context):
        self._debug('ForwardKinematics')
        time.sleep(0.1)  # add sleep for apply tcp and ref frame
        framework_data = self.get_framework_data()

        jpos = list(request.jpos)  # Get ForwardKinematics in Input Pos

        self._debug('jpos: ' + str(jpos))
        res = self._control_client.Calculate_FK(jpos=jpos)
        if res is not None:
            self._debug('res: ' + str(res['tpos']))
            response = control_data.ForwardKinematicsRes()
            json_format.ParseDict(res, response)
            return response
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return control_data.ForwardKinematicsRes()

    # -------------------------#
    # Violation Recovery
    # -------------------------#
    @check_token
    def SetManualRecoverMode(self, request, context):
        self._debug('SetManualRecoverMode: ' + str(request.enable))
        res = self._control_client.SetManualRecovery(enable=request.enable)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response(code=0)

    @check_token
    def SetServoRecover(self, request, context):
        self._debug('SetServoRecover: ' + str(request.index) + ': ' + str(request.enable))
        res = self._device_client.SetServo(index=request.index, enable=request.enable)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response(code=0)

    @check_token
    def JogJointRecover(self, request, context):
        self._debug('JogJointRecover: ' + str(request.joint_num) + ': ' + str(request.distance))
        framework_data = self.get_framework_data()

        if framework_data['control_data']['op_state'] != RTDEClient.CTRL_MANUAL_RECOVER:
            context.set_code(grpc.StatusCode.CANCELLED)
            return common_data.Response(code=1, msg='Jog Recover is only available in Manual Recover Mode')

        j_index = request.joint_num
        distance = request.distance
        cur_q = framework_data['control_data']['q']

        vel_ratio = Common.Config().to_vel_ratio(request.vel_level)
        acc_ratio = Common.Config().to_acc_ratio(request.vel_level)

        if distance == 180.0 or distance == -180.0:
            distance = distance * 10

        holdmove_jtarget = [0 for i in range(Common.Config().ROBOT_DOF)]
        holdmove_jtarget[j_index] = distance
        motion_base = ControlClient.RELATIVE_JOINT

        self._debug('JogJointRecover: ' + str(holdmove_jtarget))
        self._debug('q: ' + str(cur_q[j_index]))
        self._debug('upper limit: ' + str(self.__joint_upper_limits[j_index]))
        self._debug('lower limit: ' + str(self.__joint_lower_limits[j_index]))

        res = self._control_client.MoveRecoverJoint(jtarget=holdmove_jtarget,
                                                    base_type=motion_base, )
        self.__unmark_target_reached()

        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response(code=0)

    @check_token
    def Recover(self, request, context):
        self._debug('Recover')
        res = self._control_client.Recover()
        if res is None:
            self._error('Recover: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.RecoverRes()

    @check_token
    def SetDO(self, request, context):
        self._debug('SetDO')
        signals_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetDO: ' + str(signals_dict))
        res = self._device_client.SetDO(self.__to_digital_request_signals__(signals_dict['signals']))

        if res is None:
            self._error('SetDO: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return common_data.Response(code=int(res['code']), msg=res['msg'])

    @check_token
    def SetAO(self, request, context):
        self._debug('SetAO')
        signals_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetAO: ' + str(signals_dict))
        res = self._device_client.SetAO(self.__to_analog_request_signals__(signals_dict['signals']))
        if res is None:
            self._error('SetAO: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return common_data.Response(code=int(res['code']), msg=res['msg'])

    @check_token
    def SetEndDO(self, request, context):
        self._debug('SetEndDO')
        signals_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetEndDO: ' + str(signals_dict))
        res = self._device_client.SetEndDO(end_do_signal_list=signals_dict['signals'])
        if res is None:
            self._error('SetEndDO: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return common_data.Response(code=1, msg='SetEndDO: Service unavailable')

        return common_data.Response()

    @check_token
    def SetEndAO(self, request, context):
        self._debug('SetEndAO')
        signals_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetEndAO: ' + str(signals_dict))
        res = self._device_client.SetEndAO(signals_dict['signals'])
        if res is None:
            self._error('SetEndAO: Service unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return common_data.Response()

    @check_token
    def GetPalletMakerList(self, request, context):
        self._debug('GetPalletMakerList')
        response = conty_data.GetPalletMakerListRes()
        pallet_maker_list = self._pallet.load_pallet_maker_list()
        if pallet_maker_list is not None:
            json_format.ParseDict(pallet_maker_list, response)
        return response

    @check_token
    def SetPalletMakerList(self, request, context):
        self._debug('SetPalletMakerList')
        pallet_maker_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )

        self._pallet.save_pallet_maker_list(pallet_maker_dict)
        return conty_data.SetPalletMakerListRes()

    @check_token
    def GetConveyor(self, request: common_data.Empty, context) -> device_data.Conveyor:
        self._debug('GetConveyor')
        response = device_data.Conveyor()
        conveyor_dict = self._device_client.GetConveyor()
        if conveyor_dict is not None:
            json_format.ParseDict(conveyor_dict, response)
        return response

    @check_token
    def SetConveyorName(self, request: common_data.Name, context) -> common_data.Response:
        self._debug('SetConveyorName')
        response = common_data.Response()
        resp = self._device_client.SetConveyorName(name=request.name)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorByName(self, request: common_data.Name, context) -> common_data.Response:
        self._debug('SetConveyorByName')
        response = common_data.Response()
        resp = self._device_client.SetConveyorByName(name=request.name)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorEncoder(self, request: device_data.Encoder, context) -> common_data.Response:
        self._debug('SetConveyorEncoder')
        response = common_data.Response()
        resp = self._device_client.SetConveyorEncoder(
            encoder_type=request.type, channel1=request.channel1, channel2=request.channel2,
            sample_num=request.sample_num, mm_per_tick=request.mm_per_tick, vel_const_mmps=request.vel_const_mmps,
            reversed=request.reversed)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorTrigger(self, request: device_data.Trigger, context) -> common_data.Response:
        self._debug('SetConveyorTrigger')
        response = common_data.Response()
        resp = self._device_client.SetConveyorTrigger(
            trigger_type=request.type, channel=request.channel, detect_rise=request.detect_rise)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorOffset(self, request: common_data.Float, context) -> common_data.Response:
        self._debug('SetConveyorOffset')
        response = common_data.Response()
        resp = self._device_client.SetConveyorOffset(offset_mm=request.value)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorLockedJoint(self, request: common_data.Int, context) -> common_data.Response:
        self._debug('SetConveyorLockedJoint')
        response = common_data.Response()
        resp = self._device_client.SetConveyorLockedJoint(locked_joint=request.value)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorToolLink(self, request: common_data.Int, context) -> common_data.Response:
        self._debug('SetConveyorToolLink')
        response = common_data.Response()
        resp = self._device_client.SetConveyorToolLink(tool_link=request.value)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorStartingPose(self, request: common_data.PosePair, context) -> common_data.Response:
        self._debug('SetConveyorStartingPose')
        response = common_data.Response()
        resp = self._device_client.SetConveyorStartingPose(jpos=request.q, tpos=request.p)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetConveyorTerminalPose(self, request: common_data.PosePair, context) -> common_data.Response:
        self._debug('SetConveyorTerminalPose')
        response = common_data.Response()
        resp = self._device_client.SetConveyorTerminalPose(jpos=request.q, tpos=request.p)
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetConveyorState(self, request: common_data.Empty, context) -> device_data.Conveyor:
        self._debug('GetConveyorState')
        response = device_data.ConveyorState()
        conveyor_dict = self._device_client.GetConveyorState()
        if conveyor_dict is not None:
            json_format.ParseDict(conveyor_dict, response)
        return response

    @check_token
    def GetConveyorObjectDistances(self, request: common_data.Empty, context) -> device_data.Conveyor:
        self._debug('GetConveyorObjectDistances')
        response = device_data.ConveyorObjectDistances()
        res = self._device_client.GetConveyorObjectDistances()
        if res is not None:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def HoldToMoveConveyor(self, request: conty_data.HoldToMoveConveyorReq, context) -> device_data.Conveyor:
        self._debug('HoldToMoveConveyor')
        response = common_data.Response()

        res = self._control_client.MoveConveyor(
            teaching_mode=True, bypass_singular=request.bypass_singular, acc_ratio=request.acc_ratio)

        if isinstance(res, Common.utils.GRPCReturn):
            self._error('HoldToMoveConveyor failed!')
            context.set_code(res.code)
            context.set_details(res.details)
        elif res is not None:
            self.__unmark_target_reached()
            json_format.ParseDict(res, response)
        return response

    @check_token
    def GetConveyorList(self, request: conty_data.GetConveyorListReq, context) -> conty_data.GetConveyorListRes:
        self._debug('GetConveyorList')
        response = conty_data.GetConveyorListRes()
        conveyor_dict = self._config_client.GetConveyorList()
        if conveyor_dict is not None:
            json_format.ParseDict(conveyor_dict, response)
        return response

    @check_token
    def SetConveyorList(self, request: conty_data.SetConveyorListReq, context) -> conty_data.SetConveyorListRes:
        self._debug('SetConveyorList')
        conveyor_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._config_client.SetConveyorList(conveyor_dict)
        return conty_data.SetPalletMakerListRes()

    @check_token
    def CheckAproachRetractValid(self, request, context):
        self._debug('CheckAproachRetractValid')
        framework_data = self.get_framework_data()
        self._debug('cur_jpos: ' + str(framework_data['control_data']['q']))
        self._debug('cur_tpos: ' + str(framework_data['control_data']['p']))
        self._debug('init_jpos: ' + str(list(request.init_jpos)))
        self._debug('tpos: ' + str(list(request.tpos)))
        self._debug('pre_tpos: ' + str(list(request.pre_tpos)))
        self._debug('post_tpos: ' + str(list(request.post_tpos)))
        approach_retract_pack = self._control_client.CheckAproachRetractValid(
            tpos=list(request.tpos),
            init_jpos=list(request.init_jpos),
            # tpos=framework_data['control_data']['p'],
            # init_jpos=framework_data['control_data']['q'],
            pre_tpos=list(request.pre_tpos),
            post_tpos=list(request.post_tpos)
        )
        self._debug('CheckAproachRetractValid 1: ' + str(approach_retract_pack))
        if approach_retract_pack is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            response = control_data.CheckAproachRetractValidRes()

        elif approach_retract_pack['is_valid']:
            response = control_data.CheckAproachRetractValidRes()
            json_format.ParseDict(approach_retract_pack, response)
        else:
            response = control_data.CheckAproachRetractValidRes(
                is_valid=False, response=common_data.Response(msg="Is not valid position"))
        return response

    @check_token
    def GetPalletPointList(self, request, context):
        self._debug('GetPalletPointList')
        self._debug(f'{request}')
        tpos, pallet_pattern, width, height, jpos = self._pallet.get_pallet(request.name)

        pallet_pack = self._control_client.GetPalletPointList(
            tpos=list(tpos),
            jpos=list(jpos),
            pre_tpos=list(request.pre_tpos), post_tpos=list(request.post_tpos),
            pallet_pattern=pallet_pattern, width=width, height=height
        )
        self._debug('Pallet: ' + str(pallet_pack))

        if pallet_pack is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            response = control_data.GetPalletPointListRes()
        else:
            response = control_data.GetPalletPointListRes()
            json_format.ParseDict(pallet_pack, response)
        self._debug('Pallet Resp: ' + str(response))

        return response

    @check_token
    def SetPalletPointList(self, request, context):  # DEPRECATED
        self._debug('SetPalletPointList')
        return super().SetPalletPointList(request, context)

    @check_token
    def SetJointControlGain(self, request, context):
        self._debug('SetJointControlGain')
        if self._config_client.SetJointControlGain(
                kp=list(request.kp), kv=list(request.kv), kl2=list(request.kl2)
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetJointControlGainRes()

    @check_token
    def GetJointControlGain(self, request, context):
        self._debug('GetJointControlGain')
        joint_gains = self._config_client.GetJointControlGain()
        if joint_gains is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetJointControlGainRes()
        response = conty_data.GetJointControlGainRes(
            kp=joint_gains['kp'],
            kv=joint_gains['kv'],
            kl2=joint_gains['kl2']
        )
        return response

    @check_token
    def SetTaskControlGain(self, request, context):
        self._debug('SetTaskControlGain')
        if self._config_client.SetTaskControlGain(
                kp=list(request.kp), kv=list(request.kv), kl2=list(request.kl2)
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return conty_data.SetTaskControlGainRes()

    @check_token
    def GetTaskControlGain(self, request, context):
        self._debug('GetTaskControlGain')
        task_gains = self._config_client.GetTaskControlGain()
        if task_gains is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetTaskControlGainRes()

        return conty_data.GetTaskControlGainRes(
            kp=task_gains['kp'],
            kv=task_gains['kv'],
            kl2=task_gains['kl2']
        )

    @check_token
    def SetImpedanceControlGain(self, request, context):
        self._debug('SetImpedanceControlGain')

        if self._config_client.SetImpedanceControlGain(
                mass=list(request.mass), damping=list(request.damping), stiffness=list(request.stiffness),
                kl2=list(request.kl2)
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetImpedanceControlGainRes()

    @check_token
    def GetImpedanceControlGain(self, request, context):
        self._debug('GetImpedanceControlGain')
        impedance_gains = self._config_client.GetImpedanceControlGain()
        if impedance_gains is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetImpedanceControlGainRes()

        response = conty_data.GetImpedanceControlGainRes(
            mass=impedance_gains['mass'],
            damping=impedance_gains['damping'],
            stiffness=impedance_gains['stiffness'],
            kl2=impedance_gains['kl2'],
        )
        return response

    @check_token
    def SetForceControlGain(self, request, context):
        self._info(f'SetForceControlGain({request.kp}, {request.kv}, {request.kl2}, {request.mass},'
                   f' {request.damping}, {request.stiffness},  {request.kpf}, {request.kif})')

        if self._config_client.SetForceControlGain(
                kp=list(request.kp), kv=list(request.kv), kl2=list(request.kl2),
                mass=list(request.mass), damping=list(request.damping), stiffness=list(request.stiffness),
                kpf=list(request.kpf), kif=list(request.kif)
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetForceControlGainRes()

    @check_token
    def GetForceControlGain(self, request, context):
        self._info('GetForceControlGain')
        force_gains = self._config_client.GetForceControlGain()
        if force_gains is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetForceControlGainRes()

        response = conty_data.GetForceControlGainRes(
            kp=force_gains['kp'],
            kv=force_gains['kv'],
            kl2=force_gains['kl2'],
            mass=force_gains['mass'],
            damping=force_gains['damping'],
            stiffness=force_gains['stiffness'],
            kpf=force_gains['kpf'],
            kif=force_gains['kif'],
        )
        return response

    @check_token
    def SetComplianceControlJointGain(self, request, context):
        self._info(f'SetComplianceControlJointGain({request.kp}, {request.kv}, {request.kl2}, {request.kd}, {request.bd}, {request.rate}, {request.ks}, {request.ki}, {request.km})')
        if self._config_client.SetComplianceControlJointGain(
                kp=request.kp, kv=request.kv, kl2=request.kl2,
                kd=request.kd, bd=request.bd, rate=request.rate,
                ki=request.ki, ks=request.ks, km=request.km
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetComplianceGainRes()

    @check_token
    def GetComplianceControlJointGain(self, request, context):
        self._info('GetComplianceJointGain')
        sensorless_joint_gains = self._config_client.GetComplianceControlJointGain()
        if sensorless_joint_gains is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetComplianceGainRes()

        response = conty_data.GetComplianceGainRes(
            kp=sensorless_joint_gains['kp'],
            kv=sensorless_joint_gains['kv'],
            kl2=sensorless_joint_gains['kl2'],
            kd=sensorless_joint_gains['kd'],
            bd =sensorless_joint_gains['bd'],
            rate=sensorless_joint_gains['rate'],
            ki=sensorless_joint_gains['ki'],
            ks=sensorless_joint_gains['ks'],
            km=sensorless_joint_gains['km']
        )
        return response

    @check_token
    def SetExtAxisControlGain(self, request, context):
        self._info(f'SetExtAxisControlGain({request.kp}, {request.kv}, {request.kl2}')
        if self._has_linear_axis:
            for i, (kp, kv, kl2) in enumerate(zip(request.kp, request.kv, request.kl2)):
                if self._linear_client.set_control_gain(index=i, kp=kp, kv=kv, ki=kl2) is None:
                    context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetExtAxisControlGainRes()

    @check_token
    def GetExtAxisControlGain(self, request, context):
        self._info('GetExtAxisControlGain')
        response = conty_data.GetExtAxisControlGainRes()
        if self._has_linear_axis:
            kp = [0.0, 0.0, 0.0]
            kv = [0.0, 0.0, 0.0]
            kl2 = [0.0, 0.0, 0.0]
            for i in range(3):
                ext_axis_gains = self._linear_client.get_control_gain(i)
                self._warn(f"ext_axis_gains {ext_axis_gains}")
                if ext_axis_gains is None:
                    context.set_code(grpc.StatusCode.UNAVAILABLE)
                    return conty_data.GetExtAxisControlGainRes()
                kp[i] = ext_axis_gains['kp']
                kv[i] = ext_axis_gains['kv']
                kl2[i] = ext_axis_gains['ki']

            response = conty_data.GetExtAxisControlGainRes(
                kp=kp,
                kv=kv,
                kl2=kl2
            )
        return response


    @check_token
    def SetFricComp(self, request, context):
        self._debug('SetFricComp')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetFricComp: ' + str(request_dict))
        res = self._config_client.SetFrictionComp(
            control_comp=request_dict['control_comp'],
            control_comp_levels=request_dict['control_comp_levels'],
            dt_comp=request_dict['dt_comp'],
            dt_comp_levels=request_dict['dt_comp_levels']
        )
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return conty_data.SetFricCompRes(msg='')

    @check_token
    def GetFricComp(self, request, context):
        self._debug('GetFricComp')
        fric_comp = self._config_client.GetFrictionComp()
        if fric_comp is None:
            return None

        fric_config = dict(
            control_comp=fric_comp['control_comp_enable'],
            control_comp_levels=fric_comp['control_comp_levels'],
            dt_comp=fric_comp['teaching_comp_enable'],
            dt_comp_levels=fric_comp['teaching_comp_levels'],
        )

        if fric_config is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetFricCompRes()

        self._debug('GetFricComp: ' + str(fric_config))
        return conty_data.GetFricCompRes(
            control_comp=fric_config['control_comp'],
            control_comp_levels=fric_config['control_comp_levels'],
            dt_comp=fric_config['dt_comp'],
            dt_comp_levels=fric_config['dt_comp_levels'],
        )

    @check_token
    def SetMountPos(self, request, context):
        self._debug('SetMountPos')
        msg = self.__check_reconfiguration_available__()
        if msg is not None:
            return conty_data.SetMountPosRes(msg=msg)

        res = self._config_client.SetMountPos(rot_y=request.ry, rot_z=request.rz)

        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        elif 'code' in res and int(res['code']) == 1:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        return conty_data.SetMountPosRes()

    @check_token
    def GetMountPos(self, request, context):
        self._debug('GetMountPos')

        mounting_angles = self._config_client.GetMountPos()
        if mounting_angles is not None:
            return conty_data.GetMountPosRes(ry=mounting_angles['ry'], rz=mounting_angles['rz'])
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetMountPosRes()

    @check_token
    def SetToolProperty(self, request, context):
        self._debug('SetToolProperty')
        tool_properties = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        res = self._config_client.SetToolProperty(
            mass=tool_properties['mass'],
            center_of_mass=tool_properties['center_of_mass'],
            inertia=tool_properties['inertia'])
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        elif 'code' in res and int(res['code']) == 1:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)

        return conty_data.SetToolPropertyRes()

    @check_token
    def GetToolProperty(self, request, context):
        self._debug('GetToolProperty')
        tool_property = self._config_client.GetToolProperty()
        if tool_property is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetToolPropertyRes()

        response = conty_data.GetToolPropertyRes(
            mass=tool_property['mass'],
            center_of_mass=tool_property['center_of_mass'],
            inertia=tool_property['inertia']
        )
        return response

    @check_token
    def InitCollSensParam(self, request, context):
        self._debug('InitCollSensParam')
        default_collision_params = self._config_client.GetDefaultCollSensParam()
        res = self._config_client.SetCollSensParam(default_collision_params)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response()

    @check_token
    def SetCollSensParam(self, request, context):
        self._debug('SetCollSensParam')
        col_params = json_format.MessageToDict(request,
                                               including_default_value_fields=True,
                                               preserving_proto_field_name=True,
                                               use_integers_for_enums=True)
        res = self._config_client.SetCollSensParam(col_params)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response()

    @check_token
    def GetCollSensParam(self, request, context):
        self._debug('GetCollSensParam')
        collision_params = self._config_client.GetCollSensParam()
        if collision_params is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return config_data.CollisionThresholds()

        response = config_data.CollisionThresholds()
        json_format.ParseDict(collision_params, response)
        return response

    @check_token
    def SetCollSensLevel(self, request, context):
        self._debug('SetCollSensLevel')
        res = self._config_client.SetCollSensLevel(level=request.level)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response(code=0)

    @check_token
    def GetCollSensLevel(self, request, context):
        self._debug('GetCollSensLevel')
        sens_level = self._config_client.GetCollSensLevel()['level']

        if sens_level is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return config_data.CollisionSensLevel()

        return config_data.CollisionSensLevel(level=sens_level)

    @check_token
    def GetCollisonModelMargin(self, request, context):
        self._debug('GetCollisonModelMargin')
        res = self._config_client.GetCollisonModelMargin()

        response = config_data.CollisionModelMargin()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def SetCollisonModelMargin(self, request, context):
        self._debug('SetCollisonModelMargin')
        res = self._config_client.SetCollisonModelMargin(
            collision_margin=request.collision_margin, recover_margin=request.recover_margin)

        response = common_data.Response()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def SetToolShapeList(self, request, context):
        self._debug('SetToolShapeList')
        tool_shape_list = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        res = self._config_client.SetToolShapeList(tool_shape_list)

        response = common_data.Response()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def GetToolShapeList(self, request, context):
        self._debug('GetToolShapeList')
        res = self._config_client.GetToolShapeList()

        response = config_data.ToolShapeList()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def SetEnvironmentList(self, request, context):
        self._debug('SetEnvironmentList')
        env_list = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        res = self._config_client.SetEnvironmentList(env_list)

        response = common_data.Response()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def GetEnvironmentList(self, request, context):
        self._debug('GetEnvironmentList')
        res = self._config_client.GetEnvironmentList()

        response = config_data.EnvironmentList()
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            json_format.ParseDict(res, response)
        return response

    @check_token
    def SetCollPolicy(self, request, context):
        self._debug('SetCollPolicy')
        res = self._config_client.SetCollPolicy(
            policy=request.policy,
            sleep_time=request.sleep_time
        )
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return common_data.Response()

    @check_token
    def GetCollPolicy(self, request, context):
        self._debug('GetCollPolicy')
        collision_policy = self._config_client.GetCollPolicy()

        if collision_policy is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return config_data.CollisionPolicy()

        response = config_data.CollisionPolicy()
        json_format.ParseDict(collision_policy, response)
        return response

    @check_token
    def SetSimpleCollThreshold(self, request, context):
        self._debug('SetSimpleCollThreshold')
        collision_policy = self._config_client.SetSimpleCollThreshold()
        return common_data.Response()

    @check_token
    def PlayTuningProgram(self, request, context):
        self._debug('PlayTuningProgram')
        file_name = os.path.basename(request.file_dir)
        self._info('Play Tuning Program ' + file_name + ' Vel: ' + str(request.vel_level_max))
        prog_response = self._control_client.PlayTuningProgram(
            prog_name=file_name,
            prog_idx=-1,
            tuning_space=request.tuning_space,
            precision=request.precision,
            vel_level_max=request.vel_level_max
        )
        if prog_response is None:
            self._warn('Play Tuning Program ' + file_name + ' failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details('Play Tuning Program ' + file_name + ' failed!')
            return config_data.CollisionThresholds()
        else:
            self._info('Play Tuning Program ' + file_name + ' success')
            self._debug(f'{prog_response}')
            response = config_data.CollisionThresholds()
            json_format.ParseDict(prog_response, response)
            return response

    @check_token
    def StartAutoTuneControlGain(self, request, context):
        self._info('StartAutoTuneControlGain')
        file_name = os.path.basename(request.file_dir)
        if (self._autotune_thread is None) or (not self._autotune_thread.is_alive()):
            self._autotune_thread = threading.Thread(target=autotune_control_gain,
                                                     args = [file_name,
                                                             self._config_client,
                                                             self._control_client,
                                                             self._rtde_client])
            self._autotune_thread.start()
        return common_data.Empty()

    @check_token
    def StopAutoTuneControlGain(self, request, context):
        self._info('StopAutoTuneControlGain')
        autotune_control_gain.flag_stop = True
        return common_data.Empty()

    @check_token
    def SetSafetyLimitConfig(self, request, context):
        self._debug('SetSafetyLimitConfig')
        if self._config_client.SetSafetyLimits(
                power_limit=request.power_limit, power_limit_ratio=request.power_limit_ratio,
                tcp_force_limit=request.tcp_force_limit, tcp_force_limit_ratio=request.tcp_force_limit_ratio,
                tcp_speed_limit=request.tcp_speed_limit, tcp_speed_limit_ratio=request.tcp_speed_limit_ratio
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetSafetyLimitConfigRes()

    @check_token
    def GetSafetyLimitConfig(self, request, context):
        self._debug('GetSafetyLimitConfig')
        safety_limit_config = self.get_framework_data()["safety_limits"]
        if safety_limit_config is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetSafetyLimitConfigRes()

        if safety_limit_config['joint_upper_limits'] is not None:
            safety_limit_config.pop('joint_upper_limits')

        if safety_limit_config['joint_lower_limits'] is not None:
            safety_limit_config.pop('joint_lower_limits')

        response = conty_data.GetSafetyLimitConfigRes()
        json_format.ParseDict(safety_limit_config, response)
        return response

    @check_token
    def SetSafetyStopConfig(self, request, context):
        self._debug('SetSafetyStopConfig')

        if self._config_client.SetSafetyStopConfig(
                jpos_limit_stop_cat=request.joint_position_limit_stop_cat,
                jvel_limit_stop_cat=request.joint_speed_limit_stop_cat,
                jtau_limit_stop_cat=request.joint_torque_limit_stop_cat,
                tvel_limit_stop_cat=request.tcp_speed_limit_stop_cat,
                tforce_limit_stop_cat=request.tcp_force_limit_stop_cat,
                power_limit_stop_cat=request.power_limit_stop_cat,
                safegd_stop_cat=request.safegd_stop_cat,
                safegd_type=request.safegd_type
        ) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.SetSafetyStopConfigRes()

    @check_token
    def GetSafetyStopConfig(self, request, context):
        self._debug('GetSafetyStopConfig')
        safety_stop_config = self._config_client.GetSafetyStopConfig()

        if safety_stop_config is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetSafetyStopConfigRes()

        response = conty_data.GetSafetyStopConfigRes()
        json_format.ParseDict(safety_stop_config, response)
        return response

    @check_token
    def GetSafetyConfigHash(self, request, context):
        self._debug('GetSafetyConfigHash')
        concatenated_content = ""
        for file_path in Common.Config().SAFETY_PATH_LIST:
            if os.path.isfile(get_abs_path(file_path)):
                with open(get_abs_path(file_path), 'r', encoding='utf-8') as file:
                    concatenated_content += file.read()
        response = conty_data.GetSafetyConfigHashRes(hash=hash_data(concatenated_content))
        return response

    @check_token
    def GetKinematicsParams(self, request, context):
        self._debug('GetSafetyStopConfig')
        kin_params = self._config_client.GetKinematicsParams()
        response = config_data.KinematicsParams()
        json_format.ParseDict(kin_params, response)
        return response

    @check_token
    def SetToolList(self, request, context):
        self._debug('SetToolList')
        tools_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetToolList: ' + str(tools_dict))
        resp = self._config_client.SetToolList(tools_dict)
        response = common_data.Response()
        json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetToolList(self, request, context):
        self._debug('GetToolList')
        tool_list = self._config_client.GetToolList()
        self._debug('GetToolList: ' + str(tool_list))
        response = config_data.ToolList()
        if tool_list is not None:
            json_format.ParseDict(tool_list, response)
        return response

    @check_token
    def RebootSW(self, request, context):
        self._debug('Reboot')
        self.__reboot = True
        self.__sw_update = True
        # self._control_client.Reboot()
        return conty_data.RebootRes()

    @check_token
    def Reboot(self, request, context):
        self._debug('Reboot')
        self.__reboot = True
        # self.__sw_update = True
        # self._control_client.Reboot()
        return conty_data.RebootRes()

    @check_token
    def PowerOff(self, request, context):
        self._debug('PowerOff')
        self._control_client.StopMotion()
        self.__power_off = True
        return conty_data.PowerOffRes()

    @try_wrap
    def UpdateIndySW(self, request_iterator, context):
        file_size = 0
        message = "Success"

        print('Software Update Request')
        self.__sw_update = False
        file_dir = Common.Config.SW_UPDATE_FILE_NAME
        try:  # Save file to disk
            with open(file_dir, 'wb') as f:
                for chunk in request_iterator:
                    print('chunk: ' + str(len(chunk.file_buffer)))
                    file_size += len(chunk.file_buffer)
                    f.write(chunk.file_buffer)

        except Exception as ex:
            self._error('UpdateIndySW Error: ' + str(traceback.format_exc()))

        self.__sw_update = True
        print('Software Update Request Done')
        return conty_data.UpdateIndySWRes(file_length=file_size, msg=message)

    @check_token
    def SetDOConfigList(self, request, context):
        self._debug('SetDOConfigList')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetDOConfigList: ' + str(request_dict))
        self._config_client.SetDOConfigList(request_dict)
        return common_data.Response()

    @check_token
    def GetDOConfigList(self, request, context):
        self._debug('GetDOConfigList')
        response = config_data.DOConfigList()
        do_config_list = self._config_client.GetDOConfigList()
        self._debug('GetDOConfigList: ' + str(do_config_list))
        if do_config_list is not None:
            json_format.ParseDict(do_config_list, response)
        return response

    @check_token
    def SetDIConfigList(self, request, context):
        self._debug('SetDIConfigList')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetDIConfigList' + str(request_dict))
        self._config_client.SetDIConfigList(request_dict)
        return common_data.Response()

    @check_token
    def GetDIConfigList(self, request, context):
        self._debug('GetDIConfigList')
        response = config_data.DIConfigList()
        di_config_list = self._config_client.GetDIConfigList()
        self._debug('GetDIConfigList' + str(di_config_list))
        if di_config_list is not None:
            json_format.ParseDict(di_config_list, response)
        return response

    @check_token
    def SetAutoServoOff(self, request, context):
        self._debug('SetAutoServoOff')
        res = self._config_client.SetAutoServoOff(enable=request.enable, time=request.time)
        if res is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return conty_data.SetAutoServoOffRes()

    @check_token
    def GetAutoServoOff(self, request, context):
        self._debug('GetAutoServoOff')
        auto_servooff_config = self._config_client.GetAutoServoOff()
        if auto_servooff_config is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return conty_data.GetAutoServoOffRes()

        response = conty_data.GetAutoServoOffRes(
            enable=auto_servooff_config['enable'],
            time=auto_servooff_config['time']
        )
        return response

    @check_token
    def ExecuteTool(self, request, context):
        self._debug('ExecuteTool')
        result = self._device_client.ExecuteTool(request.name)
        response = common_data.Response()
        json_format.ParseDict(result, response)
        return response

    @check_token
    def GetLogList(self, request, context):
        self._debug('GetLogList')
        log_file_names, sizes, modified_dates = self._logger.get_log_list()
        response = conty_data.GetLogListRes(
            log_file_names=log_file_names,
            sizes=sizes,
            modified_dates=modified_dates
        )
        return response

    @check_token
    def GetLogContent(self, request, context):
        self._debug('GetLogContent')
        res, log_content = self._logger.get_log_file(request.file_name)
        if res:
            yield conty_data.GetLogContentRes(content=bytes(log_content), msg="Success")
        else:
            yield conty_data.GetLogContentRes(msg="Getting Log File Failed!")

    @check_token
    def GetLogContentList(self, request, context):
        self._debug('GetLogContentList')
        log_content_list = self._logger.get_log_files(request.file_name_list)
        yield conty_data.GetLogContentListRes(content_list=log_content_list, msg="Success")

    @check_token
    def GetLog(self, request, context):
        self._debug('GetLog')
        return conty_data.GetLogRes()

    @check_token
    def SetOSDateTime(self, request, context):
        self._debug('SetOSDateTime')
        cmd = "date -s \"{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}\"".format(request.year,
                                                                             request.month,
                                                                             request.day,
                                                                             request.hour,
                                                                             request.minute,
                                                                             request.second)
        print(cmd)
        os.system(cmd)
        return common_data.Response()#(code=0)

    @check_token
    def GetFile(self, request, context):
        self._info('GetFile: ' + request.file_dir)
        file_content = self.__read_program_file(get_abs_path(request.file_dir))
        if len(file_content) > 0:
            yield conty_data.GetFileRes(buffer=bytes(file_content), msg='Success')
        else:
            yield conty_data.GetFileRes(msg='Program Not Found')

    @check_token
    def SetFile(self, request_iterator, context):
        self._debug('SetFile')
        file_dir = ""
        message = ""
        for chunk in request_iterator:
            file_dir = get_abs_path(chunk.file_dir)
            content = chunk.buffer
            try:
                with open(file_dir, 'wb') as f:
                    f.write(content)
                message = 'Success'
                self._info('SetFile ' + chunk.file_dir + ' success')

            except Exception as ex:
                file_dir = ''
                message = "File content couldn't be saved because of " + str(ex)
                self._error("File content couldn't be saved because of " + str(ex))

        return conty_data.SetFileRes(file_length=os.path.getsize(file_dir), msg=message)

    @check_token
    def RenameFile(self, request, context):
        self._debug('RenameFile')
        # cur_file_dir = os.path.basename(request.cur_file_dir)
        # new_file_dir = os.path.basename(request.new_file_dir)
        cur_file_dir = get_abs_path(request.cur_file_dir)
        new_file_dir = get_abs_path(request.new_file_dir)
        cur_file_content = self.__read_program_file(cur_file_dir)
        new_file_content = self.__read_program_file(new_file_dir)

        self._debug('RenameFile ' + os.path.basename(request.cur_file_dir) +
                    ' to ' + os.path.basename(request.new_file_dir))

        message = ''
        if len(cur_file_content) > 0 and len(new_file_content) == 0:
            # Create new file
            try:
                with open(new_file_dir, 'wb') as f:
                    f.write(cur_file_content)
                message = ''

                # Remove old file
                self.__remove_program_file(cur_file_dir)

            except Exception as ex:
                message = 'Rename failed: ' + str(ex)
                self._error('Rename failed: ' + str(ex))

        return conty_data.RenameFileRes(msg=message)

    @check_token
    def RemoveFile(self, request, context):
        self._info('RemoveFile ' + os.path.basename(request.file_dir))
        file_dir = get_abs_path(request.file_dir)
        self.__remove_program_file(file_dir)
        return conty_data.RemoveFileRes(msg='')

    @check_token
    def GetIndexProgramList(self, request, context):
        self._debug('GetIndexProgramList')
        prog_list = self.__load_program_list(folder_dir=Common.Config().INDEX_PROGRAM_DIR)

        # Parse program indices
        indices = []
        for prog in prog_list["dir"]:
            file_name = os.path.basename(prog)
            indices.append(int(file_name.split('.')[0]))

        return conty_data.GetIndexProgramListRes(
            indices=indices,
            program_dirs=prog_list["dir"],
            sizes=prog_list["size"],
            modified_dates=prog_list["time"]
        )

    @check_token
    def GetProgramList(self, request, context):
        self._info('GetProgramList')
        prog_list = self.__load_program_list(folder_dir=Common.Config().PROGRAM_DIR)

        return conty_data.GetProgramListRes(
            program_dirs=prog_list["dir"],
            sizes=prog_list["size"],
            modified_dates=prog_list["time"]
        )

    @check_token
    def PlayProgram(self, request, context):
        self._info('PlayProgram')
        if Common.Config().USE_AUTO_MODE and Common.Config().USE_SAFETYIO and Common.Config().USE_INDYKEY:
            framework_data = self.get_framework_data()
            if framework_data['safety_control_data']['auto_mode']:
                self._warn('PlayProgram from Conty is not allowed in AUTO mode with IndyKey')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                return conty_data.PlayProgramRes()
        file_name = os.path.basename(request.file_dir)
        if self._control_client.PlayProgram(
                prog_name=file_name,
                prog_idx=-1
        ) is None:
            self._warn('Play Program ' + file_name + ' failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._info('Play Program ' + file_name)

        return conty_data.PlayProgramRes()

    @check_token
    def PlayProgramLine(self, request, context):
        self._info('PlayProgram')
        if Common.Config().USE_AUTO_MODE and Common.Config().USE_SAFETYIO and Common.Config().USE_INDYKEY:
            framework_data = self.get_framework_data()
            if framework_data['safety_control_data']['auto_mode']:
                self._warn('PlayProgram from Conty is not allowed in AUTO mode with IndyKey')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                return conty_data.PlayProgramRes()
        file_name = os.path.basename(request.file_dir)
        start_idx = int(os.path.basename(request.start_line))
        if self._control_client.PlayProgramLine(
                prog_name=file_name,
                prog_idx=start_idx
        ) is None:
            self._warn('Play Program ' + file_name + ' failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._info('Play Program ' + file_name)

        return conty_data.PlayProgramRes()

    @check_token
    def PlayIndexProgram(self, request, context):
        self._debug('PlayIndexProgram')
        if Common.Config().USE_AUTO_MODE and Common.Config().USE_SAFETYIO and Common.Config().USE_INDYKEY:
            framework_data = self.get_framework_data()
            if framework_data['safety_control_data']['auto_mode']:
                self._warn('PlayProgram from Conty is not allowed in AUTO mode with IndyKey')
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                return conty_data.PlayProgramRes()
        if self._control_client.PlayProgram(
                prog_name='',
                prog_idx=request.index
        ) is None:
            self._error('Play Index Program ' + str(request.index) + ' failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        else:
            self._debug('Play Index Program ' + str(request.index))
        return conty_data.PlayIndexProgramRes()

    @check_token
    def ResumeProgram(self, request, context):
        self._debug('ResumeProgram')
        if self._control_client.ResumeProgram() is None:
            self._error('Resume Program failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.ResumeProgramRes()

    @check_token
    def StopProgram(self, request, context):
        self._debug('StopProgram')
        if self._control_client.StopProgram() is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.StopProgramRes()

    @check_token
    def PauseProgram(self, request, context):
        self._debug('PauseProgram')
        if self._control_client.PauseProgram() is None:
            self._error('Pause Program failed!')
            context.set_code(grpc.StatusCode.UNAVAILABLE)

        return conty_data.PauseProgramRes()

    @check_token
    def GetOnStartProgramConfig(self, request, context):
        self._debug('GetOnStartProgramConfig')
        on_start_program_index = self._config_client.GetOnStartProgramConfig()

        prog_list = self.__load_program_list(folder_dir=Common.Config().INDEX_PROGRAM_DIR)

        # Parse program indices
        indices = []
        for prog in prog_list["dir"]:
            prog_name = os.path.basename(prog)
            prog_idx = int(prog_name.split('.')[0])
            if prog_idx == on_start_program_index['index']:
                return conty_data.GetOnStartProgramConfigRes(
                    auto_run=on_start_program_index['auto_run'],
                    index=on_start_program_index['index'] - 1,
                    file_dir=os.path.basename(prog_name.split('.')[1]))

        return conty_data.GetOnStartProgramConfigRes(auto_run=False, index=-1, file_dir='')

    @check_token
    def SetOnStartProgramConfig(self, request, context):
        self._debug('SetOnStartProgramConfig')
        self._config_client.SetOnStartProgramConfig(auto_run=request.auto_run, index=request.index + 1)
        return conty_data.SetOnStartProgramConfigRes()

    ############################
    # Un-implemented
    ############################

    @check_token
    def GetVariableList(self, request, context):
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug('GetVariableList')
        framework_data = self.get_framework_data()

        response = conty_data.GetVariableListRes()
        result = []
        modbus_var_list = self._control_client.GetModbusVariable()  # include name
        name_list = self._control_client.GetVariableNameList()
        int_var_list = self._control_client.GetIntVariable()
        bool_var_list = self._control_client.GetBoolVariable()
        float_var_list = self._control_client.GetFloatVariable()
        jpos_var_list = self._control_client.GetJPosVariable()
        tpos_var_list = self._control_client.GetTPosVariable()
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug('Modbus vars: ' + str(modbus_var_list))
            self._debug('Name vars: ' + str(name_list))
            self._debug('Int vars: ' + str(int_var_list))
            self._debug('Float vars: ' + str(float_var_list))
            self._debug('Jpos vars: ' + str(jpos_var_list))
            self._debug('TPos vars: ' + str(tpos_var_list))
            self._debug('Program state: ' + str(framework_data['program_data']['program_state']))

        for var in modbus_var_list:
            result.append(dict(name=var["name"], addr=var["addr"], type="M", mvar=var["value"]))

        for name in name_list:
            if not name['in_watching']:
                continue
            if name['type'] == "I":
                for var in int_var_list:
                    if name['addr'] == var["addr"]:
                        result.append(dict(name=name["name"], addr=var["addr"], type="I", ivar=var["value"]))
                        break
            elif name['type'] == "B":
                for var in bool_var_list:
                    if name['addr'] == var["addr"]:
                        result.append(dict(name=name["name"], addr=var["addr"], type="B", bvar=var["value"]))
                        break
            elif name['type'] == "F":
                for var in float_var_list:
                    if name['addr'] == var["addr"]:
                        result.append(dict(name=name["name"], addr=var["addr"], type="F", fvar=var["value"]))
                        break
            elif name['type'] == "JPOS":
                for var in jpos_var_list:
                    if name['addr'] == var["addr"]:
                        result.append(dict(name=name["name"], addr=var["addr"], type="JPOS", jpos=var["jpos"]))
                        break
            elif name['type'] == "TPOS":
                for var in tpos_var_list:
                    if name['addr'] == var["addr"]:
                        result.append(dict(name=name["name"], addr=var["addr"], type="TPOS", tpos=var["tpos"]))
                        break
        if result:
            json_format.ParseDict(dict(variables=result), response)
        return response

    @check_token
    def GetMonitoringVariableList(self, request, context):
        self._info('GetMonitoringVariableList')
        return conty_data.GetMonitoringVariableListRes()

    @check_token
    def SetMonitoringVariableList(self, request, context):
        self._info('SetMonitoringVariableList')
        return conty_data.SetMonitoringVariableListRes()

    @check_token
    def SetInching(self, request, context):
        self._debug('SetInching')
        return conty_data.SetInchingRes()

    @check_token
    def StopInching(self, request, context):
        self._debug('StopInching')
        return conty_data.StopInchingRes()

    @check_token
    def SetArc(self, request, context):
        self._debug('SetArc')
        return conty_data.SetArcRes()

    @check_token
    def SetTouch(self, request, context):
        self._debug('SetTouch')
        return conty_data.SetTouchRes()

    @check_token
    def SetGas(self, request, context):
        self._debug('SetGas')
        return conty_data.SetGasRes()

    @check_token
    def IsTouched(self, request, context):
        self._debug('IsTouched')
        return conty_data.IsTouchedRes()

    @check_token
    def GetVisionServerList(self, request, context):
        self._debug('GetVisionServerList')
        response = conty_data.GetVisionServerListRes()
        vision_server_list = self._config_client.GetVisionServerList()
        if vision_server_list is not None:
            json_format.ParseDict(vision_server_list, response)
        return response

    @check_token
    def SetVisionServerList(self, request, context):
        self._info('SetVisionServerList')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._config_client.SetVisionServerList(request_dict)
        return conty_data.SetVisionServerListRes()

    @check_token
    def GetVisionObjectList(self, request, context):
        self._debug('GetVisionObjectList')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        vision_server = request_dict['vision_server']  # name of vision server
        if vision_server['vision_server_type'] == 0:  # IndyEye
            self._debug('GetVisionObjectList: ' + str(vision_server))
            try:
                indyeye_client = IndyEyeClient(vision_server['ip'], vision_server['port'])
                detected_objects = indyeye_client.get_object_list()
                return conty_data.GetVisionObjectListRes(objects=detected_objects)

            except grpc.RpcError as ex:
                self._error(str(ex))
                return conty_data.GetVisionObjectListRes(msg='Vision Server is unavailable')
        else:
            return conty_data.GetVisionObjectListRes(msg='Unsupported Vision Type')

    @check_token
    def GetVisionDetection(self, request, context):
        self._debug('GetVisionDetection')
        framework_data = self.get_framework_data()

        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        response = device_data.VisionResult()

        self._info('GetVisionDetection ' + str(request_dict))
        vision_server = request_dict['vision_server']  # name of vision server
        obj_name = request_dict['object']
        vision_frame = request_dict['frame_type']

        if vision_server['vision_server_type'] == 0:  # IndyEye
            try:
                indyeye_client = IndyEyeClient(vision_server['ip'], vision_server['port'])
                detected_objects = indyeye_client.get_object_list()
                detected_objects.insert(0,'all')
                self._debug('Detected: ' + str(detected_objects))
                if (obj_name in detected_objects) or ((obj_name == 'all') and (len(detected_objects) > 0)):
                    # if obj_name == 'all':
                    #     obj_name = detected_objects[0]
                    obj_idx = detected_objects.index(obj_name)
                    task_pos = Common.Utils.pos_to_transform(framework_data['control_data']['p'])  # Trt (mm)
                    ref_frame = Common.Utils.pos_to_transform(framework_data['control_data']['ref_frame'])  # Tbr (mm)
                    tool_frame = Common.Utils.pos_to_transform(framework_data['control_data']['tool_frame'])  # Tet (mm)

                    # pure robot task pose: Tbe = Tbr * Trt * inv(Tet)
                    robot_pos = np.matmul(np.matmul(ref_frame, task_pos), np.linalg.inv(tool_frame))
                    robot_pos[:3, 3] /= 1000  # convert to m
                    robot_pos = Common.Utils.transform_to_pos(robot_pos)  # Tbe

                    interfaces = NetworkManager.list_interfaces()
                    local_ip = ""
                    for iface in interfaces:
                        if iface == 'lo':
                            continue
                        reachable = NetworkManager.check_connection_via_iface(iface, vision_server['ip'], vision_server['port'])
                        if reachable:
                            local_ip, netmask = NetworkManager.get_ip_and_netmask(iface)
                            break
                    self._info('Robot IP: ' + local_ip)
                    self._info('Robot Pos: ' + str(framework_data['control_data']['p']))
                    self._info('Robot OriPos: ' + str(robot_pos))
                    self._info('Vision Frame: ' + str(vision_frame))
                    frame, cls, detected, passed, msg = indyeye_client.detect_by_object_name(obj_idx, vision_frame,
                                                                                             robot_pos, local_ip)
                    if frame is not None:
                        frame[0] *= 1000  # convert to mm
                        frame[1] *= 1000  # convert to mm
                        frame[2] *= 1000  # convert to mm
                        if vision_frame == 1:  # end-effector pose case
                            frame = Common.Utils.pos_to_transform(frame)  # Tbe (mm)
                            # robot task pose on current frames: Trt = inv(Tbr) * Tbe * Tet
                            frame = np.matmul(np.matmul(np.linalg.inv(ref_frame), frame), tool_frame)
                            frame = Common.Utils.transform_to_pos(frame)  # Trt (mm)
                        # else:  # object pose case
                        #    frame # Tbo

                    detect_vision_dict = dict()
                    detect_vision_dict['detected'] = detected
                    detect_vision_dict['passed'] = passed
                    detect_vision_dict['object'] = obj_name
                    if frame is None:
                        detect_vision_dict['frame'] = [0, 0, 0, 0, 0, 0]
                    else:
                        detect_vision_dict['frame'] = list(frame)
                    if msg is not None:
                        detect_vision_dict['msg'] = msg
                    detect_vision_dict['frame_type'] = vision_frame  # OBJECT=0, END_EFFECTOR=1
                    self._info('Detect frame: ' + str(detect_vision_dict))
                    json_format.ParseDict(detect_vision_dict, response)

            except grpc.RpcError as ex:
                response = device_data.VisionResult(msg='Vision Server is unavailable')
        elif vision_server['vision_server_type'] == 1:
            try:
                self._info('vision server type is photoneo, and is gonna call deviceclient photoneodetection')
                solution_id = request_dict['solution_id']
                vision_id = request_dict['vision_id']
                result = self._device_client.GetPhotoneoDetection(vision_server, obj_name, vision_frame, solution_id, vision_id)
                self._info('result dictionary: ' + str(result))
                json_format.ParseDict(result, response)
            except grpc.RpcError as ex:
                response = device_data.VisionResult(msg='Vision Server is unavailable')
        return response


    @check_token
    def GetVisionRetrieval(self, request, context):
        framework_data = self.get_framework_data()

        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        response = device_data.VisionResult()

        self._info('GetVisionRetrieval ' + str(request_dict))
        vision_server = request_dict['vision_server']  # name of vision server
        obj_name = request_dict['object']
        vision_frame = request_dict['frame_type']

        if vision_server['vision_server_type'] == 0:  # IndyEye
            try:
                indyeye_client = IndyEyeClient(vision_server['ip'], vision_server['port'])
                detected_objects = indyeye_client.get_object_list()
                detected_objects.insert(0,'all')
                self._debug('Detected: ' + str(detected_objects))
                if (obj_name in detected_objects) or ((obj_name == 'all') and (len(detected_objects) > 0)):
                    # if obj_name == 'all':
                    #     obj_name = detected_objects[0]
                    obj_idx = detected_objects.index(obj_name)

                    self._info('Vision Frame: ' + str(vision_frame))
                    frame, cls, detected, passed, msg = indyeye_client.retrieve_by_object_name(obj_idx, vision_frame)
                    if frame is not None:
                        ref_frame = Common.Utils.pos_to_transform(framework_data['control_data']['ref_frame'])  # Tbr (mm)
                        tool_frame = Common.Utils.pos_to_transform(framework_data['control_data']['tool_frame'])  # Tet (mm)

                        frame[0] *= 1000  # convert to mm
                        frame[1] *= 1000  # convert to mm
                        frame[2] *= 1000  # convert to mm
                        if vision_frame == 1:  # end-effector pose case
                            frame = Common.Utils.pos_to_transform(frame)  # Tbe (mm)
                            # robot task pose on current frames: Trt = inv(Tbr) * Tbe * Tet
                            frame = np.matmul(np.matmul(np.linalg.inv(ref_frame), frame), tool_frame)
                            frame = Common.Utils.transform_to_pos(frame)  # Trt (mm)
                        # else:  # object pose case
                        #    frame # Tbo

                    detect_vision_dict = dict()
                    detect_vision_dict['detected'] = detected
                    detect_vision_dict['passed'] = passed
                    detect_vision_dict['object'] = obj_name
                    if frame is None:
                        detect_vision_dict['frame'] = [0, 0, 0, 0, 0, 0]
                    else:
                        detect_vision_dict['frame'] = list(frame)
                    if msg is not None:
                        detect_vision_dict['msg'] = msg
                    detect_vision_dict['frame_type'] = vision_frame  # OBJECT=0, END_EFFECTOR=1
                    self._info('Detect frame: ' + str(detect_vision_dict))
                    json_format.ParseDict(detect_vision_dict, response)

            except grpc.RpcError as ex:
                if __name__ == '__main__':
                    response = device_data.VisionResult(msg='Vision Server is unavailable')
        elif vision_server['vision_server_type'] == 1:
            try:
                solution_id = request_dict['solution_id']
                vision_id = request_dict['vision_id']
                result = self._device_client.GetPhotoneoRetrieval(vision_server, obj_name, vision_frame, solution_id, vision_id)
                json_format.ParseDict(result, response)
            except grpc.RpcError as ex:
                response = device_data.VisionResult(msg='Vision Server is unavailable')

        return response

    @check_token
    def GetGcodeMotionList(self, request, context):
        self._info('GetGcodeMotionList')
        if not os.path.exists(Common.Config().GCODE_DIR):
            os.makedirs(Common.Config().GCODE_DIR)
        gcode_list = self.__load_gcode_list(folder_dir=Common.Config().GCODE_DIR)

        return conty_data.GetGcodeMotionListRes(
            gcode_file_name=gcode_list
        )

    @check_token
    def GetModbusServerList(self, request, context):
        self._debug('GetModbusServerList')
        response = conty_data.GetModbusServerListRes()
        modbus_server_list = self._config_client.GetModbusServerList()
        if modbus_server_list is not None:
            self._debug('GetModbusServerList: ' + str(modbus_server_list))
            json_format.ParseDict(modbus_server_list, response)
        return response

    @check_token
    def SetModbusServerList(self, request, context):
        self._debug('SetModbusServerList')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetModbusServerList: ' + str(request_dict))
        self._config_client.SetModbusServerList(request_dict)
        return conty_data.SetModbusServerListRes()

    @check_token
    def CheckModbusConnection(self, request, context):
        self._debug('CheckModbusConnection')
        request_dict = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._info('CheckModbusConnection: ' + request_dict['modbus_servers']['ip'])
        _modbus_client = ModbusClient(host=request_dict['modbus_servers']['ip'],
                                      port=request_dict['modbus_servers']['port'], debug=False)
        res = "" if _modbus_client.open() else "False"
        _modbus_client.close()
        return conty_data.CheckModbusConnectionRes(msg=res)

    @check_token
    def GetCustomPosList(self, request, context):
        self._debug('GetCustomPosList')
        custom_pos_list = self._config_client.GetCustomPosList()
        self._debug('GetCustomPosList: ' + str(custom_pos_list))
        response = conty_data.GetCustomPosListRes()
        if custom_pos_list is None:
            self._error("Failed GetCustomPosList")
        else:
            json_format.ParseDict(custom_pos_list, response)

        return response

    @check_token
    def SetCustomPosList(self, request, context):
        self._debug('SetCustomPosList')
        custom_pos_list = json_format.MessageToDict(
            request,
            including_default_value_fields=True,
            use_integers_for_enums=True,
            preserving_proto_field_name=True
        )
        self._debug('SetCustomPosList: ' + str(custom_pos_list))
        self._config_client.SetCustomPosList(custom_pos_list)
        return conty_data.SetCustomPosListRes()

    @check_token
    def GetAutoModeConfig(self, request: common_data.Empty, context):
        if Common.Config().USE_AUTO_MODE:
            if Common.Config().USE_SAFETYIO and Common.Config().USE_INDYKEY:
                auto_mode_config = conty_data.GetAutoModeConfigRes.AutoModeConfig.AUTO_MODE_BY_INDYKEY
            else:
                auto_mode_config = conty_data.GetAutoModeConfigRes.AutoModeConfig.AUTO_MODE_BY_CONTY
        else:
            auto_mode_config = conty_data.GetAutoModeConfigRes.AutoModeConfig.AUTO_MODE_NOT_USED
        response = conty_data.GetAutoModeConfigRes(config = auto_mode_config)
        return response

    @check_token
    def SetAutoMode(self, request: device_data.SetAutoModeReq, context):
        res_dict = self._device_client.SetAutoMode(request.on)
        response = device_data.SetAutoModeRes()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def CheckAutoMode(self, request: common_data.Empty, context):
        res_dict = self._device_client.CheckAutoMode()
        response = device_data.CheckAutoModeRes()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def CheckReducedMode(self, request: common_data.Empty, context):
        res_dict = self._device_client.CheckReducedMode()
        response = device_data.CheckReducedModeRes()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def GetReducedRatio(self, request: common_data.Empty, context):
        framework_data = self.get_framework_data()
        res_dict = framework_data['reduced_ratio']
        response = config_data.GetReducedRatioRes()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def GetReducedSpeed(self, request: common_data.Empty, context):
        res_dict = self._config_client.GetReducedSpeed()
        response = config_data.GetReducedSpeedRes()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def SetReducedSpeed(self, request: config_data.SetReducedSpeedReq, context):
        res_dict = self._config_client.SetReducedSpeed(request.speed)
        response = common_data.Response()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def GetStopState(self, request: common_data.Empty, context) -> rtde_data.StopState:
        res_dict = self._rtde_client.GetStopState()
        response = rtde_data.StopState()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def GetSafetyFunctionState(self, request: common_data.Empty, context) -> device_data.SafetyFunctionState:
        res_dict = self._device_client.GetSafetyFunctionState()
        response = device_data.SafetyFunctionState()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def RequestSafetyFunction(self, request: device_data.SafetyFunctionState, context) -> common_data.Response:
        res_dict = self._device_client.RequestSafetyFunction(id=request.id,
                                                             state=request.state)
        response = common_data.Response()
        if res_dict is not None:
            json_format.ParseDict(res_dict, response)
        return response

    @check_token
    def GetTeleOpDevice(self, request: common_data.Empty, context) -> control_data.TeleOpDevice:
        self._debug('GetTeleOpDevice')
        device_dict = self._control_client.GetTeleOpDevice()
        response = control_data.TeleOpDevice()
        if device_dict is not None:
            json_format.ParseDict(device_dict, response)
        return response

    @check_token
    def GetTeleOpState(self, request: common_data.Empty, context) -> control_data.TeleOpState:
        self._debug('GetTeleOpState')
        tele_state = self._control_client.GetTeleOpState()
        response = control_data.TeleOpState()
        if tele_state is not None:
            json_format.ParseDict(tele_state, response)
        return response

    @check_token
    def ConnectTeleOpDevice(self, request: control_data.TeleOpDevice, context) -> common_data.Response:
        self._debug('ConnectTeleOpDevice')
        resp = self._control_client.ConnectTeleOpDevice(
            name=request.name, type=request.type,
            ip=request.ip, port=request.port
        )
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def DisConnectTeleOpDevice(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('DisConnectTeleOpDevice')
        resp = self._control_client.DisConnectTeleOpDevice()
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def ReadTeleOpInput(self, request: common_data.Empty, context) -> control_data.TeleP:
        self._debug('ReadTeleOpInput')
        resp = self._control_client.ReadTeleOpInput()
        response = control_data.TeleP()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StartTeleCalib(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StartTeleCalib')
        resp = self._control_client.StartTeleOp(mode=control_data.TeleMode.TELE_CALIB,
                                                method=control_data.TeleMethod.TELE_RECORD_ABSOLUTE)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StartTeleRecord(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StartTeleRecord')
        resp = self._control_client.StartTeleOp(mode=control_data.TeleMode.TELE_RECORD,
                                                method=control_data.TeleMethod.TELE_RECORD_ABSOLUTE)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StartTelePlay(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StartTelePlay')
        resp = self._control_client.StartTeleOp(mode=control_data.TeleMode.TELE_PLAY,
                                                method=control_data.TeleMethod.TELE_RECORD_ABSOLUTE)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StartTeleJogL(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StartTeleJogL')
        resp = self._control_client.StartTeleOp(mode=control_data.TeleMode.TELE_RAW,
                                                method=control_data.TeleMethod.TELE_TASK_RELATIVE)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StartTeleJogJ(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StartTeleJogJ')
        resp = self._control_client.StartTeleOp(mode=control_data.TeleMode.TELE_RAW,
                                                method=control_data.TeleMethod.TELE_JOINT_RELATIVE)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def StopTeleOp(self, request: common_data.Empty, context) -> common_data.Response:
        self._debug('StopTeleOp')
        resp = self._control_client.StopTeleOp()
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetPlayRate(self, request: control_data.TelePlayRate, context) -> common_data.Response:
        self._debug('SetPlayRate')
        resp = self._control_client.SetPlayRate(request.rate)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SetTeleOpParams(self, request: config_data.TeleOpParams, context) -> common_data.Response:
        self._debug('SetTeleOpParams')
        resp = self._config_client.SetTeleOpParams(request.smooth_factor, request.cutoff_freq, request.error_gain)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetTeleOpParams(self, request: common_data.Empty, context) -> config_data.TeleOpParams:
        self._debug('GetTeleOpParams')
        resp = self._config_client.GetTeleOpParams()
        response = config_data.TeleOpParams()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetPlayRate(self, request: common_data.Empty, context) -> control_data.TelePlayRate:
        self._debug('GetPlayRate')
        resp = self._control_client.GetPlayRate()
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetTeleFileList(self, request: common_data.Empty, context) -> control_data.TeleOpFileList:
        self._debug('GetTeleFileList')
        resp = self._control_client.GetTeleFileList()
        response = control_data.TeleOpFileList()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def SaveTeleMotion(self, request: control_data.TeleFileReq, context) -> common_data.Response:
        self._debug('SaveTeleMotion')
        resp = self._control_client.SaveTeleMotion(name=request.name)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def LoadTeleMotion(self, request: control_data.TeleFileReq, context) -> common_data.Response:
        self._debug('LoadTeleMotion')
        resp = self._control_client.LoadTeleMotion(name=request.name)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def DeleteTeleMotion(self, request: control_data.TeleFileReq, context) -> common_data.Response:
        self._debug('DeleteTeleMotion')
        resp = self._control_client.DeleteTeleMotion(name=request.name)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetLoadFactors(self, request: common_data.Empty, context) -> device_data.GetLoadFactorsRes:
        if time.time() - self._update_last > UPDATE_PRINT_PERIOD:
            self._debug('GetLoadFactors')
        resp = self._device_client.GetLoadFactors()
        response = device_data.GetLoadFactorsRes()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response


    @check_token
    def GetFTSensorData(self, request, context):
        self._debug('GetFTSesnorData')
        # res = self._device_client.GetFTSensorData()
        res = self._control_client.GetTransformedFTSensorData()
        if res is not None:
            response = device_data.FTSensorData()
            json_format.ParseDict(res, response)
            return response
        else:
            self._error('FT Sensor Unavailable')
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return device_data.FTSensorData()

    @check_token
    def SetFTSensorConfig(self, request, context):
        self._debug('SetFTSensorConfig')
        msg = self.__check_reconfiguration_available__()
        if msg is not None:
            return common_data.Response(msg=msg)

        if self._config_client.SetFTSensorConfig(
                dev_type=request.dev_type,
                com_type=request.com_type,
                ip_address=request.ip_address,
                ft_frame_translation_offset_x=request.ft_frame_translation_offset_x,
                ft_frame_translation_offset_y=request.ft_frame_translation_offset_y,
                ft_frame_translation_offset_z=request.ft_frame_translation_offset_z,
                ft_frame_rotation_offset_r=request.ft_frame_rotation_offset_r,
                ft_frame_rotation_offset_p=request.ft_frame_rotation_offset_p,
                ft_frame_rotation_offset_y=request.ft_frame_rotation_offset_y) is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
        return common_data.Response()

    @check_token
    def GetFTSensorConfig(self, request, context):
        self._debug('GetFTSensorConfig')
        ft_sensor_config = self._config_client.GetFTSensorConfig()
        if ft_sensor_config is not None:
            response = config_data.FTSensorDevice()
            json_format.ParseDict(ft_sensor_config, response)
            return response
        else:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return config_data.FTSensorDevice()

    @check_token
    def SetSanderCommand(self, request: device_data.SanderCommand, context):
        resp = self._device_client.SetSanderCommand(request.type, request.ip, request.speed, request.state)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def GetSanderCommand(self, request, context) -> device_data.SanderCommand:
        resp = self._device_client.GetSanderCommand()
        response = device_data.SanderCommand()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    ## Safetics Function

    @check_token
    def LoginSFD(self, request, context):
        self._debug('Login Safetics')
        return self._cri_client.login(request.email, request.token)

    @check_token
    def IsSFDLogin(self, request, context):
        dat = self._cri_client.is_login()
        return common_data.State(enable=dat)

    @check_token
    def LogoutSFD(self, request, context):
        return self._cri_client.logout()

    @check_token
    def SaveSFDLoginInfo(self, request, context):
        return self._cri_client.save_account(request.email, request.token)

    @check_token
    def LoadSFDLoginInfo(self, request, context):
        res = self._cri_client.load_account()
        return cri_data.SFDAccount(email=res["email"], token=res["token"])

    @check_token
    def GenerateSFDToken(self, request, context):
        res = self._cri_client.generate_token(request.email)
        return cri_data.SFDAccount(email=request.email, token=res)

    @check_token
    def GetSFDLoginInfo(self, request, context):
        res = self._cri_client.get_account()
        return cri_data.SFDAccount(email=res["email"], token=res["token"])

    @check_token
    def SelectSFDTarget(self, request, context):
        self._debug('Set Target Safetics')
        return self._cri_client.select_target(request.pn, request.fn, request.rn, request.iso)

    @check_token
    def IsSFDTargetValid(self, request, context):
        res = self._cri_client.is_target_valid()
        return common_data.State(enable=res)

    @check_token
    def ReleaseSFDTarget(self, request, context):
        return common_data.State(enable=self._cri_client.release_target())

    @check_token
    def GetSFDTarget(self, request, context):
        res = self._cri_client.get_target()
        return cri_data.SFDTarget(pn=res["pn"], fn=res["fn"], rn=res["rn"], iso=res["iso"])

    @check_token
    def ActiveCRIVel(self, request, context):
        self._debug('Set Option Safetics')
        return self._cri_client.active_cri_vel(request.enable)

    @check_token
    def GetSFDProjList(self, request, context):
        self._debug('Get Project List')
        dat = self._cri_client.get_proj_list()
        return cri_data.SFDProjectList(list=dat)

    @check_token
    def GetCRI(self, request, context):
        self._debug('Get CRI')
        dat = self._cri_client.get_cri()
        return  cri_data.CriData(time = dat["time"], cri = dat["cri"], velRatio = dat["velRatio"])

    @check_token
    def SaveSFDAutoSet(self, request, context):
        return self._cri_client.save_auto_set(request.login, request.pn,
                                              request.fn, request.rn,
                                              request.iso)

    @check_token
    def LoadSFDAutoSet(self, request, context):
        res = self._cri_client.load_auto_set()
        return cri_data.SFDAutoSet(login=res["login"], pn=res["pn"],
                                   fn=res["fn"], rn=res["rn"], iso=res["iso"])

    @check_token
    def AddPhotoneoCalibPoint(self, request, context):
        self._debug('Add PhotoneoCalibPoint')
        resp = self._device_client.AddPhotoneoCalibPoint(request.vision_name, request.px, request.py, request.pz)
        response = common_data.Response()
        if resp is not None:
            json_format.ParseDict(resp, response)
        return response

    @check_token
    def ConnectMimicServer(self, request, context):
        try:
            server_info = request.mimic_server
            self.__mimic_channel = grpc.insecure_channel(f"{server_info.ip}:{server_info.port}")
            self.__mimic_stub = mimic_grpc.MoveMimicStub(self.__mimic_channel)
            return common_data.Response(code=1, message="Connected to Mimic Server successfully.")
        except Exception as e:
            context.set_details(str(e))
            return common_data.Response(code=0, message="Failed to connect to Mimic Server.")

    @check_token
    def DisconnectMimicServer(self, request, context):
        try:
            if self.__mimic_channel:
                self.__mimic_channel.close()
                self.__mimic_channel = None
                self.__mimic_stub = None
                return common_data.Response(code=1, message="Disconnected from Mimic Server successfully.")
            else:
                return common_data.Response(code=1, message="No connection to Mimic Server.")
        except Exception as e:
            context.set_details(str(e))
            return common_data.Response(code=0, message="Failed to disconnect from Mimic Server.")

    @check_token
    def GetSkillList(self, request, context):
        try:
            if self.__mimic_stub:
                # peer = context.peer()
                # if peer.startswith('ipv4:'):
                #     client_ip = peer.split(':')[1]
                # else:
                #     client_ip = 'unknown'
                # # print(f"IP: {client_ip}")
                # self.__mimic_stub.SetRobotAddress(mimic_data.Address(ip=client_ip,port=0))
                # time.sleep(0.01)
                response = self.__mimic_stub.GetSkillList(mimic_data.Empty())
                return mimic_data.MimicSkillList(skill_list=response.skill_list)
            else:
                context.set_details("Not connected to Mimic Server")
                # context.set_code(grpc.StatusCode.UNAVAILABLE)
                return mimic_data.MimicSkillList()
        except Exception as e:
            context.set_details(str(e))
            return mimic_data.MimicSkillList()

    @check_token
    def GetSkillHome(self, request, context):
        try:
            if self.__mimic_stub:
                skill_name = request.name
                response = self.__mimic_stub.GetSkillHome(mimic_data.MimicSkillName(name=skill_name))
                return mimic_data.GetSkillHomeRes(jpos=response.jpos)
            else:
                context.set_details("Not connected to Mimic Server")
                # context.set_code(grpc.StatusCode.UNAVAILABLE)
                return mimic_data.GetSkillHomeRes()
        except Exception as e:
            context.set_details(str(e))
            return mimic_data.GetSkillHomeRes()

    @check_token
    def HoldToRunSkill(self, request, context):
        # self._debug('HoldToRunSkill')
        try:
            if self.__mimic_stub:
                skill_name = request.name
                response = self.__mimic_stub.RunSkill(mimic_data.MimicSkillName(name=skill_name))
                return common_data.Response(code=1, message="Mimic skill started.")
            else:
                context.set_details("Not connected to Mimic Server")
                return common_data.Response(code=0, message="No connection to Mimic Server.")
        except Exception as e:
            context.set_details(str(e))
            return common_data.Response(code=0, message="Failed to start Mimic kill.")

    @check_token
    def StopSkill(self, request, context):
        try:
            if self.__mimic_stub:
                self.__mimic_stub.StopSkill(mimic_data.Empty())
                return common_data.Response(code=1, message="Mimic skill stopped.")
            else:
                context.set_details("Not connected to Mimic Server")
                return common_data.Response(code=0, message="No connection to Mimic Server.")
        except Exception as e:
            context.set_details(str(e))
            return common_data.Response(code=0, message="Failed to stop Mimic kill.")

    @check_token
    def GetNetworkSettings(self, request: common_data.Empty, context) -> conty_data.NetworkSettings:
        self._debug("GetNetworkSettings")

        interfaces = NetworkManager.list_interfaces()
        gateways = NetworkManager.get_gateways_by_interface()
        dns = NetworkManager.get_dns_by_resolv_conf()

        ifaces = []
        for iface in interfaces:
            ip, netmask = NetworkManager.get_ip_and_netmask(iface)
            mac = NetworkManager.get_mac_address(iface)
            gateway = gateways.get(iface)
            dhcp = NetworkManager.is_using_dhcp(iface)
            if dhcp is None:
                self._error(f"DHCP read fail for {iface}")
                dhcp = True
            ifaces.append(dict(
                name = iface,
                mac_address = mac,
                ip_address = ip,
                subnet_mask = netmask,
                gateway = gateway,
                use_dhcp = dhcp)
            )

        response = conty_data.NetworkSettings()
        json_format.ParseDict(dict(ifaces=ifaces, dns_servers=dns), response)
        return response

    @check_token
    def SetNetworkSettings(self, request: conty_data.NetworkSettings, context) -> common_data.Response:
        self._warn(f"SetNetworkSettings: \n{request}")
        ret = 0

        interfaces = NetworkManager.list_interfaces()
        gateways = NetworkManager.get_gateways_by_interface()
        dns = NetworkManager.get_dns_by_resolv_conf()

        ifaces_backup = {}
        for iface in interfaces:
            if iface == 'lo':
                continue
            ip, netmask = NetworkManager.get_ip_and_netmask(iface)
            mac = NetworkManager.get_mac_address(iface)
            gateway = gateways.get(iface)
            dhcp = NetworkManager.is_using_dhcp(iface)
            if dhcp is None:
                self._error(f"DHCP read fail for {iface}")
                dhcp = True

            ifaces_backup[iface] = dict(
                name = iface,
                mac_address = mac,
                ip_address = ip,
                subnet_mask = netmask,
                gateway = gateway,
                use_dhcp = dhcp)

        message = ""
        for iface in request.ifaces:
            if ((not ifaces_backup[iface.name]["use_dhcp"])  # static ip
                    and (ifaces_backup[iface.name]["ip_address"] in NetworkManager.IPS_FIXED)):  # reserved ips
                ret = -1
                message = f"IP {ifaces_backup[iface.name]['ip_address']} ({iface.name}) is locked for internal use"
                self._error(message)
                continue

            ret_tmp = NetworkManager.configure_interface(iface.name, use_dhcp=iface.use_dhcp, ip=iface.ip_address,
                                                         netmask=iface.subnet_mask, gateway=iface.gateway)
            if ret_tmp != 0:
                NetworkManager.configure_interface(iface.name, use_dhcp=ifaces_backup[iface.name]['use_dhcp'],
                                                   ip=ifaces_backup[iface.name]['ip_address'],
                                                   netmask=ifaces_backup[iface.name]['subnet_mask'],
                                                   gateway=ifaces_backup[iface.name]['gateway'])
                ret = ret_tmp
                message = f"Failed to set interface {iface}"
                self._error(message)
        if len(request.dns_servers) > 0:
            NetworkManager.configure_dns(request.dns_servers)
        return common_data.Response(code=ret, msg=message)

    @check_token
    def GetProcessResources(self, request: common_data.Empty, context) -> conty_data.TaskResources:
        self._debug("GetProcessResources")

        response = conty_data.TaskResources()
        resources = self._process_resource_list
        task_times = self._device_client.GetRTTaskTimes()
        if task_times is not None:
            task_times = task_times['task_times']
        for resource_dict in resources:
            name = resource_dict['name']
            if task_times is not None:
                for tdict in task_times:
                    if tdict['name'] in name:
                        resource_dict['task_time_us'] = float(tdict['value'])
            resource_dict['name'] = extract_name_from_cmd(name)

        json_format.ParseDict(dict(resources=resources), response)
        return response

    @check_token
    def GetLogLevel(self, request: common_data.Empty, context) -> common_data.Int:
        deploy_json = load_json(get_abs_path(Common.Config().DEPLOY_JSON))
        if deploy_json is None:
            value = 0
        else:
            if "log-level" in deploy_json:
                value = int(deploy_json["log-level"])
            else:
                value = 0
        return common_data.Int(value=value)

    @check_token
    def SetLogLevel(self, request: common_data.Int, context) -> common_data.Response:
        self._debug('SetLogLevel')
        deploy_json = load_json(get_abs_path(Common.Config().DEPLOY_JSON))
        if request.value >= 1 and request.value <= 4:
            deploy_json["log-level"] = request.value
            write_json(get_abs_path(Common.Config().DEPLOY_JSON), deploy_json)
            self._debug(f'Reboot To Apply Log Level {request.value}')
            self.__reboot = True
        return common_data.Response()

    ############################
    # Threading
    ############################
    def has_framework_connected(self) -> bool:
        return self._has_framework_connected

    def has_linear_axis(self) -> bool:
        return self._has_linear_axis

    def has_conty_connected(self) -> bool:
        return (time.time() - self._last_conty_request_time) < self.CONTY_UPDATE_TIMEOUT

    def get_framework_data(self) -> dict:
        with self._lock_data_updating:
            framework_data = {
                'boot_data': self._boot_data,
                'device_info': self._device_info,
                'path_config': self._path_config,
                'safety_limits': self._safety_limits,
                'reduced_ratio': self._reduced_ratio,
                'control_data': self._control_data,
                'motion_data': self._motion_data,
                'io_data': self._io_data,
                'servo_data': self._servo_data,
                'program_data': self._program_data,
                'safety_control_data': self._safety_control_data,
                'violation_data': self._violation_data,
                'violation_queue_data': self._violation_queue_data,
                'collision_model_state': self._collision_model_state,
                'linear_data': self._linear_data,
                'data_id': self._data_id,
            }
            return framework_data

    def _update_framework_data(self):
        framework_connected_prev = False
        control_on_prev = False
        while self._is_data_update_running:
            with self._lock_data_updating:
                sleep_time = self.UPDATE_PERIOD
                self._boot_data = self._boot_client.GetBootStatus()
                self._has_boot_server_connected = self._boot_data is not None
                if self._has_boot_server_connected:
                    control_on = 'control_on' in self._boot_data and self._boot_data['control_on']
                    if control_on and not control_on_prev:
                        time.sleep(self.RECONNECT_PERIOD)  # wait long for the first time to make sure services alive
                    control_on_prev = control_on
                    if control_on and control_on_prev:
                        self._control_data = self._rtde_client.GetControlData()
                        # print(self._control_data)
                        self._motion_data = self._rtde_client.GetMotionData()
                        self._io_data = self._rtde_client.GetIOData()
                        self._servo_data = self._rtde_client.GetServoData()
                        self._program_data = self._rtde_client.GetProgramData()
                        self._safety_control_data = self._device_client.GetSafetyControlData()
                        self._violation_data = self._rtde_client.GetViolationData()
                        self._violation_queue_data = self._rtde_client.GetViolationMessageQueue()
                        self._collision_model_state = self._rtde_client.GetCollisionModelState()
                        self._device_info = self._device_client.GetDeviceInfo()
                        self._path_config = self._config_client.GetPathConfig()
                        self._safety_limits = self._config_client.GetSafetyLimits()
                        self._reduced_ratio = self._config_client.GetReducedRatio()
                        self._has_framework_connected = not (self._control_data is None
                                                             or self._motion_data is None
                                                             or self._io_data is None
                                                             or self._servo_data is None
                                                             or self._program_data is None
                                                             or self._safety_control_data is None
                                                             or self._violation_data is None
                                                             or self._violation_queue_data is None
                                                             or self._collision_model_state is None
                                                             or self._device_info is None
                                                             or self._path_config is None
                                                             or self._safety_limits is None
                                                             or self._reduced_ratio is None)
                        if self._has_framework_connected:
                            if self._has_linear_axis is not False:  # try if not determined as False
                                self._linear_data = self._linear_client.get_axis_data()
                            if self._has_linear_axis is None:  # determine if not determined (None)
                                self._has_linear_axis = self._linear_data is not None
                        if not self._has_framework_connected:
                            sleep_time = self.RECONNECT_PERIOD  # wait long - framework down and accessed
                            self._warn(f"Framework Connection Failed - Try reconnection after {sleep_time} s")
                    else:
                        self._has_framework_connected = False
                        sleep_time = self.UPDATE_PERIOD  # no need to wait long - only alive boot service is accessed
                else:
                    self._has_framework_connected = False
                    sleep_time = self.RECONNECT_PERIOD  # wait long - boot service is also down and being accessed
                    self._warn(f"Boot Service Connection Failed - Try reconnection after {sleep_time} s")

            if self._has_framework_connected:
                if self.has_conty_connected():
                    self._control_client.PingFromConty()

                violation_queue = self._violation_queue_data['violation_queue']
                violation_queue_num = len(violation_queue)
                violation_logged_num = len(self.__violation_logged_queue)

                violation_queue_new_log_from = violation_logged_num
                if violation_queue_num < violation_logged_num:  # queue decreased -> whole new violation stack
                    violation_queue_new_log_from = 0
                else:  # queue same or increased -> compare violation stack
                    for i_log in range(violation_queue_num):
                        violation_queued = violation_queue[i_log]
                        if i_log >= violation_logged_num:  # non-logged new violation
                            violation_queue_new_log_from = i_log
                            break
                        else:  # compare with old logged violation
                            violation_logged = self.__violation_logged_queue[i_log]
                            if violation_queued['violation_id'] != violation_logged['violation_id']:
                                # mismatch: means whole new violation stack
                                violation_queue_new_log_from = 0
                                break

                for i_log in range(violation_queue_new_log_from, violation_queue_num):
                    self._error('Violation: ' + violation_queue[i_log]['violation_str'])
                self.__violation_logged_queue = violation_queue

                if self._control_data['op_state'] == common_data.OP_COLLISION:
                    if int(self._violation_data['violation_code']) == 0:  # this is collision message
                        if not self.__collision_logged:
                            self._error(self._violation_data['violation_str'])
                            self.__collision_logged = True
                else:
                    self.__collision_logged = False

                    # check if active violation code is not printed yet
                    violation_id = int(self._violation_data['violation_id'])
                    printed = False
                    for i_log in range(violation_queue_num):
                        if int(violation_queue[i_log]['violation_id']) == violation_id:
                            printed = True
                            # messsage in queue is earlier and more close to original
                            self._violation_data['violation_str'] = violation_queue[i_log]['violation_str']
                            break
                    if not printed:
                        violation_message = self._violation_data['violation_str']
                        if violation_id != self.__violation_id_prev and violation_message != '':
                            self._error('Violation: ' + violation_message)
                self.__violation_id_prev = violation_id


            if self._device.has_conty() and not self.has_conty_connected():
                self._error('Conty Timeout: ' + str(time.time() - self._last_conty_request_time))
                self._device.update_conty(connected=False)

            if self._token.token_cache is not None:
                self._token.update_token_cache()

            if self._has_framework_connected and not framework_connected_prev:
                self._info(
                    f"Framework Version {self._device_info['controller_ver']}-{self._device_info['controller_detail']}"
                    + f" [{self._device_info['controller_date']}] Connected")
            framework_connected_prev = self._has_framework_connected

            self._data_id += 1
            time.sleep(sleep_time)

        self._info('Stop Updating Framework Data')

    def __resource_monitor(self):
        resource_exception_keys = ["EtherCAT", "logrotate", "IndyEye_main.py", NO_PROCESS]
        SW_CPU_MEM_MISUSE = 0x8000000000
        MISUSE_STOP_CAT = 2
        ID_CPU_OVERUSE = 0
        ID_RAM_OVERUSE = 1
        CPU_CUT = 30.0
        MEM_CUT = 15.0
        root_pid_set = set(get_pids("indy_run.py")).union(get_pids("UDEVMonitor"))
        self._info(f"Start Resource Monitoring Except Root PIDs: {list(root_pid_set)}")
        while self._is_resource_monitoring:
            try:
                time.sleep(1)
                if not self._has_framework_connected:
                    continue
                self._process_resource_list = get_process_resources()
                tree_str = ""
                not_matched = None
                misuse_type = -1
                percentage = 0.0
                app_pids = get_pids("IndyDeployment")
                for proc_dict in self._process_resource_list:
                    ancestors = get_ancestor_pids(proc_dict['pid'])
                    # print(f"ancestors {ancestors}")
                    if root_pid_set.union(app_pids).isdisjoint(ancestors):  # non-root sharing busy process
                        is_exception = False
                        tree_str = get_tree(proc_dict['pid'])
                        for exception_key in resource_exception_keys:
                            if exception_key in tree_str or exception_key in proc_dict['name']:
                                is_exception = True
                                self._debug(f"Resource Misuse Detected (PID: {proc_dict['pid']}) But Ignored - Command: '{proc_dict['name']}'")
                                if NO_PROCESS in tree_str:
                                    self._debug(f"Process Disappeared")
                                else:
                                    self._debug(f"Process Tree: \n{tree_str}")
                                break;
                        if not is_exception:
                            if proc_dict['cpu_percent'] >= CPU_CUT:
                                not_matched = proc_dict
                                misuse_type = ID_CPU_OVERUSE
                                percentage = proc_dict['cpu_percent']
                                break
                            elif proc_dict['mem_percent'] >= MEM_CUT:
                                not_matched = proc_dict
                                misuse_type = ID_MEM_OVERUSE
                                percentage = proc_dict['mem_percent']
                                break
                if not_matched is not None:
                    process_name = extract_name_from_cmd(not_matched['name'])
                    self._device_client.CommitViolation(violation_type=SW_CPU_MEM_MISUSE,
                                                        stop_category=MISUSE_STOP_CAT,
                                                        source=0,
                                                        axis_idx=0,
                                                        misc_fvalue=percentage,
                                                        misc_ivalue=misuse_type,
                                                        misc_min=0.0,
                                                        misc_max=0.0,
                                                        misc_text=process_name
                    )
                    self._error(f"Resource Misuse From CMD: '{not_matched['name']}' (PID: {proc_dict['pid']})")
                    self._warn(f"Process Tree: \n{tree_str}")
                    time.sleep(10)
            except Exception as e:
                self._err(f"Error in Resource Monitor: {e}")

        self._info('Stop Resource Monitoring')

    ############################
    # Private
    ############################
    def __check_reconfiguration_available__(self):
        self._debug('Check Reconfiguration Available')
        msg = None
        if self.has_framework_connected():
            framework_data = self.get_framework_data()
            if framework_data['program_data']['program_state'] == RTDEClient.PROG_RUNNING:
                msg = "Error: Robot is in auto mode"
            # # Reconfiguration in violation or servo off should be allow for recovering
            # if framework_data['control_data']['op_state'] == RTDEClient.CTRL_VIOLATE:
            #     msg = "Error: Robot is in violate state"
            #
            # for servo_state in framework_data['servo_data']['servo_actives']:
            #     if not servo_state:
            #         msg = "Error: Robot's servo is turned off"
            #         break
        return msg

    def __read_program_file(self, file_dir):
        self._debug('__read_program_file')
        content = bytearray()
        try:
            with open(file_dir, 'rb') as file:
                while True:
                    piece = file.read(self.CHUNK_SIZE)
                    if len(piece) == 0:
                        break
                    content = content + piece
        except OSError as ex:
            pass  # print(ex)
        return content

    def __remove_program_file(self, file_dir):
        self._debug('__remove_program_file')
        try:
            if os.path.isfile(file_dir):
                os.remove(file_dir)

        except Exception as ex:
            print(ex)

    def __get_onstart_program_info(self):
        self._debug('__get_onstart_program_info')
        on_start_program_index = self._config_client.GetOnStartProgramConfig()
        prog_list = self.__load_program_list(folder_dir=Common.Config().INDEX_PROGRAM_DIR)

        # Parse program indices
        indices = []
        for prog in prog_list["dir"]:
            prog_name = os.path.basename(prog)
            prog_idx = int(prog_name.split('.')[0])
            if prog_idx == on_start_program_index['index']:
                return dict(
                    auto_run=on_start_program_index['auto_run'],
                    index=on_start_program_index['index'],
                    file_dir=os.path.basename(prog_name.split('.')[1]))

        return dict(auto_run=False, index=-1, file_dir='')

    def __load_program_list(self, folder_dir=None):
        if folder_dir is None:
            folder_dir = Common.Config().PROGRAM_DIR
        self._debug('__load_program_list')
        prog_list = dict()
        # prog_list["dir"] = glob.glob('{}/*.*.py'.format(folder_dir))  # name.model.py
        prog_list["dir"] = glob.glob('{}/*.*.json'.format(folder_dir))  # name.model.json
        dir_list_filtered = []
        for file_path in prog_list["dir"]:
            file_name = os.path.basename(file_path)
            filename_split = file_name.split('.')
            if len(filename_split) >= 3 and filename_split[-2].lower() == Common.Config().ROBOT_NAME.lower():
                dir_list_filtered.append(file_path)
        prog_list["dir"] = dir_list_filtered
        prog_list["size"] = []
        prog_list["time"] = []
        prog_list["content"] = []
        for file_dir in prog_list["dir"]:
            prog_list["size"].append(str(os.path.getsize(file_dir) / 1024) + " KB")  # KB
            prog_list["time"].append(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(file_dir))))
            prog_list["content"].append(self.__read_program_file(file_dir))
        return prog_list

    def __load_gcode_list(self, folder_dir=None):
        self._debug('__load_gcode_list')
        if folder_dir is None:
            folder_dir = Common.Config().GCODE_DIR
        gcode_list = glob.glob('{}/*.gcode'.format(folder_dir))
        gcode_name_list = []
        for gcode_file_path in gcode_list:
            file_name = os.path.basename(gcode_file_path)
            gcode_name_list.append(file_name)
        return gcode_name_list

    def __get_ref_frame_name(self, ref_frame: list = None) -> str:
        if ref_frame is None or len(ref_frame) == 0:
            return 'Unknown'

        ref_frame_list = self._config_client.GetRefFrameList()['ref_frames']
        for saved_frame in ref_frame_list:
            matched = True
            for i in range(len(saved_frame['tpos'])):
                if math.fabs(ref_frame[i] - saved_frame['tpos'][i]) > 1e-3:
                    matched = False
                    break
            if matched:
                return saved_frame['name']
        return 'Unknown'

    def __get_tool_frame_name(self, tool_frame: list = None) -> str:
        if tool_frame is None or len(tool_frame) == 0:
            return 'Unknown'
        tool_frame_list = self._config_client.GetToolFrameList()['tool_frames']
        for saved_frame in tool_frame_list:
            matched = True
            for i in range(len(saved_frame['tpos'])):
                if math.fabs(tool_frame[i] - saved_frame['tpos'][i]) > 1e-3:
                    matched = False
                    break
            if matched:
                return saved_frame['name']
        return 'Unknown'

    def __convert_digital_bool_list__(self, grpc_signals: list) -> list:
        """
        Convert gRPC Digital Signal List to boolean list
        :param grpc_signals: list(DigitalSignal)
        :return: list(bool)
        """
        # self._debug('__convert_digital_bool_list__')
        bool_list = []
        for signal in grpc_signals:
            if signal['state'] == device_data.ON_STATE:
                bool_list.append(dict(address=signal['address'], state=1))
            elif signal['state'] == device_data.OFF_STATE:
                bool_list.append(dict(address=signal['address'], state=0))

        return bool_list

    def __to_digital_request_signals__(self, digital_signal_list: list) -> list:
        signals = []
        for signal in digital_signal_list:
            state = signal['state']
            signals.append(dict(address=signal['address'], state=state))
        return signals

    def __convert_analog_value_list__(self, grpc_signals: list) -> list:
        # self._debug('__convert_analog_value_list__')
        analog_list = []
        for signal in grpc_signals:
            analog_list.append(signal['voltage'])
        return analog_list

    def __to_analog_request_signals__(self, analog_signal_list: list) -> list:
        signals = []
        for signal in analog_signal_list:
            signals.append(dict(address=signal['address'], voltage=signal['voltage']))

        return signals

    def __unmark_target_reached(self):
        if self.has_framework_connected():
            self.get_framework_data()['motion_data']['is_target_reached'] = False

    def __unmark_linear_axis_target_reached(self):
        if self.has_framework_connected():
            self.get_framework_data()['linear_data']['is_target_reached'] = False

    ############################
    # Console Logging
    ############################
    def _info(self, content='', source='ContyServicer'):
        self._logger.info(content=content, source=source)

    def _debug(self, content='', source='ContyServicer'):
        self._logger.debug(content=content, source=source)

    def _warn(self, content='', source='ContyServicer'):
        self._logger.warn(content=content, source=source)

    def _error(self, content='', source='ContyServicer'):
        self._logger.error(content=content, source=source)

