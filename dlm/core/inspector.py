import logging
from typing import Optional
from dlm.storage.db import OracleDBManager

logger = logging.getLogger(__name__)

class SchemaInspector:
    """오라클 데이터베이스의 데이터 사전 뷰를 분석하여 메타데이터 마스터에 등록하는 클래스"""

    def __init__(self, metadata_db: OracleDBManager):
        self.db = metadata_db

    def inspect_and_register(self, target_db: OracleDBManager):
        """
        대상 오라클 DB의 데이터 사전을 조회하여 신규 테이블, 파티션, 인덱스를 감지하고
        메타데이터 DB(DLM_OBJECTS)에 등록 및 동기화합니다.
        """
        logger.info("대상 오라클 DB 데이터 사전 분석 시작")

        try:
            # 1. 파티션 테이블 마스터 등록
            # USER_PART_TABLES를 조회하여 파티션 테이블 부모 목록을 추출합니다.
            part_tables_query = """
                SELECT TABLE_NAME 
                FROM USER_PART_TABLES 
                WHERE TABLE_NAME NOT LIKE 'DLM_%'
            """
            part_tables = target_db.fetch_all(part_tables_query)
            
            for pt in part_tables:
                t_name = pt['TABLE_NAME']
                # 부모 테이블을 TABLE 유형으로, IS_PARTITIONED=1로 등록
                self._get_or_create_object(
                    name=t_name,
                    obj_type="TABLE",
                    is_partitioned=1
                )

            # 2. 세부 파티션 목록 등록
            # USER_TAB_PARTITIONS를 조회하여 각 파티션의 소속 정보를 매핑합니다.
            partitions_query = """
                SELECT TABLE_NAME, PARTITION_NAME 
                FROM USER_TAB_PARTITIONS 
                WHERE TABLE_NAME NOT LIKE 'DLM_%'
            """
            partitions = target_db.fetch_all(partitions_query)
            
            for part in partitions:
                parent_name = part['TABLE_NAME']
                part_name = part['PARTITION_NAME']
                
                # 부모 테이블 ID 조회
                parent_obj = self.db.fetch_one(
                    "SELECT ID FROM DLM_OBJECTS WHERE NAME = ? AND OBJECT_TYPE = 'TABLE';",
                    (parent_name,)
                )
                
                if parent_obj:
                    # 파티션 오브젝트 물리 명칭은 'TABLE_NAME$PARTITION_NAME' 형태로 등록
                    # (예: USERS$P_202606)
                    full_part_name = f"{parent_name}${part_name}"
                    self._get_or_create_object(
                        name=full_part_name,
                        obj_type="PARTITION",
                        parent_id=parent_obj['ID'],
                        is_partitioned=0
                    )
                else:
                    logger.warning(f"파티션 {part_name}의 부모 테이블 {parent_name}이 등록되어 있지 않습니다.")

            # 3. 일반 테이블(비파티션 테이블) 등록
            # USER_TABLES 중 USER_PART_TABLES에 존재하지 않는 순수 테이블만 추출합니다.
            normal_tables_query = """
                SELECT TABLE_NAME 
                FROM USER_TABLES 
                WHERE TABLE_NAME NOT LIKE 'DLM_%'
                  AND TABLE_NAME NOT IN (SELECT TABLE_NAME FROM USER_PART_TABLES)
            """
            normal_tables = target_db.fetch_all(normal_tables_query)
            
            for nt in normal_tables:
                t_name = nt['TABLE_NAME']
                self._get_or_create_object(
                    name=t_name,
                    obj_type="TABLE",
                    is_partitioned=0
                )

            # 4. 인덱스 목록 등록
            # USER_INDEXES를 조회하여 테이블과 연관된 인덱스를 매핑합니다.
            indexes_query = """
                SELECT INDEX_NAME, TABLE_NAME 
                FROM USER_INDEXES 
                WHERE TABLE_NAME NOT LIKE 'DLM_%'
            """
            indexes = target_db.fetch_all(indexes_query)
            
            for idx in indexes:
                idx_name = idx['INDEX_NAME']
                tbl_name = idx['TABLE_NAME']
                
                # 인덱스의 대상 테이블 ID 조회
                target_obj = self.db.fetch_one(
                    "SELECT ID FROM DLM_OBJECTS WHERE NAME = ? AND OBJECT_TYPE = 'TABLE';",
                    (tbl_name,)
                )
                
                if target_obj:
                    self._get_or_create_object(
                        name=idx_name,
                        obj_type="INDEX",
                        parent_id=target_obj['ID'],
                        is_partitioned=0
                    )
                else:
                    logger.warning(f"인덱스 {idx_name}의 대상 테이블 {tbl_name}이 등록되어 있지 않습니다.")

            logger.info("오라클 DB 데이터 사전 분석 및 메타 동기화 완료")

        except Exception as e:
            logger.error(f"오라클 데이터 사전 분석 중 오류 발생: {e}")
            raise e

    def _get_or_create_object(self, name: str, obj_type: str, parent_id: Optional[int] = None, is_partitioned: int = 0) -> int:
        """오브젝트가 존재하면 ID를 반환하고, 없으면 신규 등록 후 ID를 반환합니다."""
        existing = self.db.fetch_one(
            "SELECT ID FROM DLM_OBJECTS WHERE NAME = ?;",
            (name,)
        )
        if existing:
            return existing['ID']

        insert_query = """
            INSERT INTO DLM_OBJECTS (NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED, BACKUP_FLAG, DELETE_FLAG)
            VALUES (?, ?, ?, ?, 'N', 'N')
        """
        row_id = self.db.execute_insert(insert_query, (name, obj_type, parent_id, is_partitioned))
        logger.info(f"신규 오브젝트 등록: {name} (유형: {obj_type}, ID: {row_id})")
        return row_id
