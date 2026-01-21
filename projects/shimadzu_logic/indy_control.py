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
import joblib

# Vision Handler import
try:
    from .vision_client_for_smz import VisionHandler
    VISION_HANDLER_AVAILABLE = True
except ImportError as e:
    VISION_HANDLER_AVAILABLE = False
    print(f"[WARNING] VisionHandler import failed: {e}")

# Zone Predictor import
try:
    from .ml_recovery.zone_predictor import ZonePredictor
    ZONE_PREDICTOR_AVAILABLE = True
except ImportError:
    ZONE_PREDICTOR_AVAILABLE = False
    # print("[WARNING] ZonePredictor import failed")

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
 
        #Sehoon CMD lifecycle timing
        self.cmd_send_ts = None
        self.cmd_ack_ts = None
        self.cmd_done_ts = None
        self.cmd_tracking_id = None
        self.last_done_ts = None  # track last DONE to measure idle gap before next CMD
        self.o_motion_done = None
        self.o_motion_ack = None
 
        # indy_communication에서 설정되는 속성들을 안전하게 초기화합니다.
        self.robot_current_pos = [0.0, 0.0, 0.0]
        self.program_state = ProgramState.PROG_IDLE
        self.program_name = ""

        ''' Conty Int variable, first initialization '''
        self.indy.set_int_variable([
            {'addr': int(self.config["int_var/cmd/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/grip_state/addr"]), 'value': 0},
            {'addr': int(self.config["int_var/grip_retry/addr"]), 'value': 0},
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
        self.bin_picking_home = self.config["bin_picking_home_pos"]
        # [Robot Home Move] 홈 이동 상태 관리
        self.robot_home_last_enable_time = None

        # [Zone Predictor] 모델 로드
        self.zone_predictor = None
        if ZONE_PREDICTOR_AVAILABLE:
            Logger.info("[Indy7] Initializing Zone Predictor...")
            try:
                self.zone_predictor = ZonePredictor()
                if self.zone_predictor.load_model():
                    Logger.info(f"[Indy7] Zone predictor model loaded successfully")
                else:
                    Logger.warn(f"[Indy7] Failed to load zone predictor model")
            except Exception as e:
                Logger.error(f"[Indy7] Error initializing ZonePredictor: {e}")

        # [Vision Handler] Bin Picking을 위한 VisionHandler 초기화
        self.vision_handler = None
        if VISION_HANDLER_AVAILABLE:
            vision_ip = general_config.get("bin_picking_ip", "192.168.2.16")
            vision_port = general_config.get("bin_picking_port", 5003)
            try:
                self.vision_handler = VisionHandler(host=vision_ip, port=vision_port, robot_ip=robot_ip)
                Logger.info(f'[VisionHandler] VisionHandler initialized successfully (Vision: {vision_ip}:{vision_port}, Robot: {robot_ip})')
            except Exception as e:
                Logger.error(f'[VisionHandler] Failed to initialize VisionHandler: {e}', exc_info=True)
                self.vision_handler = None
        else:
            Logger.warn(f'[VisionHandler] VisionHandler module not available. Bin Picking features will be disabled.')

        # [Tensile Test] Hardcoded Positions & Calculation Variables
        self.tensile_pos_1_p = [-210.2356, -160.18307, 641.5257, -168.5878, -108.025406, 170.19357]
        self.tensile_pos_2_p =  [-300.77945, -164.11026, 653.3784, -171.25029, -107.91982, 172.89037]

        self.calc_tensile_jpos_1 = None
        self.calc_tensile_jpos_2 = None
        self.calc_tensile_jpos_3 = None
        
        self.last_ana_result_params = None

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
    def go_home_bin_picking(self):
        """ Robot move to bin picking home position """
        Logger.info("[Indy7] Moving to bin picking home position...")
        self.indy.movej(self.bin_picking_home, vel_ratio=50)
        self.indy.wait_for_motion_state('is_target_reached')
        Logger.info("[Indy7] Reached home position.")

    def execute_cmd_sequence(self, cmd_list, description=""):
        """
        로봇에게 일련의 CMD ID를 순차적으로 전송하고 완료를 대기합니다.
        (indy_control 내부에서 직접 제어할 때 사용)
        """
        # [Fix] 로봇 프로그램 실행 상태 확인 및 자동 시작
        # execute_cmd_sequence는 메인 루프를 블로킹하므로 직접 상태를 확인해야 합니다.
        try:
            prog_data = self.indy.get_program_data()
            if prog_data["program_state"] != ProgramState.PROG_RUNNING:
                Logger.warn(f"[ToolChange] Robot program is NOT running. Attempting to start...")
                
                # Auto Mode 확인 및 설정
                is_auto_mode = self.indy.check_auto_mode()
                if not is_auto_mode.get('on'):
                    self.indy.set_auto_mode(True)
                    time.sleep(0.5)

                self.indy.play_program(prog_idx=int(self.config["conty_main_program_index"]))
                
                # 프로그램 시작 대기 (최대 5초)
                for _ in range(50):
                    time.sleep(0.1)
                    prog_data = self.indy.get_program_data()
                    if prog_data["program_state"] == ProgramState.PROG_RUNNING:
                        Logger.info("[ToolChange] Robot program started.")
                        # ACK/DONE 초기화 (Init=True -> False)
                        init_addr = int(self.config["int_var/init/addr"])
                        self.indy.set_bool_variable([{'addr': init_addr, 'value': True}])
                        time.sleep(0.1)
                        self.indy.set_bool_variable([{'addr': init_addr, 'value': False}])
                        break
                else:
                    Logger.error("[ToolChange] Failed to start robot program. Aborting sequence.")
                    return False
        except Exception as e:
            Logger.error(f"[ToolChange] Error checking/starting robot program: {e}")
            return False

        Logger.info(f"[ToolChange] Starting sequence: {description}")
        cmd_addr = int(self.config["int_var/cmd/addr"])
        ack_addr = int(self.config["int_var/motion_ack/addr"])
        done_addr = int(self.config["int_var/motion_done/addr"])
        init_addr = int(self.config["int_var/init/addr"])

        for cmd_id in cmd_list:
            Logger.info(f"[ToolChange] Executing CMD {cmd_id}...")
            
            # 1. Send CMD & Init=True
            self.indy.set_int_variable([{'addr': cmd_addr, 'value': cmd_id}])
            self.indy.set_bool_variable([{'addr': init_addr, 'value': True}])
            
            # 2. Wait for ACK (CMD + 500)
            start_time = time.time()
            while time.time() - start_time < 5.0:
                int_vars = self.indy.get_int_variable()['variables']
                ack = self.get_intvar_address(int_vars, ack_addr)
                if ack == cmd_id + 500:
                    break
                time.sleep(0.05)
            else:
                Logger.error(f"[ToolChange] Timeout waiting for ACK of CMD {cmd_id}")
                return False
            
            # 3. Reset CMD & Init=False
            self.indy.set_int_variable([{'addr': cmd_addr, 'value': 0}])
            self.indy.set_bool_variable([{'addr': init_addr, 'value': False}])
            
            # 4. Wait for DONE (CMD + 10000)
            start_time = time.time()
            while time.time() - start_time < 30.0:
                int_vars = self.indy.get_int_variable()['variables']
                done = self.get_intvar_address(int_vars, done_addr)
                if done == cmd_id + 10000:
                    break
                time.sleep(0.05)
            else:
                Logger.error(f"[ToolChange] Timeout waiting for DONE of CMD {cmd_id}")
                return False
            
            Logger.info(f"[ToolChange] CMD {cmd_id} Done.")
        
        Logger.info(f"[ToolChange] Sequence '{description}' completed successfully.")
        return True

    def run(self):
        """ Thread's target function """
        acc_loop = 0.0
        max_loop = 0.0
        n = 0
        window_start = time.perf_counter()
        prev_start = None
 
        while self.running:
            loop_start = time.perf_counter()
            time.sleep(0.001)
            self.receive_data_from_bb()  # Get bb data, process bb data          
            self.handle_int_variable()  # Get bb data, process bb data      
            self.indy_communication()  # Get indy data        
            self.send_data_to_bb()  # Send indy data to bb            
            self.process_recording() # [Data Recorder] 기록 처리
 
            if prev_start is not None:
                loop_period = loop_start - prev_start
                acc_loop += loop_period; n += 1
                max_loop = max(max_loop, loop_period)
               
            prev_start = loop_start
 
            # if time.perf_counter() - window_start >= 5.0 and n > 0:
            #     Logger.info(
            #         f"[IndyTiming] loop avg {acc_loop/n*1000:.2f} ms max {max_loop*1000:.2f} ms (n={n})"
            #     )
            #     acc_loop = 0.0
            #     max_loop = 0.0
            #     n = 0
            #     window_start = time.perf_counter()
 

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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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

        # [Tensile Test] Update positions based on ANA_RESULT (VALUEPOS)
        ana_result = bb.get("shimadzu/ana_result")
        if ana_result and ana_result != self.last_ana_result_params:
            self.last_ana_result_params = ana_result
            try:
                value_pos = float(ana_result.get("VALUEPOS", 0))
                self._update_tensile_positions(value_pos)
            except Exception as e:
                Logger.error(f"[Indy] Failed to update tensile positions: {e}")

        # [Vision Control] MQTT → Blackboard → VisionHandler 명령 처리
        if bb.get("ui/cmd/vision/trigger"):
            bb.set("ui/cmd/vision/trigger", 0)  # Consume trigger
            action = bb.get("ui/cmd/vision/action")

            if self.vision_handler is None:
                Logger.error("[VisionControl] VisionHandler is not initialized.")
            else:
                if action == "connect":
                    Logger.info("[VisionControl] Connecting to Vision System...")
                    success = self.vision_handler.connect()
                    if success:
                        self.vision_handler.handshake()
                        Logger.info("[VisionControl] Vision System connected successfully.")
                    else:
                        Logger.error("[VisionControl] Failed to connect to Vision System.")
                elif action == "disconnect":
                    Logger.info("[VisionControl] Disconnecting from Vision System...")
                    self.vision_handler.disconnect()
                    Logger.info("[VisionControl] Vision System disconnected.")

        # [Bin Pick Control] MQTT → Blackboard → VisionHandler 명령 처리
        if bb.get("ui/cmd/binpick/trigger"):
            bb.set("ui/cmd/binpick/trigger", 0)  # Consume trigger
            action = bb.get("ui/cmd/binpick/action")

            if self.vision_handler is None:
                Logger.error("[BinPickControl] VisionHandler is not initialized.")
            elif not self.vision_handler.client.sock:
                Logger.error("[BinPickControl] Vision System is not connected. Please connect first.")
            else:
                if action == "start":
                    Logger.info("[BinPickControl] Starting Bin Picking sequence...")
                    # status: 0:초기값/1:인식/2:이동/3:잡기/4:인지/5:놓기/6:홈 이동/7:완료/10:쉐이킹
                    
                    # [Tool Check] Bin Picking 시작 전 툴 상태 확인
                    # ATC_2_2_SENSOR (Bin Tool): 1=In Station(미장착), 0=On Robot(장착)
                    atc_2_2 = bb.get("device/remote/input/ATC_2_2_SENSOR")
                    # ATC_1_2_SENSOR (Pro Tool): 1=In Station(미장착), 0=On Robot(장착)
                    atc_1_2 = bb.get("device/remote/input/ATC_1_2_SENSOR")

                    # 1. Pro Tool이 장착되어 있는 경우 -> Pro Tool 반납 후 Bin Tool 장착
                    if atc_1_2 == 0:
                        Logger.info("[BinPickControl] Pro Tool detected (ATC_1_2 OFF). Initiating tool change to Bin Tool.")
                        
                        # Drop Pro Tool Sequence: 111 -> 106 -> 107 -> 108 -> 109 -> 110 (End here)
                        drop_pro_seq = [
                            RobotMotionCommand.TOOL_CHANGE_HOME,
                            RobotMotionCommand.PRO_TOOL_MOVE_POS,
                            RobotMotionCommand.PRO_TOOL_MOVE_INSERT,
                            RobotMotionCommand.PRO_TOOL_ENTER_SENSOR_1_1,
                            RobotMotionCommand.PRO_TOOL_ENTER_SENSOR_1_2,
                            RobotMotionCommand.PRO_TOOL_INSERT_MOVE_UP
                        ]
                        if not self.execute_cmd_sequence(drop_pro_seq, "Drop Pro Tool"):
                            Logger.error("[BinPickControl] Failed to drop Pro Tool. Aborting.")
                            bb.set("process/binpick/status", 0)
                            return
                        
                        # Pro Tool 반납 완료. 바로 Bin Tool 장착 (110 -> 105 Direct)
                        Logger.info("[BinPickControl] Pro Tool dropped. Moving directly to Pick Bin Tool.")
                        
                        pick_bin_seq = [
                            RobotMotionCommand.BIN_TOOL_INSERT_MOVE_UP,
                            RobotMotionCommand.BIN_TOOL_ENTER_SENSOR_2_2,
                            RobotMotionCommand.BIN_TOOL_ENTER_SENSOR_2_1,
                            RobotMotionCommand.BIN_TOOL_MOVE_INSERT,
                            RobotMotionCommand.BIN_TOOL_MOVE_POS,
                            RobotMotionCommand.TOOL_CHANGE_HOME,
                            RobotMotionCommand.RECOVERY_HOME
                        ]
                        if not self.execute_cmd_sequence(pick_bin_seq, "Pick Bin Tool (Direct)"):
                            Logger.error("[BinPickControl] Failed to pick Bin Tool. Aborting.")
                            bb.set("process/binpick/status", 0)
                            return

                    # 2. Bin Tool이 장착되어 있지 않은 경우 (빈 손) -> Bin Tool 장착
                    elif atc_2_2 == 1:
                        Logger.info("[BinPickControl] Robot is empty (ATC_2_2 ON). Picking Bin Tool.")
                        
                        # Pick Bin Tool Sequence: 111 -> 105 -> 104 -> 103 -> 102 -> 101 -> 111 -> 100
                        pick_bin_seq = [
                            RobotMotionCommand.TOOL_CHANGE_HOME,
                            RobotMotionCommand.BIN_TOOL_INSERT_MOVE_UP,
                            RobotMotionCommand.BIN_TOOL_ENTER_SENSOR_2_2,
                            RobotMotionCommand.BIN_TOOL_ENTER_SENSOR_2_1,
                            RobotMotionCommand.BIN_TOOL_MOVE_INSERT,
                            RobotMotionCommand.BIN_TOOL_MOVE_POS,
                            RobotMotionCommand.TOOL_CHANGE_HOME,
                            RobotMotionCommand.RECOVERY_HOME
                        ]
                        if not self.execute_cmd_sequence(pick_bin_seq, "Pick Bin Tool"):
                            Logger.error("[BinPickControl] Failed to pick Bin Tool. Aborting.")
                            bb.set("process/binpick/status", 0)
                            return

                    Logger.info("[BinPickControl] Tool check complete. Bin Tool is ready.")

                    try:
                        specimen_idx = 1
                        # [Loop] 시편이 없을 때까지 반복
                        while True:
                            # [Update] 빈피킹 루프 중에도 로봇 상태 업데이트
                            self.indy_communication()
                            self.send_data_to_bb()

                            # [Stop Check] 시작 전 확인
                            if bb.get("ui/cmd/binpick/action") == "stop":
                                Logger.info("[BinPickControl] Stop signal detected. Aborting loop.")
                                break

                            # Step 1: Check Scene 요청 (status=1: 인식)
                            bb.set("process/binpick/status", 1)
                            # 이전 결과가 남아있을 수 있으므로 초기화
                            bb.set("device/vision/scene_result", None)
                            Logger.info("[BinPickControl] Step 1: Sending CHECK_SCENE request... (status=1)")
                            self.vision_handler.check_scene(mode="SINGLE")

                            # Step 2: SCENE_RESULT 응답 대기 (binpicking.md Section 7 참조)
                            Logger.info("[BinPickControl] Step 2: Waiting for SCENE_RESULT...")
                            timeout = 60.0  # 60초 타임아웃 (Vision 처리에 시간이 오래 걸릴 수 있음)
                            start_time = time.time()
                            scene_result = None

                            while (time.time() - start_time) < timeout:
                                # [Stop Check] 대기 중 정지 명령 확인
                                if bb.get("ui/cmd/binpick/action") == "stop":
                                    Logger.info("[BinPickControl] Stop command detected during wait. Aborting.")
                                    return

                                scene_result = bb.get("device/vision/scene_result")
                                if scene_result and scene_result.get("type") == "SCENE_RESULT":
                                    Logger.info(f"[BinPickControl] SCENE_RESULT received: status={scene_result.get('status')}")
                                    break
                                
                                # [Update] 대기 중 로봇 상태 업데이트
                                self.indy_communication()
                                self.send_data_to_bb()
                                
                                time.sleep(0.1)  # 100ms 주기로 체크

                            if not scene_result:
                                Logger.error("[BinPickControl] Timeout waiting for SCENE_RESULT.")
                                bb.set("process/binpick/status", 0)  # 초기화
                                break

                            # Step 3: SCENE_RESULT 분석
                            status = scene_result.get("status")
                            Logger.info(f"[BinPickControl] Processing status: {status}")

                            if status == "TASK_DONE":
                                Logger.info("[BinPickControl] No specimens detected (TASK_DONE). Loop finished.")
                                bb.set("process/binpick/status", 7)  # 완료
                                break
                            elif status == "OVERLAPPING":
                                Logger.warn("[BinPickControl] Specimens are overlapping. Shake motion needed.")
                                bb.set("process/binpick/status", 10)  # 쉐이킹
                                # TODO: Shake 동작 구현 필요 시 여기에 추가
                                # Shake 후 다시 루프 처음으로 돌아가서 인식 시도
                                # 현재는 구현 없으므로 break
                                break
                            elif status == "TASK_EXECUTION":
                                Logger.info(f"[BinPickControl] Status is TASK_EXECUTION. Processing specimens...")
                                
                                # [Stop Check]
                                if bb.get("ui/cmd/binpick/action") == "stop":
                                    Logger.info("[BinPickControl] Stop command detected. Aborting.")
                                    break

                                # Step 4: 시편 위치로 로봇 이동 (status=2: 이동)
                                bb.set("process/binpick/status", 2)
                                specimens = scene_result.get("specimens", [])
                                if not specimens:
                                    Logger.error("[BinPickControl] No specimen data in TASK_EXECUTION result.")
                                    bb.set("process/binpick/status", 0)  # 초기화
                                    break

                                Logger.info(f"[BinPickControl] Step 4: Moving to specimen location (status=2)...")

                                # [Stop Check]
                                if bb.get("ui/cmd/binpick/action") == "stop":
                                    Logger.info("[BinPickControl] Stop command detected. Aborting.")
                                    break

                                # Step 5: 시편 잡기 (status=3: 잡기)
                                # bb.set("process/binpick/status", 3)
                                Logger.info(f"[BinPickControl] Step 5: Picking specimen (status=3)...")
                                pick_success = self.vision_handler.move_to_vision_target_test()

                                if pick_success:
                                    # Step 6: 그립 확인 (status=4: 인지)
                                    bb.set("process/binpick/status", 4)
                                    Logger.info("[BinPickControl] Step 6: Pick confirmed (status=4). Proceeding to place...")

                                    # [Stop Check]
                                    if bb.get("ui/cmd/binpick/action") == "stop":
                                        Logger.info("[BinPickControl] Stop command detected. Aborting.")
                                        break

                                    # Step 7: 시편 Place (status=5: 놓기)
                                    # bb.set("process/binpick/status", 5)
                                    Logger.info(f"[BinPickControl] Step 7: Placing specimen at point {specimen_idx} (status=5)...")
                                    place_success = self.vision_handler.place_specimen(point_index=specimen_idx)

                                    if place_success:
                                        # Step 8: 홈 이동 (status=6: 홈 이동)
                                        bb.set("process/binpick/status", 6)
                                        Logger.info("[BinPickControl] Step 8: Moving to home position (status=6)...")
                                        self.go_home_bin_picking()
                                        # place_specimen 내부에서 홈 이동 수행됨

                                        # Step 9: 완료 (status=7: 완료)
                                        bb.set("process/binpick/status", 7)
                                        Logger.info("[BinPickControl] One cycle completed. Restarting for next specimen...")
                                        # 루프 계속 (다음 시편 인식)
                                        specimen_idx += 1
                                        if specimen_idx > 3:
                                            specimen_idx = 1

                                    else:
                                        Logger.error("[BinPickControl] Failed to place specimen.")
                                        bb.set("process/binpick/status", 0)  # 초기화
                                        break
                                else:
                                    Logger.error("[BinPickControl] Failed to pick specimen.")
                                    bb.set("process/binpick/status", 0)  # 초기화
                                    break
                            else:
                                Logger.error(f"[BinPickControl] Unknown SCENE_RESULT status: {status}")
                                bb.set("process/binpick/status", 0)  # 초기화
                                break

                    except Exception as e:
                        Logger.error(f"[BinPickControl] Error during Bin Picking: {e}", exc_info=True)
                        bb.set("process/binpick/status", 0)  # 에러 발생 시 초기화
                elif action == "stop":
                    Logger.info("[BinPickControl] Stopping scene check...")
                    self.vision_handler.stop_scene()

        ''' MQTT Protocol compliant robot control '''
        # TODO 146-172번째 줄 코드 프로그램 정지 상태일때만 가능하도록 코드작성
        if bb.get("ui/cmd/robot_control/trigger"):
            bb.set("ui/cmd/robot_control/trigger", 0) # Consume trigger

            payload = bb.get("ui/cmd/robot_control/data")
            
            # [추가] Gripper Retry 명령 처리 (프로그램 상태와 무관하게 처리)
            if payload and isinstance(payload, dict):
                if payload.get("target") == "gripper" and payload.get("action") == "retry":
                    Logger.info(f"Received robot_control command via MQTT->BB: target=gripper, action=retry")
                    bb.set("int_var/grip_retry/val", 1)
                    return

                # [추가] Log 명령 처리 (Blackboard 전체 데이터 덤프)
                if payload.get("target") == "log" and payload.get("action") == "send":
                    Logger.info(f"[Robot] Log command received. Dumping Blackboard data...")
                    try:
                        bb_keys = load_json("configs/blackboard.json").keys()
                        bb_dump = {key: bb.get(key) for key in bb_keys}
                        Logger.info(f"[Blackboard Dump]\n{json.dumps(bb_dump, indent=2, ensure_ascii=False)}")
                    except Exception as e:
                        Logger.error(f"Failed to dump Blackboard: {e}")
                    return

            # 프로그램이 실행 중이 아닐 때(IDLE 상태)만 수동 제어 명령을 처리합니다.
            if self.program_state == ProgramState.PROG_IDLE:
                if bb.get("device/remote/input/SELECT_SW") != 1:
                    Logger.info("[Robot] Robot control command ignored: System is in MANUAL mode (SELECT_SW != 1).")
                    # payload = bb.get("ui/cmd/robot_control/data")
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

                        # Robot Home Move
                        # enable이 0.5초 이내로 계속 들어오면 홈으로 이동, 끊기거나 disable이 오면 중단
                        elif target == "robot_home":
                            if action == "enable":
                                Logger.info("[Home Move] Enable signal received. Starting home movement.")
                                last_enable_time = time.time()

                                while True:
                                    # 10ms마다 체크
                                    time.sleep(0.01)

                                    # 블랙보드에서 최신 명령 확인
                                    if bb.get("ui/cmd/robot_control/trigger"):
                                        bb.set("ui/cmd/robot_control/trigger", 0)
                                        current_payload = bb.get("ui/cmd/robot_control/data")

                                        if current_payload and isinstance(current_payload, dict):
                                            current_target = current_payload.get("target")
                                            current_action = current_payload.get("action")

                                            # disable 신호 감지 시 즉시 중단
                                            if current_target == "robot_home" and current_action == "disable":
                                            #     Logger.info("[Home Move] Disable signal received. Stopping.")
                                            #     try:
                                            #         self.indy.stop_motion(stop_category=0)
                                            #     except Exception as e:
                                            #         Logger.error(f"[Home Move] Failed to stop: {e}")
                                                break

                                            # enable 신호 계속 들어오는 경우
                                            if current_target == "robot_home" and current_action == "enable":
                                                last_enable_time = time.time()

                                    # 0.5초 동안 enable 신호 없으면 중단
                                    if time.time() - last_enable_time > 0.5:
                                        Logger.info("[Home Move] Timeout (0.5s). Stopping.")
                                        # try:
                                        #     self.indy.stop_motion(stop_category=0)
                                        # except Exception as e:
                                        #     Logger.error(f"[Home Move] Failed to stop: {e}")
                                        break

                                    # 홈 위치에 도달하면 중단
                                    if self.is_home_pos:
                                        Logger.info("[Home Move] Reached home position.")
                                        # bb.set("logic/send_event", {
                                        #     "kind": "event",
                                        #     "evt": "error",
                                        #     "status": "Manual",
                                        #     "category": "robot",
                                        #     "code": "R-004",
                                        #     "message": "이미 홈 위치에 도달했습니다.."
                                        # })
                                        break

                                    # 홈으로 이동 (teaching_mode로 부드럽게)
                                    try:
                                        self.indy.movej(self.home_pos, teaching_mode=True, vel_ratio=30)
                                    except Exception as e:
                                        Logger.error(f"[Home Move] Failed to move: {e}")
                                        break
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

    def _update_tensile_positions(self, value_pos):
        """
        ANA_RESULT의 VALUEPOS 값을 반영하여 인장 시험 위치를 재계산합니다.
        """
        try:
            # 1번 위치 계산
            target_p_1 = list(self.tensile_pos_1_p) # copy
            target_p_1[2] += value_pos
            # res1 = self.indy.inverse_kin(target_p_1, self.tensile_pos_1_q)
            # self.calc_tensile_jpos_1 = res1.get('jpos')
            
            # if not self.calc_tensile_jpos_1:
            #     Logger.warn(f"[Indy] JPOS1 calculation failed. Using default JPOS1. Response: {res1}")
            #     self.calc_tensile_jpos_1 = self.tensile_pos_1_q

            # # 2번 위치 계산
            target_p_2 = list(self.tensile_pos_2_p) # copy
            target_p_2[2] += value_pos
            # res2 = self.indy.inverse_kin(target_p_2, self.tensile_pos_2_q)
            # self.calc_tensile_jpos_2 = res2.get('jpos')
            
            # if not self.calc_tensile_jpos_2:
            #     Logger.warn(f"[Indy] JPOS2 calculation failed. Using default JPOS2. Response: {res2}")
            #     self.calc_tensile_jpos_2 = self.tensile_pos_2_q

            # # 3번 위치 계산
            # target_p_3 = target_p_2.copy() # copy
            # target_p_3[0] -= 28

            # res3 = self.indy.inverse_kin(target_p_3, self.tensile_pos_3_q)
            # self.calc_tensile_jpos_3 = res3.get('jpos')
            
            # if not self.calc_tensile_jpos_3:
            #     Logger.warn(f"[Indy] JPOS3 calculation failed. Using default JPOS3. Response: {res3}")
            #     self.calc_tensile_jpos_3 = self.tensile_pos_3_q

            Logger.info(f"[Indy] Calculated Tensile TPOS with VALUEPOS={value_pos}")
            Logger.info(f"  TPOS1: {target_p_1}")
            Logger.info(f"  TPOS2: {target_p_2}")
            # Logger.info(f"  TPOS3: {target_p_3}")

            # # Blackboard에 저장 (필요 시 사용)
            # bb.set("robot/tensile/jpos_1", self.calc_tensile_jpos_1)
            # bb.set("robot/tensile/jpos_2", self.calc_tensile_jpos_2)
            # bb.set("robot/tensile/jpos_3", self.calc_tensile_jpos_3)

            # 로봇 전역 변수(Global Variable)에 쓰기
            # addr1 = int(self.config.get("tpos_var/tensile_pos1/addr", 34))

            
            addr1 = int(self.config.get("tpos_var/tensile_pos1/addr", 400))
            addr2 = int(self.config.get("tpos_var/tensile_pos2/addr", 401))
            # addr3 = int(self.config.get("tpos_var/tensile_pos3/addr", 402))

            tpos_vars = []
   
            tpos_vars.append({'addr': addr1, 'tpos': target_p_1})

            tpos_vars.append({'addr': addr2, 'tpos': target_p_2})

            # tpos_vars.append({'addr': addr3, 'tpos': target_p_3})
            
            self.indy.set_tpos_variable(tpos_vars)

            Logger.info(f"[Indy] Updated TPos variables at {[v['addr'] for v in tpos_vars]} with positions {target_p_1}, {target_p_2}")

            # jpos_vars = []
            # if self.calc_tensile_jpos_1:
            #     jpos_vars.append({'addr': addr1, 'jpos': self.calc_tensile_jpos_1})
            # if self.calc_tensile_jpos_2:
            #     jpos_vars.append({'addr': addr2, 'jpos': self.calc_tensile_jpos_2})
            # if self.calc_tensile_jpos_3:
            #     jpos_vars.append({'addr': addr3, 'jpos': self.calc_tensile_jpos_3})

            # if jpos_vars:
            #     self.indy.set_jpos_variable(jpos_vars)
            #     Logger.info(f"[Indy] Updated JPos variables at {[v['addr'] for v in jpos_vars]}")

            # float 변수 설정 추가
            # kin_tpos_z_addr = int(self.config.get("float_var/kin_tpos_z/addr", 35))
            # self.indy.set_float_variable([{'addr': kin_tpos_z_addr, 'value': value_pos}])
            # Logger.info(f"[Indy] Updated Float variable at {kin_tpos_z_addr} with value {value_pos}")

        except Exception as e:
            Logger.error(f"[Indy] Error in inverse kinematics calculation: {e}")


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
            #int_var 리딩
            motion_ack = self.get_intvar_address(int_var, int(self.config["int_var/motion_ack/addr"]))
            motion_done = self.get_intvar_address(int_var, int(self.config["int_var/motion_done/addr"]))
            robot_pos = self.get_intvar_address(int_var, int(self.config["int_var/robot/position/addr"]))
            grip_state = self.get_intvar_address(int_var, int(self.config["int_var/grip_state/addr"]))
            grip_retry = self.get_intvar_address(int_var, int(self.config["int_var/grip_retry/addr"]))
            
            #Sehoon
            # bFlag = False
            # if motion_ack != self.o_motion_ack:
            #     self.o_motion_ack = motion_ack
            #     bFlag = True
            # if motion_done != self.o_motion_done:
            #     self.o_motion_done = motion_done
            #     bFlag = True
            # if bFlag:
            #     Logger.info(f"[IndyTiming] CMD={bb.get('int_var/cmd/val')} motion_ack={motion_ack} motion_done={motion_done}")
                

            if motion_ack is not None:
                bb.set("int_var/motion_ack/val", motion_ack)
                # 로봇의 현재 위치를 ack 값 기반으로 저장 (충돌 방지 로직용)
                if motion_ack >= 1500: # 자동화 공정 기준으로 값 결정
                    current_pos_id = motion_ack - 500
                    bb.set("robot/current/position", current_pos_id)
                    # Logger.info(f"[Safety] Robot position updated to: {current_pos_id}")
                #Sehoon ACK timestamp capture
                # if self.cmd_tracking_id is not None and motion_ack == (self.cmd_tracking_id + 500) and self.cmd_ack_ts is None:
                #     self.cmd_ack_ts = time.perf_counter()
                    
            
            if motion_done is not None:
                bb.set("int_var/motion_done/val", motion_done)
                #Sehoon DONE timestamp capture
                # if self.cmd_tracking_id is not None and (motion_done == self.cmd_tracking_id or motion_done == self.cmd_tracking_id + 10000):
                #     self.cmd_done_ts = time.perf_counter()
                #     self.last_done_ts = self.cmd_done_ts

           
            if robot_pos is not None:
                bb.set("int_var/robot/position/val", robot_pos) 

            # [추가] 로봇 컨트롤러의 grip_state 읽기 (백업용)
            
            if grip_state is not None:
                prev_grip_state = bb.get("int_var/grip_state/val") or 0
                bb.set("int_var/grip_state/val", grip_state)

                # 그리퍼 상태 변화 감지 및 에러 처리 (3=완전닫힘/시편없음, 4=파지기준부적합)
                if grip_state in [3, 4] and prev_grip_state != grip_state:
                    error_message = "그리퍼 완전 닫힘 (시편 없음)" if grip_state == 3 else "그리퍼 파지 실패 (파지 기준 부적합)"
                    error_detail = f"Gripper state changed from {prev_grip_state} to {grip_state}"

                    # MQTT 에러 이벤트 전송
                    error_payload = {
                        "kind": "event",
                        "evt": "error",
                        "status": "Auto",
                        "category": "robot",
                        "code": "R-002",
                        "message": error_message,
                        "detail": error_detail
                    }
                    bb.set("logic/send_event", error_payload)
                    Logger.error(f"[Gripper] {error_message}: grip_state={grip_state}")

            # [추가] 로봇 컨트롤러의 grip_retry 읽기
            
            if grip_retry is not None:
                # Conty에서 읽은 이전 값 추적 (내부 상태 추적용)
                prev_grip_retry_conty = bb.get("robot/gripper/retry_prev") or 0

                # 재시도 시작 감지 (0에서 1로 변경)
                if prev_grip_retry_conty == 0 and grip_retry == 1:
                    # 재시도 카운트 증가
                    retry_count = bb.get("robot/gripper/retry_count") or 0
                    bb.set("robot/gripper/retry_count", retry_count + 1)
                    bb.set("robot/gripper/retry_start_time", time.time())
                    Logger.info(f"[Gripper] 재시도 시작 (횟수: {retry_count + 1}/5)")

                # 재시도 후 grip_retry가 1에서 0으로 변경되면 재시도 완료 (Conty 기준)
                if prev_grip_retry_conty == 1 and grip_retry == 0:
                    # grip_state 확인하여 성공/실패 판단
                    current_grip_state = bb.get("int_var/grip_state/val") or 0
                    if current_grip_state in [0, 1, 2]:
                        # 재시도 성공 (정상 상태)
                        Logger.info(f"[Gripper] 재시도 성공: grip_state={current_grip_state}")
                        # 재시도 성공 플래그 설정 및 카운트 초기화
                        bb.set("robot/gripper/retry_success", True)
                        bb.set("robot/gripper/retry_count", 0)
                        bb.set("robot/gripper/retry_start_time", None)
                    else:
                        # 재시도 실패 (여전히 에러 상태)
                        retry_count = bb.get("robot/gripper/retry_count") or 0
                        Logger.error(f"[Gripper] 재시도 실패: grip_state={current_grip_state} (시도 {retry_count}/5)")

                        # 최대 재시도 횟수 초과 확인 (5회)
                        if retry_count >= 5:
                            Logger.error(f"[Gripper] 최대 재시도 횟수 초과 (5회)")

                            # MQTT 에러 이벤트 전송 (팝업 띄우기)
                            error_payload = {
                                "kind": "event",
                                "evt": "error",
                                "status": "Auto",
                                "category": "robot",
                                "code": "R-003",
                                "message": "그리퍼 재시도 실패 (5회 시도)",
                                "detail": f"Retry failed after 5 attempts with grip_state={current_grip_state}"
                            }
                            bb.set("logic/send_event", error_payload)

                            # 재시도 카운트 초기화 및 강제 중단
                            bb.set("robot/gripper/retry_count", 0)
                            bb.set("robot/gripper/retry_start_time", None)
                            bb.set("int_var/grip_retry/val", 0)  # 강제로 재시도 중단
                            Logger.info(f"[Gripper] 재시도 강제 중단 (grip_retry=0 설정)")

                # 재시도 타임아웃 확인 (60초)
                retry_start_time = bb.get("robot/gripper/retry_start_time")
                if grip_retry == 1 and retry_start_time and (time.time() - retry_start_time > 60.0):
                    Logger.error(f"[Gripper] 재시도 타임아웃 (60초)")
                    retry_count = bb.get("robot/gripper/retry_count") or 0

                    # 5회 이상 시도했으면 완전히 중단
                    if retry_count >= 5:
                        Logger.error(f"[Gripper] 타임아웃 후 최대 횟수 초과 - 재시도 중단")
                        error_payload = {
                            "kind": "event",
                            "evt": "error",
                            "status": "Auto",
                            "category": "robot",
                            "code": "R-003",
                            "message": "그리퍼 재시도 타임아웃 (5회 시도)",
                            "detail": f"Retry timeout after 5 attempts"
                        }
                        bb.set("logic/send_event", error_payload)
                        bb.set("robot/gripper/retry_count", 0)

                    # 강제로 재시도 중단
                    bb.set("int_var/grip_retry/val", 0)
                    bb.set("robot/gripper/retry_start_time", None)

                # Conty에서 읽은 현재 값을 이전 값으로 저장 (다음 사이클 비교용)
                bb.set("robot/gripper/retry_prev", grip_retry)

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
            #Sehoon send timestamp capture
            # if cmd_to_write != 0:
            #     if self.cmd_tracking_id != cmd_to_write:
            #         self.cmd_tracking_id = cmd_to_write
            #         self.cmd_send_ts = time.perf_counter()
            #         self.cmd_ack_ts = None
            #         self.cmd_done_ts = None
            #         gap_ms = None
            #         if self.last_done_ts is not None:
            #             gap_ms = (self.cmd_send_ts - self.last_done_ts) * 1000
            #         gap_str = f"{gap_ms:.2f} ms" if gap_ms is not None else "n/a"
            #         Logger.info(f"[IndyTiming] CMD {cmd_to_write} sent (tracking started, done->send {gap_str})")
 
            vars_to_set.append({'addr': int(self.config["int_var/cmd/addr"]), 'value': cmd_to_write})

            # Handle other variables to write
            # None일 경우를 대비하여 기본값 0으로 처리
            grip_state_val = int(bb.get("int_var/grip_state/val") or 0)
            vars_to_set.append({'addr': int(self.config["int_var/grip_state/addr"]), 'value': grip_state_val})

            # grip_retry 변수 쓰기
            grip_retry_val = int(bb.get("int_var/grip_retry/val") or 0)
            vars_to_set.append({'addr': int(self.config["int_var/grip_retry/addr"]), 'value': grip_retry_val})

            # Part 3: Write the collected integer variables to the robot.
            if vars_to_set:
                self.indy.set_int_variable(vars_to_set)
             #Sehoon DONE latency logging
            # if self.cmd_tracking_id is not None and self.cmd_done_ts is not None:
            #     send_ack = (self.cmd_ack_ts - self.cmd_send_ts) * 1000 if self.cmd_ack_ts and self.cmd_send_ts else None
            #     send_done = (self.cmd_done_ts - self.cmd_send_ts) * 1000 if self.cmd_send_ts else None
            #     ack_done = (self.cmd_done_ts - self.cmd_ack_ts) * 1000 if self.cmd_ack_ts else None
            #     send_ack_str = f"{send_ack:.2f}" if send_ack is not None else "n/a"
            #     send_done_str = f"{send_done:.2f}" if send_done is not None else "n/a"
            #     ack_done_str = f"{ack_done:.2f}" if ack_done is not None else "n/a"
                
            #     # [추가] ACK와 DONE이 동시에 수신되었는지 표시 (1ms 미만 차이)
            #     note = ""
            #     if ack_done is not None and ack_done < 1.0:
            #         note = " (Simultaneous Recv)"
            #         Logger.info(f"note !! \n")

            #     Logger.info(
            #         f"[IndyTiming] CMD {self.cmd_tracking_id} timings: send->ACK {send_ack_str} ms, send->DONE {send_done_str} ms, ACK->DONE {ack_done_str} ms{note}"
            #     )
            #     self.cmd_send_ts = None
            #     self.cmd_ack_ts = None
            #     self.cmd_done_ts = None
            #     self.cmd_tracking_id = None
            # Part 4: Handle boolean variables (like CMD_Init) separately.
            # 로봇이 CMD를 인식하려면 init이 True여야 하므로, CMD가 살아있는 동안에는 True를 유지합니다.            
            if bb.get("indy_command/reset_init_var"):
                bb.set("indy_command/reset_init_var", False)
                self.indy.set_bool_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': True}])
                Logger.info("Sent CMD_Init (True) to robot controller to reset ACK/DONE.")
            else:
                # CMD가 0이 아닐 때는 init을 True로 유지해 컨트롤러가 CMD를 계속 인식하도록 한다.
                keep_init_on = cmd_to_write != 0
                self.indy.set_bool_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': keep_init_on}])
                # CMD_Init을 False로 유지하여 ACK/DONE 변수가 깜빡이는 현상을 방지합니다.
                # reset_init_var가 True일 때만 한 사이클 동안 True가 됩니다.
                # self.indy.set_bool_variable([{'addr': int(self.config["int_var/init/addr"]), 'value': False}])
        except Exception as e:
            Logger.error(f"Error in handle_int_variable cycle: {e}")

    def indy_communication(self):
        ''' Get Indy status '''
        try:
            control_data = self.indy.get_control_data()
            program_data = self.indy.get_program_data()
            self.robot_current_pos = control_data['p'][0:3]
            self.control_data_p = control_data['p'] # [Data Recorder] 전체 P 데이터(x,y,z,u,v,w) 저장

            # [Zone Predictor] 현재 위치 기반 Zone 예측
            if self.zone_predictor is not None:
                try:
                    result = self.zone_predictor.predict_with_recovery_action(self.control_data_p)
                    current_zone = result.get("predicted_zone") if result.get("success") else 0

                    prev_zone = bb.get("robot/predicted_zone")

                    # Zone 변경 필터링: 게이지(2), 정렬기(3)에서 홈(6)으로 갑자기 바뀌는 것 방지
                    # 그리퍼 동작 시 잘못된 Zone 예측 방지
                    if prev_zone in [2, 3] and current_zone == 6:
                        # 이전 Zone 유지 (게이지/정렬기/-> 홈 직접 전환 무시)
                        current_zone = prev_zone

                    if prev_zone != current_zone:
                        # Logger.info(f"[Zone Predictor] Zone changed: {prev_zone} -> {current_zone}")
                        pass

                    bb.set("robot/predicted_zone", current_zone)
                except Exception as e:
                    Logger.error(f"[Zone Predictor] Prediction failed: {e}")

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
            # Logger.info(f"Robot Position : {self.control_data_p}")
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
            bb.set("system/emo/on", 1)
        else:
            # 비상정지 해제 시 초기화
            bb.set("system/emo/on", 0)

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

        # [추가] SELECT_SW가 0(Manual)이면 즉시 정지
        is_manual_mode = bb.get("device/remote/input/SELECT_SW") == 0

        # 1. 도어 열림 감지 시 또는 수동 모드 전환 시 즉시 정지
        # if is_door_open or is_manual_mode:
        #     if self.indy.get_motion_data().get("speed_ratio") != 0:
        #         self.indy.set_speed_ratio(0)
        #         reason = "door open" if is_door_open else "manual mode switch"
        #         Logger.info(f"[Robot] Paused by {reason}. Set Speed Ratio to 0.")
        
        # # 2. 도어가 닫혀 있을 경우, UI 명령 처리
        # else:
        #     # 2.1. UI에서 '일시정지' 명령을 받은 경우
        #     if program_control_cmd == ProgramControl.PROG_PAUSE:
        #         bb.set("ui/reset/program_control", True) # 명령 소비
        #         if self.indy.get_motion_data().get("speed_ratio") != 0:
        #             self.indy.set_speed_ratio(0)
        #             Logger.info(f"[Robot] Paused by UI command. Set Speed Ratio to 0.")
            
        #     # 2.2. UI에서 '재시작' 또는 '시작' 명령을 받은 경우
        #     elif program_control_cmd in (ProgramControl.PROG_RESUME, ProgramControl.PROG_START):
        #         bb.set("ui/reset/program_control", True) # 명령 소비
        #         if bb.get("process/program/is_resume") and self.indy.get_motion_data().get("speed_ratio") != 100:
        #             self.indy.set_speed_ratio(100) # (70)
        #             bb.set("process/program/is_resume", False)
        #             Logger.info(f"[Robot] Resumed by UI command. Set Speed Ratio to 100.")
        #             Logger.info(f"[Robot] is_resume flag detected. Set Speed Ratio to 100. and reset the flag.")
        
        # 3. 현재 로봇 속도를 블랙보드에 기록합니다.
        if self.program_state == ProgramState.PROG_RUNNING:
            # 1. 도어 열림 또는 수동 모드(SELECT_SW != 1) 전환 시 즉시 정지 (속도 0)
            if is_door_open or is_manual_mode:
                #TODO warming state == 1일 경우에는 수동모드일지라도 속도가 100이 되도록 해줘. 
                if bb.get("ui/state/warming_state") == 1 :
                    if self.indy.get_motion_data().get("speed_ratio") == 0:
                        self.indy.set_speed_ratio(100)
                        Logger.info(f"[Robot] Resumed by warming state (Manual Mode ignored). Set Speed Ratio to 100.")
                elif self.indy.get_motion_data().get("speed_ratio") != 0:
                    self.indy.set_speed_ratio(0)
                    reason = "door open" if is_door_open else "manual mode switch"
                    Logger.info(f"[Robot] Paused by {reason}. Set Speed Ratio to 0.")
            # 2. 자동 모드(SELECT_SW == 1) 복귀 시 속도 100으로 재개
            else: # not is_door_open and not is_manual_mode
                if self.indy.get_motion_data().get("speed_ratio") == 0:
                    self.indy.set_speed_ratio(100)
                    Logger.info(f"[Robot] Resumed by auto mode switch. Set Speed Ratio to 100.")

        robot_speed = self.indy.get_motion_data()['speed_ratio']
        bb.set("robot/speed", robot_speed)

        match = re.search(r'/index/(\d+)', self.program_name)
        if match:
            program_index = match.group(1)
            if program_index == str(self.config.get("conty_main_program_index", "1")):
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

            elif program_index == str(self.config.get("conty_warming_program_index", "3")):
                ''' 예열 On, Off 버튼 '''
                if self.program_state == ProgramState.PROG_IDLE:
                    bb.set("ui/state/warming_state", 0)
                elif self.program_state == ProgramState.PROG_RUNNING:
                    bb.set("ui/state/warming_state", 1)
                elif self.program_state == ProgramState.PROG_STOPPING:
                    bb.set("ui/state/warming_state", 2)
