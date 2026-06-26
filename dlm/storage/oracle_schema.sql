-- DLM System Metadata Schema for Oracle Database
-- 데이터 생명주기 관리(DLM) 시스템의 상태 및 이력을 관리하기 위한 오라클 메타데이터 스키마 정의

-- 1. 관리 대상 오브젝트 마스터
-- ID 생성을 위한 전용 시퀀스 선언
CREATE SEQUENCE SEQ_DLM_OBJECTS START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE DLM_OBJECTS (
    ID NUMBER DEFAULT SEQ_DLM_OBJECTS.NEXTVAL NOT NULL,      -- 오브젝트 식별자 (PK)
    NAME VARCHAR2(255) NOT NULL,                             -- 오브젝트 물리 명칭 (예: 'USERS', 'USERS$P_202606', 'IDX_USERS_ID')
    OBJECT_TYPE VARCHAR2(50) NOT NULL,                       -- 오브젝트의 논리 유형 (TABLE, PARTITION, INDEX)
    PARENT_ID NUMBER,                                        -- 부모 테이블 식별자 (PARTITION 이나 INDEX가 어떤 TABLE에 소속되어 있는지 표시)
    IS_PARTITIONED NUMBER(1) DEFAULT 0,                      -- 파티션 테이블 여부 (1: 파티션 분할이 적용된 부모 테이블, 0: 일반 단일 테이블 또는 파티션/인덱스 자체)
    BACKUP_FLAG CHAR(1) DEFAULT 'N',                         -- 백업 정책 대상 여부 ('Y': 삭제 전 백업 성공 이력 필수, 'N': 백업 없이 삭제 허용)
    DELETE_FLAG CHAR(1) DEFAULT 'N',                         -- 데이터 자동 삭제 정책 대상 여부 ('Y': 주기적인 데이터 삭제 대상, 'N': 자동 삭제 비대상)
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,          -- 메타데이터 등록 일시
    CONSTRAINT PK_DLM_OBJECTS PRIMARY KEY (ID),
    CONSTRAINT UQ_DLM_OBJECTS_NAME UNIQUE (NAME),
    CONSTRAINT CHK_DLM_OBJ_TYPE CHECK (OBJECT_TYPE IN ('TABLE', 'PARTITION', 'INDEX')),
    CONSTRAINT CHK_DLM_BACKUP_FLG CHECK (BACKUP_FLAG IN ('Y', 'N')),
    CONSTRAINT CHK_DLM_DELETE_FLG CHECK (DELETE_FLAG IN ('Y', 'N')),
    CONSTRAINT CHK_DLM_IS_PART CHECK (IS_PARTITIONED IN (0, 1)),
    CONSTRAINT FK_DLM_OBJ_PARENT FOREIGN KEY (PARENT_ID) REFERENCES DLM_OBJECTS(ID) ON DELETE CASCADE
);

COMMENT ON TABLE DLM_OBJECTS IS 'DLM 시스템에서 추적하고 제어하는 모든 데이터베이스 오브젝트(테이블, 파티션, 인덱스)의 메타 정보를 보관하는 마스터 테이블';
COMMENT ON COLUMN DLM_OBJECTS.ID IS '오브젝트 식별자 (시퀀스 기반 PK)';
COMMENT ON COLUMN DLM_OBJECTS.NAME IS '오브젝트 물리 명칭 (예: 테이블명, 파티션명, 인덱스명)';
COMMENT ON COLUMN DLM_OBJECTS.OBJECT_TYPE IS '오브젝트의 논리 유형 (TABLE: 일반/부모 테이블, PARTITION: 파티션, INDEX: 인덱스)';
COMMENT ON COLUMN DLM_OBJECTS.PARENT_ID IS '부모 테이블 식별자 (PARTITION 이나 INDEX가 소속된 부모 TABLE의 ID, 일반 TABLE인 경우 NULL)';
COMMENT ON COLUMN DLM_OBJECTS.IS_PARTITIONED IS '파티션 테이블 여부 (1: 파티션 분할이 적용된 부모 테이블, 0: 일반 테이블 또는 파티션/인덱스)';
COMMENT ON COLUMN DLM_OBJECTS.BACKUP_FLAG IS '백업 정책 대상 여부 (Y: 삭제 전 백업 성공 이력 확인 필수, N: 백업 없이 삭제 허용)';
COMMENT ON COLUMN DLM_OBJECTS.DELETE_FLAG IS '데이터 자동 삭제 정책 대상 여부 (Y: 주기적인 데이터 삭제/TRUNCATE 대상, N: 자동 삭제 비대상)';
COMMENT ON COLUMN DLM_OBJECTS.CREATED_AT IS '메타데이터가 시스템에 최초 등록된 일시';


-- 2. 오브젝트별 물리 용량 및 행 수 이력
-- ID 생성을 위한 전용 시퀀스 선언
CREATE SEQUENCE SEQ_DLM_VOLUME_HISTORY START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE DLM_VOLUME_HISTORY (
    ID NUMBER DEFAULT SEQ_DLM_VOLUME_HISTORY.NEXTVAL NOT NULL, -- 용량 이력 식별자 (PK)
    OBJECT_ID NUMBER NOT NULL,                                 -- 대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)
    COLLECTED_DATE VARCHAR2(10) NOT NULL,                      -- 용량 수집 일자 (형식: YYYY-MM-DD)
    PHYSICAL_SIZE_BYTES NUMBER NOT NULL,                       -- 수집 시점의 디스크 물리적 점유 크기 (단위: Bytes)
    ROW_COUNT NUMBER NOT NULL,                                 -- 수집 시점의 실제 레코드 건수 (행 수)
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,            -- 데이터 적재 일시
    CONSTRAINT PK_DLM_VOLUME_HISTORY PRIMARY KEY (ID),
    CONSTRAINT FK_DLM_VOL_OBJ FOREIGN KEY (OBJECT_ID) REFERENCES DLM_OBJECTS(ID) ON DELETE CASCADE,
    CONSTRAINT UQ_DLM_VOL_OBJ_DATE UNIQUE (OBJECT_ID, COLLECTED_DATE)
);

COMMENT ON TABLE DLM_VOLUME_HISTORY IS '수집기(Collector)가 매일 측정한 테이블, 파티션, 인덱스의 데이터 물리 크기 및 레코드 수를 저장하는 이력 테이블';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.ID IS '용량 이력 식별자 (시퀀스 기반 PK)';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.OBJECT_ID IS '대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.COLLECTED_DATE IS '용량 및 건수 수집 일자 (형식: YYYY-MM-DD)';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.PHYSICAL_SIZE_BYTES IS '수집 시점의 디스크 물리적 점유 크기 (단위: Bytes)';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.ROW_COUNT IS '수집 시점의 실제 레코드 건수 (행 수)';
COMMENT ON COLUMN DLM_VOLUME_HISTORY.CREATED_AT IS '용량 이력 레코드가 생성된 일시';


-- 3. 백업 이력 및 진행 단계 추적
-- ID 생성을 위한 전용 시퀀스 선언
CREATE SEQUENCE SEQ_DLM_BACKUP_HISTORY START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE DLM_BACKUP_HISTORY (
    ID NUMBER DEFAULT SEQ_DLM_BACKUP_HISTORY.NEXTVAL NOT NULL, -- 백업 작업 식별자 (PK)
    OBJECT_ID NUMBER NOT NULL,                                 -- 백업 대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)
    BACKUP_TYPE VARCHAR2(50) NOT NULL,                         -- 백업 주기 정책 유형 (DAILY, MONTHLY, YEARLY, FULL)
    STATUS VARCHAR2(50) NOT NULL,                              -- 백업 현재 상태 (STARTED, DUMPING, COMPRESSING, COMPLETED, FAILED)
    STEP_DETAILS VARCHAR2(4000),                               -- 실시간으로 진행되는 세부 단계 기록용 텍스트 필드
    BACKUP_PATH VARCHAR2(1000),                                -- 생성된 백업 파일의 물리 저장 경로
    STARTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,            -- 백업 시작 일시
    COMPLETED_AT TIMESTAMP,                                    -- 백업 완료/실패 일시
    CONSTRAINT PK_DLM_BACKUP_HISTORY PRIMARY KEY (ID),
    CONSTRAINT CHK_DLM_BKP_TYPE CHECK (BACKUP_TYPE IN ('DAILY', 'MONTHLY', 'YEARLY', 'FULL')),
    CONSTRAINT CHK_DLM_BKP_STATUS CHECK (STATUS IN ('STARTED', 'DUMPING', 'COMPRESSING', 'COMPLETED', 'FAILED')),
    CONSTRAINT FK_DLM_BKP_OBJ FOREIGN KEY (OBJECT_ID) REFERENCES DLM_OBJECTS(ID) ON DELETE CASCADE
);

COMMENT ON TABLE DLM_BACKUP_HISTORY IS '백업 프로세스(Backup Manager)의 실행 결과와 실시간 상세 진행 상태를 모니터링하기 위한 이력 테이블';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.ID IS '백업 작업 식별자 (시퀀스 기반 PK)';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.OBJECT_ID IS '백업 대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.BACKUP_TYPE IS '백업 주기 정책 유형 (DAILY: 일단위, MONTHLY: 월단위, YEARLY: 년단위, FULL: 전체 백업)';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.STATUS IS '백업 작업의 현재 진행 상태 (STARTED, DUMPING, COMPRESSING, COMPLETED, FAILED)';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.STEP_DETAILS IS '실시간으로 진행되는 세부 단계 기록 (예: 1단계 dump 완료, 2단계 압축 중 등)';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.BACKUP_PATH IS '생성된 백업 파일의 물리 디스크 경로';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.STARTED_AT IS '백업 작업이 시작된 일시';
COMMENT ON COLUMN DLM_BACKUP_HISTORY.COMPLETED_AT IS '백업 작업이 완료되거나 실패한 일시';


-- 4. 데이터 삭제 이력
-- ID 생성을 위한 전용 시퀀스 선언
CREATE SEQUENCE SEQ_DLM_DELETE_HISTORY START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE DLM_DELETE_HISTORY (
    ID NUMBER DEFAULT SEQ_DLM_DELETE_HISTORY.NEXTVAL NOT NULL, -- 삭제 작업 식별자 (PK)
    OBJECT_ID NUMBER NOT NULL,                                 -- 삭제 대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)
    DELETE_TYPE VARCHAR2(50) NOT NULL,                         -- 삭제 처리 형태 및 범위 (DAILY, MONTHLY, YEARLY, TRUNCATE, DROP_PARTITION)
    STATUS VARCHAR2(50) NOT NULL,                              -- 삭제 처리 결과 상태 (COMPLETED, FAILED)
    STARTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,            -- 삭제 작업 시작 일시
    COMPLETED_AT TIMESTAMP,                                    -- 삭제 작업 완료 일시
    ERROR_MESSAGE VARCHAR2(4000),                              -- 작업 실패 시 예외 또는 오류 원인 상세 메시지
    CONSTRAINT PK_DLM_DELETE_HISTORY PRIMARY KEY (ID),
    CONSTRAINT CHK_DLM_DEL_TYPE CHECK (DELETE_TYPE IN ('DAILY', 'MONTHLY', 'YEARLY', 'TRUNCATE', 'DROP_PARTITION')),
    CONSTRAINT CHK_DLM_DEL_STATUS CHECK (STATUS IN ('COMPLETED', 'FAILED')),
    CONSTRAINT FK_DLM_DEL_OBJ FOREIGN KEY (OBJECT_ID) REFERENCES DLM_OBJECTS(ID) ON DELETE CASCADE
);

COMMENT ON TABLE DLM_DELETE_HISTORY IS '삭제 정책(Data Deleter)에 의해 수행된 데이터 삭제 작업 및 TRUNCATE 이력을 보관하는 테이블';
COMMENT ON COLUMN DLM_DELETE_HISTORY.ID IS '삭제 작업 식별자 (시퀀스 기반 PK)';
COMMENT ON COLUMN DLM_DELETE_HISTORY.OBJECT_ID IS '삭제 대상 오브젝트 식별자 (FK: DLM_OBJECTS.ID)';
COMMENT ON COLUMN DLM_DELETE_HISTORY.DELETE_TYPE IS '삭제 처리 형태 및 범위 (일/월/년 데이터 삭제, TRUNCATE, 파티션 DROP 등)';
COMMENT ON COLUMN DLM_DELETE_HISTORY.STATUS IS '삭제 처리 결과 상태 (COMPLETED: 성공, FAILED: 실패)';
COMMENT ON COLUMN DLM_DELETE_HISTORY.STARTED_AT IS '삭제 작업이 시작된 일시';
COMMENT ON COLUMN DLM_DELETE_HISTORY.COMPLETED_AT IS '삭제 작업이 완료되거나 실패한 일시';
COMMENT ON COLUMN DLM_DELETE_HISTORY.ERROR_MESSAGE IS '작업 실패 시 발생한 데이터베이스 에러 또는 정합성 검증 실패 예외 상세 메시지';
