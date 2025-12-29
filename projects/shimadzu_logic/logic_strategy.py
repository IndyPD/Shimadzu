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

        # 2. DB에서 공정 계획 로드 및 실행 테이블 기입
        # get_batch_data 내부에서 데이터 가공 및 Blackboard(bb) 저장이 자동으로 수행됩니다.
        batch_info = context.db.get_batch_data()
        if batch_info is not None:
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
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")

            # MQTT 'process_stopped' 이벤트 발행
            batch_id = bb.get("process/auto/batch_data").get("batch_id", "N/A")
            event_payload = {
                "evt": "process_stopped",
                "reason": "The process was successfully stopped by user command.",
                "data": {"batch_id": batch_id}
            }
            bb.set("logic/events/one_shot", event_payload)

            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP
        # 현재 시편 완료 후 정지 (Step Stop)
        elif tensile_cmd == 4:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STEP_STOP command. Will stop after current specimen completes.")
            # 시편 완료 후 정지를 위해 플래그 설정
            bb.set("process/auto/step_stop_requested", True)

        batch_data = bb.get("process/auto/batch_data")
        if not batch_data or 'processData' not in batch_data:
            Logger.error("[Logic] DetermineTask: Batch data is invalid or not found.")
            return LogicEvent.VIOLATION_DETECT

        # 1. 현재 진행 중인 시편 찾기 (RUNNING: 2)
        current_specimen = next((s for s in batch_data['processData'] if s.get('seq_status') == 2), None)
        
        # 2. 진행 중인 시편이 없으면 다음 READY(1) 시편 시작
        if not current_specimen:
            Logger.info("[Logic] DetermineTask: No running sequence found, searching for the next ready one.")
            current_specimen = next((s for s in batch_data['processData'] if s.get('seq_status') == 1), None)
            if not current_specimen:
                # 모든 시편 완료
                Logger.info("[Logic] DetermineTask: No more ready sequences found. Process is complete.")
                return LogicEvent.DO_PROCESS_COMPLETE
            
            # 새 시편 시작: 상태 업데이트
            current_specimen['seq_status'] = 2 # RUNNING
            bb.set("process/auto/current_specimen_no", 1) # 시편 번호 1번부터 시작
            bb.set("process/auto/batch_data", batch_data)
            
            # DB 업데이트 (Tray RUNNING, Specimen 1 RUNNING)
            Logger.info(f"[Logic] DetermineTask: Updating sequence {current_specimen['seq_order']} status to RUNNING (2) in DB.")
            context.db.update_processing_status(current_specimen['seq_order'], 2)
            context.db.insert_summary_log(batch_id=batch_data['batch_id'], tray_no=current_specimen['tray_no'], specimen_no=1, work_history="START")

            # test_tray_items 상태 업데이트
            Logger.info(f"[Logic] DetermineTask: Initializing all specimens in tray {current_specimen['tray_no']} to 'WAITING' (1) in DB.")
            tray_no = current_specimen['tray_no']
            test_spec = current_specimen['test_method']
            # 해당 트레이의 모든 시편을 '대기' 상태로 설정
            for i in range(1, 6):
                context.db.update_test_tray_item(tray_no, i, {'status': 1, 'test_spec': test_spec})
            # 첫 번째 시편만 '진행중' 상태로 변경
            context.db.update_test_tray_item(tray_no, 1, {'status': 2})
            Logger.info(f"[Logic] DetermineTask: Setting specimen 1 in tray {tray_no} to 'RUNNING' (2) in DB.")
            
            # 작업 정보 설정
            bb.set("process/auto/target_floor", current_specimen['tray_no'])
            bb.set("process/auto/target_num", 1) # Robot에게 1번 시편 위치 지시
            bb.set("process/auto/sequence", current_specimen['seq_order'])
            
            # 첫 번째 단계 시작 (Command.md 1번: QR 인식)
            bb.set("process/auto/current_step", 1)
            Logger.info(f"[Logic] DetermineTask: Starting sequence {current_specimen['seq_order']} (Tray: {current_specimen['tray_no']}). First step is DO_MOVE_TO_RACK_FOR_QR.")
            return LogicEvent.DO_MOVE_TO_RACK_FOR_QR

        # 3. 진행 중인 시편의 다음 단계 결정 (Command.md 흐름 준수)
        step = bb.get("process/auto/current_step")
        Logger.info(f"[Logic] DetermineTask: Current sequence {current_specimen['seq_order']} is at step {step}.")
        
        if step == 1: # QR 인식 완료 -> 시편 가져오기 (2번)
            Logger.info("[Logic] DetermineTask: Step 1 (QR Read) is done. Moving to Step 2 (Pick Specimen).")
            bb.set("process/auto/current_step", 2)
            return LogicEvent.DO_PICK_SPECIMEN
        elif step == 2: # 시편 가져오기 완료 -> 측정기 이동 (3번)
            Logger.info("[Logic] DetermineTask: Step 2 (Pick Specimen) is done. Moving to Step 3 (Move to Indicator).")
            bb.set("process/auto/current_step", 3)
            return LogicEvent.DO_MOVE_TO_INDIGATOR
        elif step == 3: # 측정기 이동 완료 -> 시편 거치 및 측정 (4번)
            Logger.info("[Logic] DetermineTask: Step 3 (Move to Indicator) is done. Moving to Step 4 (Place and Measure).")
            bb.set("process/auto/current_step", 4)
            return LogicEvent.DO_PLACE_SPECIMEN_AND_MEASURE
        elif step == 4: # 측정 완료 -> 측정기 시편 반출 (5번)
            Logger.info("[Logic] DetermineTask: Step 4 (Place and Measure) is done. Updating dimension and moving to Step 5 (Pick from Indicator).")
            # 측정된 두께를 test_tray_items에 업데이트
            tray_no = current_specimen['tray_no']
            specimen_no = bb.get("process/auto/current_specimen_no")
            thickness_map = bb.get("process/auto/thickness") or {}
            
            dimension = thickness_map.get(str(specimen_no))
            if dimension is not None:
                Logger.info(f"[Logic] DetermineTask: Updating dimension for Tray {tray_no}, Specimen {specimen_no} to {dimension}.")
                context.db.update_test_tray_item(tray_no, specimen_no, {'dimension': float(dimension)})
            else:
                Logger.warn(f"[Logic] DetermineTask: No dimension data found for specimen {specimen_no} to update.")

            bb.set("process/auto/current_step", 5)
            return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_INDIGATOR
        elif step == 5: # 반출 완료 -> 시편 정렬 (6번)
            Logger.info("[Logic] DetermineTask: Step 5 (Pick from Indicator) is done. Moving to Step 6 (Align Specimen).")
            bb.set("process/auto/current_step", 6)
            return LogicEvent.DO_ALIGN_SPECIMEN
        elif step == 6: # 정렬 완료
            Logger.info("[Logic] DetermineTask: Step 6 (Align Specimen) is done.")
            # 만약 다음 시편을 미리 준비 중이었다면, 여기서 멈추고 이전 시편 수거를 위해 스위칭
            if bb.get("process/auto/pre_preparing"):
                prev_spec_no = bb.get("process/auto/current_specimen_no") - 1
                bb.set("process/auto/waiting_at_aligner", True)
                
                # 이전 시편으로 컨텍스트 전환 (수거 단계 11번으로)
                bb.set("process/auto/current_specimen_no", prev_spec_no)
                bb.set("process/auto/target_num", prev_spec_no)
                bb.set("process/auto/current_step", 11)
                
                Logger.info(f"[Logic] DetermineTask: Specimen {prev_spec_no+1} pre-prepared. Switching back to collect Specimen {prev_spec_no} at step 11.")
                return LogicEvent.DO_PICK_TENSILE_MACHINE
            
            Logger.info("[Logic] DetermineTask: Moving to Step 7 (Pick from Aligner).")
            bb.set("process/auto/current_step", 7)
            return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_ALIGN
        elif step == 7: # 반출 완료 -> 인장기 장착 (8번)
            Logger.info("[Logic] DetermineTask: Step 7 (Pick from Aligner) is done. Moving to Step 8 (Load Tensile Machine).")
            bb.set("process/auto/current_step", 8)
            return LogicEvent.DO_LOAD_TENSILE_MACHINE
        elif step == 8: # 장착 완료 -> 인장기 후퇴 (9번)
            Logger.info("[Logic] DetermineTask: Step 8 (Load Tensile Machine) is done. Moving to Step 9 (Retreat Tensile Machine).")
            bb.set("process/auto/current_step", 9)
            return LogicEvent.DO_RETREAT_TENSILE_MACHINE
        elif step == 9: # 후퇴 완료 -> 인장 시험 시작 (10번)
            Logger.info("[Logic] DetermineTask: Step 9 (Retreat Tensile Machine) is done. Moving to Step 10 (Start Tensile Test).")
            bb.set("process/auto/current_step", 10)
            return LogicEvent.DO_START_TENSILE_TEST
        elif step == 10: # 인장 시험 시작 명령 전송 완료
            Logger.info("[Logic] DetermineTask: Step 10 (Start Tensile Test) command sent.")
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
                # `batch_test_items`는 트레이(시퀀스) 단위로 상태를 관리하므로, 개별 시편 상태는 DB에 업데이트하지 않음.
                Logger.info(f"[Logic] DetermineTask: Pipelining - Pre-preparing Specimen {next_spec_no} while {curr_spec_no} is testing. Moving to Step 1 (QR Read).")
                return LogicEvent.DO_MOVE_TO_RACK_FOR_QR
            else:
                # 마지막 시편인 경우 준비할 것이 없으므로 바로 수거 단계로 진행
                Logger.info(f"[Logic] DetermineTask: Last specimen in tray is testing. No pipelining. Moving to Step 11 (Pick from Tensile Machine).")
                bb.set("process/auto/current_step", 11)
                return LogicEvent.DO_PICK_TENSILE_MACHINE
        elif step == 11: # 수거 완료 -> 후퇴 및 스크랩 처리 (12번)
            Logger.info("[Logic] DetermineTask: Step 11 (Pick from Tensile Machine) is done. Moving to Step 12 (Retreat and Handle Scrap).")
            bb.set("process/auto/current_step", 12)
            return LogicEvent.DO_RETREAT_AND_HANDLE_SCRAP
        elif step == 12: # 스크랩 처리 완료
            Logger.info("[Logic] DetermineTask: Step 12 (Retreat and Handle Scrap) is done. Current specimen cycle finished.")
            # 만약 정렬기에서 대기 중인 다음 시편이 있다면 해당 시편으로 복귀
            if bb.get("process/auto/waiting_at_aligner"):
                next_spec_no = bb.get("process/auto/current_specimen_no") + 1
                bb.set("process/auto/waiting_at_aligner", False)
                bb.set("process/auto/pre_preparing", False)
                
                bb.set("process/auto/current_specimen_no", next_spec_no)
                bb.set("process/auto/target_num", next_spec_no)
                bb.set("process/auto/current_step", 7) # 정렬기 반출(7번)부터 재개
                
                Logger.info(f"[Logic] DetermineTask: Collection done. Resuming Specimen {next_spec_no} from aligner at step 7.")
                return LogicEvent.DO_PICK_SPECIMEN_OUT_FROM_ALIGN

            spec_no = bb.get("process/auto/current_specimen_no")

            # Step Stop 요청이 있었는지 확인
            if bb.get("process/auto/step_stop_requested"):
                bb.set("process/auto/step_stop_requested", False) # 플래그 소비
                Logger.info("[Logic] Step Stop executed. Transitioning to WAIT_COMMAND.")

                # MQTT 'process_step_stopped' 이벤트 발행
                batch_id = bb.get("process/auto/batch_data").get("batch_id", "N/A")
                event_payload = {
                    "evt": "process_step_stopped",
                    "reason": "The process was successfully stopped after completing the current specimen.",
                    "data": {"batch_id": batch_id, "last_completed_specimen": spec_no}
                }
                bb.set("logic/events/one_shot", event_payload)

                context.process_complete() # 공정 완료 처리 호출
                return LogicEvent.PROCESS_STOP # 정지 이벤트 발생
            
            # 현재 시편 완료 기록 (3.2, 3.3)
            tray_no = current_specimen['tray_no']
            context.db.insert_summary_log(batch_id=batch_data['batch_id'], tray_no=current_specimen['tray_no'], specimen_no=spec_no, work_history="DONE")
            # test_tray_items 상태 '완료'로 업데이트
            context.db.update_test_tray_item(tray_no, spec_no, {'status': 3})
            Logger.info(f"[Logic] DetermineTask: Specimen {spec_no} in Tray {tray_no} is marked as DONE in DB.")
            
            if spec_no < 5:
                # 다음 시편으로 루프 (동일 트레이)
                next_spec_no = spec_no + 1
                bb.set("process/auto/current_specimen_no", next_spec_no)
                bb.set("process/auto/target_num", next_spec_no)
                bb.set("process/auto/current_step", 1)
                # `batch_test_items`는 트레이(시퀀스) 단위로 상태를 관리하므로, 개별 시편 상태는 DB에 업데이트하지 않음.
                context.db.insert_summary_log(batch_id=batch_data['batch_id'], tray_no=current_specimen['tray_no'], specimen_no=next_spec_no, work_history="START")
                # test_tray_items 상태 '진행중'으로 업데이트
                context.db.update_test_tray_item(tray_no, next_spec_no, {'status': 2})
                Logger.info(f"[Logic] DetermineTask: Moving to next specimen {next_spec_no} in same tray. Starting from Step 1 (QR Read).")
                return LogicEvent.DO_MOVE_TO_RACK_FOR_QR
            else:
                # 트레이 내 모든 시편 완료 -> 다음 트레이 탐색
                current_specimen['seq_status'] = 3 # DONE
                bb.set("process/auto/batch_data", batch_data)
                context.db.update_processing_status(current_specimen['seq_order'], 3) # 트레이 상태를 완료로 DB 업데이트
                bb.set("process/auto/current_step", 0)
                Logger.info(f"[Logic] DetermineTask: All specimens in Tray {current_specimen['tray_no']} are complete. Finding next tray.")
                return self.operate(context) # 재귀 호출로 다음 트레이 탐색

        Logger.error(f"[Logic] DetermineTask: Reached an unknown step ({step}). This should not happen.")
        return LogicEvent.VIOLATION_DETECT

    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicMoveToRackForQRReadStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Moving to rack for QR read.")
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        return context.pick_specimen(floor, num)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicMoveToIndigatorStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Moving to indigator.")
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        return context.move_to_indigator(floor, num)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPlaceSpecimenAndMeasureStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Placing specimen and measuring.")
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

        return context.start_tensile_test()
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicPickTensileMachineStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] Picking from tensile machine.")
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

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
        context._seq = 0
    def operate(self, context: LogicContext) -> LogicEvent:
        tensile_cmd = bb.get("ui/cmd/auto/tensile")
        # 즉시 정지 (Stop)
        if tensile_cmd == 3:
            bb.set("ui/cmd/auto/tensile", 0) # 명령 소비
            Logger.info("[Logic] Received STOP command. Stopping current motion and returning to WAIT_COMMAND.")
            # 진행 중인 로봇/장비 명령 취소
            bb.set("process/auto/robot/cmd", None)
            bb.set("process/auto/device/cmd", None)
            bb.set("indy_command/stop_program", True) # 로봇 프로그램 정지
            return LogicEvent.PROCESS_STOP

        floor = bb.get("process/auto/target_floor")
        num = bb.get("process/auto/target_num")
        seq = bb.get("process/auto/sequence")
        return context.retreat_and_handle_scrap(floor, num, seq)
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")

class LogicProcessCompleteStrategy(Strategy):
    def prepare(self, context: LogicContext, **kwargs):
        bb.set("logic/fsm/strategy", {"state": context.state.name, "strategy": self.__class__.__name__})
        Logger.info("[Logic] All batch processes are complete.")
        context._seq = 0

        # MQTT 'process_completed' 이벤트 발행
        batch_data = bb.get("process/auto/batch_data")
        batch_id = batch_data.get("batch_id", "N/A")
        total_completed = batch_data.get("procedure_num", 0)
        event_payload = {
            "kind": "event",
            "evt": "process_completed",
            "reason": "All processes for the batch have been successfully completed.",
            "data": {"batch_id": batch_id, "total_completed": total_completed}
        }
        bb.set("logic/events/one_shot", event_payload)
    
    def operate(self, context: LogicContext) -> LogicEvent:
        return LogicEvent.DONE
    
    def exit(self, context: LogicContext, event: LogicEvent) -> None:
        Logger.info(f"[Logic] exit {self.__class__.__name__} with event: {event}")