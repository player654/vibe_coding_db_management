import os
import unittest
from dlm.storage.db import OracleDBManager
from dlm.core.collector import CapacityCollector

class TestCapacityCollector(unittest.TestCase):
    def setUp(self):
        self.meta_db_path = "test_meta.db"
        self.target_db_path = "test_target.db"

        # 기존 파일 정리
        for path in [self.meta_db_path, self.target_db_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

        # 1. DB 매니저 초기화
        self.meta_db = OracleDBManager(mock_db_path=self.meta_db_path)
        self.target_db = OracleDBManager(mock_db_path=self.target_db_path)
        self.collector = CapacityCollector(self.meta_db)

        # 2. 대상 가상 오라클 DB 딕셔너리 테이블 생성
        self.target_db.execute("CREATE TABLE USER_TABLES (TABLE_NAME TEXT, NUM_ROWS INTEGER);")
        self.target_db.execute("CREATE TABLE USER_PART_TABLES (TABLE_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_TAB_PARTITIONS (TABLE_NAME TEXT, PARTITION_NAME TEXT, NUM_ROWS INTEGER);")
        self.target_db.execute("CREATE TABLE USER_INDEXES (INDEX_NAME TEXT, TABLE_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_SEGMENTS (SEGMENT_NAME TEXT, PARTITION_NAME TEXT, BYTES INTEGER);")

        # 3. 메타 DB 마스터 테이블에 사전에 분석된 오브젝트 적재
        # USERS (일반 테이블)
        self.users_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, IS_PARTITIONED) VALUES (?, ?, ?);",
            ("USERS", "TABLE", 0)
        )
        # ORDERS (파티션 부모 테이블)
        self.orders_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, IS_PARTITIONED) VALUES (?, ?, ?);",
            ("ORDERS", "TABLE", 1)
        )
        # ORDERS$P_202605 (파티션 1)
        self.p05_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED) VALUES (?, ?, ?, ?);",
            ("ORDERS$P_202605", "PARTITION", self.orders_id, 0)
        )
        # ORDERS$P_202606 (파티션 2)
        self.p06_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED) VALUES (?, ?, ?, ?);",
            ("ORDERS$P_202606", "PARTITION", self.orders_id, 0)
        )
        # IDX_USERS_ID (인덱스)
        self.idx_users_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED) VALUES (?, ?, ?, ?);",
            ("IDX_USERS_ID", "INDEX", self.users_id, 0)
        )
        # IDX_ORDERS_DATE (인덱스)
        self.idx_orders_id = self.meta_db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED) VALUES (?, ?, ?, ?);",
            ("IDX_ORDERS_DATE", "INDEX", self.orders_id, 0)
        )

    def tearDown(self):
        OracleDBManager._instance = None
        for path in [self.meta_db_path, self.target_db_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

    def test_collect_and_save(self):
        # 1. 대상 모의 DB 딕셔너리에 용량 및 행 수 데이터 주입
        
        # 일반 테이블 USERS: 행 수 100건, 물리 크기 100KB (102400 Bytes)
        self.target_db.execute("INSERT INTO USER_TABLES (TABLE_NAME, NUM_ROWS) VALUES (?, ?);", ("USERS", 100))
        self.target_db.execute("INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", ("USERS", None, 102400))
        
        # 파티션 부모 테이블 ORDERS 등록
        self.target_db.execute("INSERT INTO USER_PART_TABLES (TABLE_NAME) VALUES (?);", ("ORDERS",))
        self.target_db.execute("INSERT INTO USER_TABLES (TABLE_NAME, NUM_ROWS) VALUES (?, ?);", ("ORDERS", 110))
        
        # 파티션 P_202605: 행 수 50건, 물리 크기 50KB (51200 Bytes)
        self.target_db.execute(
            "INSERT INTO USER_TAB_PARTITIONS (TABLE_NAME, PARTITION_NAME, NUM_ROWS) VALUES (?, ?, ?);", 
            ("ORDERS", "P_202605", 50)
        )
        self.target_db.execute(
            "INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", 
            ("ORDERS", "P_202605", 51200)
        )
        
        # 파티션 P_202606: 행 수 60건, 물리 크기 60KB (61440 Bytes)
        self.target_db.execute(
            "INSERT INTO USER_TAB_PARTITIONS (TABLE_NAME, PARTITION_NAME, NUM_ROWS) VALUES (?, ?, ?);", 
            ("ORDERS", "P_202606", 60)
        )
        self.target_db.execute(
            "INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", 
            ("ORDERS", "P_202606", 61440)
        )

        # 일반 인덱스 IDX_USERS_ID: 물리 크기 20KB (20480 Bytes)
        self.target_db.execute("INSERT INTO USER_INDEXES (INDEX_NAME, TABLE_NAME) VALUES (?, ?);", ("IDX_USERS_ID", "USERS"))
        self.target_db.execute("INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", ("IDX_USERS_ID", None, 20480))

        # 파티션 인덱스 IDX_ORDERS_DATE: 파티션 단위 세그먼트 생성 (각 10KB씩 총 20KB)
        self.target_db.execute("INSERT INTO USER_INDEXES (INDEX_NAME, TABLE_NAME) VALUES (?, ?);", ("IDX_ORDERS_DATE", "ORDERS"))
        self.target_db.execute("INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", ("IDX_ORDERS_DATE", "P_202605", 10240))
        self.target_db.execute("INSERT INTO USER_SEGMENTS (SEGMENT_NAME, PARTITION_NAME, BYTES) VALUES (?, ?, ?);", ("IDX_ORDERS_DATE", "P_202606", 10240))

        # 2. Collector 기동
        collected_date = "2026-06-26"
        self.collector.collect_and_save(self.target_db, collected_date)

        # 3. 메타 DB의 DLM_VOLUME_HISTORY 검증
        
        # 일반 테이블 USERS 검증
        users_vol = self.meta_db.fetch_one(
            "SELECT PHYSICAL_SIZE_BYTES, ROW_COUNT FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
            (self.users_id, collected_date)
        )
        self.assertIsNotNone(users_vol)
        self.assertEqual(users_vol['PHYSICAL_SIZE_BYTES'], 102400)
        self.assertEqual(users_vol['ROW_COUNT'], 100)

        # 파티션 부모 테이블 ORDERS 검증 (자식 합산 크기)
        orders_vol = self.meta_db.fetch_one(
            "SELECT PHYSICAL_SIZE_BYTES, ROW_COUNT FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
            (self.orders_id, collected_date)
        )
        self.assertIsNotNone(orders_vol)
        self.assertEqual(orders_vol['PHYSICAL_SIZE_BYTES'], 112640) # 51200 + 61440
        self.assertEqual(orders_vol['ROW_COUNT'], 110) # 50 + 60

        # 개별 파티션 P_202605 검증
        p05_vol = self.meta_db.fetch_one(
            "SELECT PHYSICAL_SIZE_BYTES, ROW_COUNT FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
            (self.p05_id, collected_date)
        )
        self.assertIsNotNone(p05_vol)
        self.assertEqual(p05_vol['PHYSICAL_SIZE_BYTES'], 51200)
        self.assertEqual(p05_vol['ROW_COUNT'], 50)

        # 일반 인덱스 IDX_USERS_ID 검증 (부모 테이블 레코드 수와 크기)
        idx_users_vol = self.meta_db.fetch_one(
            "SELECT PHYSICAL_SIZE_BYTES, ROW_COUNT FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
            (self.idx_users_id, collected_date)
        )
        self.assertIsNotNone(idx_users_vol)
        self.assertEqual(idx_users_vol['PHYSICAL_SIZE_BYTES'], 20480)
        self.assertEqual(idx_users_vol['ROW_COUNT'], 100)

        # 파티션 인덱스 IDX_ORDERS_DATE 검증 (합산 세그먼트 크기 및 부모 레코드 수)
        idx_orders_vol = self.meta_db.fetch_one(
            "SELECT PHYSICAL_SIZE_BYTES, ROW_COUNT FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
            (self.idx_orders_id, collected_date)
        )
        self.assertIsNotNone(idx_orders_vol)
        self.assertEqual(idx_orders_vol['PHYSICAL_SIZE_BYTES'], 20480) # 10240 + 10240
        self.assertEqual(idx_orders_vol['ROW_COUNT'], 110)

if __name__ == '__main__':
    unittest.main()
