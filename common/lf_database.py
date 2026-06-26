import importlib
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, List
from lf_auth import Maria_auth, Oracle_auth, Postgre_auth
from lf_encryption import AESCipher


class DBType(str, Enum):
    MYSQL = "mysql"
    ORACLE = "oracle"      # python-oracledb (신버전)
    ORACLE_CX = "cx_oracle"  # cx_Oracle (구버전)
    POSTGRESQL = "postgresql"


@dataclass
class DBConfig:
    db_type: DBType
    host: str
    port: int
    user: str
    password: str
    database: str


def load_driver(db_type: DBType):
    """
    DB 종류에 따라 필요한 드라이버를 동적으로 import
    """
    module_map = {
        DBType.MYSQL: "pymysql",
        DBType.ORACLE: "oracledb",
        DBType.ORACLE_CX: "cx_Oracle",  # 대소문자 주의 (cx_Oracle)
        DBType.POSTGRESQL: "psycopg2",
    }

    module_name = module_map.get(db_type)
    if not module_name:
        raise ValueError(f"지원하지 않는 DB 타입: {db_type}")

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            f"DB 드라이버 '{module_name}'가 설치되어 있지 않습니다. pip install {module_name}"
        )


def get_connection(db: str):
    db = db.upper()
    cipher = AESCipher()  # TODO key정보 환경변수에 숨기기
    
    auth = None
    db_type = None
    
    if db in Oracle_auth:
        if db == "LFMDW":
            db_type = DBType.ORACLE_CX
        else:
            db_type = DBType.ORACLE
        auth = Oracle_auth[db]
    elif db in Maria_auth:
        db_type = DBType.MYSQL
        auth = Maria_auth[db]
    elif db in Postgre_auth:
        db_type = DBType.POSTGRESQL
        auth = Postgre_auth[db]
    else:
        raise ValueError(f"지원하지 않는 DB : {db}")

    cfg = DBConfig(
        db_type=db_type,
        host=cipher.decrypt(auth['ip']),
        port=int(cipher.decrypt(auth['port'])),
        user=cipher.decrypt(auth['user']),
        password=cipher.decrypt(auth['pw']),
        database=cipher.decrypt(auth['service']),
    )

    
    driver = load_driver(cfg.db_type)

    if cfg.db_type == DBType.MYSQL:
        return driver.connect(
            host=cfg.host, port=cfg.port,
            user=cfg.user, password=cfg.password, database=cfg.database
        )

    elif cfg.db_type == DBType.ORACLE:
        dsn = driver.makedsn(cfg.host, cfg.port, service_name=cfg.database)
        return driver.connect(user=cfg.user, password=cfg.password, dsn=dsn)

    elif cfg.db_type == DBType.ORACLE_CX:
        # cx_Oracle의 DSN 생성 및 연결 방식
        dsn = driver.makedsn(cfg.host, cfg.port, service_name=cfg.database)
        return driver.connect(user=cfg.user, password=cfg.password, dsn=dsn)

    elif cfg.db_type == DBType.POSTGRESQL:
        return driver.connect(
            host=cfg.host, port=cfg.port,
            user=cfg.user, password=cfg.password, dbname=cfg.database
        )




class Database:
    """
    with 구문에서 사용하는 공통 DB 인터페이스 래퍼

    예:
        cfg = DBConfig(...)
        with Database(cfg) as db:
            rows = db.query("SELECT * FROM table WHERE id = %s", (1,))
    """

    def __init__(self, schema: str):
        self.schema = schema
        self.conn = None
        self.cursor = None

    # 1. with 구문을 쓰기 위한 진입/종료 메서드
    def __enter__(self) -> "Database":
        self.conn = get_connection(self.schema)
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc, tb):
        # 예외가 없으면 commit, 있으면 rollback
        if exc_type is None:
            try:
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        else:
            self.conn.rollback()

        # 리소스 정리
        if self.cursor is not None:
            self.cursor.close()
        if self.conn is not None:
            self.conn.close()
            
    def _row_to_dict(self, row):
        """
        - MySQL / PostgreSQL: DictCursor → 이미 dict 이므로 그대로 리턴
        - Oracle 등: tuple → cursor.description 보고 dict로 변환
        """
        if row is None:
            return None

        if isinstance(row, dict):
            return row

        # tuple → dict 변환
        cols = [col[0] for col in self.cursor.description]
        return {col: row[idx] for idx, col in enumerate(cols)}

    def rows_to_dict_list(self, rows) -> List[Dict[str, Any]]:
        return [self._row_to_dict(r) for r in rows]

    # 2. 공통 인터페이스 메서드들
    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        """
        SELECT / INSERT / UPDATE / DELETE 등 공통 실행
        """
        if params is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, params)
        return self.cursor

    def executemany(self, sql: str, param_list: Sequence[Sequence[Any]]):
        """
        bulk insert/update용
        """
        self.cursor.executemany(sql, param_list)
        return self.cursor

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size: int):
        return self.cursor.fetchmany(size)

    def query(self, sql: str, params: Optional[Sequence[Any]] = None):
        """
        SELECT 편의 메서드: 실행 후 fetchall까지 한 번에
        """
        self.execute(sql, params)
        return self.fetchall()
    
    def commit(self):
        """블록 중간에 명시적 커밋 필요 시 사용"""
        self.conn.commit()

    def rollback(self):
        """블록 중간에 명시적 롤백 필요 시 사용"""
        self.conn.rollback()

"""
# 사용방법

with Database("DBNAME") as db:
    db.execute("CREATE TABLE IF NOT EXISTS logs(id SERIAL PRIMARY KEY, msg TEXT)")
    db.execute("INSERT INTO logs(msg) VALUES (%s)", ("hello postgres",))
    rows = db.query("SELECT * FROM logs")
    print("PostgreSQL:", rows)


# 파라미터 바인딩 방식 정리
# =========================

## 1) Oracle (cx_Oracle / oracledb)
- 플레이스홀더: :name 또는 :1
- Python DB-API execute:
    cursor.execute(sql, {"id": 1})
    cursor.execute(sql, (1, "ACTIVE"))

### 예시 (이름 기반)
sql = '''
SELECT *
FROM users
WHERE id = :id
  AND status = :status
'''
params = {"id": 1001, "status": "ACTIVE"}
cursor.execute(sql, params)

### 예시 (위치 기반)
sql = '''
SELECT *
FROM users
WHERE id = :1
  AND status = :2
'''
params = (1001, "ACTIVE")
cursor.execute(sql, params)


## 2) MySQL (mysqlclient / PyMySQL / mysql-connector)
- 플레이스홀더: %s 또는 %(name)s
- 타입 상관없이 무조건 %s 사용
- Python DB-API execute:
    cursor.execute(sql, (1,))
    cursor.execute(sql, {"id": 1})

### 예시 (위치 기반)
sql = '''
SELECT *
FROM users
WHERE id = %s
  AND status = %s
'''
params = (1001, "ACTIVE")
cursor.execute(sql, params)

### 예시 (이름 기반)
sql = '''
SELECT *
FROM users
WHERE id = %(id)s
  AND status = %(status)s
'''
params = {"id": 1001, "status": "ACTIVE"}
cursor.execute(sql, params)


## 3) PostgreSQL (psycopg2 / psycopg)
- 플레이스홀더: %s 또는 %(name)s
- PostgreSQL 서버의 $1/$2와 혼동하지 말 것 (Python 드라이버에서는 %s가 정식)
- Python DB-API execute:
    cursor.execute(sql, (1,))
    cursor.execute(sql, {"id": 1})

### 예시 (위치 기반)
sql = '''
SELECT *
FROM users
WHERE id = %s
  AND status = %s
'''
params = (1001, "ACTIVE")
cursor.execute(sql, params)

### 예시 (이름 기반)
sql = '''
SELECT *
FROM users
WHERE id = %(id)s
  AND status = %(status)s
'''
params = {"id": 1001, "status": "ACTIVE"}
cursor.execute(sql, params)


# DB별 요약
# ---------
# Oracle      : :id, :status / :1, :2 형식
# MySQL       : %s
# PostgreSQL  : %s
"""
