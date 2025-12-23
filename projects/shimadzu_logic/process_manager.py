# process_manager.py
import threading
import time
from .constants import *
from . import indy_control
from pkg.utils.file_io import load_json, save_json
from pkg.utils.blackboard import GlobalBlackboard
from pkg.configs.global_config import GlobalConfig

from pkg.utils.logging import Logger

# Device FSM 및 Context 임포트
from .devices_fsm import DeviceFsm
from .devices_context import DeviceContext

# Robot FSM 및 Context 임포트
from .robot_fsm_v1 import RobotFSM
from .robot_context import RobotContext

# Logic FSM 및 Context 임포트
from .logic_fsm import LogicFSM
from .logic_context import LogicContext


bb = GlobalBlackboard()
global_config = GlobalConfig()

class ProcessManager:
    def __init__(self):
        self.running = False
        self.thread = None
        self.robot_error = None
        self.prog_stopped = None

        config_path = 'projects/shimadzu_logic/configs/configs.json'
        config : dict = load_json(config_path)
        
        test_mode = config.get("test_mode")
        Logger.info(f"configs robot : {config.get('robot_ip')}")
        Logger.info(f"configs remot io : {config.get('remote_io')}")
        Logger.info(f"configs mqtt : {config.get('mqtt_ip')}")
        Logger.info(f"configs shimadzu : {config.get('shimadzu_ip')} : {config.get('shimadzu_port')}")
        if test_mode :
            Logger.info(f"실행 모드 : TEST 모드")
        else :
            Logger.info(f"실행 모드 : Run 모드")
        
        # FSM 인스턴스 생성
        # Device FSM
        Logger.info("Initializing Device FSM...")
        self.device_fsm = DeviceFsm(DeviceContext())
        self.device_fsm.start_service_background()
        Logger.info("Device FSM initialized.")

        # # Robot FSM
        # Logger.info("Initializing Robot FSM...")
        # self.robot_fsm = RobotFSM(RobotContext())
        # self.robot_fsm.start_service_background()
        # Logger.info("Robot FSM initialized.")

        # # Logic FSM
        # Logger.info("Initializing Logic FSM...")
        # self.logic_fsm = LogicFSM(LogicContext())
        # self.logic_fsm.start_service_background()
        # Logger.info("Logic FSM initialized.")


        time.sleep(5)



    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, 'logic_fsm'):
            self.logic_fsm.stop()
            
        Logger.info("[ProcessManager] All FSMs stopped.")

    def check_device_state(self) :
        if bb.get("ui/state/robot_state") in [2,8]:
            bb.set("ui/state/error",1)
        if bb.get("ui/state/input_unit/state") > 1000 :
            bb.set("ui/state/error",1)
        if bb.get("ui/state/pot1/state") > 1000 :
            bb.set("ui/state/error",1)
        if bb.get("ui/state/pot2/state") > 1000 :
            bb.set("ui/state/error",1)

    def run(self):
        while self.running:
            time.sleep(0.01)
            # Logger.info(f"[ProcessManager] Running main loop...")
