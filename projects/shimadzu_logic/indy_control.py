import threading
import time
import datetime
import re
from collections import deque
from pkg.utils.blackboard import GlobalBlackboard

from neuromeka import IndyDCP3
from pkg.utils.file_io import load_json, save_json
from .constants import *
from pkg.configs.global_config import GlobalConfig
from pkg.utils.rotation_utils import diff_cmd

import numpy as np

global_config = GlobalConfig()
bb = GlobalBlackboard()

def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class RobotCommunication:
    def __init__(self, config_file="projects/shimadzu_logic/configs/indy_command.json", *args, **kwargs):
        ''' Thread related '''
        self.running = False
        self.thread = None

        ''' Config '''
        self.config = load_json(config_file)
        self.home_pos = self.config["home_pos"]
        self.packaging_pos = self.config["packaging_pos"]

        # Load general configs to get robot_ip
        general_config = load_json("projects/shimadzu_logic/configs/configs.json")
        robot_ip = general_config.get("robot_ip")

        ''' Indy command '''
        Logger.info(f'[Indy7] Attempting to connect to robot at {robot_ip}')
        self.indy = IndyDCP3(robot_ip, *args, **kwargs)
        self.indy.set_speed_ratio(100) 
        # self.indy.set_auto_mode(True)
        is_auto_mode : dict = self.indy.check_auto_mode()
        if not is_auto_mode.get('on') :
            self.indy.set_auto_mode(True)
            Logger.info(f'[Indy7] Auto mode enabled.')
            time.sleep(0.5)
        Logger.info(f'[Indy7] Robot connection and initial setup successful.')


        ''' Home and packaging pose '''
        self.check_home_min = -10
        self.check_home_max = 10
        self.is_home_pos = False
        self.is_packaging_pos = False
        self.is_detect_pos = False

        self.robot_state = 0
        self.is_sim_mode = False
        self.robot_running_hour = 0
        self.robot_running_min = 0

        # indy_communication에서 설정되는 속성들을 안전하게 초기화합니다.
        self.robot_current_pos = [0.0, 0.0, 0.0]
        self.program_state = ProgramState.PROG_IDLE
        self.program_name = ""

        ''' Conty Int variable, first initialization '''
        self.indy.set_int_variable([
            {'addr': int(self.config["int_var/cmd/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/grip_state/addr"]), 'value': 0},
        ])
        # CMD_Init은 bool 변수이므로 별도로 초기화합니다.
        self.indy.set_bool_variable([
            {'addr': int(self.config["int_var/init/addr"]), 'value': False}
        ])

        ''' Indy ioboard '''
        self.btn_direct_teaching = 0
        self.btn_stop = 0

        self.robot_paused = False

        ###아날로그 변수값####
        self.analog_min = 0
        self.analog_max = 100
        self.analog_min_avg = 100
        self.analog_max_avg = 800
        self.data_queue = deque(maxlen=10)

    def start(self):
        """ Start the robot communication thread """

        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        """ Stop the app communication thread """
        if self.running:
            self.running = False

            if self.program_state in (ProgramState.PROG_RUNNING, ProgramState.PROG_PAUSING):
                try:
                    Logger.info("Stop program!!")
                    self.indy.stop_program()
                    bb.set("ui/reset/robot/recover_motion",True)
                    self.indy.set_speed_ratio(100) 
                except:
                    Logger.error("Stop program fail")

            self.indy.stop_motion(stop_category=2)
            self.indy.set_int_variable([{'addr': int(self.config["int_var/cmd/addr"]), 'value': 0}])

            if self.thread:
                self.thread.join()

    def run(self):
        """ Thread's target function """
        while self.running:
            time.sleep(0.001)
            self.receive_data_from_bb()  # Get bb data, process bb data
            self.handle_int_variable()  # Get bb data, process bb data

            self.indy_communication()  # Get indy data
            self.send_data_to_bb()  # Send indy data to bb

    def get_dio_channel(self, di, ch):
        return next((int(item['state']) for item in di if item['address'] == ch), None)

    def get_intvar_address(self, int_var, addr):
        return next((int(item['value']) for item in int_var if item['addr'] == addr), None)

    def get_tposvar_address(self, tpos_var, addr):
        return next((item['tpos'] for item in tpos_var if item['addr'] == addr), None)


    def receive_data_from_bb(self):
        """
        Command request from FSM by blackbaord
        - only work in NotReadyIdle mode (Program is NOT running)
        """

        ''' MQTT Protocol compliant robot control '''
        if bb.get("ui/cmd/robot_control/trigger"):
            bb.set("ui/cmd/robot_control/trigger", 0) # Consume trigger
            payload = bb.get("ui/cmd/robot_control/data")
            if payload and isinstance(payload, dict):
                target = payload.get("target")
                action = payload.get("action")
                Logger.info(f"Received robot_control command via MQTT->BB: target={target}, action={action}")

                # Gripper Control (target: gripper, action: open/close)
                if target == "gripper":
                    if action == "open":
                        Logger.info("Sending Gripper Open command (90) to Conty.")
                        bb.set("int_var/cmd/val", 90)
                    elif action == "close":
                        Logger.info("Sending Gripper Close command (91) to Conty.")
                        bb.set("int_var/cmd/val", 91)

                # Direct Teaching Control (target: robot_direct_teaching_mode, action: enable/disable)
                elif target == "robot_direct_teaching_mode":
                    if action == "enable":
                        if self.program_state != ProgramState.PROG_RUNNING:
                            try:
                                is_auto_mode : dict = self.indy.check_auto_mode()
                                self.indy.set_direct_teaching(True)
                                bb.set("ui/state/direct_state", 1)
                            except Exception as e:
                                Logger.error(f"Start direct teaching program fail: {e}")

                    elif action == "disable":
                        try:
                            Logger.info("Stop direct teaching program (MQTT)")
                            self.indy.set_direct_teaching(False)
                            bb.set("ui/state/direct_state", 2)
                        except Exception as e:
                            Logger.error(f"Stop direct teaching program fail: {e}")

        ''' Start program (Main program, index=1) '''
        if bb.get("indy_command/play_program"):
            bb.set("indy_command/play_program", False)
            if self.program_state != ProgramState.PROG_RUNNING:
                try:
                    is_auto_mode : dict = self.indy.check_auto_mode()
                    if not is_auto_mode.get('on') :
                        self.indy.set_auto_mode(True)
                        time.sleep(0.5)
                    Logger.info(f"indy 310 robot pos 1 set")    
                    bb.set("process/robot/position",1)                    
                    self.indy.play_program(prog_idx=int(self.config["conty_main_program_index"]))
                except:
                    Logger.error("Start main program fail")

        ''' Start program by index from MQTT '''
        if bb.get("indy_command/play_program_trigger"):
            bb.set("indy_command/play_program_trigger", False)
            program_index = bb.get("indy_command/play_program_index")
            if self.program_state != ProgramState.PROG_RUNNING:
                try:
                    is_auto_mode : dict = self.indy.check_auto_mode()
                    if not is_auto_mode.get('on') :
                        self.indy.set_auto_mode(True)
                        time.sleep(0.5)
                    Logger.info(f"Starting Conty program by index: {program_index}")
                    self.indy.play_program(prog_idx=int(program_index))
                except Exception as e:
                    Logger.error(f"Failed to start program by index {program_index}: {e}")

        ''' Stop program '''
        if bb.get("indy_command/stop_program"):
            bb.set("indy_command/stop_program", False)
            if self.program_state in (ProgramState.PROG_RUNNING, ProgramState.PROG_PAUSING):
                try:
                    Logger.info("Stop program!!")
                    self.indy.stop_program()
                    time.sleep(0.5)
                    is_auto_mode : dict = self.indy.check_auto_mode()
                    # if is_auto_mode.get('on') :
                    #     self.indy.set_auto_mode(False)
                    bb.set("robot/recover/motion/cmd",0)
                    self.indy.set_speed_ratio(100)
                except:
                    Logger.error("Stop program fail")


        ''' Reset '''
        if bb.get("indy_command/recover"):
            bb.set("indy_command/recover", False)
            self.indy.recover()
            Logger.info(f"Robot Send Recovery command")


    def handle_int_variable(self):
        """
        Handles direct communication with the robot controller (Conty) via integer variables based on the protocol defined in Command.md.
        This function performs a read-process-write cycle:
        1. Reads current ACK and DONE values from the robot.
        2. Checks if the current command on the blackboard has been acknowledged by the robot.
        3. If acknowledged, it automatically resets the command on the blackboard to 0, fulfilling the CMD/ACK handshake.
        4. Writes the (potentially updated) command and other variables to the robot.
        - Program must be running in ReadyIdle mode.
        """
        '''
        Integer Variable Communication Protocol (Logic <-> Conty)
            Write variables (Logic -> Conty)
                - CMD (600): Motion command ID.
                - CMD_Init (770): Signal to initialize CMD_ack and CMD_done. (Set to 1 to trigger)

            Read variables (Conty -> Logic)
                - CMD_ack (610): Acknowledgement that CMD has been received.
                - CMD_done (700): Signal that the motion command is complete.
        '''

        try:
            # Part 1: Read all relevant variables from the robot first.
            int_var = self.indy.get_int_variable()['variables']

            motion_ack = self.get_intvar_address(int_var, int(self.config["int_var/motion_ack/addr"]))
            if motion_ack is not None:
                bb.set("int_var/motion_ack/val", motion_ack)
                # 로봇의 현재 위치를 ack 값 기반으로 저장 (충돌 방지 로직용)
                if motion_ack > 500: # 유효한 ack 값일 경우 (e.g. CMD 100 -> ACK 600)
                    current_pos_id = motion_ack - 500
                    bb.set("robot/current/position", current_pos_id)
                    Logger.info(f"[Safety] Robot position updated to: {current_pos_id}")
            
            motion_done = self.get_intvar_address(int_var, int(self.config["int_var/motion_done/addr"]))
            if motion_done is not None:
                bb.set("int_var/motion_done/val", motion_done)

            robot_pos = self.get_intvar_address(int_var, int(self.config["int_var/robot/position/addr"]))
            if robot_pos is not None:
                bb.set("int_var/robot/position/val", robot_pos)

            # Part 2: Process and decide what to write based on the CMD/ACK handshake.
            vars_to_set = []
            
            # 블랙보드에서 현재 명령 값을 안전하게 읽어옵니다. 값이 없으면 0으로 간주합니다.
            current_cmd = int(bb.get("int_var/cmd/val") or 0)
            
            # If the robot has acknowledged the current command, we can stop sending it.
            if current_cmd != 0 and motion_ack == (current_cmd + 500): # Command.md 프로토콜: ACK = CMD + 500
                Logger.info(f"[Indy] ACK received for CMD {current_cmd}. Resetting CMD to 0.")
                bb.set("int_var/cmd/val", 0)
                cmd_to_write = 0
            else:
                # No ACK yet, or CMD is already 0. Keep sending the current command.
                cmd_to_write = current_cmd

            vars_to_set.append({'addr': int(self.config["int_var/cmd/addr"]), 'value': cmd_to_write})

            # Handle other variables to write
            # None일 경우를 대비하여 기본값 0으로 처리
            grip_state_val = int(bb.get("int_var/grip_state/val") or 0)
            vars_to_set.append({'addr': int(self.config["int_var/grip_state/addr"]), 'value': grip_state_val})

            # Part 3: Write the collected integer variables to the robot.
            if vars_to_set:
                self.indy.set_int_variable(vars_to_set)

            # Part 4: Handle boolean variables (like CMD_Init) separately.
            if bb.get("indy_command/reset_init_var"):
                bb.set("indy_command/reset_init_var", False)
                self.indy.set_bool_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': True}])
                Logger.info("Sent CMD_Init (True) to robot controller to reset ACK/DONE.")
            else:
                # To ensure the init signal is a one-shot trigger, we must explicitly set it to False
                # when not being triggered. This mirrors the original logic of setting the int var to 0.
                self.indy.set_bool_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': False}])

        except Exception as e:
            Logger.error(f"Error in handle_int_variable cycle: {e}")

    def indy_communication(self):
        ''' Get Indy status '''
        try:
            control_data = self.indy.get_control_data()
            program_data = self.indy.get_program_data()
            self.robot_current_pos = control_data['p'][0:3]
            self.robot_state = control_data["op_state"]
            self.is_sim_mode = control_data["sim_mode"]
            self.robot_running_hour = control_data["running_hours"]
            self.robot_running_min = control_data["running_mins"]
            self.program_state = program_data["program_state"]
            self.program_name = program_data["program_name"]
            q = self.indy.get_control_data()["q"]
            self.is_home_pos = all(self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.home_pos))
            self.is_packaging_pos = all(self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.packaging_pos))
            bb.set("device/robot/comm_status", 1)
        except Exception as e:
            # 통신 실패 시 상태를 0으로 설정하고, 로봇 상태를 안전한 기본값으로 초기화합니다.
            Logger.error(f"[Indy7] Robot communication failed during status update: {e}")
            bb.set("device/robot/comm_status", 0)
            self.robot_state = Robot_OP_State.OP_SYSTEM_OFF
            self.program_state = ProgramState.PROG_IDLE

    def send_data_to_bb(self):
        """
        Set data to bb
            - bb send to App
            - bb sent to FSM
        """

        ''' Indy status '''
        indy_data = {
            "robot_pos" : self.robot_current_pos,
            "robot_state": self.robot_state,
            "is_sim_mode": self.is_sim_mode,
            "program_state": self.program_state,
            "is_home_pos": self.is_home_pos,
            "is_packaging_pos": self.is_packaging_pos,
            "is_detect_pos": self.is_detect_pos
        }
        bb.set("indy", indy_data)

        # Logger.info(f"Nuri State : {indy_data}")

        ''' App '''
        robot_state_ui = 0
        if self.robot_state in (Robot_OP_State.OP_SYSTEM_OFF, Robot_OP_State.OP_SYSTEM_ON):
            robot_state_ui = 1  # Off
        elif self.robot_state in (Robot_OP_State.OP_VIOLATE, Robot_OP_State.OP_VIOLATE_HARD):
            robot_state_ui = 2  # Emergency
        elif self.robot_state in (Robot_OP_State.OP_RECOVER_SOFT, Robot_OP_State.OP_RECOVER_HARD,
                                  Robot_OP_State.OP_BRAKE_CONTROL, Robot_OP_State.OP_SYSTEM_RESET,
                                  Robot_OP_State.OP_SYSTEM_SWITCH, Robot_OP_State.OP_MANUAL_RECOVER):
            robot_state_ui = 3  # Error
        elif self.robot_state in (Robot_OP_State.OP_IDLE, Robot_OP_State.OP_MOVING,
                                  Robot_OP_State.OP_TEACHING, Robot_OP_State.OP_COMPLIANCE,
                                  Robot_OP_State.TELE_OP):
            robot_state_ui = 4  # Ready
        elif self.robot_state == Robot_OP_State.OP_COLLISION:
            robot_state_ui = 5  # Collision

        # Robot state, working time
        bb.set("ui/state/robot_state", robot_state_ui)
        bb.set("ui/state/working_time", self.robot_running_hour)
        bb.set("ui/state/working_minute", self.robot_running_min)

        if robot_state_ui == 2 :
            bb.set("system/emo/on",1)

        # Logger.info(f"send_data_to_bb {robot_state_ui} {self.robot_running_hour} {self.robot_running_min}")

        ''' Direct teaching (On, Off) '''
        if self.robot_state == Robot_OP_State.OP_TEACHING:
            bb.set("ui/state/direct_state", 1)  # On
        else:
            bb.set("ui/state/direct_state", 2)  # Off

        ''' Program control (일시정지, 다시시작) '''
        # 로봇 속도 제어 로직:
        # 1. 도어 열림 상태를 최우선으로 확인하여 정지합니다.
        # 2. 도어가 닫혀 있을 경우, MQTT를 통해 수신된 UI 명령(일시정지/재시작)을 처리합니다.
        program_control_cmd = bb.get("ui/command/program_control")

        # 도어 상태 확인 (하나라도 0이면 '열림'으로 간주)
        is_door_open = not all([
            bb.get("device/remote/input/DOOR_1_OPEN"),
            bb.get("device/remote/input/DOOR_2_OPEN"),
            bb.get("device/remote/input/DOOR_3_OPEN"),
            bb.get("device/remote/input/DOOR_4_OPEN")
        ])
        # Test중일때는 사용안함
        is_door_open = False

        # 1. 도어 열림 감지 시 즉시 정지
        if is_door_open:
            if self.indy.get_motion_data().get("speed_ratio") != 0:
                self.indy.set_speed_ratio(0)
                Logger.info(f"[Robot] Paused by door open. Set Speed Ratio to 0.")
        
        # 2. 도어가 닫혀 있을 경우, UI 명령 처리
        else:
            # 2.1. UI에서 '일시정지' 명령을 받은 경우
            if program_control_cmd == ProgramControl.PROG_PAUSE:
                bb.set("ui/reset/program_control", True) # 명령 소비
                if self.indy.get_motion_data().get("speed_ratio") != 0:
                    self.indy.set_speed_ratio(0)
                    Logger.info(f"[Robot] Paused by UI command. Set Speed Ratio to 0.")
            
            # 2.2. UI에서 '재시작' 또는 '시작' 명령을 받은 경우
            elif program_control_cmd in (ProgramControl.PROG_RESUME, ProgramControl.PROG_START):
                bb.set("ui/reset/program_control", True) # 명령 소비
                if self.indy.get_motion_data().get("speed_ratio") != 100:
                    self.indy.set_speed_ratio(100)
                    Logger.info(f"[Robot] Resumed by UI command. Set Speed Ratio to 100.")
        
        # 3. 현재 로봇 속도를 블랙보드에 기록합니다.
        robot_speed = self.indy.get_motion_data()['speed_ratio']
        bb.set("robot/speed", robot_speed)

        match = re.search(r'/index/(\d+)', self.program_name)
        if match:
            program_index = match.group(1)
            if program_index == "1":
                ''' 프로그램 시작/일시정지/정지/다시시작 버튼  '''
                if self.program_state == ProgramState.PROG_IDLE:
                    bb.set("ui/state/program_state", 0)  # Init
                elif self.program_state == ProgramState.PROG_RUNNING:
                    if self.indy.get_motion_data().get("speed_ratio", 100) == 0:
                        bb.set("ui/state/program_state", 3)  # Pause
                    elif self.indy.get_motion_data().get("speed_ratio", 100) == 100:
                        bb.set("ui/state/program_state", 1)  # Start
                elif self.program_state == ProgramState.PROG_STOPPING:
                    bb.set("ui/state/program_state", 4)  # Stop
                    if self.indy.get_motion_data().get("speed_ratio", 100) == 0:
                        bb.set("ui/state/program_state", 3)  # Pause
                    elif self.indy.get_motion_data().get("speed_ratio", 100) == 100:
                        bb.set("ui/state/program_state", 2)  # Resume
