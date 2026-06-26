import os

# DLM 프로젝트 기본 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 메타데이터 데이터베이스 경로
# 기본값으로 workspace 루트의 dlm_metadata.db를 사용합니다.
METADATA_DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "dlm_metadata.db")

# 테스트용 대상 데이터베이스 경로 (일반/파티션 테이블 시뮬레이션용)
TARGET_DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "dlm_target.db")

# 백업 파일들이 저장될 디렉토리 경로
BACKUP_DIR = os.path.join(os.path.dirname(BASE_DIR), "dlm_backups")

# 리오그(Reorg) 관련 임계 용량 (단위: Bytes)
# 일반 테이블의 물리 크기가 이 값을 초과하면 담당자 수동 작업 알림(수동 분기)이 발생합니다.
# 기본 임계치는 10MB (10 * 1024 * 1024) 로 설정합니다.
REORG_THRESHOLD_BYTES = 10 * 1024 * 1024

# 동시 작업 제한 설정 (NFR-02)
# Disk I/O 병목 방지를 위해 백업, 삭제, 리오그 등의 동시 실행 태스크 수를 제한합니다.
MAX_CONCURRENT_JOBS = 2

# 디렉토리 자동 생성
os.makedirs(BACKUP_DIR, exist_ok=True)
