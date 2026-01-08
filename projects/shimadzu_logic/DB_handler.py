import pymysql
from contextlib import contextmanager
import logging
import threading
import time
import sys
import os

try:
    from pkg.utils.blackboard import GlobalBlackboard
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    from pkg.utils.blackboard import GlobalBlackboard

from datetime import datetime

logger = logging.getLogger(__name__)
bb = GlobalBlackboard()

class DBHandler:
    """
    데이터베이스 연결 및 쿼리를 관리하는 클래스입니다.
    실시간 상태 정보(I/O, 트레이, 설비 상태) 관련 테이블이 제거됨에 따라,
    해당 테이블에 접근하던 메서드들이 삭제되었습니다.
    이제 이 클래스는 배치 정보, 레시피, 이력 로그 등 영구 데이터만 처리합니다.
    """
    def __init__(self, host, user, password, db_name, enable_monitor=True):
        self.host = host
        self.user = user
        self.password = password
        self.db_name = db_name
        self.conn = None
        self.enable_monitor = enable_monitor

        # UI 명령 처리를 위한 스레드 시작
        self.running = True
        self.command_thread = None
        if self.enable_monitor:
            self.command_thread = threading.Thread(target=self._thread_command_monitor, daemon=True)
            self.command_thread.start()

    def connect(self):
        """데이터베이스에 연결합니다."""
        try:
            self.conn = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                db=self.db_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info("Successfully connected to the database.")
            return True
        except pymysql.MySQLError as e:
            logger.error(f"Error connecting to MySQL Database: {e}")
            self.conn = None
            return False

    def disconnect(self):
        """데이터베이스 연결을 닫습니다."""
        self.running = False
        if self.command_thread and self.command_thread.is_alive():
            self.command_thread.join(timeout=1)
            logger.info("DB command monitor thread stopped.")

        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Database connection closed.")

    def _thread_command_monitor(self):
        """
        Blackboard를 감시하여 UI로부터의 데이터 저장/리셋 명령을 처리합니다.
        """
        while self.running:
            try:
                # 데이터 저장 명령 처리 (UI -> Logic -> BB)
                if bb.get("ui/cmd/data/save") == 1:
                    logger.info("[DBHandler] Received data save command. Loading batch plan.")
                    self.load_batch_plan_from_ui()
                    bb.set("ui/cmd/data/save", 0) # 명령 처리 후 플래그 리셋

                # 데이터 리셋 명령 처리 (UI -> Logic -> BB)
                if bb.get("ui/cmd/data/reset") == 1:
                    logger.info("[DBHandler] Received data reset command. Resetting batch data.")
                    self.reset_batch_test_items_data()
                    self.reset_batch_plan_items_data()
                    # 리셋 후 Blackboard의 관련 값들도 초기화
                    bb.set("process/auto/target_floor", 0)
                    bb.set("process/auto/current_tray_no", 0)
                    bb.set("process/auto/current_specimen_no", 0)
                    bb.set("process_status/runtime", 0)
                    bb.set("process_status/system_status", "대기중")
                    bb.set("ui/cmd/data/reset", 0) # 명령 처리 후 플래그 리셋

            except Exception as e:
                # 로거가 초기화되기 전에 에러가 발생할 수 있으므로 print도 사용
                print(f"[DBHandler] Error in _thread_command_monitor: {e}")
                logger.error(f"[DBHandler] Error in _thread_command_monitor: {e}")
            
            time.sleep(0.2) # 0.2초 주기로 확인
        
        logger.info("[DBHandler] Command monitor thread is stopping.")

    @contextmanager
    def cursor(self):
        """커서 컨텍스트 매니저를 제공합니다."""
        if not self.conn or not self.conn.open:
            logger.warning("DB connection not available. Attempting to reconnect.")
            self.connect()
        
        if not self.conn:
            raise ConnectionError("Database connection failed.")

        try:
            with self.conn.cursor() as cursor:
                yield cursor
        finally:
            self.conn.commit()

    # --- 배치 및 레시피 데이터 관리 ---

    def load_batch_plan_from_ui(self):
        """
        UI에서 설정한 배치 계획(`batch_plan_items`)을 `batch_test_items`로 복사/로드합니다.
        또한, 실시간 시편 상태를 기록할 `test_tray_items` 테이블을 초기화합니다.
        """
        # 1. test_tray_items 테이블 초기화
        self.initialize_test_tray_items()

        with self.cursor() as cur:
            # 2. 기존 테스트 항목 삭제
            cur.execute("TRUNCATE TABLE batch_test_items")
            logger.info("Truncated `batch_test_items` table.")

            # 3. UI 계획을 테스트 항목으로 복사
            sql = """
            INSERT INTO batch_test_items (tray_no, seq_order, seq_status, test_method, batch_id, lot, qr_no)
            SELECT tray_no, seq_order, seq_status, test_method, batch_id, lot, qr_no
            FROM batch_plan_items
            """
            cur.execute(sql)
            logger.info(f"{cur.rowcount} rows copied from `batch_plan_items` to `batch_test_items`.")

            # 4. batch_test_items 정보를 바탕으로 test_tray_items 업데이트
            # seq_order > 0 인 항목에 대해 test_spec 업데이트 및 status=1(대기) 설정
            update_sql = """
            UPDATE test_tray_items t
            JOIN batch_test_items b ON t.tray_no = b.tray_no
            SET t.test_spec = b.test_method, t.status = 1
            WHERE b.seq_order > 0
            """
            cur.execute(update_sql)
            logger.info(f"Updated `test_tray_items` based on `batch_test_items`. Rows affected: {cur.rowcount}")

            # 5. 배치 정보를 블랙보드에 업데이트
            # batch_test_items에서 첫 번째 항목의 정보를 가져와서 블랙보드에 설정
            cur.execute("""
                SELECT batch_id, lot, test_method, qr_no
                FROM batch_test_items
                WHERE seq_order > 0
                ORDER BY seq_order ASC
                LIMIT 1
            """)
            batch_info = cur.fetchone()

            if batch_info:
                batch_id, lot_name, test_method, qr_no = batch_info
                bb.set("process_status/batch_id", batch_id if batch_id else "")
                bb.set("process_status/lot_name", lot_name if lot_name else "")
                bb.set("process_status/test_method", test_method if test_method else "")
                bb.set("process_status/qr_no", qr_no if qr_no else "")
                logger.info(f"Updated blackboard with batch info: batch_id={batch_id}, lot={lot_name}, test_method={test_method}, qr_no={qr_no}")
            else:
                # 배치 정보가 없는 경우 초기화
                bb.set("process_status/batch_id", "")
                bb.set("process_status/lot_name", "")
                bb.set("process_status/test_method", "")
                bb.set("process_status/qr_no", "")
                logger.warning("No batch items found. Cleared blackboard batch info.")

            return cur.rowcount

    def initialize_test_tray_items(self):
        """
        test_tray_items 테이블을 초기 상태로 되돌립니다.
        테이블에 50개의 시편 슬롯이 있으면 기존 데이터를 초기화하고, 없으면 새로 생성합니다.
        """
        with self.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM test_tray_items")
            row_count = cur.fetchone()['count']

            if row_count == 50:
                # 50개 행이 이미 존재하면, id, tray_no, specimen_no를 제외하고 초기화합니다.
                logger.info("`test_tray_items` has 50 rows. Updating to initial state.")
                # status와 dimension은 0으로, test_spec은 빈 문자열로 설정합니다.
                sql = "UPDATE test_tray_items SET status = 0, test_spec = '', dimension = 0.0"
                cur.execute(sql)
                logger.info(f"Reset {cur.rowcount} rows in `test_tray_items`.")
            else:
                # 50개 행이 없으면, 테이블을 비우고 새로 생성합니다.
                logger.warning(f"`test_tray_items` has {row_count} rows, not 50. Re-initializing table.")
                cur.execute("TRUNCATE TABLE test_tray_items")
                logger.info("Truncated `test_tray_items` table.")
                
                insert_queries = []
                # 사용자가 요청한 순서(tray_no 10 -> 1)에 따라 id가 1부터 50까지 매핑되도록 역순으로 생성합니다.
                for tray in range(10, 0, -1):
                    for specimen in range(1, 6):
                        # (tray_no, specimen_no, status=0, test_spec='', dimension=0.0)
                        insert_queries.append((tray, specimen, 0, '', 0.0))
                
                sql = "INSERT INTO test_tray_items (tray_no, specimen_no, status, test_spec, dimension) VALUES (%s, %s, %s, %s, %s)"
                cur.executemany(sql, insert_queries)
                logger.info("Initialized `test_tray_items` with 50 specimen slots (tray 10 to 1).")

    def update_test_tray_item(self, tray_no: int, specimen_no: int, updates: dict):
        """
        test_tray_items 테이블의 특정 시편 정보를 업데이트합니다.
        """
        if not updates:
            return

        set_clause = ", ".join([f"`{key}` = %s" for key in updates.keys()])
        values = list(updates.values()) + [tray_no, specimen_no]

        with self.cursor() as cur:
            sql = f"UPDATE test_tray_items SET {set_clause} WHERE tray_no = %s AND specimen_no = %s"
            cur.execute(sql, tuple(values))
            logger.info(f"Updated test_tray_items for tray {tray_no}, specimen {specimen_no} with {updates}")

    def get_test_tray_items(self, tray_no: int):
        """트레이 번호에 해당하는 시편 목록을 조회합니다."""
        with self.cursor() as cur:
            cur.execute("SELECT * FROM test_tray_items WHERE tray_no = %s ORDER BY specimen_no ASC", (tray_no,))
            return cur.fetchall()

    def get_batch_data(self):
        """
        `batch_test_items`에서 현재 배치 데이터를 조회하고,
        가공하여 Blackboard에 저장한 후 결과를 반환합니다.
        """
        with self.cursor() as cur:
            # seq_order와 seq_status가 0이 아닌 유효한 공정 데이터만 조회
            cur.execute("SELECT * FROM batch_test_items WHERE seq_order != 0 AND seq_status != 0 ORDER BY seq_order ASC")
            process_data = cur.fetchall()

        if not process_data:
            logger.warning("No valid batch data found in `batch_test_items` (seq_order > 0).")
            bb.set("process/auto/batch_data", None)
            return None
        logger.info(f"Read Data from `batch_test_items`: {process_data}")

        # 첫 번째 항목에서 배치 정보 추출
        first_item = process_data[0]
        batch_id = first_item.get("batch_id")
        
        # Command.md에 명시된 데이터 구조로 가공
        batch_info = {
            "batch_id": batch_id,
            "procedure_num": len(process_data),
            "timestamp": datetime.now().isoformat(),
            "processData": process_data
        }
        
        # Blackboard에 저장
        bb.set("process/auto/batch_data", batch_info)
        logger.info(f"Batch data for '{batch_id}' loaded and set to blackboard.")
        logger.info(f"Batch Info: {batch_info}")
        
        return batch_info

    def update_processing_status(self, seq_order, new_status):
        """
        특정 시험 항목(seq_order)의 상태(seq_status)를 업데이트합니다.
        """
        with self.cursor() as cur:
            cur.execute(
                "UPDATE batch_test_items SET seq_status = %s WHERE seq_order = %s",
                (new_status, seq_order)
            )
            logger.info(f"Updated seq_status of seq_order {seq_order} to {new_status}.")

    def reset_batch_test_items_data(self):
        """
        UI의 리셋 요청에 따라 `batch_test_items`와 `test_tray_items` 테이블을 초기화합니다.
        """
        # 1. test_tray_items 테이블 초기화
        self.initialize_test_tray_items()

        # 2. batch_test_items 테이블 내용 초기화
        with self.cursor() as cur:
            # id와 tray_no는 유지하면서 나머지 컬럼을 초기화합니다.
            sql = """
            UPDATE batch_test_items
            SET
                seq_order = 0,
                seq_status = 0,
                test_method = '',
                batch_id = '',
                lot = '',
                qr_no = ''
            """
            cur.execute(sql)
            logger.info(f"Reset {cur.rowcount} rows in `batch_test_items` table to initial state.")
        return True
    
    def reset_batch_plan_items_data(self):
        """
        UI의 리셋 요청에 따라 `batch_test_items`와 `test_tray_items` 테이블을 초기화합니다.
        """
        # 1. test_tray_items 테이블 초기화
        self.initialize_test_tray_items()

        # 2. batch_plan_items 테이블 내용 초기화
        with self.cursor() as cur:
            # id와 tray_no는 유지하면서 나머지 컬럼을 초기화합니다.
            sql = """
            UPDATE batch_plan_items
            SET
                seq_order = 0,
                seq_status = 0,
                test_method = '',
                batch_id = '',
                lot = '',
                qr_no = ''
            """
            cur.execute(sql)
            logger.info(f"Reset {cur.rowcount} rows in `batch_test_items` table to initial state.")
        return True


    def get_test_method_details(self, qr_no):
        """
        시험 방법 이름으로 `batch_method_items` 테이블에서 상세 정보를 조회합니다.
        """
        with self.cursor() as cur:
            cur.execute("SELECT * FROM batch_method_items WHERE qr_no = %s", (qr_no,))
            return cur.fetchone()

    def get_qr_recipe(self, qr_no):
        """
        QR 번호에 해당하는 레시피 정보를 `qr_recipe_items` 테이블에서 조회합니다.
        """
        with self.cursor() as cur:
            cur.execute("SELECT * FROM qr_recipe_items WHERE qr_no = %s", (qr_no,))
            return cur.fetchone()

    # --- 로그 데이터 관리 ---

    def insert_summary_log(self, batch_id, tray_no, specimen_no, work_history, process_type="PROCESS"):
        """요약 이력(`summary_data_items`)을 기록합니다."""
        log_data = {
            'date_time': datetime.now(),
            'process_type': process_type,
            'batch_id': batch_id,
            'tray_no': tray_no,
            'specimen_no': specimen_no,
            'work_history': work_history
        }
        with self.cursor() as cur:
            sql = """INSERT INTO summary_data_items 
                     (date_time, process_type, batch_id, tray_no, specimen_no, work_history) 
                     VALUES (%(date_time)s, %(process_type)s, %(batch_id)s, %(tray_no)s, %(specimen_no)s, %(work_history)s)"""
            cur.execute(sql, log_data)

    def insert_detail_log(self, log_data: dict):
        """상세 이력(`detail_data_items`)을 기록합니다."""
        with self.cursor() as cur:
            sql = "INSERT INTO detail_data_items (date_time, process_type, batch_id, tray_no, specimen_no, equipment, work_status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            values = (log_data.get('date_time'), log_data.get('process_type'), log_data.get('batch_id'), log_data.get('tray_no'), log_data.get('specimen_no'), log_data.get('equipment'), log_data.get('work_status'))
            cur.execute(sql, values)

# --- 참고: 삭제된 메서드 ---
# 아래 메서드들은 `DB.md` 명세 변경에 따라 실시간 상태를 DB에 기록하지 않게 되면서 삭제되었습니다.
# - get_current_specimen_info()
# - update_tray_specimen_status()
# - log_io_change()
# - get_system_status()
# - update_system_status()

if __name__ == '__main__':
    import os
    import json
    
    # 로깅 설정 (콘솔 출력)
    logging.basicConfig(level=logging.INFO)

    # 설정 파일 로드 시도
    config_path = os.path.join(os.path.dirname(__file__), 'configs', 'configs.json')
    db_config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            db_config = {
                'host': config.get('db_host', 'localhost'),
                'user': config.get('db_user', 'root'),
                'password': config.get('db_password', ''),
                'db_name': config.get('db_name', 'shimadzu_db')
            }
    else:
        print(f"Config file not found at {config_path}. Using defaults.")
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'db_name': 'shimadzu_db'
        }

    print(f"Connecting to DB with: {db_config}")
    db = DBHandler(**db_config, enable_monitor=False)
    
    if db.connect():
        try:
            while True:
                print("\n--- DB Handler Test Menu ---")
                print("1. get_test_tray_items (Input: tray_no)")
                print("2. get_batch_data (No input)")
                print("3. get_test_method_details (Input: qr_no/test_method)")
                print("4. get_qr_recipe (Input: qr_no)")
                print("q. Quit")
                
                choice = input("Select function: ").strip()
                
                if choice == '1':
                    try:
                        tray_no = int(input("Enter tray_no: "))
                        items = db.get_test_tray_items(tray_no)
                        print(f"Result: {items}")
                    except ValueError:
                        print("Invalid input for tray_no")
                elif choice == '2':
                    data = db.get_batch_data()
                    
                    print(f"Result: {data}")
                    
                elif choice == '3':
                    qr_no = input("Enter qr_no (or test_method name): ")
                    details = db.get_test_method_details(qr_no)

                    print(f"Result: {details}")
                    mname = details['test_method'] if details else 'N/A'
                    print(f"Test Method: {mname}")
                elif choice == '4':
                    qr_no = input("Enter qr_no: ")
                    recipe = db.get_qr_recipe(qr_no)
                    print(f"Result: {recipe}")
                elif choice.lower() == 'q':
                    break
                else:
                    print("Invalid selection")
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            db.disconnect()
    else:
        print("Failed to connect to database.")