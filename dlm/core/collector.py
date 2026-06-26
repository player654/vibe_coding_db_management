import logging
from typing import Dict, Tuple
from dlm.storage.db import OracleDBManager

logger = logging.getLogger(__name__)

class CapacityCollector:
    """대상 오라클 데이터베이스의 용량 및 행 수 통계를 수집하여 메타 DB에 기록하는 클래스"""

    def __init__(self, metadata_db: OracleDBManager):
        self.db = metadata_db

    def collect_and_save(self, target_db: OracleDBManager, collected_date: str):
        """
        대상 DB의 세그먼트 용량 및 테이블 행 수 딕셔너리를 조회하여
        메타 DB(DLM_VOLUME_HISTORY)에 적재합니다.
        """
        logger.info(f"[{collected_date}] 일일 용량 통계 수집 시작")

        try:
            # 1. 대상 오라클 DB의 물리 세그먼트 크기 조회
            # USER_SEGMENTS 뷰를 통해 모든 테이블, 파티션, 인덱스 크기를 조회하여 캐싱합니다.
            segments_query = """
                SELECT SEGMENT_NAME, PARTITION_NAME, BYTES 
                FROM USER_SEGMENTS
                WHERE SEGMENT_NAME NOT LIKE 'DLM_%'
            """
            segments_rows = target_db.fetch_all(segments_query)
            
            # (오브젝트명, 파티션명) -> 물리 크기(Bytes) 맵 구성
            # 일반 오브젝트는 파티션명이 None
            segments_map: Dict[Tuple[str, Optional[str]], int] = {}
            for r in segments_rows:
                name = r['SEGMENT_NAME']
                part = r['PARTITION_NAME']
                bytes_size = r['BYTES']
                segments_map[(name, part)] = bytes_size

            # 2. 대상 오라클 DB의 테이블/파티션 행 수 조회
            # 일반 테이블 행 수 캐싱
            tables_query = "SELECT TABLE_NAME, NUM_ROWS FROM USER_TABLES WHERE TABLE_NAME NOT LIKE 'DLM_%'"
            tables_rows = target_db.fetch_all(tables_query)
            
            rows_map: Dict[Tuple[str, Optional[str]], int] = {}
            for r in tables_rows:
                rows_map[(r['TABLE_NAME'], None)] = r['NUM_ROWS'] if r['NUM_ROWS'] is not None else 0

            # 파티션 테이블 행 수 캐싱
            part_rows_query = "SELECT TABLE_NAME, PARTITION_NAME, NUM_ROWS FROM USER_TAB_PARTITIONS WHERE TABLE_NAME NOT LIKE 'DLM_%'"
            part_rows = target_db.fetch_all(part_rows_query)
            for r in part_rows:
                rows_map[(r['TABLE_NAME'], r['PARTITION_NAME'])] = r['NUM_ROWS'] if r['NUM_ROWS'] is not None else 0

            # 3. DLM_OBJECTS에 등록된 마스터 데이터 조회
            objects = self.db.fetch_all("SELECT ID, NAME, OBJECT_TYPE, PARENT_ID, IS_PARTITIONED FROM DLM_OBJECTS")

            # 4. 각 오브젝트의 용량 및 건수 계산 및 저장
            for obj in objects:
                obj_id = obj['ID']
                obj_name = obj['NAME']
                obj_type = obj['OBJECT_TYPE']
                parent_id = obj['PARENT_ID']
                is_partitioned = obj['IS_PARTITIONED']

                size_bytes = 0
                row_count = 0

                if obj_type == "TABLE":
                    if is_partitioned == 1:
                        # 파티션 테이블의 총 크기는 자식 파티션들의 세그먼트 크기 합산
                        # USER_SEGMENTS에서 SEGMENT_NAME=table_name인 모든 파티션의 크기 합산
                        size_bytes = sum(val for (name, part), val in segments_map.items() if name == obj_name)
                        # 행 수도 자식 파티션의 행 수 합산
                        row_count = sum(val for (name, part), val in rows_map.items() if name == obj_name and part is not None)
                    else:
                        # 일반 단일 테이블
                        size_bytes = segments_map.get((obj_name, None), 0)
                        row_count = rows_map.get((obj_name, None), 0)

                elif obj_type == "PARTITION":
                    # 파티션 오브젝트 물리 명칭 규칙: TABLE_NAME$PARTITION_NAME
                    if "$" in obj_name:
                        tbl_name, part_name = obj_name.split("$", 1)
                        size_bytes = segments_map.get((tbl_name, part_name), 0)
                        row_count = rows_map.get((tbl_name, part_name), 0)

                elif obj_type == "INDEX":
                    # 일반 인덱스 혹은 파티션 인덱스의 총 크기 합산
                    size_bytes = sum(val for (name, part), val in segments_map.items() if name == obj_name)
                    
                    # 인덱스의 행 수는 부모 테이블의 행 수와 동일하다고 간주
                    if parent_id:
                        parent_obj = self.db.fetch_one(
                            "SELECT NAME, OBJECT_TYPE, IS_PARTITIONED FROM DLM_OBJECTS WHERE ID = ?;",
                            (parent_id,)
                        )
                        if parent_obj:
                            p_name = parent_obj['NAME']
                            p_type = parent_obj['OBJECT_TYPE']
                            
                            if p_type == "PARTITION":
                                # 파티션에 속한 인덱스인 경우 해당 파티션의 행 수 조회
                                if "$" in p_name:
                                    t_name, pt_name = p_name.split("$", 1)
                                    row_count = rows_map.get((t_name, pt_name), 0)
                            else:
                                # 테이블에 속한 인덱스인 경우 부모 테이블의 총 행 수 조회
                                if parent_obj['IS_PARTITIONED'] == 1:
                                    row_count = sum(val for (name, part), val in rows_map.items() if name == p_name and part is not None)
                                else:
                                    row_count = rows_map.get((p_name, None), 0)

                # 5. 수집 이력 저장 (동작의 DB 독립성을 위해 SELECT 후 INSERT/UPDATE 기법 적용)
                existing = self.db.fetch_one(
                    "SELECT ID FROM DLM_VOLUME_HISTORY WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;",
                    (obj_id, collected_date)
                )

                if existing:
                    self.db.execute(
                        """
                        UPDATE DLM_VOLUME_HISTORY 
                        SET PHYSICAL_SIZE_BYTES = ?, ROW_COUNT = ? 
                        WHERE OBJECT_ID = ? AND COLLECTED_DATE = ?;
                        """,
                        (size_bytes, row_count, obj_id, collected_date)
                    )
                else:
                    self.db.execute(
                        """
                        INSERT INTO DLM_VOLUME_HISTORY (OBJECT_ID, COLLECTED_DATE, PHYSICAL_SIZE_BYTES, ROW_COUNT)
                        VALUES (?, ?, ?, ?);
                        """,
                        (obj_id, collected_date, size_bytes, row_count)
                    )

            logger.info(f"[{collected_date}] 일일 용량 통계 수집 및 적재 완료")

        except Exception as e:
            logger.error(f"용량 통계 수집 중 오류 발생: {e}")
            raise e
