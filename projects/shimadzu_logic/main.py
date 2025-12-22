import sys
import signal
import time
import threading
import traceback

from pkg.configs.global_config import GlobalConfig
from pkg.utils.blackboard import GlobalBlackboard

from pkg.utils.logging import Logger, LogLevel
from projects.shimadzu_logic import mqtt_comm
from projects.shimadzu_logic.process_manager import ProcessManager
from projects.shimadzu_logic import indy_control

from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

project_name = "shimadzu_logic"
bb = GlobalBlackboard()
global_config = GlobalConfig()
global_config.initialize(project_name)
terminate_flag = threading.Event()
app_server = None
process = None
robot = None
mqtt_communicator = None

def stop():
    """외부에서 시스템을 안전하게 종료하기 위한 함수"""
    terminate_flag.set()

def sig_handler(signum, frame):
    Logger.warn(f"[SIGNAL] Received signal {signum}. Gracefully shutting down...")
    stop()

def main(blocking=False):
    ''' Signal handler '''
    global robot, process, app_server, mqtt_communicator
    should_cleanup = blocking

    # Ensure the termination flag is reset at start
    terminate_flag.clear()

    # signal.signal은 main 스레드에서만 동작하므로,
    # run.py와 같이 main 함수를 직접 실행하는 경우에만 유효합니다.
    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except ValueError:
        Logger.info("[SYSTEM] Signal handlers skipped (Notebook environment).")

    Logger.info(f"[SYSTEM] Starting {project_name} System...")

    process = None
    robot = None
    mqtt_communicator = None
    try:        
        
        # TODO DB관련 내용 추가    

        # Indy 로봇 통신 시작
        # robot = indy_control.RobotCommunication()
        # robot.start()
        # time.sleep(0.1)

        #MQTT 통신 시작
        mqtt_communicator = mqtt_comm.MqttComm(role='logic', is_dummy=False, 
                                               rule_path="projects/shimadzu_logic/configs/mqtt_rule.json",
                                               stop_event=terminate_flag)
        mqtt_communicator.run()
        time.sleep(0.1)
        
        # ProcessManager를 생성하고 시작합니다.
        # 이 start() 함수 내부에서 FSM 스레드를 실행하게 됩니다.
        process = ProcessManager()
        process.start()
        

        Logger.info(f"[SYSTEM] {project_name} system initialized. Running...")

        # if not blocking:
        #     return

        # 메인 스레드 대기 루프: terminate_flag가 set될 때까지 대기합니다.
        # while not terminate_flag.is_set():
        #     time.sleep(0.5)

    except Exception as e:
        Logger.error(f"[SYSTEM ERROR] Unexpected exception: {e}")
        Logger.error(traceback.format_exc())
        should_cleanup = True

    finally:
        if should_cleanup:
            if mqtt_communicator:
                mqtt_communicator.stop()
            if process:
                process.stop()
            Logger.info("[SYSTEM] System Shutdown Complete.")

if __name__ == '__main__':
    main()
