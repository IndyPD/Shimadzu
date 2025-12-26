import time

from pkg.utils.blackboard import GlobalBlackboard
from .robot_context_v1 import *

bb = GlobalBlackboard()

# ========================================
# 1. 기본 FSM 전략
# ========================================

class RobotConnectingStrategy(Strategy):
    """로봇 컨트롤러 연결 시도"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Attempting to connect to robot controller.")
        context.control_tower_lamp(yellow=True)
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 연결 체크: CONNECTION_TIMEOUT 위반이 없으면 연결 성공
        if not (context.check_violation() & RobotViolation.CONNECTION_TIMEOUT):
            context.status.is_connected.up()
            return RobotEvent.CONNECTION_SUCCESS
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        if event == RobotEvent.CONNECTION_SUCCESS:
            Logger.info("Robot controller connected successfully")
            context.control_tower_lamp(green=True)


class RobotErrorStrategy(Strategy):
    """에러 상태 처리"""
    
    def prepare(self, context: RobotContext, **kwargs):
        violation_names = [v.name for v in RobotViolation if v & context.violation_code]
        Logger.error(f"Robot Violation Detected: {' | '.join(violation_names)}", popup=True)
        
        # 에러 표시
        context.control_tower_lamp(red=True)
        context.buzzer_control(True)
        time.sleep(0.5)
        context.buzzer_control(False)
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 위반이 해소되면 복구 가능
        if not context.check_violation():
            return RobotEvent.RECOVER
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ErrorStrategy with event: {event}")
        if event == RobotEvent.RECOVER:
            Logger.info("Violation cleared, starting recovery")


class RobotRecoveringStrategy(Strategy):
    """복구 프로세스"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Starting recovery process (SW/HW Reset).")
        context.control_tower_lamp(yellow=True)
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 복구 실행
        if context.recover_robot():
            # 홈 위치로 복귀
            context.go_home_pos()
            time.sleep(2.0)
            
            if context.is_home_pos():
                return RobotEvent.DONE
        
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RecoveringStrategy with event: {event}")
        if event == RobotEvent.DONE:
            Logger.info("Recovery completed successfully")
            context.control_tower_lamp(green=True)


class RobotStopOffStrategy(Strategy):
    """비상 정지 상태"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.warn("Robot: Emergency Stop Engaged. Turning off motors.")
        context.control_tower_lamp(red=True)
        context.buzzer_control(True)
        
        # 안전하게 정지
        context.stop_motion()
        context.stop_program()
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # EMO가 해제되면 재연결 시도
        if not context._check_emergency_stop():
            context.buzzer_control(False)
            return RobotEvent.DONE
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit StopOffStrategy with event: {event}")
        if event == RobotEvent.DONE:
            Logger.info("Emergency stop released, reconnecting...")


class RobotReadyStrategy(Strategy):
    """준비 완료 상태"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Ready and waiting for commands.")
        context.control_tower_lamp(green=True)

    def operate(self, context: RobotContext) -> RobotEvent:
        # 위반 체크
        if context.check_violation():
            return RobotEvent.VIOLATION_DETECT
        
        # 자동 모드 시작 명령 대기
        if bb.get("ui/cmd/auto/tensile"):
            bb.set("ui/cmd/auto/tensile", 0)
            return RobotEvent.DO_AUTO_MOTION_PROGRAM_AUTO_ON
        
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit WaitAutoCommandStrategy with event: {event}")


# ========================================
# 2. 프로그램 제어
# ========================================

class RobotProgramAutoOnStrategy(Strategy):
    """자동 모드 켜기"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Turning on Auto Mode.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # Conty 프로그램 실행
        context.play_program()
        
        # 프로그램 실행 확인
        if context.check_program_running():
            return RobotEvent.PROGRAM_AUTO_ON_DONE
        
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ProgramAutoOnStrategy with event: {event}")
        Logger.info("Auto mode enabled, waiting for commands")


class RobotProgramManualOffStrategy(Strategy):
    """수동 모드로 전환"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Turning off Auto Mode (Manual).")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 프로그램 정지
        context.stop_program()
        return RobotEvent.PROGRAM_MANUAL_OFF_DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ProgramManualOffStrategy with event: {event}")
        Logger.info("Manual mode enabled")


class RobotWaitAutoCommandStrategy(Strategy):
    """자동 명령 대기"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Waiting for auto process command.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 위반 체크
        if context.check_violation():
            return RobotEvent.VIOLATION_DETECT
        
        # TODO: 상위 시스템(Logic FSM)으로부터 명령 수신
        # 현재는 테스트용 임시 로직
        if bb.get("test/robot/motion", 0):
            bb.set("test/robot/motion", 0)
            return RobotEvent.DO_AUTO_MOTION_MOVE_HOME
        
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ReadyStrategy with event: {event}")


# ========================================
# 3. 기본 모션
# ========================================

class RobotMoveHomeStrategy(Strategy):
    """홈 위치 이동"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to Home.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 모션 명령: 100 (복구용 홈 이동)
        context.send_motion_command(100)
        
        if context.wait_motion_complete(100, ack_timeout=5.0, done_timeout=30.0):
            return RobotEvent.AUTO_MOTION_MOVE_HOME_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterScrapStrategy with event: {event}")
        context.motion_command_reset()


class RobotToolChangeStrategy(Strategy):
    """툴 변경"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Changing Tool.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 툴 타입에 따라 다른 모션 (101: binpicking용, 102: 일반용)
        tool_type = bb.get("robot/tool_type")
        context.send_motion_command(tool_type)
        
        if context.wait_motion_complete(tool_type, ack_timeout=5.0, done_timeout=30.0):
            # 툴 장착 확인
            if self._verify_tool_attached(context, tool_type):
                return RobotEvent.AUTO_MOTION_TOOL_CHANGE_DONE
            else:
                Logger.error("Tool change failed: Tool not properly attached")
                return RobotEvent.VIOLATION_DETECT
        
        return RobotEvent.VIOLATION_DETECT
    
    def _verify_tool_attached(self, context: RobotContext, tool_type: int) -> bool:
        """툴 장착 확인 (센서로 검증)"""
        if tool_type == 101:
            return bb.get("device/remote/input/ATC_1_1_SENSOR")
        elif tool_type == 102:
            return bb.get("device/remote/input/ATC_2_1_SENSOR")
        return False
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        context.motion_command_reset()


# ========================================
# 4. 그리퍼 제어
# ========================================

class RobotAutoGripperOpenStrategy(Strategy):
    """그리퍼 열기"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Opening Gripper.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(90)
        
        if context.wait_motion_done(10090, timeout=5.0):
            return RobotEvent.AUTO_GRIPPER_OPEN_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachScrapStrategy with event: {event}")
        context.motion_command_reset()


class RobotAutoGripperCloseStrategy(Strategy):
    """그리퍼 닫기"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Closing Gripper.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(91)
        
        if context.wait_motion_done(10091, timeout=5.0):
            return RobotEvent.AUTO_GRIPPER_CLOSE_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RetractFromTensileStrategy with event: {event}")
        context.motion_command_reset()


# ========================================
# 5. 랙 작업 모션
# ========================================

class RobotApproachRackStrategy(Strategy):
    """랙 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Rack.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(1000)
        
        if context.wait_motion_complete(1000, ack_timeout=5.0, done_timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_RACK_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterTensileStrategy with event: {event}")
        context.motion_command_reset()


class RobotMoveToQRStrategy(Strategy):
    """QR 인식 위치 이동"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Moving to QR Position.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 목표 층수 가져오기
        floor = bb.get("robot/target_floor")
        motion_cmd = 1000 + floor * 10
        
        context.send_motion_command(motion_cmd)
        expected_done = motion_cmd + 10000
        
        if context.wait_motion_done(expected_done, timeout=20.0):
            # QR 읽기 트리거
            context.trigger_vision()
            time.sleep(1.0)
            
            # QR 읽기 성공 확인
            if bb.get("device/remote/input/BCR_OK"):
                Logger.info("QR code read successfully")
                return RobotEvent.AUTO_MOTION_MOVE_TO_QR_DONE
            else:
                Logger.error("QR code read failed")
                return RobotEvent.VIOLATION_DETECT
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachTensileStrategy with event: {event}")
        context.motion_command_reset()


class RobotApproachPickStrategy(Strategy):
    """시편 픽업 위치 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Pick Position.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        floor = bb.get("robot/target_floor")
        motion_cmd = 1000 + floor * 10
        
        context.send_motion_command(motion_cmd)
        expected_done = motion_cmd + 10000
        
        if context.wait_motion_done(expected_done, timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_PICK_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RetractFromAlignerStrategy with event: {event}")
        context.motion_command_reset()


class RobotPickSpecimenStrategy(Strategy):
    """시편 픽업"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Picking Specimen.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        floor = bb.get("robot/target_floor")
        position = bb.get("robot/target_position")
        
        motion_cmd = 1000 + floor * 10 + position
        context.send_motion_command(motion_cmd)
        expected_done = motion_cmd + 10000
        
        if context.wait_motion_done(expected_done, timeout=20.0):
            # 그리퍼 닫기
            context.gripper_control(open=False)
            time.sleep(1.0)
            
            # 그리핑 확인 (그리퍼 센서)
            if bb.get("device/remote/input/GRIPPER_1_CLAMP"):
                Logger.info("Specimen gripped successfully")
                return RobotEvent.AUTO_MOTION_PICK_SPECIMEN_DONE
            else:
                Logger.error("Gripper failed to hold specimen")
                return RobotEvent.VIOLATION_DETECT
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterAlignerStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromTrayStrategy(Strategy):
    """트레이 앞 후퇴"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Tray.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        floor = bb.get("robot/target_floor")
        motion_cmd = 2000 + floor * 10
        
        context.send_motion_command(motion_cmd)
        expected_done = motion_cmd + 10000
        
        if context.wait_motion_done(expected_done, timeout=20.0):
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_TRAY_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachAlignerStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromRackStrategy(Strategy):
    """랙 앞 후퇴"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Rack.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(2000)
        
        if context.wait_motion_done(12000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_RACK_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RetractFromThicknessStrategy with event: {event}")
        context.motion_command_reset()


# ========================================
# 6. 두께 측정 모션
# ========================================

class RobotApproachThicknessStrategy(Strategy):
    """두께 측정기 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Thickness Gauge.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(3000)
        
        if context.wait_motion_done(13000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_THICKNESS_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterThicknessPos3Strategy with event: {event}")
        context.motion_command_reset()


class RobotEnterThicknessPos1Strategy(Strategy):
    """두께 측정 위치 1"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 1.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(3001)
        
        if context.wait_motion_done(13001, timeout=15.0):
            context.gripper_control(open=True)
            time.sleep(1.5)  # 측정 대기
            
            # 측정값 읽기
            thickness = bb.get("device/gauge/thickness")
            Logger.info(f"Thickness measurement 1: {thickness}")
            bb.set("specimen/thickness_1", thickness)
            
            return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_1_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterThicknessPos2Strategy with event: {event}")
        context.motion_command_reset()


class RobotEnterThicknessPos2Strategy(Strategy):
    """두께 측정 위치 2"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 2.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 먼저 시편 다시 잡기
        context.send_motion_command(3011)
        if not context.wait_motion_done(13011, timeout=10.0):
            return RobotEvent.VIOLATION_DETECT
        
        context.gripper_control(open=False)
        time.sleep(0.5)
        
        # 측정 위치 2로 이동
        context.send_motion_command(3002)
        if context.wait_motion_done(13002, timeout=15.0):
            context.gripper_control(open=True)
            time.sleep(1.5)
            
            thickness = bb.get("device/gauge/thickness")
            Logger.info(f"Thickness measurement 2: {thickness}")
            bb.set("specimen/thickness_2", thickness)
            
            return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_2_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit EnterThicknessPos1Strategy with event: {event}")
        context.motion_command_reset()


class RobotEnterThicknessPos3Strategy(Strategy):
    """두께 측정 위치 3"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Thickness Position 3.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 시편 다시 잡기
        context.send_motion_command(3012)
        if not context.wait_motion_done(13012, timeout=10.0):
            return RobotEvent.VIOLATION_DETECT
        
        context.gripper_control(open=False)
        time.sleep(0.5)
        
        # 측정 위치 3으로 이동
        context.send_motion_command(3003)
        if context.wait_motion_done(13003, timeout=15.0):
            context.gripper_control(open=True)
            time.sleep(1.5)
            
            thickness = bb.get("device/gauge/thickness")
            Logger.info(f"Thickness measurement 3: {thickness}")
            bb.set("specimen/thickness_3", thickness)
            
            # 평균 두께 계산
            t1 = bb.get("specimen/thickness_1")
            t2 = bb.get("specimen/thickness_2")
            t3 = thickness
            avg_thickness = (t1 + t2 + t3) / 3.0
            bb.set("specimen/thickness_avg", avg_thickness)
            Logger.info(f"Average thickness: {avg_thickness}")
            
            return RobotEvent.AUTO_MOTION_ENTER_THICKNESS_POS_3_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachThicknessStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromThicknessStrategy(Strategy):
    """두께 측정기 앞 후퇴"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Thickness Gauge.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 마지막 위치에서 시편 다시 잡기
        context.send_motion_command(3013)
        if not context.wait_motion_done(13013, timeout=10.0):
            return RobotEvent.VIOLATION_DETECT
        
        context.gripper_control(open=False)
        time.sleep(0.5)
        
        # 두께 측정기 앞으로 후퇴
        context.send_motion_command(4000)
        if context.wait_motion_done(14000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_THICKNESS_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RetractFromRackStrategy with event: {event}")
        context.motion_command_reset()


# ========================================
# 7. 정렬기 모션
# ========================================

class RobotApproachAlignerStrategy(Strategy):
    """정렬기 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Aligner.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(5000)
        
        if context.wait_motion_done(15000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_ALIGNER_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit RetractFromTrayStrategy with event: {event}")
        context.motion_command_reset()


class RobotEnterAlignerStrategy(Strategy):
    """정렬기 진입 및 정렬"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Aligner.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 정렬 위치로 이동
        context.send_motion_command(5001)
        
        if context.wait_motion_done(15001, timeout=15.0):
            # 시편 놓기
            context.gripper_control(open=True)
            time.sleep(0.5)
            
            # 정렬기 작동 (3축 정렬)
            for i in range(1, 4):
                context.control_aligner(i, push=True)
            
            time.sleep(2.0)  # 정렬 대기
            
            # 정렬 완료 확인 (모든 축이 PUSH 상태)
            align_ok = all([
                bb.get("device/remote/input/ALIGN_1_PUSH"),
                bb.get("device/remote/input/ALIGN_2_PUSH"),
                bb.get("device/remote/input/ALIGN_3_PUSH")
            ])
            
            if align_ok:
                Logger.info("Specimen aligned successfully")
                return RobotEvent.AUTO_MOTION_ENTER_ALIGNER_DONE
            else:
                Logger.error("Aligner positioning failed")
                return RobotEvent.VIOLATION_DETECT
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit PickSpecimenStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromAlignerStrategy(Strategy):
    """정렬기에서 시편 회수"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Aligner.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 정렬기 열기 (PULL)
        for i in range(1, 4):
            context.control_aligner(i, push=False)
        
        time.sleep(1.0)
        
        # 시편 잡기
        context.send_motion_command(5011)
        if not context.wait_motion_done(15011, timeout=10.0):
            return RobotEvent.VIOLATION_DETECT
        
        context.gripper_control(open=False)
        time.sleep(0.5)
        
        # 정렬기 앞으로 후퇴
        context.send_motion_command(6000)
        if context.wait_motion_done(16000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_ALIGNER_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachPickStrategy with event: {event}")
        context.motion_command_reset()


# ========================================
# 8. 인장시험기 모션
# ========================================

class RobotApproachTensileStrategy(Strategy):
    """인장시험기 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Tensile Machine.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(7000)
        
        if context.wait_motion_done(17000, timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_TENSILE_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit MoveToQRStrategy with event: {event}")
        context.motion_command_reset()


class RobotEnterTensileStrategy(Strategy):
    """인장시험기에 시편 장착"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Tensile Machine.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 시편 장착 위치로 이동
        context.send_motion_command(7001)
        
        if context.wait_motion_done(17001, timeout=15.0):
            # 인장시험기 그리퍼가 준비될 때까지 대기
            # TODO: Device FSM으로부터 그리퍼 준비 신호 대기
            time.sleep(2.0)
            
            # 로봇 그리퍼 열기 (시편 놓기)
            context.gripper_control(open=True)
            time.sleep(1.0)
            
            Logger.info("Specimen placed in tensile machine")
            return RobotEvent.AUTO_MOTION_ENTER_TENSILE_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ApproachRackStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromTensileStrategy(Strategy):
    """인장시험기에서 시편 수거"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Tensile Machine.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 시험 완료 대기
        # TODO: Device FSM으로부터 시험 완료 신호 대기
        Logger.info("Waiting for tensile test completion...")
        
        # 시편 수거 위치로 이동
        context.send_motion_command(7011)
        if not context.wait_motion_done(17011, timeout=15.0):
            return RobotEvent.VIOLATION_DETECT
        
        # 시편 잡기
        context.gripper_control(open=False)
        time.sleep(1.0)
        
        # 인장시험기 앞으로 후퇴
        context.send_motion_command(8000)
        if context.wait_motion_done(18000, timeout=20.0):
            Logger.info("Specimen collected from tensile machine")
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_TENSILE_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit AutoGripperCloseStrategy with event: {event}")
        context.motion_command_reset()


# ========================================
# 9. 스크랩 모션
# ========================================

class RobotApproachScrapStrategy(Strategy):
    """스크랩 통 앞 접근"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Approaching Scrap Box.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(7020)
        
        if context.wait_motion_done(17020, timeout=20.0):
            return RobotEvent.AUTO_MOTION_APPROACH_SCRAP_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit AutoGripperOpenStrategy with event: {event}")
        context.motion_command_reset()


class RobotEnterScrapStrategy(Strategy):
    """스크랩 통에 시편 배출"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Entering Scrap Box.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        context.send_motion_command(7021)
        
        if context.wait_motion_done(17021, timeout=15.0):
            # 그리퍼 열기 (시편 떨어뜨리기)
            context.gripper_control(open=True)
            time.sleep(1.0)
            
            Logger.info("Specimen discarded to scrap box")
            return RobotEvent.AUTO_MOTION_ENTER_SCRAP_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit ToolChangeStrategy with event: {event}")
        context.motion_command_reset()


class RobotRetractFromScrapStrategy(Strategy):
    """스크랩 통 앞 후퇴"""
    
    def prepare(self, context: RobotContext, **kwargs):
        Logger.info("Robot: Retracting from Scrap Box.")
        
    def operate(self, context: RobotContext) -> RobotEvent:
        # 스크랩 통에서 후퇴 (홈으로 복귀)
        context.send_motion_command(26)  # 스크랩 배출 앞 - 홈 이동
        
        if context.wait_motion_done(10026, timeout=20.0):
            Logger.info("Cycle completed, returned to home")
            return RobotEvent.AUTO_MOTION_RETRACT_FROM_SCRAP_DONE
        
        return RobotEvent.VIOLATION_DETECT
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit MoveHomeStrategy with event: {event}")
        context.motion_command_reset()