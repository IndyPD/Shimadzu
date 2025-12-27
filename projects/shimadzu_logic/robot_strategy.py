import time

from pkg.utils.blackboard import GlobalBlackboard
from .robot_context import *

bb = GlobalBlackboard()

# ----------------------------------------------------
# 1. 범용 FSM 전략
# ----------------------------------------------------

class RobotConnectingStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Attempting to connect to robot controller...")
        # 연결 상태 플래그를 초기에 내립니다.
        context.status.is_connected.down()

    def operate(self, context: RobotContext) -> RobotEvent:
        # 1. 블랙보드에서 실제 로봇 통신 상태를 확인합니다.
        # 이 값은 indy_control.py의 indy_communication 스레드에서 주기적으로 업데이트됩니다.
        is_robot_comm_ok = int(bb.get("device/robot/comm_status") or 0) == 1

        if not is_robot_comm_ok:
            # 아직 연결되지 않았으면 계속 대기합니다.
            return RobotEvent.NONE

        # 2. 연결이 확인되면, 컨텍스트의 내부 상태 플래그를 업데이트합니다.
        context.status.is_connected.up()
        
        # 3. 연결이 된 상태에서 다른 위반 사항이 있는지 확인합니다.
        # is_connected 플래그가 올라갔으므로, check_violation은 더 이상 CONNECTION_TIMEOUT을 보고하지 않습니다.
        violation_code = context.check_violation()
        if violation_code != 0:
            # 연결은 되었지만 다른 문제가 발생한 경우 (예: 비상 정지)
            # FSM이 ERROR 상태로 전환하도록 VIOLATION_DETECT 이벤트를 발생시킵니다.
            return RobotEvent.VIOLATION_DETECT

        # 4. 연결되었고 다른 위반 사항도 없으면, 연결 성공 이벤트를 반환합니다.
        return RobotEvent.CONNECTION_SUCCESS
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        if event == RobotEvent.CONNECTION_SUCCESS:
            Logger.info("[Robot] Robot controller connected successfully.")
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")
        
class RobotErrorStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        violation_names = [v.name for v in RobotViolation if v & context.violation_code]
        Logger.error(f"Robot Violation Detected: {'|'.join(violation_names)}", popup=True)
    def operate(self, context: RobotContext) -> RobotEvent:
        # 오류 발생 시 외부 명령 없이 자동으로 복구 상태로 전환합니다.
        return RobotEvent.RECOVER
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")

class RobotRecoveringStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Starting recovery process (SW/HW Reset).")
        # 실제 복구 시퀀스 (ExecutionSequence)를 여기에 설정
    def operate(self, context: RobotContext) -> RobotEvent:
        # if recovery_sequence.execute():
        return RobotEvent.DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")
        # return RobotEvent.NONE

class RobotStopOffStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Emergency Stop Engaged. Turning off motors.")
    def operate(self, context: RobotContext) -> RobotEvent:
        # 안전하게 모터 전원 차단 후, DONE 이벤트 반환
        return RobotEvent.DONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")

class RobotReadyStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Ready and waiting for commands.")
        # 수동 모션 테스트를 위한 상태 변수
        self.manual_cmd_id = None
        self.manual_cmd_name = None
        self.manual_cmd_start_time = None
        self.manual_cmd_state = "idle"  # "idle" 또는 "waiting_done"

    def operate(self, context: RobotContext) -> RobotEvent:
        if context.check_violation():
            return RobotEvent.VIOLATION_DETECT
        
        # 수동 모션 테스트 로직
        if self.manual_cmd_state == "idle":
            manual_cmd_id = int(bb.get("manual/robot/tester") or 0)
            if manual_cmd_id > 0:
                bb.set("manual/robot/tester", 0)  # 명령 소비

                self.manual_cmd_id = manual_cmd_id
                self.manual_cmd_name = f"Manual CMD ID {manual_cmd_id}"
                
                Logger.info(f"[Robot] Manual Test: Executing '{self.manual_cmd_name}'")
                
                # 1. ACK/DONE 변수 초기화 요청
                bb.set("indy_command/reset_init_var", True)
                time.sleep(0.1)  # Conty가 초기화를 처리할 시간을 줌

                # 2. 모션 명령 전송
                bb.set("int_var/cmd/val", self.manual_cmd_id)
                
                # 3. 완료 대기 상태로 전환
                self.manual_cmd_state = "waiting_done"
                self.manual_cmd_start_time = time.time()

        elif self.manual_cmd_state == "waiting_done":
            motion_done_val = int(bb.get("int_var/motion_done/val") or 0)
            expected_done_val = self.manual_cmd_id + 10000

            # 모션 완료 확인
            if motion_done_val == expected_done_val:
                Logger.info(f"[Robot] Manual Test: Motion '{self.manual_cmd_name}' completed successfully.")
                bb.set("indy_command/reset_init_var", True)  # 다음 명령을 위해 ACK/DONE 초기화
                self.manual_cmd_state = "idle"
            
            # 타임아웃 확인 (예: 60초)
            elif time.time() - self.manual_cmd_start_time > 60.0:
                Logger.error(f"[Robot] Manual Test: DONE timeout for '{self.manual_cmd_name}' (CMD ID: {self.manual_cmd_id})")
                context.stop_motion()
                bb.set("int_var/cmd/val", 0)  # 명령 전송 중단
                bb.set("indy_command/reset_init_var", True)
                self.manual_cmd_state = "idle"

        # 자동화 시작 명령 대기
        # if bb.get("robot/start_auto"):
        #     return RobotEvent.PROGRAM_AUTO_ON_DONE
        return RobotEvent.NONE
    
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        # 상태를 나갈 때 진행 중이던 수동 명령이 있다면 정리
        if self.manual_cmd_state != "idle":
            Logger.warn(f"[Robot] Exiting ReadyStrategy while manual command '{self.manual_cmd_name}' was in progress.")
            bb.set("int_var/cmd/val", 0)
            bb.set("indy_command/reset_init_var", True)
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")

# ----------------------------------------------------
# 2. 로봇 작업 특화 전략
# ----------------------------------------------------

class RobotProgramAutoOnStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Turning on Auto Mode.")
    def operate(self, context: RobotContext) -> RobotEvent:
        # TODO Conty프로그램 run 명령 전달
        # bb.set("robot/program/run",1)
        return RobotEvent.PROGRAM_AUTO_ON_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")

class RobotProgramManualOffStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Turning off Auto Mode (Manual).")
    def operate(self, context: RobotContext) -> RobotEvent:
        return RobotEvent.PROGRAM_MANUAL_OFF_DONE
    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")

class RobotWaitAutoCommandStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Robot] Waiting for auto process start command.")

    def operate(self, context: RobotContext) -> RobotEvent:
        if context.check_violation():
            return RobotEvent.VIOLATION_DETECT

        robot_cmd_key = "process/auto/robot/cmd"
        robot_cmd : dict = bb.get(robot_cmd_key)
        if robot_cmd :
            # LogicContext에서 발행한 모든 모션 명령을 감지하여 범용 모션 실행 이벤트 발생
            return RobotEvent.DO_MOTION
        else :
            return RobotEvent.NONE

    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")


class RobotExecuteMotionStrategy(Strategy):
    def prepare(self, context: RobotContext, **kwargs):
        bb.set("robot/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        self.cmd_id = None
        self.motion_name = None
        self.start_time = time.time()
        self.timeout = 60.0  # 각 모션에 대한 타임아웃 (60초)

        robot_cmd_key = "process/auto/robot/cmd"
        robot_cmd = bb.get(robot_cmd_key)

        if not robot_cmd:
            Logger.error("RobotExecuteMotionStrategy: Blackboard에서 명령을 찾을 수 없습니다.")
            self.cmd_id = -1  # 잘못된 명령
            return

        self.motion_name = robot_cmd.get("process")
        floor = robot_cmd.get("target_floor")
        num = robot_cmd.get("target_num")
        pos = robot_cmd.get("position")

        # 문자열 모션 이름을 정수 CMD ID로 변환
        self.cmd_id = context.get_motion_cmd(self.motion_name, floor=floor, num=num, pos=pos)

        if self.cmd_id:
            # 충돌 방지를 위해 이동이 안전한지 확인
            if not context.is_safe_to_move(self.cmd_id):
                Logger.error(f"[Robot] Safety violation: Move from {bb.get('robot/current/position')} to {self.cmd_id} is not allowed.")
                # 안전하지 않은 이동이므로 실패 처리
                self.cmd_id = -1
                return

            Logger.info(f"[Robot] '{self.motion_name}' 모션 실행 (CMD ID: {self.cmd_id})")
            # CMD_ack와 CMD_done 초기화 요청
            bb.set("indy_command/reset_init_var", True)
            time.sleep(0.1)  # 초기화가 처리될 시간 확보
            # 모션 명령 설정
            context.robot_motion_control(self.cmd_id)
        else:
            Logger.error(f"[Robot] 알 수 없는 모션 명령 '{self.motion_name}'")
            self.cmd_id = -1

    def operate(self, context: RobotContext) -> RobotEvent:
        if self.cmd_id is None or self.cmd_id == -1:
            return RobotEvent.MOTION_FAIL

        if context.check_violation():
            context.stop_motion()
            return RobotEvent.VIOLATION_DETECT

        # 타임아웃 확인
        if time.time() - self.start_time > self.timeout:
            Logger.error(f"[Robot] '{self.motion_name}' 모션 (CMD: {self.cmd_id}) 시간 초과.")
            context.stop_motion()
            return RobotEvent.MOTION_FAIL

        # 모션 완료 확인 (CMD_done 값)
        motion_done_val_str = bb.get("int_var/motion_done/val")
        motion_done_val = None
        if motion_done_val_str is not None:
            motion_done_val = int(motion_done_val_str)
        expected_done_val = self.cmd_id + 10000

        if motion_done_val == expected_done_val:
            Logger.info(f"[Robot] '{self.motion_name}' 모션 (CMD: {self.cmd_id}) 완료.")
            return RobotEvent.MOTION_DONE

        return RobotEvent.NONE

    def exit(self, context: RobotContext, event: RobotEvent) -> None:
        Logger.info(f"[Robot] exit {self.__class__.__name__} with event: {event}")
        # Blackboard 정리
        robot_cmd_key = "process/auto/robot/cmd"
        current_cmd = bb.get(robot_cmd_key)
        if current_cmd:
            if event == RobotEvent.MOTION_DONE:
                current_cmd["state"] = "done"
            else:
                current_cmd["state"] = "error"
            # Logic FSM이 명령을 소비할 수 있도록 bb에 다시 씀
            bb.set(robot_cmd_key, current_cmd)

        # 다음 모션을 위해 명령 변수 초기화
        context.robot_motion_control(0)  # CMD를 0으로 설정
        bb.set("indy_command/reset_init_var", True)  # ACK/DONE 초기화