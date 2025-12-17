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

class GripperControl:
    def __init__(self, alpha=0.9):
        self.alpha = alpha  # EMA smoothing
        self.filtered_signal = 0
        self.target_state = "OPEN"
        self.last_state = "OPEN"
        self.close_failure_duration = 0
        self.open_failure_duration = 0

    def update_signal(self, new_signal, gripper_open):
        # EMA 필터
        if self.filtered_signal == 0:
            self.filtered_signal = new_signal
        else:
            self.filtered_signal = self.alpha * new_signal + (1 - self.alpha) * self.filtered_signal

        # 상태 판단
        open_low, open_high = global_config.get("gripper.open_bound")
        close_low, close_high = global_config.get("gripper.close_bound")

        if open_low < self.filtered_signal < open_high:
            current_state = "OPEN"
        elif close_low < self.filtered_signal < close_high:
            current_state = "CLOSED_BASKET"
        else:
            current_state = "TRANSITION"

        # 실패 누적 시간 계산
        self.close_failure_duration = self.close_failure_duration + 1 \
            if not gripper_open and current_state != "CLOSED_BASKET" else 0

        self.open_failure_duration = self.open_failure_duration + 1 \
            if gripper_open and current_state != "OPEN" else 0

        # 실패 여부 판단
        close_failure = self.close_failure_duration > global_config.get("gripper.close_failure_duration")
        open_failure = self.open_failure_duration > global_config.get("gripper.open_failure_duration")

        # 상태 업데이트
        # Logger.info(f"{close_failure}, {open_failure}, {gripper_open}, {current_state}, {self.filtered_signal},"
        #             f"{self.close_failure_duration}, {self.open_failure_duration}")
        self.last_state = current_state
        return current_state, close_failure, open_failure


class RobotCommunication:
    def __init__(self, config_file="projects/shimadzu_logic/configs/indy_command.json", *args, **kwargs):
        ''' Thread related '''
        self.running = False
        self.thread = None

        ''' Config '''
        self.config = load_json(config_file)
        self.home_pos = self.config["home_pos"]
        self.packaging_pos = self.config["packaging_pos"]

        ''' Indy command '''
        self.indy = IndyDCP3(global_config.get("robot_ip"), *args, **kwargs)
        self.indy.set_speed_ratio(100) 
        # self.indy.set_auto_mode(True)
        is_auto_mode : dict = self.indy.check_auto_mode()
        if not is_auto_mode.get('on') :
            self.indy.set_auto_mode(True)
            time.sleep(0.5)


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

        self.gripper_control = GripperControl(alpha=global_config.get("gripper.filter_alpha"))

        ''' Conty Int variable, first initialization '''
        self.int_var_init = 0
        self.int_var_motion_done = 0

        self.indy.set_int_variable([
            {'addr': int(self.config["int_var/cmd/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/init/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/grip_state/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/recover_done/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/pull_done/addr"]), 'value': 0},
        ])

        ''' Indy ioboard '''
        self.btn_direct_teaching = 0
        self.btn_stop = 0

        ''' Indy endtool gripper '''
        self.endtool_ai = False
        self.is_gripper_open = False

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

        # ''' Gripper control '''
        # if bb.get("indy_command/gripper_open"):
        #     self.indy.set_endtool_do(self.gripper_open_command)
        #     bb.set("indy_command/gripper_open", False)

        # if bb.get("indy_command/gripper_close"):
        #     self.indy.set_endtool_do(self.gripper_close_command)
        #     bb.set("indy_command/gripper_close", False)

        ''' Direct teaching '''
        if bb.get("indy_command/direct_teaching_on") == 1:
            bb.set("indy_command/direct_teaching_on", 0)
            if self.program_state != ProgramState.PROG_RUNNING:
                try:
                    is_auto_mode : dict = self.indy.check_auto_mode()
                    if not is_auto_mode.get('on') :
                        self.indy.set_auto_mode(True)
                        time.sleep(0.5)
                    Logger.info("Start direct teching program")
                    self.indy.play_program(prog_idx=int(self.config["conty_direct_teaching_program_index"]))
                    bb.set("ui/state/direct_state",1)
                except:
                    Logger.error("Start direct teching program fail")
            # self.indy.set_direct_teaching(True)
        if bb.get("indy_command/direct_teaching_on") == 2:
            bb.set("indy_command/direct_teaching_on", 0)
            if self.program_state in (ProgramState.PROG_RUNNING, ProgramState.PROG_PAUSING):
                try:
                    Logger.info("Stop program!!")
                    self.indy.stop_program()
                    time.sleep(0.5)
                    is_auto_mode : dict = self.indy.check_auto_mode()
                    # if is_auto_mode.get('on') :
                    #     self.indy.set_auto_mode(False)
                    bb.set("ui/state/direct_state",2)
                    self.indy.set_speed_ratio(100)
                except:
                    Logger.error("Stop program fail")

        if bb.get("indy_command/direct_teaching_off"):
            bb.set("indy_command/direct_teaching_off", False)
            # self.indy.set_direct_teaching(False)

        ''' Buzzer '''
        if bb.get("indy_command/buzzer_on"):
            bb.set("indy_command/buzzer_on", False)
            # self.indy.set_do([{'address': self.buzzer_ch, 'state': DigitalState.ON_STATE}])

        if bb.get("indy_command/buzzer_off"):
            bb.set("indy_command/buzzer_off", False)
            # self.indy.set_do([{'address': self.buzzer_ch, 'state': DigitalState.OFF_STATE}])

        ''' Speed ratio control '''
        if bb.get("indy_command/speed_ratio_full"):
            bb.set("indy_command/speed_ratio_full", False)
            self.indy.set_speed_ratio(100) 

        if bb.get("indy_command/speed_ratio_zero"):
            bb.set("indy_command/speed_ratio_zero", False)
            self.indy.set_speed_ratio(0)

        ''' Stop motion '''
        if bb.get("indy_command/stop_motion"):
            bb.set("indy_command/stop_motion", False)
            self.indy.stop_motion(stop_category=2)

        ''' Move to home position '''
        if bb.get("indy_command/go_home"):
            # bb.set("indy_command/go_home", False)
            try:
                
                self.indy.set_auto_mode(True)
                cur_data: dict = self.indy.get_control_data()
                while bb.get("indy_command/go_home") :
                    data =  bb.get("indy_command/go_home")
                    # Logger.info(f"go home {data}")
                    cur_pos = cur_data.get("q")
                    cur_joint_pos = np.array(cur_pos)
                    home_joint_pos = np.array(self.home_pos)
                    self.indy.set_speed_ratio(30)
                    self.indy.movej(home_joint_pos)
                    time.sleep(0.1)
                Logger.info(f"indy 283 robot pos 1 set")
                bb.set("process/robot/position",1)
                bb.set("process/manual/recover",0)                
                self.indy.stop_motion(2)
                self.indy.set_speed_ratio(100)
                self.indy.set_auto_mode(True)


            except:
                Logger.error("Fail to execute move command")

        ''' Move to packaging position '''
        if bb.get("indy_command/go_packaging"):
            bb.set("indy_command/go_packaging", False)
            try:
                self.indy.movej(self.packaging_pos, teaching_mode=True, vel_ratio=30)
            except:
                Logger.error("Fail to execute move command")

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

        ''' Start program (Direct Teaching program, index=2) '''
        if bb.get("indy_command/direct_teaching_program"):
            bb.set("indy_command/direct_teaching_program", False)
            if self.program_state != ProgramState.PROG_RUNNING:
                try:
                    self.indy.play_program(prog_idx=int(self.config["conty_direct_teaching_program_index"]))
                except:
                    Logger.error("Start direct teaching program fail")

        ''' Start program (Warming motion, index=3) '''
        if bb.get("indy_command/play_warming_program"):
            bb.set("indy_command/play_warming_program", False)
            if self.program_state != ProgramState.PROG_RUNNING:
                try:
                    self.indy.play_program(prog_idx=int(self.config["conty_warming_program_index"]))
                except:
                    Logger.error("Start warming program fail")

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
        # Gripper Clamp
        if bb.get("ui/command/robot/gripper")  == 1:
            Logger.info("Robot Gripper Clamp")  
            bb.set("ui/reset/robot/gripper", True)
            signal = [
                {'address':0, 'state':DigitalState.ON_STATE},
                {'address':1, 'state':DigitalState.OFF_STATE},
                {'address':2, 'state':DigitalState.OFF_STATE}
            ]
            self.indy.set_do(signal)
            time.sleep(0.1)
            signal = [
                {'address':0, 'state':DigitalState.OFF_STATE},
                {'address':1, 'state':DigitalState.ON_STATE},
                {'address':2, 'state':DigitalState.OFF_STATE}
            ]
            self.indy.set_do(signal)

            read_signal = self.indy.get_do().get('signals')
            do_01 = read_signal[1].get('state')
            do_02 = read_signal[2].get('state')
            Logger.info(f"do_01 : {do_01}, do_02 : {do_02}")

            if do_01 == 1 and do_02 == 0 :
                bb.set("ui/state/robot/gripper_state",1)

        # Gripper UnClamp
        elif bb.get("ui/command/robot/gripper")  == 2:
            Logger.info("Robot Gripper Unclamp") 
            bb.set("ui/reset/robot/gripper", True)
            signal = [
                {'address':0, 'state':DigitalState.ON_STATE},
                {'address':1, 'state':DigitalState.OFF_STATE},
                {'address':2, 'state':DigitalState.OFF_STATE}
            ]
            self.indy.set_do(signal)
            time.sleep(0.1)
            signal = [
                {'address':0, 'state':DigitalState.OFF_STATE},
                {'address':1, 'state':DigitalState.OFF_STATE},
                {'address':2, 'state':DigitalState.ON_STATE}
            ]
            self.indy.set_do(signal)

            read_signal = self.indy.get_do().get('signals')
            do_01 = read_signal[1].get('state')
            do_02 = read_signal[2].get('state')
            Logger.info(f"do_01 : {do_01}, do_02 : {do_02}")
            if do_01 == 0 and do_02 == 1 :
                bb.set("ui/state/robot/gripper_state",2)


        ''' Reset '''
        if bb.get("indy_command/recover"):
            bb.set("indy_command/recover", False)
            self.indy.recover()
            Logger.info(f"Robot Send Recovery command")


    def handle_int_variable(self):
        """
        Command request from FSM by blackbaord
        - only work in ReadyIdle mode (Program is Running)
        """
        '''
        Variables
            Write variables (FSM -> Conty)
                - cmd (600)
                - grip_state (100)
                - retry_grip (101): conty에서 0으로 초기화
                - putin_shake (130)
                - shake_num (131)
                - shake_break (132)
            Read variables (Conty -> FSM)
                - init (700): 동일 동작을 위해 Python에서 초기화
                - pickup_done (102)                
        '''

        ''' Reset variables '''
        if bb.get("indy_command/reset_init_var"):
            bb.set("indy_command/reset_init_var", False)
            self.indy.set_int_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': 0}])
        
        if bb.get("indy_command/reset_pull_done"):
            bb.set("indy_command/reset_pull_done", False)
            self.indy.set_int_variable([{'addr': int(self.config["int_var/pull_done/addr"]), 'value': 0}])
        

        ''' Read Variables: Send int variable from Conty to bb '''
        int_var = self.indy.get_int_variable()['variables']

        self.int_var_init = self.get_intvar_address(int_var, int(self.config["int_var/init/addr"]))
        bb.set("int_var/init/val", self.int_var_init)
        self.int_var_motion_done = self.get_intvar_address(int_var, int(self.config["int_var/motion_done/addr"]))
        bb.set("int_var/motion_done/val", self.int_var_motion_done)

        bb.set("recipe/pot1/shift/basket",self.get_intvar_address(int_var, int(self.config[f"int_var/left_pull_done/addr"])))
        bb.set("recipe/pot2/shift/basket",self.get_intvar_address(int_var, int(self.config[f"int_var/right_pull_done/addr"])))

        bb.set(f"int_var/robot/position/val", self.get_intvar_address(int_var, int(self.config[f"int_var/robot/position/addr"])))
        # bb.set(f"int_var/pickup_done/val", self.get_intvar_address(int_var, int(self.config[f"int_var/pickup_done/addr"])))
        # bb.set(f"int_var/putin_done/val", self.get_intvar_address(int_var, int(self.config[f"int_var/putin_done/addr"])))
        # bb.set(f"int_var/current_pos/val", self.get_intvar_address(int_var, int(self.config[f"int_var/current_pos/addr"])))
        bb.set(f"int_var/pull_done/val", self.get_intvar_address(int_var, int(self.config[f"int_var/pull_done/addr"])))
        if bb.get(f"int_var/pull_done/val") == 1 :
            bb.set("process/robot/pull_done",1)

        ''' Write Variables: Set Int variable from bb to Conty '''
        self.indy.set_int_variable([
            {'addr': int(self.config["int_var/cmd/addr"]),                  'value': int(bb.get("int_var/cmd/val"))},
            {'addr': int(self.config["int_var/grip_state/addr"]),           'value': int(bb.get("int_var/grip_state/val"))},
            {'addr': int(self.config["indy_command/place/go_home/addr"]),   'value': bb.get("indy_command/place/go_home")},
            {'addr': int(self.config["int_var/recover_done/addr"]),         'value': bb.get("int_var/recover_done/val")},
            {'addr': int(self.config["left_basket_stack_num/addr"]),        'value': bb.get("process/pot1/basket_stack_num")},
            {'addr': int(self.config["right_basket_stack_num/addr"]),       'value': bb.get("process/pot2/basket_stack_num")},
            {'addr': int(self.config["recover_pose/addr"]),                 'value': bb.get("process/recover_pose")}
        ])

        if bb.get("recipe/pot1/shift/basket/init") :
            Logger.info("Reset pot1 basket stack num to 0")
            bb.set("recipe/pot1/shift/basket/init", False)
            self.indy.set_int_variable([
                {'addr': int(self.config["left_basket_stack_num/addr"]), 'value': 0}
            ])

        if bb.get("recipe/pot2/shift/basket/init") :  
            Logger.info("Reset pot2 basket stack num to 0")
            bb.set("recipe/pot2/shift/basket/init", False)
            self.indy.set_int_variable([
                {'addr': int(self.config["right_basket_stack_num/addr"]), 'value': 0}
            ])


    def indy_communication(self):
        ''' Get Indy status '''
        control_data = self.indy.get_control_data()
        program_data = self.indy.get_program_data()
        # Logger.info(f"Nuri data :\n{control_data}\n{program_data}")
        self.robot_current_pos = control_data['p'][0:3]
        self.robot_state = control_data["op_state"]
        self.is_sim_mode = control_data["sim_mode"]
        self.robot_running_hour = control_data["running_hours"]
        self.robot_running_min = control_data["running_mins"]
        self.program_state = program_data["program_state"]
        self.program_name = program_data["program_name"]

        q = self.indy.get_control_data()["q"]
        self.is_home_pos = all(self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.home_pos))
        self.is_packaging_pos = all(
            self.check_home_min <= a - b <= self.check_home_max for a, b in zip(q, self.packaging_pos))

        ''' Get Indy ioboard data '''
        do = self.indy.get_do()['signals']  # type: ignore
        di = self.indy.get_di()['signals']  # type: ignore


        ''' Gripper state '''
        read_signal = do
        do_01 = read_signal[1].get('state')
        do_02 = read_signal[2].get('state')

        if do_01 == 1 and do_02 == 0 :
            bb.set("ui/state/robot/gripper_state",1)
        elif do_01 == 0 and do_02 == 1 :
            bb.set("ui/state/robot/gripper_state",2)

        bb.set("robot/state/entire/di",di)
        bb.set("robot/state/entire/do",do)

        di_04 = di[4].get('state')
        di_05 = di[5].get('state')
        bb.set("process/safe/slow",di_04)
        bb.set("process/safe/stop",di_05)
        if bb.get("process/moving") :
            bb.set("ui/state/safe/stop",di_05)
        else :
            bb.set("ui/state/safe/stop",0)


        # ''' Get Indy endtool data '''
        # endtool_do = self.indy.get_endtool_do()['signals']  # type: ignore
        # endtool_ai = self.indy.get_endtool_ai()['signals']  # type: ignore
        # endtool_do_state = next((item['states'] for item in endtool_do if item['port'] == self.endtool_port), None)


        # if endtool_do_state == self.gripper_open_command[0]['states']:
        #     self.is_gripper_open = True     # Open
        # else:
        #     self.is_gripper_open = False    # Close

        # self.endtool_ai = next(
        #     (int(item['voltage']) for item in endtool_ai if item['address'] == self.endtool_ai_channel), None)

        # state, close_fail, open_fail = self.gripper_control.update_signal(self.endtool_ai, self.is_gripper_open)
        # if self.is_sim_mode:
        #     if self.get_dio_channel(do, 13):
        #         bb.set("int_var/grip_state/val", GripFailure.SUCCESS)
        #     elif self.get_dio_channel(do, 14):
        #         bb.set("int_var/grip_state/val", GripFailure.OPEN_FAIL)
        #     elif self.get_dio_channel(do, 15):
        #         bb.set("int_var/grip_state/val", GripFailure.CLOSE_FAIL)
        # else:
        #     if close_fail and global_config.get("grip_close_fail_fool_proof"):
        #         bb.set("int_var/grip_state/val", GripFailure.CLOSE_FAIL)
        #     elif open_fail and global_config.get("grip_open_fail_fool_proof"):
        #         bb.set("int_var/grip_state/val", GripFailure.OPEN_FAIL)
        #     else:
        #         bb.set("int_var/grip_state/val", GripFailure.SUCCESS)

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
            "endtool_ai": self.endtool_ai,
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

        # ''' Direct teaching (On, Off) '''
        # if self.robot_state == Robot_OP_State.OP_TEACHING:
        #     bb.set("ui/state/direct_state", 1)  # On
        # else:
        #     bb.set("ui/state/direct_state", 2)  # Off

        # ''' Gripper (닫기, 열기) '''
        # if self.is_gripper_open:
        #     bb.set("ui/state/gripper_state", 2)  # 닫기
        # else:
        #     bb.set("ui/state/gripper_state", 1)  # 열기

        ''' Program control (일시정지, 다시시작) '''
        if bb.get("ui/command/program_control") == ProgramControl.PROG_PAUSE:
            bb.set("ui/reset/program_control", True)
            
            self.indy.set_speed_ratio(0)
            Logger.info(f"[Robot] Set Speed Ratio {0}")
            bb.set("robot/speed",0)
        elif bb.get("ui/command/program_control") == ProgramControl.PROG_RESUME:
            bb.set("ui/reset/program_control", True)
            
            self.indy.set_speed_ratio(100)
            Logger.info(f"[Robot] Set Speed Ratio {100}")
            bb.set("robot/speed",100)
        elif bb.get("ui/command/program_control") == ProgramControl.PROG_START:
            bb.set("ui/reset/program_control", True)
            if self.program_state == ProgramState.PROG_RUNNING:
                self.indy.set_speed_ratio(100) 
                Logger.info(f"[Robot] UI command Set Speed Ratio {100}")
                bb.set("robot/speed",100)
        
        if bb.get("progress/robot/pause") == 1 :
            bb.set("progress/robot/pause",0)
            self.indy.set_speed_ratio(0)
            Logger.info(f"[Robot] Pause result Set Speed Ratio {0}")
            bb.set("robot/speed",0)
            bb.set("process/robot/state/pause",1)
        elif bb.get("progress/robot/pause") == 2 :
            # TODO if문 추가 UI에서 재시작 명령 보내주기
            if bb.get("ui/command/restart") :  
                Logger.info(f"[Robot] pause 2 Restart Button On")               
                bb.set("progress/robot/pause",0)
                self.indy.set_speed_ratio(100)
                Logger.info(f"[Robot] Pause result Set Speed Ratio {100}")
                bb.set("robot/speed",100)
                bb.set("process/robot/state/pause",0)
                time.sleep(1)
                # bb.set("ui/reset/restart",True)
        
        elif bb.get("progress/robot/pause") == 0 :
            stop = bb.get("process/safe/stop") 
            slow = bb.get("process/safe/slow")
            # Logger.info(f"test -=-=-09-8987-=-=-  {stop} {slow} ")
            robot_cur_speed = self.indy.get_motion_data()['speed_ratio']
            if bb.get("process/safe/stop") :
                # if robot_cur_speed != 0:
                self.indy.set_speed_ratio(0)
                #Logger.info(f"[Robot] Lidar Pause result Set Speed Ratio {0}")
                if bb.get("ui/state/safe/stop") :
                    self.robot_paused = True
                    Logger.info(f"[Robot] Lidar Detect Stop")
            elif bb.get("process/safe/slow") :
                if robot_cur_speed != 30:                    
                    if self.robot_paused :
                        Logger.info(f"[Robot] Slow pause 0 Restart Button On")                        
                        if bb.get("ui/command/restart") :
                            self.robot_paused = False
                            Logger.info(f"[Robot] pause slow Restart Button On")
                            # bb.set("ui/reset/restart",True)
                            Logger.info(f"restart button vlaue reset")
                    else :
                        if self.robot_paused :                            
                            if bb.get("ui/command/restart") :
                                self.robot_paused = False
                                self.indy.set_speed_ratio(30)
                                # bb.set("ui/reset/restart",True)
                                Logger.info(f"[Robot] Button on Pause result Set Speed Ratio {30}")
                        else :
                            self.indy.set_speed_ratio(30)
                            Logger.info(f"[Robot] Pause result Set Speed Ratio {30}")
            else :
                if self.robot_paused :
                    if bb.get("ui/command/restart") :
                        self.robot_paused = False
                        Logger.info(f"[Robot] pause 0 Restart Button On")
                        # bb.set("ui/reset/restart",True)
                        Logger.info(f"restart button vlaue reset")
                        self.indy.set_speed_ratio(100)
                        Logger.info(f"[Robot] Button On Pause result Set Speed Ratio {100}")
                    
                else : #bb.get(f"recipe/state/pot1/state") == RecipeFsmState.NO_MENU and bb.get(f"recipe/state/pot2/state") == RecipeFsmState.NO_MENU :
                    if robot_cur_speed != 100 :      
                        self.indy.set_speed_ratio(100)
                        Logger.info(f"[Robot] Else Pause result Set Speed Ratio {100}")

                    ######################################
            
            robot_speed  = self.indy.get_motion_data()['speed_ratio']
            bb.set(f"robot/speed",robot_speed)

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
