@echo off
setlocal
set "ROOT=%~dp0"
set "APP=%ROOT%apps\windows\CBU Code Sprint\CBU Code Sprint.exe"

if exist "%APP%" (
  "%APP%" --home "%ROOT%" %*
  exit /b %ERRORLEVEL%
)

set "PYTHONPATH=%ROOT%src"

if exist "%ROOT%.venv\Scripts\python.exe" (
  "%ROOT%.venv\Scripts\python.exe" -m cbu_code_sprint --home "%ROOT%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
  python -m cbu_code_sprint --home "%ROOT%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m cbu_code_sprint --home "%ROOT%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3.11 이상을 찾을 수 없습니다.
echo Windows PowerShell에서 다음 중 하나를 먼저 실행해주세요:
echo   winget install -e --id Python.Python.3.12
echo   또는 python.org 설치 시 "Add python.exe to PATH" 체크
exit /b 1
