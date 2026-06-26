import os
import unittest
from dlm.storage.db import OracleDBManager

class TestOracleDBManager(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_oracle_meta.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        # OracleDBManager를 Mock 모드로 강제 구동하기 위해 dsn 없이 초기화
        self.db = OracleDBManager(mock_db_path=self.db_path)

    def tearDown(self):
        # 싱글톤 해제
        OracleDBManager._instance = None
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def test_meta_table_creation(self):
        # oracle_schema.sql DDL이 Mock DB(SQLite)에 올바르게 파싱되어 테이블이 생성되었는지 확인
        tables = self.db.fetch_all("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = [t['name'].upper() for t in tables]
        
        # 생성된 메타 테이블들이 존재하는지 검증
        self.assertIn("DLM_OBJECTS", table_names)
        self.assertIn("DLM_VOLUME_HISTORY", table_names)
        self.assertIn("DLM_BACKUP_HISTORY", table_names)
        self.assertIn("DLM_DELETE_HISTORY", table_names)

    def test_execute_and_query(self):
        # 데이터 삽입 테스트 (오라클 바인드 변수 형식이 아닌, SQLite 호환 또는 범용 insert 테스트)
        # SQLite Mock의 경우 execute 메소드 내부에서 쿼리 치환 확인
        obj_id = self.db.execute_insert(
            "INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, IS_PARTITIONED) VALUES (?, ?, ?);",
            ("TEST_TABLE", "TABLE", 0)
        )
        self.assertIsNotNone(obj_id)
        
        # 데이터 조회 테스트
        row = self.db.fetch_one("SELECT * FROM DLM_OBJECTS WHERE ID = ?;", (obj_id,))
        self.assertIsNotNone(row)
        self.assertEqual(row['NAME'], "TEST_TABLE")
        self.assertEqual(row['OBJECT_TYPE'], "TABLE")
        self.assertEqual(row['IS_PARTITIONED'], 0)
        self.assertEqual(row['BACKUP_FLAG'], "N")  # default 값 정상 동작 확인

if __name__ == '__main__':
    unittest.main()
