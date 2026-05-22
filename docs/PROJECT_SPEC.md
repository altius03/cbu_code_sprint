# 씨부엉 코드 스프린트 기획/구현 명세

## 1. 프로젝트 개요

- 한글명: 씨부엉 코드 스프린트
- 영문명: CBU Code Sprint
- 폴더명: CBU-Code-Sprint
- 용도: 교내 동아리 홍보전에서 사용할 코드 따라치기 게임
- 핵심 흐름: 참가자 정보 입력 → 주언어별 코드 타이핑 → 점수 계산 → 리더보드 반영
- 행사 기간: 2~3일 운영을 전제로 하며, 모든 기록에는 날짜를 포함한다.

## 2. 앱 형태와 기술 스택

- 웹앱이 아니라 데스크톱 GUI 앱으로 만든다.
- Windows와 macOS를 모두 지원한다.
- 단일 실행파일 하나로 양 OS를 모두 지원하는 것이 아니라, 같은 USB 폴더 안에 Windows용 앱과 macOS용 앱을 각각 넣는다.
- Windows 앱과 macOS 앱은 같은 USB의 SQLite DB 파일을 번갈아 사용한다.

추천 기술 스택:

- Python
- PySide6
- SQLite
- PyInstaller onedir 패키징

## 3. USB portable 구조

USB는 exFAT 포맷을 권장한다.

최종 구조 목표:

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

실행:

- Windows: `Start-Windows.bat`
- macOS: `Start-macOS.command`

중요 원칙:

- 앱은 절대 AppData, `~/Library/Application Support`, `/Users/geonha/Desktop` 같은 OS별 사용자 경로에 DB를 저장하면 안 된다.
- 항상 USB 루트 기준 `data/leaderboard.sqlite`를 사용한다.
- 시작 스크립트가 앱에 `--home` 인자로 USB 루트를 넘기고, 앱은 그 경로 기준으로 `data/config/assets/exports/backups`를 찾는다.
- Desktop에 있는 원본 마스코트 경로를 앱에서 직접 참조하지 말고, 필요한 파일을 `assets/mascot/`로 복사해서 영어 파일명으로 사용한다.

시작 스크립트 초안:

Windows `Start-Windows.bat`:

```bat
@echo off
set ROOT=%~dp0
"%ROOT%apps\windows\CBU Code Sprint\CBU Code Sprint.exe" --home "%ROOT%"
```

macOS `Start-macOS.command`:

```bash
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/apps/macos/CBU Code Sprint.app/Contents/MacOS/CBU Code Sprint" --home "$DIR"
```

## 4. DB 공유 방식

- Windows와 macOS가 같은 `USB/data/leaderboard.sqlite`를 번갈아 사용한다.
- 동시에 여러 노트북에서 실행하는 방식은 아니다.
- 한 번에 한 노트북에서만 실행한다.
- 예: Windows에서 실행 → 종료 → USB 안전 제거 → macOS에서 실행 → 같은 리더보드 이어서 사용.
- 같은 앱 중복 실행 방지 기능이 있으면 좋다.

SQLite 권장 설정:

```sql
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
```

- WAL 모드는 피한다.
- USB 이동성과 단순성을 위해 rollback journal 기본 방식을 사용한다.

## 5. 참가자 입력 항목

시작 화면 입력:

- 이름
- 전화번호
- 주언어

제거된 항목:

- 닉네임 없음
- 앱 내 개인정보 동의 체크 없음
- 개인정보 동의서는 현장에서 별도 종이/폼으로 받는다.

주언어 선택지:

- Python
- C
- C++
- Java
- JavaScript
- 아직 잘 모름

`아직 잘 모름` 선택 시 Python 입문용 문제로 처리한다.

## 6. 개인정보 표시 정책

- DB에는 이름과 전화번호를 저장한다.
- 공개 리더보드에는 전화번호를 절대 표시하지 않는다.
- 공개 리더보드에는 이름을 마스킹해서 표시하는 것을 기본으로 한다.
- 관리자 화면에서만 실명/전화번호 확인이 가능하다.

이름 마스킹 규칙:

- 홍길동 → 홍*동
- 김현 → 김*
- Alex → A***

## 7. 날짜 정책

- DB에는 `event_date`를 `YYYY-MM-DD`로 저장한다.
- DB에는 `created_at`도 timestamp로 저장한다.
- 화면에서는 날짜를 `MM/DD` 정도로 표시하면 충분하다.
- 리더보드와 CSV에는 날짜가 반드시 포함되어야 한다.
- 전체 리더보드와 날짜별 리더보드를 모두 제공한다.

## 8. 게임 정책

- 언어별 공식 코드 따라치기 게임이다.
- 난이도는 v1에서 나누지 않는다.
- 시작 버튼 후 코드 화면이 뜬다.
- 타이머는 첫 글자를 입력하는 순간 시작한다.
- 붙여넣기는 금지한다.
  - Ctrl+V / Cmd+V 방지
  - 가능하면 우클릭 붙여넣기도 방지
- 입력 전 안내 문구: `키보드가 영문 입력 상태인지 확인해주세요.`

## 9. 점수 계산

추천 점수식:

```text
score =
  1000
  - 걸린 시간(초) × 8
  - 오타 수 × 25
  - Backspace 수 × 1
  + 정확도 100% 보너스 100
```

- 최저점은 0점으로 clamp한다.

정렬 기준:

1. 점수 높은 순
2. 정확도 높은 순
3. 시간 짧은 순

저장 항목:

- `duration_ms`
- `accuracy`
- `typo_count`
- `backspace_count`
- `score`

## 10. 리더보드 정책

종류:

- 전체 TOP 10
- 날짜별 TOP 10
- 언어별 TOP 10

공개 리더보드 표시 항목:

- 순위
- 마스킹 이름
- 주언어
- 점수
- 기록 시간
- 정확도
- 날짜(MM/DD)

표시하지 않을 것:

- 전화번호
- 실명 전체 노출

중복/재도전 정책:

- 참가자는 여러 번 도전 가능하다.
- 전체 리더보드에는 전화번호 기준 전체 기간 최고 점수 1개만 반영한다.
- 날짜별 리더보드에는 전화번호 + `event_date` 기준 최고 점수 1개만 반영한다.
- 언어별 리더보드도 기본적으로 전화번호 기준 최고 점수 1개만 반영한다.

예:

```text
홍길동 / 010-1111-2222
05/21: 800점, 920점
05/22: 890점, 950점

반영:
- 05/21 리더보드: 920점
- 05/22 리더보드: 950점
- 전체 리더보드: 950점
```

## 11. DB 스키마 초안

`participants`:

- `id INTEGER PRIMARY KEY`
- `name TEXT NOT NULL`
- `phone TEXT NOT NULL`
- `main_language TEXT NOT NULL`
- `created_at TEXT NOT NULL`

`attempts`:

- `id INTEGER PRIMARY KEY`
- `participant_id INTEGER NOT NULL REFERENCES participants(id)`
- `event_date TEXT NOT NULL`
- `language TEXT NOT NULL`
- `snippet_id TEXT NOT NULL`
- `duration_ms INTEGER NOT NULL`
- `accuracy REAL NOT NULL`
- `typo_count INTEGER NOT NULL`
- `backspace_count INTEGER NOT NULL`
- `score INTEGER NOT NULL`
- `created_at TEXT NOT NULL`

필요하면 `participants`에 `phone_normalized`를 추가해서 전화번호 중복 판단에 사용한다.
전화번호 중복 판단은 하이픈/공백 제거 후 비교하는 방식을 권장한다.

## 12. 관리자 기능

관리자 진입:

- Ctrl + Shift + A 추천
- 관리자 비밀번호 필요

v1 관리자 기능:

- 현재 DB 경로 표시
- 현재 행사 날짜 표시/변경
- 전체 참가자 수
- 오늘 참가자 수
- 전체 시도 횟수
- 오늘 시도 횟수
- 참가자 목록 보기
- 전체 시도 기록 보기
- 날짜별 필터
- 전체 리더보드 보기
- 날짜별 리더보드 보기
- 언어별 리더보드 보기
- CSV 내보내기
  - 전체 데이터
  - 오늘 데이터
  - 날짜별 데이터
  - 공개용 리더보드 CSV
- DB 백업 생성
- 특정 날짜 데이터 삭제
- 리더보드 초기화
- 개인정보 삭제
- 전체 데이터 삭제

개인정보 삭제:

- 행사 종료 후 이름/전화번호 제거 또는 DB 전체 삭제가 가능해야 한다.
- 개인정보 삭제 기능은 위험하므로 관리자 확인 다이얼로그를 띄운다.

## 13. CSV export

`exports/` 아래 저장한다.

파일명 예:

- `cbu_code_sprint_all_2026-05-21_2026-05-23.csv`
- `cbu_code_sprint_2026-05-21.csv`
- `cbu_code_sprint_public_leaderboard_2026-05-21.csv`

개인정보 포함 CSV 컬럼:

- `event_date`
- `name`
- `phone`
- `main_language`
- `score`
- `duration_ms`
- `accuracy`
- `typo_count`
- `backspace_count`
- `snippet_id`
- `created_at`

공개용 CSV 컬럼:

- `event_date`
- `display_name`
- `main_language`
- `score`
- `duration_ms`
- `accuracy`

## 14. UI/GUI 톤

- 다크모드 터미널풍 + 씨부엉 마스코트 포인트.
- 너무 귀엽기만 하면 타자게임 같고, 너무 개발자 도구 같으면 홍보전 느낌이 약해진다.
- 코드 입력 화면은 집중이 중요하므로 마스코트는 작게 둔다.
- 시작/결과/리더보드는 마스코트를 비교적 크게 써도 된다.
- 1280x720 이상에서 보기 좋게 만든다.
- 전체화면 버튼 또는 전체화면 실행 옵션이 있으면 좋다.

추천 컬러:

- 배경: `#0B1020`
- 카드: `#121A2E`
- 코드 영역: `#050816`
- 텍스트: `#E5E7EB`
- 보조 텍스트: `#94A3B8`
- 포인트: `#FACC15` 또는 동아리 대표색
- 오타: `#F87171`
- 성공: `#34D399`

## 15. 마스코트 이미지

원본 폴더:

```text
/Users/geonha/Desktop/씨부엉 마스코트 이미지
```

앱에서는 원본 경로를 직접 참조하지 말고, 필요한 이미지를 `assets/mascot/`로 복사해서 영어 파일명으로 사용한다.

추천 매핑:

- `logo_main.png` ← `CBU로고_깔끔.png`
- `app_icon.png` ← `부엉로고 동글_투명.png`
- `mascot_idle.png` ← `부엉기본_투명.png`
- `mascot_guide.png` ← `부엉찡긋_투명.png`
- `mascot_typo.png` ← `부엉머쓱_투명.png`
- `mascot_success.png` ← `부엉신남_투명.png`
- `mascot_highscore.png` ← `투명배경 네잎클로버 부엉이.png`
- `mascot_leaderboard.png` ← `투명배경 네잎클로버 부엉이.png`

Fallback:

- 이미지 파일이 없으면 앱이 죽지 말고 기본 `🦉 CBU` 텍스트 로고를 보여준다.

v1은 기존 이미지로 충분하다.
추가 생성이 필요할 만한 이미지:

- 부엉이가 노트북 앞에서 코딩하는 이미지
- 트로피를 들고 있는 부엉이
- 기존 스타일과 맞춘 타이핑/성공/실패/랭킹 세트

## 16. 문제/snippet 데이터

`config/snippets.json`으로 관리한다.

v1 문제 수:

- Python 3개
- C 3개
- C++ 3개
- Java 3개
- JavaScript 3개
- 총 15개

난이도 필드는 내부적으로 둬도 되지만 v1 UI에서는 선택하지 않는다.
`아직 잘 모름`은 Python 입문용 문제로 매핑한다.

`snippets.json` 예시 구조:

```json
[
  {
    "id": "python-001",
    "language": "Python",
    "title": "Hello CBU",
    "code": "def hello_cbu(name):\n    print(f\"Hello, {name}!\")"
  }
]
```

## 17. 화면 구성

시작 화면:

- 앱 제목
- 마스코트
- 이름 입력
- 전화번호 입력
- 주언어 선택
- 시작하기 버튼
- 리더보드 버튼
- 영문 입력 안내

게임 화면:

- 언어 표시
- 타이머
- 코드 표시 영역
- 입력 영역
- 실시간 오타 표시
- 진행률
- 정확도
- 오타 수
- Backspace 수
- 작은 마스코트

결과 화면:

- 마스코트
- 이름 마스킹 표시
- 언어
- 기록 시간
- 정확도
- 오타 수
- 점수
- 전체 순위
- 날짜별 순위
- 언어별 순위
- 다시 도전
- 리더보드
- 처음으로

리더보드 화면:

- 전체 TOP 10
- 날짜별 TOP 10
- 언어별 TOP 10
- 날짜 표시
- 이름 마스킹
- 전화번호 미표시

관리자 화면:

- 관리자 기능 섹션 참고

## 18. 구현 순서 추천

1. 프로젝트 생성 위치 제안 후 승인받기
2. 프로젝트 뼈대 생성
3. USB home 경로 처리 구현
4. SQLite DB 모듈 구현
5. `snippets.json` 작성
6. 점수 계산/마스킹/전화번호 정규화 유틸 구현
7. PySide6 시작 화면 구현
8. 게임 화면 구현
9. 타이핑 판정/타이머/붙여넣기 방지 구현
10. 결과 저장/순위 계산 구현
11. 리더보드 화면 구현
12. 관리자 화면 구현
13. 마스코트 assets 복사 및 연결
14. macOS 개발 실행 테스트
15. PyInstaller macOS onedir/app 패키징
16. Windows 빌드 방법 문서화 또는 GitHub Actions/Windows 빌드 준비
17. Windows에서 exe 빌드 및 테스트
18. exFAT USB에 최종 구조 배치
19. Windows → macOS → Windows 순서로 같은 DB 이어쓰기 테스트

## 19. 검증 체크리스트

- [ ] 앱이 `--home` 경로를 사용한다.
- [ ] DB가 USB `data/leaderboard.sqlite`에 생성된다.
- [ ] Windows/Mac에서 같은 DB를 이어서 읽을 수 있다.
- [ ] AppData 또는 `~/Library`에 DB가 생성되지 않는다.
- [ ] 참가자 입력이 저장된다.
- [ ] 전화번호 하이픈/공백 제거 후 중복 판단된다.
- [ ] 같은 전화번호가 여러 번 도전해도 전체 리더보드에는 최고점 1개만 나온다.
- [ ] 날짜별 리더보드는 전화번호+날짜 기준 최고점만 나온다.
- [ ] 리더보드에는 전화번호가 나오지 않는다.
- [ ] 이름은 마스킹된다.
- [ ] CSV export가 된다.
- [ ] DB backup이 된다.
- [ ] 특정 날짜 데이터 삭제가 된다.
- [ ] 개인정보 삭제/전체 삭제는 확인 다이얼로그가 있다.
- [ ] 붙여넣기가 막힌다.
- [ ] 첫 입력 시 타이머가 시작된다.
- [ ] 마스코트 이미지가 없을 때 fallback이 동작한다.
- [ ] 앱 종료 후 USB를 옮겨도 기록이 유지된다.

## 20. 작업 주의사항

- commit/push/release/publish는 명시 승인 전 하지 않는다.
- Desktop의 마스코트 원본은 읽어서 복사만 하고, 원본 파일은 수정하지 않는다.
- Windows 빌드는 macOS에서 바로 만들기 어렵다. 필요하면 Windows 노트북이나 GitHub Actions Windows runner를 사용한다.
- macOS 앱은 Gatekeeper 경고가 뜰 수 있고, Windows exe는 SmartScreen 경고가 뜰 수 있다. 운영진용 실행 안내를 나중에 문서화한다.
- 다른 unrelated 파일은 건드리지 않는다.
- 구현 시작 전 작업 범위와 생성/수정 예정 파일을 짧게 보고하고 승인받는다.
