# 씨부엉 코드 스프린트 (CBU Code Sprint)

교내 동아리 홍보전에서 사용할 USB portable 데스크톱 GUI 타자 게임 프로젝트입니다.

참가자가 이름, 전화번호, 주언어를 입력한 뒤 본인 언어의 짧은 코드를 빠르고 정확하게 따라 치고, 결과를 점수화해 리더보드에 반영합니다.

상세 기획/구현 명세는 `docs/PROJECT_SPEC.md`를 봅니다.
현장 실행/백업/삭제 절차는 `docs/OPERATOR_GUIDE.md`를 봅니다.

## 핵심 방향

- 앱 형태: Windows/macOS 데스크톱 GUI 앱
- 기술 스택: Python, PySide6, SQLite, PyInstaller onedir
- 데이터 저장: USB 루트 기준 `data/leaderboard.sqlite`
- 실행 방식: USB 안에 Windows 앱과 macOS 앱을 각각 배치
- 운영 방식: 한 번에 한 노트북에서만 실행하고, 같은 SQLite DB를 OS 간 번갈아 사용
- 개인정보: DB에는 저장하되 공개 리더보드에는 전화번호 미표시, 이름은 마스킹

## 현재 구현 상태

- Python 패키지 뼈대: `src/cbu_code_sprint/`
- USB home 경로 처리: `--home` 기준 `data/config/assets/exports/backups` 사용
- SQLite 스키마/저장/리더보드/CSV/백업 로직
- USB DB 보호용 단일 인스턴스 lock
- 점수 계산, 이름 마스킹, 전화번호 정규화 유틸
- 언어별 snippet 15개: `config/snippets.json`
- PySide6 GUI v1: 시작/게임/결과/리더보드/관리자 기본 화면
- 시작 스크립트: `Start-Windows.bat`, `Start-macOS.command`

## 개발 실행

PySide6가 설치되어 있어야 GUI가 뜹니다.

```bash
python3 -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m cbu_code_sprint --home .
```

macOS 개발 fallback 실행:

```bash
./Start-macOS.command
```

Windows 개발 fallback 실행:

```bat
Start-Windows.bat
```

## 테스트

현재 테스트는 PySide6 없이도 실행되는 core 로직 중심입니다.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=src python3 -m compileall -q src tests
```

## macOS 패키징

repo-local `.venv`에 개발 의존성이 설치된 상태에서 실행합니다.

```bash
./scripts/build_macos.sh
```

결과물:

- `dist/CBU Code Sprint.app`
- USB 구조용 복사본: `apps/macos/CBU Code Sprint.app`

`apps/macos/`와 `dist/`는 빌드 산출물이라 git 추적 대상에서 제외합니다.

## 관리자 화면

- 진입: `Ctrl + Shift + A`
- 기본 비밀번호: `cbu`
- 운영 전에는 환경변수 `CBU_CODE_SPRINT_ADMIN_PASSWORD`로 변경하는 것을 권장합니다.

관리자 기능 v1:

- 현재 DB 경로 표시
- 행사 날짜 변경
- 전체/오늘 참가자 및 시도 수 표시
- 참가자 목록 표시(관리자 전용 실명/전화번호 포함)
- 선택 날짜 시도 기록 표시(관리자 전용 실명/전화번호 포함)
- DB 백업 생성
- 공개 리더보드 CSV export
- 전체 데이터 CSV export(개인정보 포함)
- 현재 날짜 데이터 삭제(확인 다이얼로그 + 사전 백업)
- 리더보드 초기화(확인 다이얼로그 + 사전 백업)
- 개인정보 삭제/익명화(확인 다이얼로그 + 사전 백업)
- 전체 데이터 삭제(확인 다이얼로그 + 사전 백업)

## 예상 USB 구조

```text
CBU-Code-Sprint/
├─ Start-Windows.bat
├─ Start-macOS.command
├─ apps/
│  ├─ windows/
│  │  └─ CBU Code Sprint/
│  │     ├─ CBU Code Sprint.exe
│  │     └─ PySide6/Qt/Python 런타임 등 필요한 파일들
│  └─ macos/
│     └─ CBU Code Sprint.app
├─ data/
│  └─ leaderboard.sqlite
├─ config/
│  └─ snippets.json
├─ assets/
│  └─ mascot/
├─ exports/
└─ backups/
```

## 다음 구현 세션 시작

새 세션에서는 아래처럼 시작하면 됩니다.

```text
/Users/geonha/DEV/CBU-Code-Sprint 저장소에서 씨부엉 코드 스프린트 구현을 시작해줘. 먼저 README.md와 docs/PROJECT_SPEC.md를 읽고, 구현 계획과 작업 범위를 짧게 보고한 뒤 승인받고 진행해. commit/push/release/publish는 하지 마.
```
