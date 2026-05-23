# 씨부엉 코드 스프린트 운영 가이드

이 문서는 홍보전 현장에서 운영진이 USB portable 앱을 실행하고 데이터를 안전하게 관리하기 위한 안내입니다.

## 1. 운영 원칙

- USB는 Windows/macOS 모두 쓰기 가능한 exFAT 포맷을 권장합니다.
- 한 번에 한 노트북에서만 앱을 실행합니다.
- 노트북을 바꿀 때는 앱을 완전히 종료한 뒤 USB를 안전하게 제거합니다.
- DB는 USB 루트의 `data/leaderboard.sqlite` 한 파일을 기준으로 운영합니다.
- 공개 리더보드에는 전화번호가 표시되지 않고, 이름은 마스킹됩니다.
- 개인정보 확인/CSV export/삭제 기능은 관리자 화면에서만 사용합니다.

## 2. USB 폴더 확인

현장 USB에는 아래 구조가 있어야 합니다.

```text
CBU-Code-Sprint/
├─ Start-Windows.bat
├─ Start-macOS.command
├─ apps/
│  ├─ windows/CBU Code Sprint/
│  └─ macos/CBU Code Sprint.app
├─ data/
├─ config/snippets.json
├─ assets/mascot/
├─ exports/
└─ backups/
```

운영 중 실제 기록 DB 경로는 관리자 화면의 `현재 DB 경로`에서 확인합니다.

## 3. macOS 실행

1. USB에서 `Start-macOS.command`를 실행합니다.
2. Gatekeeper 경고가 뜨면 Finder에서 파일을 Control-click 또는 우클릭한 뒤 `열기`를 선택합니다.
3. 그래도 차단되면 `시스템 설정 > 개인정보 보호 및 보안`에서 차단된 앱의 `그래도 열기`를 선택합니다.
4. 앱이 뜨면 관리자 화면에서 DB 경로가 USB 안의 `data/leaderboard.sqlite`인지 확인합니다.

## 4. Windows 실행

1. USB에서 `Start-Windows.bat`를 실행합니다.
2. Windows SmartScreen 경고가 뜨면 `추가 정보`를 누른 뒤 `실행`을 선택합니다.
3. 앱이 뜨면 관리자 화면에서 DB 경로가 USB 안의 `data\leaderboard.sqlite`인지 확인합니다.

## 5. 참가자 진행 흐름

1. 참가자에게 현장 개인정보 수집 동의서 작성을 먼저 안내합니다.
2. 시작 화면에서 이름, 전화번호, 주언어를 입력합니다.
3. `시작하기`를 누른 뒤 코드 화면에서 첫 글자를 입력하면 타이머가 시작됩니다.
4. 붙여넣기는 사용할 수 없습니다.
5. 완료 후 결과 화면과 리더보드에서 점수를 확인합니다.
6. 결과 화면에서 전체/오늘/언어별 순위 반영 상태를 확인합니다.
7. 재도전은 가능하지만 공개 리더보드에는 전화번호 기준 최고 기록만 반영됩니다.

## 6. 관리자 화면

- 진입 단축키: `Ctrl + Shift + A`
- 기본 비밀번호: `cbu`
- 운영 전 비밀번호 변경 권장: 환경변수 `CBU_CODE_SPRINT_ADMIN_PASSWORD`

관리자 화면에서 할 수 있는 일:

- 현재 DB 경로 확인
- 행사 날짜 변경
- 전체/오늘 참가자 수와 시도 수 확인
- 참가자 목록 확인
- 선택 날짜 시도 기록 확인
- 공개 리더보드 CSV export
- 개인정보 포함 전체 데이터 CSV export
- DB 백업 생성
- 날짜별 데이터 삭제
- 리더보드 초기화
- 개인정보 삭제/익명화
- 전체 데이터 삭제

위험 기능은 실행 전 확인 다이얼로그가 뜨며, 실행 전에 가능한 경우 DB 백업을 먼저 만듭니다.

## 7. 백업/export 운영

권장 주기:

- 행사 시작 전: DB 백업 1회
- 노트북 교체 전: DB 백업 1회
- 하루 운영 종료 후: DB 백업 + 전체 데이터 CSV export
- 행사 종료 후: 최종 CSV export + DB 백업 후 개인정보 삭제 또는 전체 삭제

생성 위치:

- DB 백업: `backups/`
- CSV export: `exports/`

## 8. 노트북 교체 절차

1. 현재 노트북에서 앱을 종료합니다.
2. 가능하면 관리자 화면에서 DB 백업을 생성합니다.
3. USB를 안전하게 제거합니다.
4. 다음 노트북에 USB를 연결합니다.
5. OS에 맞는 시작 스크립트를 실행합니다.
6. 관리자 화면에서 DB 경로와 기존 리더보드 기록을 확인합니다.

## 9. 문제 대응

### 앱이 이미 실행 중이라고 뜨는 경우

- 같은 USB에서 앱이 이미 열려 있을 가능성이 있습니다.
- 기존 앱 창을 찾아 종료한 뒤 다시 실행합니다.
- 강제 종료 후에도 계속 뜨면 USB를 안전하게 제거했다가 다시 연결하고 실행합니다.

### 리더보드가 비어 있는 경우

- 관리자 화면에서 DB 경로가 USB의 `data/leaderboard.sqlite`인지 확인합니다.
- 다른 USB/폴더에서 실행한 것은 아닌지 확인합니다.
- `backups/`에 있는 최신 백업 파일 존재 여부를 확인합니다.

### 마스코트 이미지가 안 보이는 경우

- 앱은 이미지가 없어도 동작해야 합니다.
- `assets/mascot/` 아래 PNG 파일들이 있는지 확인합니다.

### 입력이 이상하게 되는 경우

- 참가자에게 키보드가 영문 입력 상태인지 확인하게 합니다.
- 붙여넣기는 막혀 있으므로 직접 타이핑해야 합니다.

## 10. 행사 전 체크리스트

```text
[ ] USB가 exFAT이다.
[ ] macOS에서 Start-macOS.command로 앱이 열린다.
[ ] Windows에서 Start-Windows.bat로 앱이 열린다.
[ ] 관리자 화면 DB 경로가 USB의 data/leaderboard.sqlite이다.
[ ] 샘플 참가자 기록이 저장되고 리더보드에 보인다.
[ ] 공개 리더보드에 전화번호가 보이지 않는다.
[ ] 이름이 마스킹된다.
[ ] CSV export가 생성된다.
[ ] DB backup이 생성된다.
[ ] 같은 USB를 Windows → macOS → Windows 순서로 옮겨도 기록이 유지된다.
[ ] 운영진이 Gatekeeper/SmartScreen 경고 처리 방법을 알고 있다.
[ ] 행사 종료 후 개인정보 삭제 또는 전체 삭제 절차를 정했다.
```

개발/패키징 직전에는 저장소 루트에서 아래 검증도 실행합니다.

```text
[ ] python -m compileall -q src tests
[ ] python -m unittest discover -s tests -p "test_*.py" -v
```
