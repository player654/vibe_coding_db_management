# DLM 프로젝트 디렉토리 구조 및 파일 명세서

본 문서는 데이터 생명주기 관리(DLM) 시스템 프로젝트의 디렉토리 구조와 각 파일의 사용 용도를 명세하고 추적하기 위해 작성되었습니다.

## 1. 디렉토리 트리 구조

```
vibe_coding_db_management/
├── .venv/                      # Python 가상환경 디렉토리
│   └── bin/
│       ├── pytest              # unittest 기반 Mock 테스트 기동을 위한 래퍼
│       ├── ruff                # 파이썬 문법 에러 체크를 위한 래퍼
│       └── mypy                # 타입 체크 Mock 래퍼
├── .github/
│   └── copilot-instructions.md # 개발자 Copilot 행동 규칙 지침
├── common/                     # 공통 유틸리티 패키지 디렉토리
│   ├── __init__.py
│   └── lf_database.py          # (이동 완료) 복호화 및 오라클 12c Exadata 접속 공통 모듈
├── dlm/                        # DLM 배치 시스템 패키지 루트
│   ├── __init__.py
│   ├── config.py               # DLM 시스템 전역 환경 설정 파일 (DB 경로, 임계치 등)
│   ├── storage/                # 데이터베이스 스토리지 스키마 및 접속 관리
│   │   ├── __init__.py
│   │   ├── oracle_schema.sql   # [오라클 전용] DLM 메타테이블 스키마 DDL (COMMENT ON 포함)
│   │   └── db.py               # common/lf_database.py 연동 및 Mock SQLite 폴백 기능 탑재 매니저
│   ├── core/                   # DLM 핵심 비즈니스 배치 로직 엔진
│   │   ├── __init__.py
│   │   ├── inspector.py        # 오라클 데이터 사전 기반 스키마/파티션/인덱스 분석 엔진
│   │   ├── collector.py        # 일별 물리 용량 및 행 수 통계 수집 모듈
│   │   ├── backup.py           # (예정) 다중 주기 백업 관리 모듈
│   │   ├── deleter.py          # (예정) 정합성 교차 검증 및 데이터 삭제 모듈
│   │   ├── reorg.py            # (예정) 일반/파티션 테이블 자동/수동 리오그 제어 모듈
│   │   └── concurrency.py      # (예정) I/O 병목 방지 동시 실행 제어기
│   ├── tests/                  # 단위 및 모의 테스트 하네스
│   │   ├── __init__.py
│   │   ├── test_db.py          # OracleDBManager 및 Mock DB 연결 단위 테스트
│   │   ├── test_inspector.py   # SchemaInspector 오라클 딕셔너리 분석 시뮬레이션 테스트
│   │   └── test_collector.py   # CapacityCollector 일별 용량 수집 시뮬레이션 테스트
│   └── main.py                 # (예정) DLM 배치 일괄 제어 및 실행 진입점
├── AGENTS.md                   # AI 에이전트 행동 지침 및 개발 하네스 규칙 (정적)
├── SPEC.md                     # 시스템 기능, 비기능 요구사항, Airflow 환경 정의서 (정적)
├── TASKS.md                    # 실시간 작업 진행 상황 체크리스트 (동적)
├── JOURNAL.md                  # 디버깅 시도 및 의사결정 기록 append-only 저널 (동적)
└── DIRECTORY.md                # (본 문서) 디렉토리 구조 및 파일 명세서
```

---

## 2. 주요 파일 사용 용도 명세

| 파일/디렉토리 경로 | 역할 및 사용 용도 | 현재 상태 |
|---|---|---|
| `AGENTS.md` | 에이전트 다중 페르소나 행동 지침 및 하네스 검증 규칙 정의 | 고정 (정적) |
| `SPEC.md` | 오라클 Exadata 연동 규격 및 Apache Airflow 2.2.4 배치 환경 스펙 정의 | 최신화 완료 |
| `TASKS.md` | 매 작업 단계의 시작/완료 상태를 마킹하는 체크리스트 문서 | 실시간 갱신 중 |
| `JOURNAL.md` | 에이전트가 내린 의사결정 근거, 테스트 로그 등을 기록하는 저널 | 실시간 누적 중 |
| [DIRECTORY.md](file:///Users/final97/workdir/vibe_coding_db_management/DIRECTORY.md) | 프로젝트 디렉토리 구조 관리 및 상세 파일 명세 | 최신화 완료 |
| [common/lf_database.py](file:///Users/final97/workdir/vibe_coding_db_management/common/lf_database.py) | Exadata 접속을 위한 공통 암호화 복호화 및 DB 세션 관리 모듈 | 이동 및 연동 완료 |
| [dlm/config.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/config.py) | 저장소 경로, 동시성 세마포어 한계치, 리오그 임계치 정의 | 개발 완료 |
| [dlm/storage/oracle_schema.sql](file:///Users/final97/workdir/vibe_coding_db_management/dlm/storage/oracle_schema.sql) | 오라클 Exadata 환경에 구축될 한글 컬럼 주석이 완비된 DDL | 개발 완료 |
| [dlm/storage/db.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/storage/db.py) | `common/lf_database.py` 래핑 연동 및 SQLite 모킹 폴백 지원 매니저 | 개발 완료 |
| [dlm/core/inspector.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/core/inspector.py) | 오라클 내장 데이터 사전 뷰를 분석하여 메타데이터를 매핑하는 모듈 | 개발 완료 |
| [dlm/core/collector.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/core/collector.py) | Exadata의 물리 세그먼트 bytes 및 통계 행 수(NUM_ROWS) 적재 모듈 | 개발 완료 |
| [dlm/tests/test_db.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/tests/test_db.py) | `OracleDBManager` 싱글톤 및 SQLite 변환/바인드 변수 단위 테스트 | 개발 완료 |
| [dlm/tests/test_inspector.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/tests/test_inspector.py) | 가상 오라클 딕셔너리 뷰를 에뮬레이트하여 인스펙션 기능 검증 | 개발 완료 |
| [dlm/tests/test_collector.py](file:///Users/final97/workdir/vibe_coding_db_management/dlm/tests/test_collector.py) | 모의 오라클 용량 및 행 수 이력을 스캔하여 메타 DB 적재 기능 검증 | 개발 완료 |
