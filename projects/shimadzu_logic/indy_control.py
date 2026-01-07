import threading
import time
import datetime
import os
import json
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
        self.indy.set_speed_ratio(100) # (70) 
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

        # [Data Recorder] 데이터 기록 관련 변수 초기화
        self.record_dir = os.path.join(os.path.dirname(__file__), "motion_data")
        os.makedirs(self.record_dir, exist_ok=True)
        self.is_recording = False
        self.trajectory_buffer = []
        self.recording_file_path = ""
        self.last_record_time = 0
        self.recording_cmd_id = 0
        self.control_data_p = [0.0] * 6  # [x, y, z, u, v, w]

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

            # if self.program_state in (ProgramState.PROG_RUNNING, ProgramState.PROG_PAUSING):
            #     try:
            #         # Logger.info("Stop program!!")
            #         # self.indy.stop_program()
            #         bb.set("ui/reset/robot/recover_motion",True)
            #         # self.indy.set_speed_ratio(30) # (70) 
            #     except:
            #         Logger.error("Stop program fail")

            # self.indy.stop_motion(stop_category=2)
            # self.indy.set_int_variable([{'addr': int(self.config["int_var/cmd/addr"]), 'value': 0}])

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
            
            self.process_recording() # [Data Recorder] 기록 처리

    def start_recording(self, cmd_id):
        """ 데이터 기록 시작 (JSON 저장을 위한 버퍼 초기화) """
        if self.is_recording:
            return

        try:
            # 폴더가 없는 경우 생성
            os.makedirs(self.record_dir, exist_ok=True)

            # CMD ID로 모션 이름 찾기
            try:
                cmd_name = RobotMotionCommand(cmd_id).name
            except ValueError:
                cmd_name = f"CMD_{cmd_id}"

            # 파일명 생성 (타임스탬프 추가로 누적 가능)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{cmd_name}_{timestamp}.json"
            self.recording_file_path = os.path.join(self.record_dir, file_name)

            # 데이터 버퍼 초기화
            self.trajectory_buffer = []

            self.is_recording = True
            self.recording_cmd_id = cmd_id
            self.last_record_time = time.time() - 0.01 # 시작 즉시 첫 데이터 기록
            Logger.info(f"[DataRecorder] Recording started for '{cmd_name}'. Saving to: {file_name}")
        except Exception as e:
            Logger.error(f"[DataRecorder] Failed to start recording: {e}")

    def stop_recording(self):
        """ 데이터 기록 종료 (JSON 파일로 저장) """
        if not self.is_recording:
            return

        try:
            # 요청된 JSON 구조 생성
            json_data = {
                "CMD": self.recording_cmd_id,
                "motion_trajectory": self.trajectory_buffer
            }

            with open(self.recording_file_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4)
            
            Logger.info(f"[DataRecorder] Motion data saved to {self.recording_file_path}")

        except Exception as e:
            Logger.error(f"[DataRecorder] Failed to save JSON data: {e}")
        finally:
            # Reset recording state
            self.is_recording = False
            self.recording_cmd_id = 0
            self.trajectory_buffer = []
            self.recording_file_path = ""
            Logger.info("[DataRecorder] Recording stopped.")

    def process_recording(self):
        """ 0.01초 주기로 데이터 기록 (버퍼에 추가) """
        if self.is_recording and (time.time() - self.last_record_time >= 0.01):
            try:
                # control_data_p는 indy_communication에서 업데이트됨
                # timestamp를 제외하고 6-DOF 좌표만 추가
                self.trajectory_buffer.append(self.control_data_p)
                self.last_record_time = time.time()
            except Exception as e:
                Logger.error(f"[DataRecorder] Error buffering data: {e}")

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
        # TODO 146-172번째 줄 코드 프로그램 정지 상태일때만 가능하도록 코드작성
        if bb.get("ui/cmd/robot_control/trigger"):
            bb.set("ui/cmd/robot_control/trigger", 0) # Consume trigger

            # 프로그램이 실행 중이 아닐 때(IDLE 상태)만 수동 제어 명령을 처리합니다.
            if self.program_state == ProgramState.PROG_IDLE:
                if bb.get("device/remote/input/SELECT_SW") != 1:
                    Logger.info("[Robot] Robot control command ignored: System is in MANUAL mode (SELECT_SW != 1).")
                    payload = bb.get("ui/cmd/robot_control/data")
                    if payload and isinstance(payload, dict):
                        target = payload.get("target")
                        action = payload.get("action")
                        Logger.info(f"Received robot_control command via MQTT->BB: target={target}, action={action}")

                        # Gripper Control (target: gripper, action: open/close)
                        if target == "gripper":
                            try:
                                if action == "open":
                                    Logger.info("Sending Gripper Open command (Endtool DO8=0, DO9=1).")
                                    self.indy.set_do([{'address': 8, 'state': DigitalState.OFF_STATE}])
                                    self.indy.set_do([{'address': 9, 'state': DigitalState.OFF_STATE}])
                                    time.sleep(0.5)
                                    self.indy.set_do([{'address': 8, 'state': DigitalState.OFF_STATE}])
                                    self.indy.set_do([{'address': 9, 'state': DigitalState.ON_STATE}])
                                elif action == "close":
                                    Logger.info("Sending Gripper Close command (Endtool DO8=1, DO9=0).")
                                    self.indy.set_do([{'address': 8, 'state': DigitalState.OFF_STATE}])
                                    self.indy.set_do([{'address': 9, 'state': DigitalState.OFF_STATE}])
                                    time.sleep(0.5)
                                    self.indy.set_do([{'address': 8, 'state': DigitalState.ON_STATE}])
                                    self.indy.set_do([{'address': 9, 'state': DigitalState.OFF_STATE}])

                            except Exception as e:
                                Logger.error(f"Failed to control gripper via Endtool DO: {e}")

                        # Direct Teaching Control (target: robot_direct_teaching_mode, action: enable/disable)
                        elif target == "robot_direct_teaching_mode":
                            if action == "enable":
                                try:
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
                else :
                    Logger.info(f"[Robot] Robot control command ignored: System is in MANUAL mode (SELECT_SW != 1).")
            else:
                Logger.warn(f"Robot control command ignored. Program is not in IDLE state (current: {ProgramState(self.program_state).name}).")

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
                    bb.set("ui/state/direct_state", 2)
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
                    # self.indy.set_speed_ratio(0) # (70)
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
                if motion_ack >= 1500: # 자동화 공정 기준으로 값 결정
                    current_pos_id = motion_ack - 500
                    bb.set("robot/current/position", current_pos_id)
                    # Logger.info(f"[Safety] Robot position updated to: {current_pos_id}")
            
            motion_done = self.get_intvar_address(int_var, int(self.config["int_var/motion_done/addr"]))
            if motion_done is not None:
                bb.set("int_var/motion_done/val", motion_done)

            robot_pos = self.get_intvar_address(int_var, int(self.config["int_var/robot/position/addr"]))
            if robot_pos is not None:
                bb.set("int_var/robot/position/val", robot_pos)

            # [Data Recorder] 기록 제어 로직
            current_cmd_bb = int(bb.get("int_var/cmd/val") or 0)
            
            # 1. 기록 시작: 새로운 명령이 있고, 아직 기록 중이 아닐 때
            if current_cmd_bb != 0 and not self.is_recording:
                self.start_recording(current_cmd_bb)
            
            # 2. 기록 종료: 기록 중이고 DONE 신호가 왔을 때
            if self.is_recording and motion_done is not None:
                # DONE 조건: CMD + 10000 (일반적) 또는 CMD (사용자 정의)
                if motion_done == (self.recording_cmd_id + 10000) or motion_done == self.recording_cmd_id:
                    self.stop_recording()


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
            self.control_data_p = control_data['p'] # [Data Recorder] 전체 P 데이터(x,y,z,u,v,w) 저장
            self.robot_state = control_data["op_state"]
            self.is_sim_mode = control_data["sim_mode"]
            self.robot_running_hour = control_data["running_hours"]
            self.robot_running_min = control_data["running_mins"]
            self.program_state = program_data["program_state"]
            self.program_name = program_data["program_name"]
            q = self.indy.get_control_data()["q"]
            self.is_home_pos = all(self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.home_pos))
            self.is_packaging_pos = all(self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.packaging_pos))

            bb.set("ui/robot/state/position",f"{self.control_data_p}")
            # Gripper state feedback from Analog Input
            get_robot_ai : dict = self.indy.get_ai()
            ai_00 : dict = get_robot_ai.get("signals")[0]
            ai_00_voltage = int(ai_00.get("voltage"))
            
            if ai_00_voltage :
                if ai_00_voltage >= 300 and ai_00_voltage < 11000:
                    bb.set("robot/gripper/actual_state", 2)
                else:
                    bb.set("robot/gripper/actual_state", 1)

            else:
                bb.set("robot/gripper/actual_state", 0)

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

        # Robot status string for UI
        robot_status_str = "대기"
        if robot_state_ui in [2, 3, 5]: # Emergency, Error, Collision
            robot_status_str = "에러"
        elif self.program_state == ProgramState.PROG_RUNNING:
            robot_status_str = "가동중"
        elif self.program_state == ProgramState.PROG_PAUSING:
            robot_status_str = "일시정지"
        bb.set("process_status/robot_status", robot_status_str)

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
                if bb.get("process/program/is_resume") and self.indy.get_motion_data().get("speed_ratio") != 100:
                    self.indy.set_speed_ratio(100) # (70)
                    bb.set("process/program/is_resume", False)
                    Logger.info(f"[Robot] Resumed by UI command. Set Speed Ratio to 100.")
                    Logger.info(f"[Robot] is_resume flag detected. Set Speed Ratio to 100. and reset the flag.")
        
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
                # elif self.program_state == ProgramState.PROG_STOPPING:
                #     bb.set("ui/state/program_state", 4)  # Stop
                #     if self.indy.get_motion_data().get("speed_ratio", 100) == 0:
                #         bb.set("ui/state/program_state", 3)  # Pause
                #     elif self.indy.get_motion_data().get("speed_ratio", 100) == 100:
                #         bb.set("ui/state/program_state", 2)  # Resume
