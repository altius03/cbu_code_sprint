@echo off
set ROOT=%~dp0
set APP=%ROOT%apps\windows\CBU Code Sprint\CBU Code Sprint.exe
if exist "%APP%" (
  "%APP%" --home "%ROOT%" %*
) else if exist "%ROOT%.venv\Scripts\python.exe" (
  set PYTHONPATH=%ROOT%src
  "%ROOT%.venv\Scripts\python.exe" -m cbu_code_sprint --home "%ROOT%" %*
) else (
  set PYTHONPATH=%ROOT%src
  py -3 -m cbu_code_sprint --home "%ROOT%" %*
)
