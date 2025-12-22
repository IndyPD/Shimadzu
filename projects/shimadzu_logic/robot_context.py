from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay

from pkg.configs.global_config import GlobalConfig

from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

class RobotStatus:
    # FSM 상태 확인을 위한 플래그
    def __init__(self):
        self.is_connected = Flagger()    # 로봇 컨트롤러 연결 상태
        self.is_ready = Flagger()        # 로봇 준비 상태 (원점 복귀, 초기화 완료)
        self.is_emg_pushed = Flagger()   # 비상 정지 버튼
        self.is_error_state = Flagger()  # 하드웨어/외부 오류 상태
        self.is_moving = Flagger()       # 로봇 동작 중 여부

        self.reset()

    def reset(self):
        self.is_connected.down()
        self.is_ready.up()
        self.is_emg_pushed.down()
        self.is_error_state.down()
        self.is_moving.down()


class RobotContext(ContextBase):
    violation_code = ViolationType
    status = RobotStatus()
    process_manager = None

    def __init__(self):
        ContextBase.__init__(self)
        self.status = RobotStatus()
        
        self.is_connected = Flagger()
        self.is_ready = Flagger()
        self.is_emg_pushed = Flagger()
        self.is_error_state = Flagger()
        self.is_moving = Flagger()

        self.violation_code = 0x00

    def check_program_running(self) :
        indy_status = bb.get("indy")
        prog_state = indy_status["program_state"]
        robot_state = indy_status["robot_state"]
        
        if prog_state == ProgramState.PROG_RUNNING :
            return True
        else :
            Logger.info(f"{get_time()}: Program is NOT running {ProgramState(prog_state).name}.")
            return False

    def check_violation(self) -> int:
        self.violation_code = 0x00
        try:
            # 1. 비상 정지 및 일반 HW 오류
            if self.status.is_emg_pushed():
                self.violation_code |= RobotViolation.ISO_EMERGENCY_BUTTON.value

            if self.status.is_error_state():
                self.violation_code |= RobotViolation.HW_VIOLATION.value
            
            # 2. 로봇 연결 및 준비 상태
            if not self.status.is_connected():
                self.violation_code |= RobotViolation.CONNECTION_TIMEOUT.value
                
            if self.status.is_connected() and not self.status.is_ready():
                 self.violation_code |= RobotViolation.HW_NOT_READY.value
            
            # 3. Indy Robot State Check
            indy_data = bb.get("indy")
            if indy_data:
                indy_state_val = indy_data.get("robot_state", 0)
                try:
                    current_indy_state = Robot_OP_State(indy_state_val)
                except ValueError:
                    current_indy_state = Robot_OP_State.OP_SYSTEM_OFF

                # 정상 상태들: OP_SYSTEM_ON과 OP_SYSTEM_RESET을 모두 포함
                if current_indy_state in (Robot_OP_State.OP_IDLE, Robot_OP_State.OP_MOVING,
                                          Robot_OP_State.OP_TEACHING, Robot_OP_State.OP_COMPLIANCE,
                                          Robot_OP_State.TELE_OP, Robot_OP_State.OP_SYSTEM_ON, 
                                          Robot_OP_State.OP_SYSTEM_RESET):
                    pass
                else:
                    # NOT_READY 상태들
                    if current_indy_state in (Robot_OP_State.OP_SYSTEM_OFF, Robot_OP_State.OP_STOP_AND_OFF):
                        self.violation_code |= RobotViolation.HW_NOT_READY.value

                    # VIOLATION 상태들
                    if current_indy_state in (Robot_OP_State.OP_VIOLATE, Robot_OP_State.OP_VIOLATE_HARD,
                                              Robot_OP_State.OP_SYSTEM_SWITCH):
                        self.violation_code |= RobotViolation.HW_VIOLATION.value

                    # COLLISION 상태
                    if current_indy_state == Robot_OP_State.OP_COLLISION:
                        self.violation_code |= RobotViolation.COLLISION_VIOLATION.value

                    # BRAKE_CONTROL 상태
                    if current_indy_state == Robot_OP_State.OP_BRAKE_CONTROL:
                        self.violation_code |= RobotViolation.HW_VIOLATION.value

                    # RECOVERING 상태들
                    if current_indy_state in (Robot_OP_State.OP_RECOVER_HARD, Robot_OP_State.OP_RECOVER_SOFT,
                                              Robot_OP_State.OP_MANUAL_RECOVER):
                        self.violation_code |= RobotViolation.HW_VIOLATION.value

                    if self.violation_code != 0:
                        Logger.error(f"{get_time()}: [Robot FSM] Violation detected "
                                     f"[indy_state={current_indy_state.name}, "
                                     f"violation_code={self.violation_code}]")

            return self.violation_code
        except Exception as e:
            reraise(e)

    def robot_state(self):
        return bb.get("indy")["robot_state"]

    def program_state(self):
        return bb.get("indy")["program_state"]

    def is_sim_mode(self):
        return bb.get("indy")["is_sim_mode"]

    def is_home_pos(self):
        return bb.get("indy")["is_home_pos"]

    def is_packaging_pos(self):
        return bb.get("indy")["is_packaging_pos"]

    def is_detect_pos(self):
        return bb.get("indy")["is_detect_pos"]

    def direct_teaching(self, onoff):
        if onoff:
            bb.set("indy_command/direct_teaching_on", True)
        else:
            bb.set("indy_command/direct_teaching_off", True)

    def gripper_control(self, open):
        if open:
            bb.set("indy_command/gripper_open", True)
        else:
            bb.set("indy_command/gripper_close", True)

    def stop_motion(self):
        bb.set("indy_command/stop_motion", True)

    def go_home_pos(self):
        bb.set("indy_command/go_home", True)

    def go_packaging_pos(self):
        bb.set("indy_command/go_packaging", True)

    def play_program(self):
        bb.set("indy_command/play_program", True)

        start = time.time()
        while time.time() - start < 10.0:
            time.sleep(0.1)
            Logger.info(f"{get_time()}: Wait for main program running")
            if self.check_program_running():
                break

    # def play_warming_program(self):
    #     bb.set("indy_command/play_warming_program", True)

    #     start = time.time()
    #     while time.time() - start < 10.0:
    #         time.sleep(0.1)
    #         Logger.info(f"{get_time()}: Wait for warming  program running")
    #         if self.check_program_running():
    #             break

    def stop_program(self):
        Logger.info("[DEBUG] stop_program: Sending stop command to Conty.")
        bb.set("indy_command/stop_program", True)

        # Conty 프로그램이 PROG_IDLE 상태가 될 때까지 최대 5초간 대기
        start_time = time.time()
        wait_timeout = 10.0
        while time.time() - start_time < wait_timeout:
            current_state = self.program_state()
            if current_state == ProgramState.PROG_IDLE:
                Logger.info(f"[DEBUG] stop_program: Conty program confirmed to be in IDLE state.")
                break
            Logger.info(f"[DEBUG] stop_program: Waiting for Conty program to stop. Current state: {ProgramState(current_state).name}")
            time.sleep(0.2)
        else:
            Logger.warn(f"[DEBUG] stop_program: Timeout waiting for Conty program to stop. Proceeding with reset anyway.")

    def recover_robot(self):
        bb.set("indy_command/recover", True)

    ''' 
    Recipe FSM related 
    '''
    def motion_done_logic(self, motion):
        ''' Motion done logic
        1. Conty CMD reset: to prevent Conty tree loop execute same motion twice
        2. Trigger Recipe FSM event, and wait Recipe FSM transition done
        3. Motion reset to trigger priority start next task computation
        '''
        ''' Conty CMD reset '''
        bb.set("int_var/cmd/val", 0)

        '''  Recipe FSM 모션 완료 트리거 → Recipe FSM 상태 천이 대기 (basket_idx = Recipe FSM index) '''
        prev_state = bb.get(f"recipe/basket{self.basket_index}/state")
        bb.set(f"recipe/command/{motion}_done", self.basket_index)
        self.wait_for_recipe_fsm_trainsition_done(prev_state)

        ''' Motion Reset: Priority schedule → Robot '''
        self.motion_command_reset()
    def robot_motion_control(self,cmd : int) :
        bb.set("int_var/cmd/val")
        
