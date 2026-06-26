import os
import unittest
from dlm.storage.db import OracleDBManager
from dlm.core.inspector import SchemaInspector

class TestSchemaInspector(unittest.TestCase):
    def setUp(self):
        # 테스트용 임시 파일 경로 설정
        self.meta_db_path = "test_meta.db"
        self.target_db_path = "test_target.db"

        # 기존 임시 파일 제거
        for path in [self.meta_db_path, self.target_db_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

        # 1. 메타 DB 및 대상 DB 관리자 초기화
        # 메타 DB는 schema.sql에 따라 메타 테이블이 자동 초기화됩니다.
        self.meta_db = OracleDBManager(mock_db_path=self.meta_db_path)
        
        # 대상 DB도 동일한 OracleDBManager 클래스를 사용해 모킹합니다.
        # (테스트 편의를 위해 일단 빈 메타 스키마를 생성해둔 뒤 오라클 데이터 사전 뷰를 테이블 형태로 생성)
        self.target_db = OracleDBManager(mock_db_path=self.target_db_path)
        self.inspector = SchemaInspector(self.meta_db)

        # 2. 대상 DB에 오라클 가상 데이터 사전 뷰(테이블) 생성
        self.target_db.execute("CREATE TABLE USER_TABLES (TABLE_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_PART_TABLES (TABLE_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_TAB_PARTITIONS (TABLE_NAME TEXT, PARTITION_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_INDEXES (INDEX_NAME TEXT, TABLE_NAME TEXT);")
        self.target_db.execute("CREATE TABLE USER_PART_INDEXES (INDEX_NAME TEXT, ALIGNMENT TEXT);")

    def tearDown(self):
        # 싱글톤 해제
        OracleDBManager._instance = None
        
        # 테스트 완료 후 임시 파일 삭제
        for path in [self.meta_db_path, self.target_db_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

    def test_inspect_and_register_oracle(self):
        # 1. 대상 가상 오라클 DB 딕셔너리에 모의 데이터 삽입
        
        # 일반 테이블 등록
        self.target_db.execute("INSERT INTO USER_TABLES (TABLE_NAME) VALUES (?);", ("USERS",))
        # 파티션 테이블 등록 (USER_PART_TABLES와 USER_TABLES 양쪽에 기록)
        self.target_db.execute("INSERT INTO USER_PART_TABLES (TABLE_NAME) VALUES (?);", ("ORDERS",))
        self.target_db.execute("INSERT INTO USER_TABLES (TABLE_NAME) VALUES (?);", ("ORDERS",))
        
        # 개별 파티션 등록
        self.target_db.execute(
            "INSERT INTO USER_TAB_PARTITIONS (TABLE_NAME, PARTITION_NAME) VALUES (?, ?);", 
            ("ORDERS", "P_202605")
        )
        self.target_db.execute(
            "INSERT INTO USER_TAB_PARTITIONS (TABLE_NAME, PARTITION_NAME) VALUES (?, ?);", 
            ("ORDERS", "P_202606")
        )
        
        # 인덱스 등록
        self.target_db.execute(
            "INSERT INTO USER_INDEXES (INDEX_NAME, TABLE_NAME) VALUES (?, ?);", 
            ("IDX_USERS_ID", "USERS")
        )
        self.target_db.execute(
            "INSERT INTO USER_INDEXES (INDEX_NAME, TABLE_NAME) VALUES (?, ?);", 
            ("IDX_ORDERS_DATE", "ORDERS")
        )
        self.target_db.execute(
            "INSERT INTO USER_PART_INDEXES (INDEX_NAME, ALIGNMENT) VALUES (?, ?);", 
            ("IDX_ORDERS_DATE", "LOCAL")
        )

        # 2. Inspector 실행
        self.inspector.inspect_and_register(self.target_db)

        # 3. 메타데이터 등록 결과 검증
        objects = self.meta_db.fetch_all("SELECT * FROM DLM_OBJECTS;")
        
        # 기대하는 등록 오프젝트 목록:
        # - USERS (TABLE, 일반)
        # - ORDERS (TABLE, 파티션 부모)
        # - ORDERS$P_202605 (PARTITION)
        # - ORDERS$P_202606 (PARTITION)
        # - IDX_USERS_ID (INDEX)
        # - IDX_ORDERS_DATE (INDEX)
        # 총 6개 오브젝트
        self.assertEqual(len(objects), 6)

        # 일반 테이블 검증
        users_obj = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'USERS';")
        self.assertIsNotNone(users_obj)
        self.assertEqual(users_obj['OBJECT_TYPE'], 'TABLE')
        self.assertEqual(users_obj['IS_PARTITIONED'], 0)

        # 파티션 부모 테이블 검증
        orders_parent = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'ORDERS';")
        self.assertIsNotNone(orders_parent)
        self.assertEqual(orders_parent['OBJECT_TYPE'], 'TABLE')
        self.assertEqual(orders_parent['IS_PARTITIONED'], 1)

        # 파티션 자식 검증
        part_1 = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'ORDERS$P_202605';")
        self.assertIsNotNone(part_1)
        self.assertEqual(part_1['OBJECT_TYPE'], 'PARTITION')
        self.assertEqual(part_1['PARENT_ID'], orders_parent['ID'])

        part_2 = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'ORDERS$P_202606';")
        self.assertIsNotNone(part_2)
        self.assertEqual(part_2['OBJECT_TYPE'], 'PARTITION')
        self.assertEqual(part_2['PARENT_ID'], orders_parent['ID'])

        # 인덱스 검증
        idx_users = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'IDX_USERS_ID';")
        self.assertIsNotNone(idx_users)
        self.assertEqual(idx_users['OBJECT_TYPE'], 'INDEX')
        self.assertEqual(idx_users['PARENT_ID'], users_obj['ID'])

        idx_orders = self.meta_db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE NAME = 'IDX_ORDERS_DATE';")
        self.assertIsNotNone(idx_orders)
        self.assertEqual(idx_orders['OBJECT_TYPE'], 'INDEX')
        self.assertEqual(idx_orders['PARENT_ID'], orders_parent['ID'])

if __name__ == '__main__':
    unittest.main()
