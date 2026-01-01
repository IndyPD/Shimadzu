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

        # 자동화 시작 명령 감지 (LogicFSM과 동일한 트리거 사용)
        if bb.get("ui/cmd/auto/tensile") == 1:
            Logger.info("[Robot] Automation start command detected. Transitioning to PROGRAM_AUTO_ON.")
            return RobotEvent.DO_AUTO_MOTION_PROGRAM_AUTO_ON
            
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
        # 시작 명령을 한 번만 보내기 위한 플래그를 초기화합니다.
        self.is_start_cmd_sent = False

    def operate(self, context: RobotContext) -> RobotEvent:
        # 1. 로봇 프로그램이 이미 실행 중인지 확인합니다.
        if context.check_program_running():
            Logger.info("[Robot] Program is running. Auto mode on is complete.")
            return RobotEvent.PROGRAM_AUTO_ON_DONE

        # 2. 프로그램이 실행 중이 아니고, 시작 명령을 아직 보내지 않았다면 보냅니다.
        if not self.is_start_cmd_sent:
            Logger.info("[Robot] Program is not running. Sending start command.")
            bb.set("indy_command/play_program", True)
            self.is_start_cmd_sent = True
        
        # 3. 시작 명령을 보냈으므로, 프로그램이 실행될 때까지 대기합니다 (다음 FSM 사이클에서 다시 확인).
        return RobotEvent.NONE

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
            # A new command should not have a 'done' or 'error' state.
            # If it does, it's a result meant for LogicFSM, so we ignore it
            # to prevent re-executing a completed command.
            if robot_cmd.get("state") in ["done", "error"]:
                return RobotEvent.NONE

            # Logic FSM이 발행한 명령을 감지합니다.
            # Race Condition을 방지하기 위해, 명령을 컨텍스트에 저장하고 블랙보드에서 즉시 제거(소비)합니다.
            context.current_motion_command = robot_cmd
            bb.set(robot_cmd_key, None)
            Logger.info(f"[Robot] Command received and consumed: {robot_cmd.get('process')}")
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

        # 블랙보드에서 직접 읽는 대신, 컨텍스트에 저장된 명령을 사용합니다.
        robot_cmd = context.current_motion_command
        Logger.info(f"[Robot] Motion Excute Step 1 - robot_cmd : {robot_cmd}")

        if not robot_cmd:
            Logger.error("RobotExecuteMotionStrategy: Context에서 명령을 찾을 수 없습니다.")
            self.cmd_id = -1  # 잘못된 명령

            return

        self.motion_name = robot_cmd.get("process")
        floor = robot_cmd.get("target_floor")
        num = robot_cmd.get("target_num")
        pos = robot_cmd.get("position")
        Logger.info(f"[Robot] Motion Excute Step 2 - motion_name : {self.motion_name}")
        Logger.info(f"[Robot] Motion Excute Step 2 - floor : {floor}")
        Logger.info(f"[Robot] Motion Excute Step 2 - num : {num}")
        Logger.info(f"[Robot] Motion Excute Step 2 - pos : {pos}")

        # 문자열 모션 이름을 정수 CMD ID로 변환
        self.cmd_id = context.get_motion_cmd(self.motion_name, floor=floor, num=num, pos=pos)

        Logger.info(f"[Robot] Motion Excute Step 3 - cmd_id : {self.cmd_id}")

        if self.cmd_id:
            # 충돌 방지를 위해 이동이 안전한지 확인
            # if not context.is_safe_to_move(self.cmd_id):
            #     Logger.error(f"[Robot] Safety violation: Move from {bb.get('robot/current/position')} to {self.cmd_id} is not allowed.")
            #     # 안전하지 않은 이동이므로 실패 처리
            #     self.cmd_id = -1
            #     return

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
        # Logic FSM이 결과를 확인할 수 있도록, 컨텍스트에 저장된 명령의 상태를 업데이트하여 블랙보드에 다시 씁니다.
        current_cmd = context.current_motion_command
        if current_cmd:
            if event == RobotEvent.MOTION_DONE:
                current_cmd["state"] = "done"
            else:
                current_cmd["state"] = "error"
            robot_cmd_key = "process/auto/robot/cmd"
            # Check if a new command has been posted by LogicFSM. If so, don't overwrite it.
            # A new command will have its "state" as "" (empty string).
            existing_cmd = bb.get(robot_cmd_key)
            if existing_cmd is None or existing_cmd.get("state") in ["done", "error"]:
                bb.set(robot_cmd_key, current_cmd)
                Logger.info(f"[Robot] Wrote command result to blackboard: {current_cmd}")
            else:
                Logger.warn(f"[Robot] A new command is on the blackboard. Not overwriting with result of '{current_cmd.get('process')}'.")
                Logger.warn(f"[Robot] Existing command: {existing_cmd}")
            

        # 다음 모션을 위해 명령 변수 초기화
        context.robot_motion_control(0)  # CMD를 0으로 설정
        bb.set("indy_command/reset_init_var", True)  # ACK/DONE 초기화
        time.sleep(2)
