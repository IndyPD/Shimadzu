import os
import sys

# 스크립트를 직접 실행할 때 'pkg' 및 'projects' 모듈을 찾을 수 있도록 경로 추가
if __name__ == "__main__":
    # 현재 파일(DB_handler.py)에서 두 단계 위가 프로젝트 루트(Shimadzu)입니다.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

import mysql.connector
from mysql.connector import Error
from pkg.utils.logging import Logger
from pkg.utils.blackboard import GlobalBlackboard
from datetime import datetime
try:
    from .constants import get_time
except (ImportError, ValueError):
    from constants import get_time

DEBUG_MODE = False

bb = GlobalBlackboard()

class DBHandler:
    def __init__(self):
        self.config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': 'root',
            'database': 'shimadzu_db'  # 데이터베이스 이름은 환경에 맞게 수정하세요.
        }
        self.connection = None

    def connect(self):
        try:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**self.config)
            return True
        except Error as e:
            Logger.error(f"MySQL Connection Error: {e}")
            return False

    def disconnect(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()

    def get_batch_data(self):
        """
        테이블의 모든 배치 시험 항목을 가져옵니다. (batch_id 필터링 제거)
        """
        if not self.connect():
            return None

        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # 1. 배치 시험 계획 조회 (batch_plan_items)
            query_process = """
                SELECT 
                    id,
                    tray_no,
                    seq_order,
                    seq_status,
                    qr_no,
                    test_method,
                    batch_id,
                    lot
                FROM batch_plan_items 
                ORDER BY seq_order ASC
            """
            cursor.execute(query_process)
            process_data = cursor.fetchall()

            # 데이터 존재 여부 로그 출력
            if process_data:
                Logger.info(f"Found {len(process_data)} rows in batch_plan_items.")
            else:
                Logger.warn("batch_plan_items table is empty.")
                
            if not process_data:
                return None

            else :
                # 읽은 데이터를 batch_test_items 테이블에 기입 (Insert or Update)
                upsert_query = """
                    INSERT INTO batch_test_items (id, tray_no, seq_order, seq_status, qr_no, test_method, batch_id, lot)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        tray_no = VALUES(tray_no), 
                        seq_order = VALUES(seq_order), 
                        seq_status = VALUES(seq_status), 
                        qr_no = VALUES(qr_no),
                        test_method = VALUES(test_method), 
                        batch_id = VALUES(batch_id), 
                        lot = VALUES(lot)
                """
                upsert_values = [
                    (row['id'], row['tray_no'], row['seq_order'], 1 if row['seq_order'] != 0 else 0, 
                     row['qr_no'], row['test_method'], row['batch_id'], row['lot'])
                    for row in process_data
                ]
                cursor.executemany(upsert_query, upsert_values)
                self.connection.commit()
            # 2. 데이터 가공 함수 호출
            batch_info = self._parse_batch_data(process_data)

            if DEBUG_MODE:
                print(f"DEBUG: Final batch_info:")
                print(f"  {batch_info}")

            # 블랙보드에 배치 데이터 저장
            bb.set("process/auto/batch_data", batch_info)
            return batch_info

        except Error as e:
            Logger.error(f"DB Query Error (get_batch_data): {e}")
            return None
        finally:
            cursor.close()

    def clear_batch_test_items(self):
        """
        batch_test_items 테이블을 초기화하고 10개의 빈 슬롯(트레이 기준)을 생성합니다.
        """
        if not self.connect():
            return False

        try:
            cursor = self.connection.cursor()
            # 1. 테이블의 모든 행을 삭제하고 Auto-Increment ID를 1로 초기화합니다.
            cursor.execute("TRUNCATE TABLE batch_test_items")
            
            # 2. 10개의 빈 행(tray_no 1~10)을 기본값으로 삽입합니다.
            init_query = """
                INSERT INTO batch_test_items (tray_no, seq_order, seq_status, qr_no, test_method, batch_id, lot)
                VALUES (%s, 0, 0, '', '', '', '')
            """
            init_values = [(i,) for i in range(1, 11)]
            cursor.executemany(init_query, init_values)
            
            self.connection.commit()
            Logger.info("Successfully cleared and initialized 10 slots in batch_test_items.")
            return True
        except Error as e:
            Logger.error(f"DB Clear Error (batch_test_items): {e}")
            return False
        finally:
            cursor.close()

    def clear_test_tray_items(self):
        """
        test_tray_items 테이블(3.2)을 초기화하고 50개의 빈 슬롯(10트레이 * 5시편)을 생성합니다.
        """
        if not self.connect(): return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("TRUNCATE TABLE test_tray_items")
            init_query = """
                INSERT INTO test_tray_items (tray_no, specimen_no, status, status_str, test_spec, dimension, batch_id, lot)
                VALUES (%s, %s, 0, 'NONE', '', 0.0, '', '')
            """
            init_values = [(t, s) for t in range(1, 11) for s in range(1, 6)]
            cursor.executemany(init_query, init_values)
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB Clear Error (test_tray_items): {e}")
            return False
        finally:
            cursor.close()

    def _parse_batch_data(self, process_data: list) -> dict:
        """
        DB에서 읽어온 원본 리스트를 Command.md 구조에 맞게 가공 및 구조화합니다.
        """
        if not process_data:
            return {
                "batch_id": "NONE",
                "procedure_num": 0,
                "timestamp": get_time(),
                "processData": []
            }

        # 1. 데이터 정렬 보장 (seq_order 기준)
        process_data.sort(key=lambda x: x.get("seq_order", 0))

        # seq_order가 0인 항목은 공정 대상이 아니므로 제외 (1번부터 시작하도록 필터링)
        filtered_data = [item for item in process_data if item.get("seq_order", 0) != 0]

        # seq_order가 0이 아닌 실제 공정 대상 항목들의 개수 계산
        active_procedure_count = len(filtered_data)

        first_batch_id = filtered_data[0]['batch_id'] if filtered_data else "NONE"
        batch_info = {
            "batch_id": first_batch_id,
            "procedure_num": active_procedure_count,
            "timestamp": get_time(),
            "processData": []
        }

        for item in filtered_data:
            # 예시 데이터 구조와 동일하게 필드 구성
            processed_item = {
                "id": item.get("id"),
                "tray_no": item.get("tray_no"),
                "seq_order": item.get("seq_order"),
                "seq_status": 1 if item.get("seq_order", 0) != 0 else 0,
                "qr_no": item.get("qr_no"),
                "test_method": item.get("test_method") if item.get("test_method") else "DEFAULT_ASTM",
                "batch_id": item.get("batch_id"),
                "lot": item.get("lot")
            }
            batch_info['processData'].append(processed_item)
        # if DEBUG_MODE:
        for batch_item in batch_info['processData']:
            print(batch_item)

        # tray_no 기준으로 seq_status 값을 1로 업데이트하여 DB에 반영
        if batch_info['processData'] and self.connect():
            try:
                cursor = self.connection.cursor()
                update_query = "UPDATE batch_test_items SET seq_status = 1 WHERE tray_no = %s AND batch_id = %s"
                update_values = [(item['tray_no'], item['batch_id']) for item in batch_info['processData']]
                cursor.executemany(update_query, update_values)
                self.connection.commit()
                cursor.close()
                Logger.info(f"Initialized seq_status to 1 for {len(update_values)} items in batch_test_items")
            except Error as e:
                Logger.error(f"DB Error in _parse_batch_data (status update): {e}")

        return batch_info

    def update_processing_status(self, batch_id, tray_no, specimen_no, status_code):
        """
        특정 시편의 진행 상태를 업데이트합니다.
        status_code: 1(진행예정), 2(진행중), 3(완료)
        """
        if not self.connect():
            return False

        # DB.md 명세 및 UI 표시용 상태 문자열 매핑
        status_map = {1: "READY", 2: "RUNNING", 3: "DONE"}
        status_str = status_map.get(status_code, "UNKNOWN")

        try:
            cursor = self.connection.cursor()
            
            # 1. 배치 시험 항목 상태 업데이트 (Tray 기준 - 3.5)
            # 시편이 진행 중이면 트레이도 진행 중, 시편 5개가 모두 끝나야 트레이가 완료됨
            if status_code == 2: # RUNNING
                query_test = "UPDATE batch_test_items SET seq_status = 2 WHERE batch_id = %s AND tray_no = %s"
                cursor.execute(query_test, (batch_id, tray_no))
            elif status_code == 3 and specimen_no == 5: # DONE (마지막 시편)
                query_test = "UPDATE batch_test_items SET seq_status = 3 WHERE batch_id = %s AND tray_no = %s"
                cursor.execute(query_test, (batch_id, tray_no))
            
            # 2. 개별 시편 정보 상태 업데이트 (Specimen 기준 - 3.2)
            query_tray = "UPDATE test_tray_items SET status = %s, status_str = %s WHERE batch_id = %s AND tray_no = %s AND specimen_no = %s"
            cursor.execute(query_tray, (status_code, status_str, batch_id, tray_no, specimen_no))
            
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB Update Error: {e}")
            return False
        finally:
            cursor.close()

    def insert_summary_log(self, batch_id, tray_no, specimen_no, work_history):
        """
        summary_data_items 테이블(3.3)에 요약 이력을 기록합니다.
        """
        if not self.connect(): return False
        try:
            cursor = self.connection.cursor()
            query = """
                INSERT INTO summary_data_items (date_time, process_type, batch_id, tray_no, specimen_no, work_history)
                VALUES (%s, 'AUTO', %s, %s, %s, %s)
            """
            cursor.execute(query, (datetime.now(), batch_id, tray_no, specimen_no, work_history))
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB Summary Log Error: {e}")
            return False
        finally:
            cursor.close()
    def update_test_tray_info(self, tray_no, specimen_no, status, status_str, batch_id, lot, test_spec=None, dimension=None):
        """
        test_tray_items 테이블의 정보를 업데이트합니다. (DB.md 3.2)
        """
        if not self.connect(): return False
        try:
            cursor = self.connection.cursor()
            query = """
                UPDATE test_tray_items 
                SET status = %s, status_str = %s, batch_id = %s, lot = %s, test_spec = %s, dimension = %s
                WHERE tray_no = %s AND specimen_no = %s
            """
            cursor.execute(query, (status, status_str, batch_id, lot, test_spec, dimension, tray_no, specimen_no))
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB test_tray_items Update Error: {e}")
            return False
        finally:
            cursor.close()

    def save_thickness_result(self, value):
        """
        현재 측정된 두께 값을 test_status_items에 저장합니다.
        """
        if not self.connect(): return False
        try:
            cursor = self.connection.cursor()
            # 가장 최근의 상태 레코드를 업데이트하거나 새로 삽입
            query = "UPDATE test_status_items SET thickness_current = %s ORDER BY id DESC LIMIT 1"
            cursor.execute(query, (value,))
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB Thickness Save Error: {e}")
            return False
        finally:
            cursor.close()

    def get_test_method_details(self, method_name: str):
        """
        test_methods 테이블에서 주어진 시험 방법 이름에 대한 상세 파라미터를 조회합니다.
        """
        if not self.connect():
            return None
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            # 'test_methods' 테이블이 존재한다고 가정합니다.
            query = "SELECT * FROM test_methods WHERE method_name = %s"
            cursor.execute(query, (method_name,))
            method_details = cursor.fetchone()

            if method_details:
                Logger.info(f"Successfully fetched details for test method: {method_name}")
                return method_details
            else:
                Logger.warn(f"No details found for test method: {method_name}. Returning default values.")
                return {} # 빈 dict를 반환하여 get() 메서드에서 기본값을 사용하도록 유도
        except Error as e:
            Logger.error(f"DB Query Error (get_test_method_details): {e}")
            return None
        finally:
            if cursor and self.connection.is_connected():
                cursor.close()

    def insert_detail_log(self, batch_id, tray_no, specimen_no, equipment, status_msg):
        """
        detail_data_items 테이블에 상세 공정 로그를 기록합니다.
        """
        if not self.connect(): return False
        try:
            cursor = self.connection.cursor()
            query = """
                INSERT INTO detail_data_items (date_time, process_type, batch_id, tray_no, specimen_no, equipment, work_status)
                VALUES (%s, 'AUTO', %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (datetime.now(), batch_id, tray_no, specimen_no, equipment, status_msg))
            self.connection.commit()
            return True
        except Error as e:
            Logger.error(f"DB Log Error: {e}")
            return False
        finally:
            cursor.close()

if __name__ == "__main__":
    # DBHandler 독립 테스트를 위한 메인 문
    handler = DBHandler()
    print("--- DB Handler Test Start ---")
    
    if handler.connect():
        print("✅ Connected to MySQL")
        
        # 1. 배치 데이터 조회 테스트
        print(f"1. Testing get_batch_data (All items)...")
        batch_data = handler.get_batch_data()
        if batch_data:
            print(f"✅ Batch ID: {batch_data['batch_id']}")
            print(f"✅ Timestamp: {batch_data['timestamp']}")
            print(f"✅ Procedure Count: {batch_data['procedure_num']}")
            for item in batch_data['processData']:
                print(f"   [{item['seq_order']}] Tray: {item['tray_no']} | QR: {item['qr_no']} | Method: {item['test_method']} | Seq Status: {item['seq_status']}")

            # 데이터가 로드된 경우에만 블랙보드 확인
            data = bb.get("process/auto/batch_data")
            print(f"✅ Blackboard Data Sync Check: {'Success' if data else 'Fail'}")
        else:
            print("⚠️ No batch data found. (batch_plan_items 테이블에 데이터가 있는지 확인하세요.)")
        
        import time
        time.sleep(10)
        
        handler.clear_batch_test_items()

        #
        handler.disconnect()
        print("\n🔌 DB Handler Test Finished.")
    else:
        print("❌ Connection failed. Check MySQL service and credentials.")
