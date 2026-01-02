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
        self.current_motion_command = None

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
                self.violation_code |= RobotViolation.ISO_EMERGENCY_BUTTON

            if self.status.is_error_state():
                self.violation_code |= RobotViolation.HW_VIOLATION
            
            # 2. 로봇 연결 및 준비 상태
            if not self.status.is_connected():
                self.violation_code |= RobotViolation.CONNECTION_TIMEOUT
                
            if self.status.is_connected() and not self.status.is_ready():
                 self.violation_code |= RobotViolation.HW_NOT_READY
            
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
                        self.violation_code |= RobotViolation.HW_NOT_READY

                    # VIOLATION 상태들
                    if current_indy_state in (Robot_OP_State.OP_VIOLATE, Robot_OP_State.OP_VIOLATE_HARD,
                                              Robot_OP_State.OP_SYSTEM_SWITCH):
                        self.violation_code |= RobotViolation.HW_VIOLATION

                    # COLLISION 상태
                    if current_indy_state == Robot_OP_State.OP_COLLISION:
                        self.violation_code |= RobotViolation.COLLISION_VIOLATION

                    # BRAKE_CONTROL 상태
                    if current_indy_state == Robot_OP_State.OP_BRAKE_CONTROL:
                        self.violation_code |= RobotViolation.HW_VIOLATION

                    # RECOVERING 상태들
                    if current_indy_state in (Robot_OP_State.OP_RECOVER_HARD, Robot_OP_State.OP_RECOVER_SOFT,
                                              Robot_OP_State.OP_MANUAL_RECOVER):
                        self.violation_code |= RobotViolation.HW_VIOLATION

                    if self.violation_code != 0:
                        Logger.info(f"{get_time()}: [Robot FSM] Violation detected "
                                     f"[indy_state={current_indy_state.name}, "
                                     f"violation_code={self.violation_code}]")

            return self.violation_code
        except Exception as e:
            Logger.error(f"[RobotContext] Exception in check_violation: {e}")
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
                bb.set("indy_command/reset_init_var", True)
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


    def robot_motion_control(self,cmd : int) :
        bb.set("int_var/cmd/val", cmd)

    def get_motion_cmd(self, motion_name: MotionCommand, floor: int = 0, num: int = 0, pos: int = 0) -> int:
        """
        Logic FSM에서 사용하는 MotionCommand Enum을 Command.md에 정의된 정수 CMD ID로 변환합니다.
        """
        # 1. 정적 명령 매핑 (주로 상태 변경 또는 파라미터 없는 이동)
        static_mapping = {
            # ACT00
            MotionCommand.HOME_RACK_FRONT: RobotMotionCommand.HOME_RACK_FRONT,
            MotionCommand.HOME_TOOL_FRONT: RobotMotionCommand.HOME_TOOL_FRONT,
            MotionCommand.HOME_THICK_GAUGE_FRONT: RobotMotionCommand.HOME_THICK_GAUGE_FRONT,
            MotionCommand.HOME_ALIGNER_FRONT: RobotMotionCommand.HOME_ALIGNER_FRONT,
            MotionCommand.HOME_TENSILE_TESTER_FRONT: RobotMotionCommand.HOME_TENSILE_TESTER_FRONT,
            MotionCommand.HOME_SCRAP_DISPOSER_FRONT: RobotMotionCommand.HOME_SCRAP_DISPOSER_FRONT,
            MotionCommand.RACK_FRONT_HOME: RobotMotionCommand.RACK_FRONT_HOME,
            MotionCommand.TOOL_FRONT_HOME: RobotMotionCommand.TOOL_FRONT_HOME,
            MotionCommand.THICK_GAUGE_FRONT_HOME: RobotMotionCommand.THICK_GAUGE_FRONT_HOME,
            MotionCommand.ALIGNER_FRONT_HOME: RobotMotionCommand.ALIGNER_FRONT_HOME,
            MotionCommand.TENSILE_TESTER_FRONT_HOME: RobotMotionCommand.TENSILE_TESTER_FRONT_HOME,
            MotionCommand.SCRAP_DISPOSER_FRONT_HOME: RobotMotionCommand.SCRAP_DISPOSER_FRONT_HOME,

            MotionCommand.MOVE_TO_INDICATOR: RobotMotionCommand.THICK_GAUGE_FRONT_MOVE,
            MotionCommand.MOVE_TO_ALIGN: RobotMotionCommand.ALIGNER_FRONT_MOVE,
            MotionCommand.ALIGNER_FRONT_WAIT: RobotMotionCommand.ALIGNER_FRONT_WAIT,
            MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_LOAD: RobotMotionCommand.TENSILE_FRONT_MOVE,
            MotionCommand.MOVE_TO_TENSILE_MACHINE_FOR_PICK: RobotMotionCommand.TENSILE_FRONT_MOVE,
            MotionCommand.MOVE_TO_SCRAP_DISPOSER: RobotMotionCommand.SCRAP_FRONT_MOVE,
            MotionCommand.MOVE_TO_HOME: RobotMotionCommand.RECOVERY_HOME,

            MotionCommand.RETREAT_FROM_ALIGN_AFTER_PLACE: RobotMotionCommand.ALIGNER_FRONT_RETURN,
            MotionCommand.RETREAT_FROM_ALIGN_AFTER_PICK: RobotMotionCommand.ALIGNER_FRONT_RETURN,
            MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_LOAD: RobotMotionCommand.TENSILE_FRONT_RETURN,
            MotionCommand.RETREAT_FROM_TENSILE_MACHINE_AFTER_PICK: RobotMotionCommand.TENSILE_FRONT_RETURN,
            MotionCommand.RETREAT_FROM_SCRAP_DISPOSER: RobotMotionCommand.SCRAP_FRONT_RETURN,

            MotionCommand.GRIPPER_OPEN_AT_INDICATOR: RobotMotionCommand.GRIPPER_OPEN,
            MotionCommand.GRIPPER_OPEN_AT_ALIGN: RobotMotionCommand.GRIPPER_OPEN,
            MotionCommand.GRIPPER_OPEN_AT_TENSILE_MACHINE: RobotMotionCommand.GRIPPER_OPEN,
            MotionCommand.GRIPPER_OPEN_AT_SCRAP_DISPOSER: RobotMotionCommand.GRIPPER_OPEN,

            MotionCommand.GRIPPER_CLOSE_FOR_RACK: RobotMotionCommand.GRIPPER_CLOSE,
            MotionCommand.GRIPPER_CLOSE_FOR_INDICATOR: RobotMotionCommand.GRIPPER_CLOSE,
            MotionCommand.GRIPPER_CLOSE_FOR_ALIGN: RobotMotionCommand.GRIPPER_CLOSE,
            MotionCommand.GRIPPER_CLOSE_FOR_TENSILE_MACHINE: RobotMotionCommand.GRIPPER_CLOSE,
        }
        if motion_name in static_mapping:
            return static_mapping[motion_name]

        # 2. 동적 명령 매핑 (파라미터 필요)
        # ACT01: Rack
        if motion_name == MotionCommand.MOVE_TO_RACK:
            return RobotMotionCommand.RACK_FRONT_MOVE
        elif motion_name == MotionCommand.MOVE_TO_QR_SCAN_POS:
            return get_rack_nF_QR_scan_pos_cmd(floor)
        elif motion_name == MotionCommand.MOVE_TO_TRAY :
            return get_rack_nF_sample_N_pos_cmd(floor, 0)
        elif motion_name == MotionCommand.PICK_SPECIMEN_FROM_RACK:
            return get_rack_nF_sample_N_pos_cmd(floor, num)
        elif motion_name == MotionCommand.RETREAT_FROM_RACK:
            return get_rack_nF_front_return_cmd(floor)

        # ACT02: Indicator
        elif motion_name == MotionCommand.PLACE_SPECIMEN_AND_MEASURE:
            if pos == 1: return RobotMotionCommand.THICK_GAUGE_SAMPLE_1_PLACE
            if pos == 2: return RobotMotionCommand.THICK_GAUGE_SAMPLE_2_PLACE
            if pos == 3: return RobotMotionCommand.THICK_GAUGE_SAMPLE_3_PLACE
        elif motion_name == MotionCommand.PICK_SPECIMEN_FROM_INDICATOR:
            if pos == 1: return RobotMotionCommand.THICK_GAUGE_SAMPLE_1_PICK
            if pos == 2: return RobotMotionCommand.THICK_GAUGE_SAMPLE_2_PICK
            if pos == 3: return RobotMotionCommand.THICK_GAUGE_SAMPLE_3_PICK
        elif motion_name == MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PLACE or motion_name == MotionCommand.RETREAT_FROM_INDICATOR_AFTER_PICK:
            if pos == 1: return RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_1
            if pos == 2: return RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_2
            if pos == 3: return RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_3

        # ACT03: Aligner
        elif motion_name == MotionCommand.PLACE_SPECIMEN_ON_ALIGN:
            return RobotMotionCommand.ALIGNER_SAMPLE_PLACE
        elif motion_name == MotionCommand.PICK_SPECIMEN_FROM_ALIGN:
            return RobotMotionCommand.ALIGNER_SAMPLE_PICK

        # ACT04 & ACT05: Tensile Machine
        elif motion_name == MotionCommand.LOAD_TENSILE_MACHINE:
            return RobotMotionCommand.TENSILE_SAMPLE_PLACE_POS_DOWN
        elif motion_name == MotionCommand.PICK_FROM_TENSILE_MACHINE:
            if pos == 1: return RobotMotionCommand.TENSILE_SAMPLE_PICK_POS_UP
            if pos == 2: return RobotMotionCommand.TENSILE_SAMPLE_PICK_POS_DOWN

        # ACT06: Scrap Disposer
        elif motion_name == MotionCommand.PLACE_IN_SCRAP_DISPOSER:
            return RobotMotionCommand.SCRAP_DROP_POS

        Logger.error(f"[RobotContext] get_motion_cmd: 알 수 없거나 매핑되지 않은 모션 이름 '{motion_name}'")
        return None

    def is_safe_to_move(self, next_cmd_id: int) -> bool:
        """
        로봇 충돌 방지를 위해 현재 위치에서 다음 동작으로의 이동이 안전한지 확인합니다.
        규칙:
        1. 주요 거점(Waypoint) 간 이동은 항상 허용됩니다.
        2. 특정 시퀀스(랙, 측정기 등) 내에서는 정해진 순서로만 이동할 수 있습니다.
        3. 홈(100)으로의 복귀는 언제나 허용됩니다.
        """
        current_pos_id = int(bb.get("robot/current/position") or 100) # 기본 위치는 HOME

        # 규칙 0: 홈 복귀는 항상 허용
        if next_cmd_id == RobotMotionCommand.RECOVERY_HOME:
            return True

        # 주요 거점(Waypoint) 정의
        WAYPOINTS = {
            RobotMotionCommand.RECOVERY_HOME,
            RobotMotionCommand.RACK_FRONT_MOVE,
            RobotMotionCommand.THICK_GAUGE_FRONT_MOVE,
            RobotMotionCommand.ALIGNER_FRONT_MOVE,
            RobotMotionCommand.TENSILE_FRONT_MOVE,
            RobotMotionCommand.SCRAP_FRONT_MOVE,
            # 복귀 동작들도 거점에 도착한 것으로 간주
            RobotMotionCommand.RACK_FRONT_RETURN,
            RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_1,
            RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_2,
            RobotMotionCommand.THICK_GAUGE_FRONT_RETURN_3,
            RobotMotionCommand.ALIGNER_FRONT_RETURN,
            RobotMotionCommand.TENSILE_FRONT_RETURN,
            RobotMotionCommand.SCRAP_FRONT_RETURN,
        }

        # 규칙 1: 거점 -> 거점 이동 허용
        if current_pos_id in WAYPOINTS and next_cmd_id in WAYPOINTS:
            return True

        # 규칙 2: 랙(Rack) 내부 시퀀스
        # 랙 앞(1000) -> QR 스캔 위치(13xx)
        if current_pos_id == RobotMotionCommand.RACK_FRONT_MOVE and (1300 <= next_cmd_id <= 1400):
            return True
        
        # 홈(100) or 랙 앞(1000) -> 랙 n층 앞(10x0) (QR 스캔 생략 시)
        if current_pos_id in [RobotMotionCommand.RECOVERY_HOME, RobotMotionCommand.RACK_FRONT_MOVE]:
             if 1000 <= next_cmd_id <= 1100 and next_cmd_id % 10 == 0:
                return True

        # QR 스캔 위치(13xx) -> 랙 n층 앞(10x0)
        if 1300 <= current_pos_id <= 1400:
            floor = (current_pos_id - 1300) // 10
            if next_cmd_id == get_rack_nF_front_pos_cmd(floor):
                return True
        # 랙 n층 앞(10x0) -> 랙 n층 N번 시편 위치(10xN)
        if 1000 <= current_pos_id <= 1100 and current_pos_id % 10 == 0:
            floor = (current_pos_id - 1000) // 10
            if get_rack_nF_front_pos_cmd(floor) < next_cmd_id < get_rack_nF_front_pos_cmd(floor) + 10:
                return True
        # 랙 n층 N번 시편 위치(10xN) -> 랙 n층 앞(10x0)
        if 1000 < current_pos_id <= 1100 and current_pos_id % 10 != 0:
            floor = (current_pos_id - 1000) // 10
            if next_cmd_id == get_rack_nF_front_pos_cmd(floor):
                return True
        # 랙 n층 앞(10x0) -> 랙 앞(1000)
        if 1000+1000 < current_pos_id <= 1100+1000 and current_pos_id % 10 == 0:
            if next_cmd_id == RobotMotionCommand.RACK_FRONT_RETURN:
                return True

        # 규칙 3: 두께 측정기(Gauge) 내부 시퀀스
        if current_pos_id == RobotMotionCommand.THICK_GAUGE_FRONT_MOVE and (3001 <= next_cmd_id <= 3003): return True
        if 3001 <= current_pos_id <= 3003 and next_cmd_id == RobotMotionCommand.THICK_GAUGE_FRONT_MOVE: return True
        if current_pos_id == RobotMotionCommand.THICK_GAUGE_FRONT_MOVE and (3011 <= next_cmd_id <= 3013): return True
        if 3011 <= current_pos_id <= 3013 and (4000 <= next_cmd_id <= 4002): return True

        # 규칙 4: 정렬기(Aligner) 내부 시퀀스
        if current_pos_id == RobotMotionCommand.ALIGNER_FRONT_MOVE and next_cmd_id == RobotMotionCommand.ALIGNER_SAMPLE_PLACE: return True
        if current_pos_id == RobotMotionCommand.ALIGNER_SAMPLE_PLACE and next_cmd_id == RobotMotionCommand.ALIGNER_FRONT_MOVE: return True
        if current_pos_id == RobotMotionCommand.ALIGNER_FRONT_MOVE and next_cmd_id == RobotMotionCommand.ALIGNER_SAMPLE_PICK: return True
        if current_pos_id == RobotMotionCommand.ALIGNER_SAMPLE_PICK and next_cmd_id == RobotMotionCommand.ALIGNER_FRONT_RETURN: return True

        # 규칙 5: 인장시험기(Tensile) 내부 시퀀스
        if current_pos_id == RobotMotionCommand.TENSILE_FRONT_MOVE and (7001 <= next_cmd_id <= 7002): return True
        if 7001 <= current_pos_id <= 7002 and next_cmd_id == RobotMotionCommand.TENSILE_FRONT_RETURN: return True
        if current_pos_id == RobotMotionCommand.TENSILE_FRONT_MOVE and (7011 <= next_cmd_id <= 7012): return True
        if 7011 <= current_pos_id <= 7012 and next_cmd_id == RobotMotionCommand.SCRAP_FRONT_MOVE: return True

        # 규칙 6: 스크랩(Scrap) 내부 시퀀스
        if current_pos_id == RobotMotionCommand.SCRAP_FRONT_MOVE and next_cmd_id == RobotMotionCommand.SCRAP_DROP_POS: return True
        if current_pos_id == RobotMotionCommand.SCRAP_DROP_POS and next_cmd_id == RobotMotionCommand.SCRAP_FRONT_RETURN: return True

        # 허용된 규칙에 해당하지 않으면 이동 불가
        Logger.warn(f"[Safety] Invalid move blocked: from {current_pos_id} to {next_cmd_id}")
        return False
