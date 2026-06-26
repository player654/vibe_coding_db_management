import os
import re
import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# lf_database 모듈 및 드라이버 존재 여부 동적 체크
USE_REAL_DB = True
try:
    from common.lf_database import Database
except (ImportError, ModuleNotFoundError) as e:
    USE_REAL_DB = False
    logger.warning(f"lf_database를 로드하지 못했거나 드라이버가 부재합니다: {e}. Mock 모드로 동작합니다.")

class MockOracleCursor:
    """단위 테스트 및 SQLite 변환을 위한 Mock 오라클 커서 에뮬레이터"""
    def __init__(self, sqlite_cursor):
        self.cursor = sqlite_cursor

    def execute(self, statement: str, parameters: Any = None):
        # 오라클 바인드 변수 형식 (:1, :name)을 SQLite (? 또는 :name) 형식으로 변환
        stmt = statement
        params = parameters

        if parameters:
            if isinstance(parameters, (list, tuple)):
                stmt = re.sub(r':\d+', '?', statement)
            elif isinstance(parameters, dict):
                pass
        
        # COMMENT ON 구문은 SQLite에서 무시
        if stmt.strip().upper().startswith("COMMENT ON"):
            return self

        try:
            if params is not None:
                self.cursor.execute(stmt, params)
            else:
                self.cursor.execute(stmt)
        except Exception as e:
            logger.debug(f"Mock SQL execution error: {stmt} -> {e}")
            raise e
        return self

    def fetchall(self) -> List[Any]:
        return self.cursor.fetchall()

    def fetchone(self) -> Optional[Any]:
        return self.cursor.fetchone()

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    @property
    def lastrowid(self) -> Any:
        return self.cursor.lastrowid

    def close(self):
        self.cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class MockOracleConnection:
    """단위 테스트 및 SQLite 변환을 위한 Mock 오라클 커넥션 에뮬레이터"""
    def __init__(self, sqlite_conn):
        self.conn = sqlite_conn

    def cursor(self):
        return MockOracleCursor(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

class OracleDBManager:
    """오라클 DB 연결 및 메타데이터를 관리하는 매니저 클래스 (싱글톤)"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(OracleDBManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, schema: str = "LFMDW", mock_db_path: str = "dlm_metadata.db"):
        if self._initialized:
            return
        self.schema = schema
        self.mock_db_path = mock_db_path
        self._initialized = True
        
        # 외부 드라이버가 없거나 Mock DB가 명시적으로 필요한 경우 mock 모드 활성화
        self.use_mock = not USE_REAL_DB

        # 만약 lf_database가 존재하더라도 실제 연결이 예외로 실패하면 Mock으로 폴백할 수 있도록 핸들링
        if not self.use_mock:
            try:
                # 연결이 잘 되는지 단순 테스트 시도
                with Database(self.schema) as db:
                    pass
            except Exception as e:
                logger.warning(f"실제 DB 연결에 실패하여 Mock 모드로 강제 폴백합니다: {e}")
                self.use_mock = True

        if self.use_mock:
            logger.info(f"Mock DB 모드로 시작합니다 (경로: {mock_db_path})")
            self.init_mock_db()

    def _convert_oracle_ddl_to_sqlite(self, sql: str) -> str:
        """오라클 DDL을 SQLite 호환 DDL로 변환합니다."""
        # 1. 컬럼 레벨 PK 자동증가 변환 (DEFAULT SEQ_... 구문 포함)
        sql = re.sub(
            r'ID\s+NUMBER\s+DEFAULT\s+SEQ_\w+\.NEXTVAL\s+NOT\s+NULL',
            'ID INTEGER PRIMARY KEY AUTOINCREMENT',
            sql,
            flags=re.IGNORECASE
        )
        # 2. 테이블 레벨 PK 제약조건 제거 (SQLite 컬럼 레벨 PK가 걸렸으므로 중복 제거)
        sql = re.sub(
            r'CONSTRAINT\s+PK_\w+\s+PRIMARY\s+KEY\s*\(\s*ID\s*\)\s*,?\s*',
            '',
            sql,
            flags=re.IGNORECASE
        )
        sql = re.sub(r'VARCHAR2\(\d+\)', 'TEXT', sql, flags=re.IGNORECASE)
        sql = re.sub(r'NUMBER\(1\)', 'INTEGER', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bNUMBER\b', 'INTEGER', sql, flags=re.IGNORECASE)
        sql = re.sub(r'CHAR\(1\)', 'TEXT', sql, flags=re.IGNORECASE)
        return sql

    def init_mock_db(self):
        """Mock 모드에서 oracle_schema.sql을 읽고 SQLite로 변환하여 메타 테이블을 초기화합니다."""
        schema_path = os.path.join(os.path.dirname(__file__), "oracle_schema.sql")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found at: {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        sqlite_ddl = self._convert_oracle_ddl_to_sqlite(schema_sql)

        with sqlite3.connect(self.mock_db_path) as conn:
            statements = []
            for stmt in sqlite_ddl.split(";"):
                stmt_clean = stmt.strip()
                if not stmt_clean or stmt_clean.upper().startswith("COMMENT ON") or stmt_clean.upper().startswith("CREATE SEQUENCE"):
                    continue
                statements.append(stmt_clean)
            
            for stmt in statements:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    logger.debug(f"SQLite DDL execution skipped/failed: {e}")
            conn.commit()

    def execute(self, query: str, params: Any = None) -> int:
        """DML 쿼리 실행 후 영향을 받은 row 수를 반환합니다."""
        if self.use_mock:
            with sqlite3.connect(self.mock_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params if params else ())
                conn.commit()
                return cursor.rowcount
        else:
            with Database(self.schema) as db:
                db.execute(query, params)
                return db.cursor.rowcount

    def execute_insert(self, query: str, params: Any = None) -> Any:
        """INSERT 실행 후 insert된 row ID를 반환합니다."""
        if self.use_mock:
            with sqlite3.connect(self.mock_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params if params else ())
                conn.commit()
                return cursor.lastrowid
        else:
            with Database(self.schema) as db:
                db.execute(query, params)
                # 오라클의 경우 insert 후 반환 키 처리가 다를 수 있으나 공통 API 준수
                return db.cursor.rowcount

    def fetch_all(self, query: str, params: Any = None) -> List[Dict[str, Any]]:
        """조회 쿼리를 수행하고 Dict 형식의 List로 반환합니다."""
        if self.use_mock:
            with sqlite3.connect(self.mock_db_path) as conn:
                conn.row_factory = sqlite3.Row
                # NVL 함수 에뮬레이션 추가
                conn.create_function("NVL", 2, lambda x, y: x if x is not None else y)
                cursor = conn.cursor()
                cursor.execute(query, params if params else ())
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        else:
            with Database(self.schema) as db:
                rows = db.query(query, params)
                return db.rows_to_dict_list(rows)

    def fetch_one(self, query: str, params: Any = None) -> Optional[Dict[str, Any]]:
        """단일 행을 조회하여 Dict 형식으로 반환합니다 (없으면 None)."""
        if self.use_mock:
            with sqlite3.connect(self.mock_db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.create_function("NVL", 2, lambda x, y: x if x is not None else y)
                cursor = conn.cursor()
                cursor.execute(query, params if params else ())
                row = cursor.fetchone()
                return dict(row) if row else None
        else:
            with Database(self.schema) as db:
                db.execute(query, params)
                row = db.fetchone()
                return db._row_to_dict(row) if row else None
