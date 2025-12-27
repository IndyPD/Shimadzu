import time

from pkg.utils.blackboard import GlobalBlackboard
from .logic_context import *

bb = GlobalBlackboard()

# ----------------------------------------------------
# 1. 범용 FSM 전략
# ----------------------------------------------------

class LogicConnectingStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Starting connection checks for all modules (Device & Robot).")
        # devices_context.py에서 dev_smz_enable이 False로 하드코딩되어 있으므로, 여기서도 동일하게 설정합니다.
        self.dev_smz_enable = False

    def operate(self, context: LogicContext) -> LogicEvent:
        # 각 모듈의 통신 상태를 블랙보드에서 확인합니다.
        # 이 값들은 각 장치 제어 스레드(indy_control, devices_context)에서 주기적으로 업데이트합니다.
        robot_ok = int(bb.get("device/robot/comm_status") or 0) == 1
        remote_io_ok = int(bb.get("device/remote/comm_status") or 0) == 1
        gauge_ok = int(bb.get("device/gauge/comm_status") or 0) == 1
        qr_ok = int(bb.get("device/qr/comm_status") or 0) == 1
        
        # Shimadzu 장비는 현재 비활성화 상태이므로, 연결 체크를 건너뜁니다.
        shimadzu_ok = True if not self.dev_smz_enable else int(bb.get("device/shimadzu/comm_status") or 0) == 1

        all_connected = all([robot_ok, remote_io_ok, gauge_ok, qr_ok, shimadzu_ok])

        if all_connected:
            context.status.is_connected_all.up()
            Logger.info("[Logic] All modules connected successfully.")
            return LogicEvent.CONNECTION_ALL_SUCCESS
        
        # 어떤 모듈의 연결이 실패했는지 상세 로그를 남깁니다.
        status_report = (
            f"[Robot] {'OK' if robot_ok else 'FAIL'}, "
            f"RemoteIO: {'OK' if remote_io_ok else 'FAIL'}, "
            f"Gauge: {'OK' if gauge_ok else 'FAIL'}, "
            f"QR: {'OK' if qr_ok else 'FAIL'}"
        )
        if self.dev_smz_enable:
            status_report += f", Shimadzu: {'OK' if shimadzu_ok else 'FAIL'}"

        Logger.info(f"[Logic] Waiting for all modules to connect... Status: [{status_report}]")
        return LogicEvent.NONE

    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicErrorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        violation_names = [v.name for v in LogicViolation if v & context.violation_code]
        Logger.error(f"Logic Critical Violation Detected: {'|'.join(violation_names)}", popup=True)
        # TODO: 모든 서브 모듈에 정지/에러 명령 전파
    def operate(self, context: LogicContext) -> LogicEvent:
        # 오류 발생 시 외부 명령 없이 자동으로 복구 상태로 전환합니다.
        return LogicEvent.RECOVER
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicRecoveringStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Coordinating full system recovery.")
        # TODO: Device FSM과 Robot FSM에 복구 명령을 순차적으로 전송
    def operate(self, context: LogicContext) -> LogicEvent:
        # if sub_module_recovery_complete:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")
        # return LogicEvent.NONE

class LogicStopOffStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Emergency Stop - Coordinating full system shutdown.")
        # TODO: 모든 서브 모듈에 Stop/Off 명령 전파
    def operate(self, context: LogicContext) -> LogicEvent:
        # if shutdown_complete:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")
        # return LogicEvent.NONE

class LogicIdleStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] System Idle and waiting for batch start command.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        if context.check_violation():
            return LogicEvent.VIOLATION_DETECT
            
        # 자동화 모드 진입 명령 대기
        if bb.get("ui/cmd/auto/tensile") == 1: # ACTION_MAP_TENSIL["start"]
            return LogicEvent.START_AUTO_COMMAND

        # 데이터 저장 명령 (UI -> Logic)
        if bb.get("ui/cmd/data/save") == 1:
            bb.set("ui/cmd/data/save", 0)
            Logger.info("[Logic] Received data save command from UI.")
            return LogicEvent.DO_REGISTER_INFO

        # 데이터 리셋 명령 (UI -> Logic)
        if bb.get("ui/cmd/data/reset") == 1:
            bb.set("ui/cmd/data/reset", 0)
            Logger.info("[Logic] Received data reset command from UI.")
            return LogicEvent.DO_DATA_RESET
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

# ----------------------------------------------------
# 2. Logic 배치 시퀀스 전략
# ----------------------------------------------------

class LogicWaitCommandStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Waiting for batch start command.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        if bb.get("ui/cmd/auto/tensile") == 1:
            return LogicEvent.START_AUTO_COMMAND
        return LogicEvent.NONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicRegisterProcessInfoStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Registering process info.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # 1. 기존 실행 데이터 초기화 (10개 슬롯 생성 및 ID 리셋)
        context.db.clear_batch_test_items()
        context.db.clear_test_tray_items()

        # 2. DB에서 공정 계획 로드 및 실행 테이블 기입
        # get_batch_data 내부에서 데이터 가공 및 Blackboard(bb) 저장이 자동으로 수행됩니다.
        batch_info = context.db.get_batch_data()
        if batch_info:
            return LogicEvent.REGISTRATION_DONE
        
        Logger.error(f"[Logic] Failed to load batch data from DB.")
        return LogicEvent.VIOLATION_DETECT
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicResetDataStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Resetting batch data.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        context.db.clear_batch_test_items()
        context.db.clear_test_tray_items()
        Logger.info("[Logic] Batch data has been reset.")
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicCheckDeviceStatusStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Checking device status.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        # 장비 상태 확인 로직
        return LogicEvent.STATUS_CHECK_DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicWaitProcessStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Waiting for process start.")
        
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.PROCESS_START
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicRunProcessStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Running process loop.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        # 하위 FSM(Robot, Device)의 상태를 모니터링하며 전체 공정 시퀀스를 제어합니다.
        # 1. Robot FSM에게 동작 명령을 내리고 완료를 대기합니다.
        # 2. Device FSM에게 동작 명령을 내리고 완료를 대기합니다.
        
        # [예시 시퀀스 제어 로직]
        # if context.robot_fsm.get_state() == RobotState.WAIT_AUTO_COMMAND:
        #     # 다음 로봇 동작 명령 전달 (예: 시편 픽업)
        #     # context.robot_fsm.trigger(RobotEvent.DO_AUTO_MOTION_APPROACH_RACK)
        #     pass

        # TODO: 실제 시퀀스 제어 로직 구현 (Robot Move -> Device Measure -> Robot Move ...)
        # 현재는 시뮬레이션을 위해 공정 완료 이벤트를 즉시 반환합니다.
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicDetermineTaskStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Determining next task.")

    def operate(self, context: LogicContext) -> LogicEvent:
        batch_data = bb.get("process/auto/batch_data")
        if not batch_data or 'processData' not in batch_data:
            return LogicEvent.VIOLATION_DETECT

        # 1. 현재 진행 중인 시편 찾기 (RUNNING: 2)
        current_specimen = next((s for s in batch_data['processData'] if s.get('seq_status') == 2), None)
        
        # 2. 진행 중인 시편이 없으면 다음 READY(1) 시편 시작
        if not current_specimen:
            current_specimen = next((s for s in batch_data['processData'] if s.get('seq_status') == 1), None)
            if not current_specimen:
                # 모든 시편 완료
                return LogicEvent.DO_PROCESS_COMPLETE
            
            # 새 시편 시작: 상태 업데이트
            current_specimen['seq_status'] = 2 # RUNNING
            bb.set("process/auto/current_specimen_no", 1) # 시편 번호 1번부터 시작
            bb.set("process/auto/batch_data", batch_data)
            
            # DB 업데이트 (Tray RUNNING, Specimen 1 RUNNING)
            context.db.update_processing_status(batch_data['batch_id'], current_specimen['tray_no'], 1, 2)
            context.db.insert_summary_log(batch_data['batch_id'], current_specimen['tray_no'], 1, "START")
            
            # 작업 정보 설정
            bb.set("process/auto/target_floor", current_specimen['tray_no'])
            bb.set("process/auto/target_num", 1) # Robot에게 1번 시편 위치 지시
            bb.set("process/auto/sequence", current_specimen['seq_order'])
            
            # 첫 번째 단계 시작 (Command.md 1번: QR 인식)
            bb.set("process/auto/current_step", 1)
            Logger.info(f"[Logic] Starting Specimen {current_specimen['seq_order']} at Tray {current_specimen['tray_no']}")
            return LogicEvent.DO_MOVE_TO_RACK_FOR_QR

        # 3. 진행 중인 시편의 다음 단계 결정 (Command.md 흐름 준수)
        step = bb.get("process/auto/current_step")
        
        if step == 1: # QR 인식 완료 -> 시편 가져오기 (2번)
            bb.set("process/auto/current_step", 2)
            return LogicEvent.DO_PICK_SPECIMEN
        elif step == 2: # 시편 가져오기 완료 -> 측정기 이동 (3번)
            bb.set("process/auto/current_step", 3)
            return LogicEvent.DO_MOVE_TO_INDIGATOR
        elif step == 3: # 측정기 이동 완료 -> 시편 거치 및 측정 (4번)
            bb.set("process/auto/current_step", 4)
            return LogicEvent.DO_PLACE_SPECIMEN_AND_MEASURE
        elif step == 4: # 측정 완료 -> 측정기 시편 반출 (5번)
            bb.set("process/auto/current_step", 5)
            return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_INDIGATOR
        elif step == 5: # 반출 완료 -> 시편 정렬 (6번)
            bb.set("process/auto/current_step", 6)
            return LogicEvent.DO_ALIGN_SPECIMEN
        elif step == 6: # 정렬 완료
            # 만약 다음 시편을 미리 준비 중이었다면, 여기서 멈추고 이전 시편 수거를 위해 스위칭
            if bb.get("process/auto/pre_preparing"):
                prev_spec_no = bb.get("process/auto/current_specimen_no") - 1
                bb.set("process/auto/waiting_at_aligner", True)
                
                # 이전 시편으로 컨텍스트 전환 (수거 단계 11번으로)
                bb.set("process/auto/current_specimen_no", prev_spec_no)
                bb.set("process/auto/target_num", prev_spec_no)
                bb.set("process/auto/current_step", 11)
                
                Logger.info(f"[Logic] Specimen {prev_spec_no+1} pre-prepared. Switching back to collect Specimen {prev_spec_no}.")
                return LogicEvent.DO_PICK_TENSILE_MACHINE
            
            bb.set("process/auto/current_step", 7)
            return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_ALIGN
        elif step == 7: # 반출 완료 -> 인장기 장착 (8번)
            bb.set("process/auto/current_step", 8)
            return LogicEvent.DO_LOAD_TENSILE_MACHINE
        elif step == 8: # 장착 완료 -> 인장기 후퇴 (9번)
            bb.set("process/auto/current_step", 9)
            return LogicEvent.DO_RETREAT_TENSILE_MACHINE
        elif step == 9: # 후퇴 완료 -> 인장 시험 시작 (10번)
            bb.set("process/auto/current_step", 10)
            return LogicEvent.DO_START_TENSILE_TEST
        elif step == 10: # 인장 시험 시작 명령 전송 완료
            # 시험 대기 시간 동안 다음 시편을 미리 준비 (트레이 내 5개 루프)
            curr_spec_no = bb.get("process/auto/current_specimen_no") or 1
            
            if curr_spec_no < 5:
                # 동일 트레이의 다음 시편 준비 시작 (Pipelining)
                bb.set("process/auto/pre_preparing", True)
                
                next_spec_no = curr_spec_no + 1
                bb.set("process/auto/current_specimen_no", next_spec_no)
                bb.set("process/auto/target_num", next_spec_no)
                bb.set("process/auto/current_step", 1) # 1번(QR)부터 시작
                
                # DB 업데이트 (다음 시편 시작 상태)
                context.db.update_processing_status(batch_data['batch_id'], current_specimen['tray_no'], next_spec_no, 2)
                Logger.info(f"[Logic] Pipelining - Pre-preparing Specimen {next_spec_no} while {curr_spec_no} is testing.")
                return LogicEvent.DO_MOVE_TO_RACK_FOR_QR
            else:
                # 마지막 시편인 경우 준비할 것이 없으므로 바로 수거 단계로 진행
                bb.set("process/auto/current_step", 11)
                return LogicEvent.DO_PICK_TENSILE_MACHINE
        elif step == 11: # 수거 완료 -> 후퇴 및 스크랩 처리 (12번)
            bb.set("process/auto/current_step", 12)
            return LogicEvent.DO_RETREAT_AND_HANDLE_SCRAP
        elif step == 12: # 스크랩 처리 완료
            # 만약 정렬기에서 대기 중인 다음 시편이 있다면 해당 시편으로 복귀
            if bb.get("process/auto/waiting_at_aligner"):
                next_spec_no = bb.get("process/auto/current_specimen_no") + 1
                bb.set("process/auto/waiting_at_aligner", False)
                bb.set("process/auto/pre_preparing", False)
                
                bb.set("process/auto/current_specimen_no", next_spec_no)
                bb.set("process/auto/target_num", next_spec_no)
                bb.set("process/auto/current_step", 7) # 정렬기 반출(7번)부터 재개
                
                Logger.info(f"[Logic] Collection done. Resuming Specimen {next_spec_no} from aligner.")
                return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_ALIGN

            spec_no = bb.get("process/auto/current_specimen_no")
            
            # 현재 시편 완료 기록 (3.2, 3.3)
            context.db.update_processing_status(batch_data['batch_id'], current_specimen['tray_no'], spec_no, 3)
            context.db.insert_summary_log(batch_data['batch_id'], current_specimen['tray_no'], spec_no, "DONE")
            
            if spec_no < 5:
                # 다음 시편으로 루프 (동일 트레이)
                next_spec_no = spec_no + 1
                bb.set("process/auto/current_specimen_no", next_spec_no)
                bb.set("process/auto/target_num", next_spec_no)
                bb.set("process/auto/current_step", 1)
                context.db.update_processing_status(batch_data['batch_id'], current_specimen['tray_no'], next_spec_no, 2)
                Logger.info(f"[Logic] Moving to next specimen {next_spec_no} in Tray {current_specimen['tray_no']}")
                return LogicEvent.DO_MOVE_TO_RACK_FOR_QR
            else:
                # 트레이 내 모든 시편 완료 -> 다음 트레이 탐색
                current_specimen['seq_status'] = 3 # DONE
                bb.set("process/auto/batch_data", batch_data)
                bb.set("process/auto/current_step", 0)
                Logger.info(f"[Logic] Completed all specimens in Tray {current_specimen['tray_no']}")
                return self.operate(context) # 재귀 호출로 다음 트레이 탐색

        return LogicEvent.VIOLATION_DETECT

    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicMoveToRackForQRReadStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Moving to rack for QR read.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.move_to_rack_for_QRRead(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPickSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Picking specimen.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        return context.pick_specimen(floor, num)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicMoveToIndigatorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Moving to indigator.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        return context.move_to_indigator(floor, num)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPlaceSpecimenAndMeasureStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Placing specimen and measuring.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.place_specimen_and_measure(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPickSpecimenOutFromIndigatorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Picking specimen out from indigator.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.Pick_specimen_out_from_indigator(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicAlignSpecimenStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Aligning specimen.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.align_specimen(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPickSpecimenOutFromAlignStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Picking specimen out from aligner.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.Pick_specimen_out_from_align(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicLoadTensileMachineStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Loading tensile machine.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.load_tensile_machine(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicRetreatTensileMachineStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Retreating from tensile machine.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.retreat_tensile_machine(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicStartTensileTestStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Starting tensile test.")
    def operate(self, context: LogicContext) -> LogicEvent:
        return context.start_tensile_test()
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPickTensileMachineStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Picking from tensile machine.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.pick_tensile_machine(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicRetreatAndHandleScrapStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Retreating and handling scrap.")
    def operate(self, context: LogicContext) -> LogicEvent:
        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.retreat_and_handle_scrap(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicProcessCompleteStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Process complete.")
    
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")