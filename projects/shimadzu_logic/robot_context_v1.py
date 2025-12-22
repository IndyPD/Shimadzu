from .constants import *
from pkg.fsm.shared import *
from pkg.utils.process_control import Flagger, reraise, FlagDelay

from pkg.configs.global_config import GlobalConfig

from pkg.utils.blackboard import GlobalBlackboard
bb = GlobalBlackboard()

class RobotStatus:
    """FSM 상태 확인을 위한 플래그"""
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
        
        # 현재 모션 상태 추적
        self.current_motion_cmd = 0
        self.last_motion_done = 0

    # ========================================
    # 상태 확인 메서드
    # ========================================
    
    def check_program_running(self):
        """Conty 프로그램 실행 상태 확인"""
        indy_status = bb.get("indy")
        prog_state = indy_status["program_state"]
        robot_state = indy_status["robot_state"]
        
        if prog_state == ProgramState.PROG_RUNNING:
            return True
        else:
            Logger.info(f"{get_time()}: Program is NOT running {ProgramState(prog_state).name}.")
            return False

    def check_violation(self) -> int:
        """모든 위반 상황 체크"""
        self.violation_code = 0x00
        try:
            # 1. 비상 정지 버튼 체크
            if self._check_emergency_stop():
                self.violation_code |= RobotViolation.ISO_EMERGENCY_BUTTON.value

            # 2. 하드웨어 오류 상태
            if self.status.is_error_state():
                self.violation_code |= RobotViolation.HW_VIOLATION.value
            
            # 3. 로봇 연결 상태
            if not self.status.is_connected():
                self.violation_code |= RobotViolation.CONNECTION_TIMEOUT.value
                
            # 4. 로봇 준비 상태
            if self.status.is_connected() and not self.status.is_ready():
                self.violation_code |= RobotViolation.HW_NOT_READY.value
            
            # 5. Indy Robot State 상세 체크
            self._check_indy_robot_state()
            
            # 6. 외부 장치 안전 체크
            self._check_external_safety()

            if self.violation_code != 0:
                violation_names = [v.name for v in RobotViolation if v.value & self.violation_code]
                Logger.error(f"{get_time()}: [Robot FSM] Violation detected: {' | '.join(violation_names)}")

            return self.violation_code
        except Exception as e:
            Logger.error(f"[RobotContextV1] Exception in check_violation: {e}")
            reraise(e)

    def _check_emergency_stop(self) -> bool:
        """비상 정지 버튼 상태 확인 (4개 EMO 스위치)"""
        emo_switches = [
            bb.get("device/remote/input/EMO_01_SW"),
            bb.get("device/remote/input/EMO_02_SW"),
            bb.get("device/remote/input/EMO_03_SW"),
            bb.get("device/remote/input/EMO_04_SW")
        ]
        return any(emo_switches)

    def _check_indy_robot_state(self):
        """Indy 로봇 상태 상세 체크"""
        indy_data = bb.get("indy")
        if not indy_data:
            return

        indy_state_val = indy_data.get("robot_state", 0)
        try:
            current_indy_state = Robot_OP_State(indy_state_val)
        except ValueError:
            current_indy_state = Robot_OP_State.OP_SYSTEM_OFF

        # 정상 상태들
        normal_states = (
            Robot_OP_State.OP_IDLE, 
            Robot_OP_State.OP_MOVING,
            Robot_OP_State.OP_TEACHING, 
            Robot_OP_State.OP_COMPLIANCE,
            Robot_OP_State.TELE_OP, 
            Robot_OP_State.OP_SYSTEM_ON, 
            Robot_OP_State.OP_SYSTEM_RESET
        )
        
        if current_indy_state in normal_states:
            return

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
            Logger.error(f"{get_time()}: [Indy State] {current_indy_state.name} (violation={self.violation_code})")

    def _check_external_safety(self):
        """외부 안전 장치 상태 확인"""
        # 안전 정지 상태 확인
        if bb.get("ui/state/safe/stop"):
            self.violation_code |= RobotViolation.HW_VIOLATION.value
            Logger.warn("Safety stop activated")

    # ========================================
    # 상태 조회 메서드
    # ========================================
    
    def robot_state(self):
        """로봇 상태 값 반환"""
        return bb.get("indy")["robot_state"]

    def program_state(self):
        """프로그램 상태 값 반환"""
        return bb.get("indy")["program_state"]

    def is_sim_mode(self):
        """시뮬레이션 모드 여부"""
        return bb.get("indy")["is_sim_mode"]

    def is_home_pos(self):
        """홈 위치 도달 여부"""
        return bb.get("indy")["is_home_pos"]

    def is_packaging_pos(self):
        """패키징 위치 도달 여부"""
        return bb.get("indy")["is_packaging_pos"]

    def is_detect_pos(self):
        """감지 위치 도달 여부"""
        return bb.get("indy")["is_detect_pos"]

    def get_gripper_state(self):
        """그리퍼 상태 확인"""
        return bb.get("int_var/grip_state/val")

    def get_current_position(self):
        """현재 로봇 위치"""
        return bb.get("int_var/robot/position/val")

    # ========================================
    # 기본 제어 명령
    # ========================================
    
    def direct_teaching(self, onoff):
        """다이렉트 티칭 모드 전환"""
        if onoff:
            bb.set("indy_command/direct_teaching_on", True)
            bb.set("robot/dt/mode", 1)
        else:
            bb.set("indy_command/direct_teaching_off", True)
            bb.set("robot/dt/mode", 0)

    def gripper_control(self, open):
        """그리퍼 제어 (열기/닫기)"""
        if open:
            bb.set("indy_command/gripper_open", True)
            Logger.info("Gripper: Opening")
        else:
            bb.set("indy_command/gripper_close", True)
            Logger.info("Gripper: Closing")
        
        # 상태 업데이트 대기
        time.sleep(0.5)

    def stop_motion(self):
        """모션 정지"""
        bb.set("indy_command/stop_motion", True)
        Logger.warn("Motion stop command sent")

    def go_home_pos(self):
        """홈 위치로 이동"""
        bb.set("indy_command/go_home", True)
        Logger.info("Moving to HOME position")

    def go_packaging_pos(self):
        """패키징 위치로 이동"""
        bb.set("indy_command/go_packaging", True)
        Logger.info("Moving to PACKAGING position")

    # ========================================
    # 프로그램 제어
    # ========================================
    
    def play_program(self):
        """메인 프로그램 실행"""
        bb.set("indy_command/play_program", True)

        start = time.time()
        while time.time() - start < 10.0:
            time.sleep(0.1)
            Logger.info(f"{get_time()}: Wait for main program running")
            if self.check_program_running():
                Logger.info("Main program started successfully")
                break
        else:
            Logger.error("Timeout waiting for main program to start")

    def stop_program(self):
        """프로그램 정지"""
        Logger.info("[DEBUG] stop_program: Sending stop command to Conty.")
        bb.set("indy_command/stop_program", True)

        # Conty 프로그램이 PROG_IDLE 상태가 될 때까지 대기
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
            Logger.warn(f"[DEBUG] stop_program: Timeout waiting for Conty program to stop.")

    def pause_program(self):
        """프로그램 일시정지"""
        bb.set("indy_command/pause_program", True)
        Logger.info("Program paused")

    def resume_program(self):
        """프로그램 재개"""
        bb.set("indy_command/resume_program", True)
        Logger.info("Program resumed")

    # ========================================
    # 복구 관련
    # ========================================
    
    def recover_robot(self):
        """로봇 복구 프로세스"""
        Logger.info("Starting robot recovery process")
        
        # 복구 플래그 초기화 및 명령 전송
        bb.set("robot/recover/is_done", False)
        bb.set("indy_command/recover", True)
        
        # 복구 완료 대기 (is_done이 True가 될 때까지)
        start_time = time.time()
        timeout = 30.0
        while time.time() - start_time < timeout:
            if bb.get("robot/recover/is_done") == True:
                Logger.info("Robot recovery completed")
                return True
            time.sleep(0.5)
        
        Logger.error("Robot recovery timeout")
        return False

    def manual_recover_complete(self):
        """수동 복구 완료 처리"""
        bb.set("ui/cmd/manual/manual_recover_complete", 1)
        bb.set("process/manual_recover/is_done", True)
        Logger.info("Manual recovery marked as complete")

    # ========================================
    # 모션 제어 (엑셀 문서 기반)
    # ========================================
    
    def send_motion_command(self, motion_cmd: int):
        """
        모션 명령 전송
        
        Args:
            motion_cmd: 모션 명령 코드 (엑셀 문서 참조)
                - 1~6: 홈에서 각 위치로 이동
                - 21~26: 각 위치에서 홈으로 복귀
                - 90: 그리퍼 열기, 91: 그리퍼 닫기
                - 100: 홈 이동 (복구)
                - 101~102: 툴 변경
                - 1000+: 공정 모션
        """
        Logger.info(f"Sending motion command: {motion_cmd}")
        bb.set("int_var/cmd/val", motion_cmd)
        self.current_motion_cmd = motion_cmd
        
    def wait_motion_ack(self, motion_cmd: int, timeout: float = 5.0) -> bool:
        """
        모션 ACK 대기 (Conty가 명령을 받았는지 확인)
        
        Args:
            motion_cmd: 모션 명령 코드
            timeout: 타임아웃 시간 (초)
            
        Returns:
            bool: 성공 여부
        """
        expected_ack_code = motion_cmd + 500
        start_time = time.time()
        while time.time() - start_time < timeout:
            motion_ack = bb.get("int_var/motion_ack/val")
            if motion_ack == expected_ack_code:
                Logger.debug(f"Motion ACK received: {motion_ack}")
                return True
            
            # Violation 체크
            if self.check_violation():
                Logger.error(f"Violation detected while waiting for ACK: {self.violation_code}")
                return False
            
            time.sleep(0.05)
        
        Logger.error(f"Motion ACK timeout: expected {expected_ack_code} (cmd {motion_cmd}), current {bb.get('int_var/motion_ack/val')}")
        return False

    def wait_motion_done(self, expected_done_code: int, timeout: float = 30.0) -> bool:
        """
        모션 완료 대기
        
        Args:
            expected_done_code: 예상되는 완료 코드 (motion + 10000)
            timeout: 타임아웃 시간 (초)
            
        Returns:
            bool: 성공 여부
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            motion_done = bb.get("int_var/motion_done/val")
            if motion_done == expected_done_code:
                Logger.info(f"Motion done: {motion_done}")
                self.last_motion_done = motion_done
                return True
            
            # Violation 체크
            if self.check_violation():
                Logger.error(f"Violation detected during motion: {self.violation_code}")
                return False
            
            time.sleep(0.1)
        
        Logger.error(f"Motion timeout: expected {expected_done_code}, current {bb.get('int_var/motion_done/val')}")
        return False
    
    def wait_motion_complete(self, motion_cmd: int, ack_timeout: float = 5.0, done_timeout: float = 30.0) -> bool:
        """
        모션 명령 전송 후 ACK 확인 → 완료 대기 (통합 메서드)
        
        Args:
            motion_cmd: 모션 명령 코드
            ack_timeout: ACK 대기 타임아웃 (초)
            done_timeout: 완료 대기 타임아웃 (초)
            
        Returns:
            bool: 성공 여부
        """
        # 1. ACK 대기 (내부에서 motion_cmd + 500 체크)
        if not self.wait_motion_ack(motion_cmd, timeout=ack_timeout):
            Logger.error(f"Motion {motion_cmd}: ACK not received")
            return False
        
        # 2. 완료 대기 (motion + 10000)
        expected_done = motion_cmd + 10000
        if not self.wait_motion_done(expected_done, timeout=done_timeout):
            Logger.error(f"Motion {motion_cmd}: Completion timeout")
            return False
        
        return True

    def motion_command_reset(self):
        """모션 명령 초기화"""
        bb.set("int_var/cmd/val", 0)
        Logger.debug("Motion command reset")

    # ========================================
    # 복합 모션 (자주 사용되는 시퀀스)
    # ========================================
    
    def move_to_rack_floor(self, floor: int) -> bool:
        """
        랙 n층 앞으로 이동
        
        Args:
            floor: 층수 (1~10)
        """
        if not 1 <= floor <= 10:
            Logger.error(f"Invalid floor number: {floor}")
            return False
        
        # 1. 홈 -> 랙 앞 (motion 1)
        self.send_motion_command(1)
        if not self.wait_motion_done(10001):
            return False
        
        # 2. 랙 앞 -> n층 앞 (motion 1{floor}0)
        floor_motion = 1000 + floor * 10
        self.send_motion_command(floor_motion)
        expected_done = floor_motion + 10000
        if not self.wait_motion_done(expected_done):
            return False
        
        Logger.info(f"Successfully moved to rack floor {floor}")
        return True

    def pick_specimen_from_rack(self, floor: int, position: int) -> bool:
        """
        랙에서 시편 픽업
        
        Args:
            floor: 층수 (1~10)
            position: 위치 번호 (1~N)
        """
        # 1. n층 N번 위치로 이동
        pick_motion = 1000 + floor * 10 + position
        self.send_motion_command(pick_motion)
        expected_done = pick_motion + 10000
        if not self.wait_motion_done(expected_done):
            return False
        
        # 2. 그리퍼 닫기
        self.gripper_control(open=False)
        time.sleep(1.0)  # 그리핑 안정화
        
        # 3. n층 앞으로 복귀
        retract_motion = 2000 + floor * 10
        self.send_motion_command(retract_motion)
        expected_done = retract_motion + 10000
        if not self.wait_motion_done(expected_done):
            return False
        
        Logger.info(f"Successfully picked specimen from floor {floor}, position {position}")
        return True

    def measure_thickness(self, num_measurements: int = 3) -> bool:
        """
        두께 측정 수행
        
        Args:
            num_measurements: 측정 횟수 (1~3)
        """
        # 1. 두께 측정기 앞 이동
        self.send_motion_command(3000)
        if not self.wait_motion_done(13000):
            return False
        
        # 2. 측정 수행
        for i in range(1, num_measurements + 1):
            # 측정 위치에 시편 놓기
            place_motion = 3000 + i
            self.send_motion_command(place_motion)
            if not self.wait_motion_done(place_motion + 10000):
                return False
            
            # 그리퍼 열기
            self.gripper_control(open=True)
            time.sleep(1.0)  # 측정 대기
            
            # TODO: 두께 측정값 읽기
            thickness = bb.get("device/gauge/thickness")
            Logger.info(f"Thickness measurement {i}: {thickness}")
            
            # 마지막 측정이 아니면 다시 잡기
            if i < num_measurements:
                grab_motion = 3010 + i
                self.send_motion_command(grab_motion)
                if not self.wait_motion_done(grab_motion + 10000):
                    return False
                self.gripper_control(open=False)
        
        # 3. 두께 측정기 앞으로 복귀
        self.send_motion_command(4000)
        if not self.wait_motion_done(14000):
            return False
        
        Logger.info(f"Thickness measurement completed ({num_measurements} measurements)")
        return True

    def align_specimen(self) -> bool:
        """시편 정렬"""
        # 1. 정렬기 앞 이동
        self.send_motion_command(5000)
        if not self.wait_motion_done(15000):
            return False
        
        # 2. 시편 놓기
        self.send_motion_command(5001)
        if not self.wait_motion_done(15001):
            return False
        
        self.gripper_control(open=True)
        
        # 3. 정렬 대기
        time.sleep(2.0)  # TODO: 정렬 완료 신호 대기로 변경
        
        # 4. 시편 잡기
        self.send_motion_command(5011)
        if not self.wait_motion_done(15011):
            return False
        
        self.gripper_control(open=False)
        
        # 5. 정렬기 앞 복귀
        self.send_motion_command(6000)
        if not self.wait_motion_done(16000):
            return False
        
        Logger.info("Specimen alignment completed")
        return True

    def place_in_tensile_machine(self) -> bool:
        """인장시험기에 시편 장착"""
        # 1. 인장시험기 앞 이동
        self.send_motion_command(7000)
        if not self.wait_motion_done(17000):
            return False
        
        # 2. 시편 장착 위치 이동
        self.send_motion_command(7001)
        if not self.wait_motion_done(17001):
            return False
        
        # 3. 그리퍼 열기
        self.gripper_control(open=True)
        
        # 4. 인장시험기 앞 복귀
        self.send_motion_command(8000)
        if not self.wait_motion_done(18000):
            return False
        
        Logger.info("Specimen placed in tensile machine")
        return True

    def collect_from_tensile_machine(self) -> bool:
        """인장시험 후 시편 수거"""
        # 1. 인장시험기 앞 이동
        self.send_motion_command(7000)
        if not self.wait_motion_done(17000):
            return False
        
        # 2. 시편 수거 위치 이동
        self.send_motion_command(7011)
        if not self.wait_motion_done(17011):
            return False
        
        # 3. 그리퍼 닫기
        self.gripper_control(open=False)
        
        # 4. 인장시험기 앞 복귀
        self.send_motion_command(8000)
        if not self.wait_motion_done(18000):
            return False
        
        Logger.info("Specimen collected from tensile machine")
        return True

    def discard_to_scrap(self) -> bool:
        """스크랩 배출"""
        # 1. 스크랩 배출대 앞 이동
        self.send_motion_command(7020)
        if not self.wait_motion_done(17020):
            return False
        
        # 2. 스크랩 버리기
        self.send_motion_command(7021)
        if not self.wait_motion_done(17021):
            return False
        
        # 3. 그리퍼 열기
        self.gripper_control(open=True)
        
        Logger.info("Specimen discarded to scrap box")
        return True

    # ========================================
    # 외부 장치 제어
    # ========================================
    
    def control_tower_lamp(self, red=False, yellow=False, green=False):
        """타워램프 제어"""
        bb.set("device/remote/output/TOWER_LAMP_RED", 1 if red else 0)
        bb.set("device/remote/output/TOWER_LAMP_YELLOW", 1 if yellow else 0)
        bb.set("device/remote/output/TOWER_LAMP_GREEN", 1 if green else 0)

    def buzzer_control(self, onoff):
        """부저 제어"""
        if onoff:
            bb.set("indy_command/buzzer_on", True)
            bb.set("device/remote/output/TOWER_BUZZER", 1)
        else:
            bb.set("indy_command/buzzer_off", True)
            bb.set("device/remote/output/TOWER_BUZZER", 0)

    def trigger_vision(self):
        """비전 트리거"""
        bb.set("device/remote/output/VISION_TRIGGER", 1)
        time.sleep(0.1)
        bb.set("device/remote/output/VISION_TRIGGER", 0)

    def control_aligner(self, align_num: int, push: bool):
        """
        정렬기 제어
        
        Args:
            align_num: 정렬기 번호 (1~3)
            push: True=Push, False=Pull
        """
        if not 1 <= align_num <= 3:
            Logger.error(f"Invalid aligner number: {align_num}")
            return
        
        action = "PUSH" if push else "PULL"
        key = f"device/remote/output/ALIGN_{align_num}_{action}"
        bb.set(key, 1)
        Logger.info(f"Aligner {align_num} {action}")

    # ========================================
    # 유틸리티
    # ========================================
    
    def get_system_comm_status(self) -> dict:
        """통신 상태 조회"""
        return {
            "robot": bb.get("sys/robot/comm/state"),
            "external": bb.get("sys/ext/comm/state"),
            "remote_io": bb.get("sys/remoteio/comm/state"),
            "gauge": bb.get("sys/gauge/comm/state")
        }

    def reset_init_variables(self):
        """초기화 변수 리셋"""
        bb.set("indy_command/reset_init_var", True)
        bb.set("int_var/init/val", 0)
        Logger.info("Init variables reset")