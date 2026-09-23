@echo off
setlocal
if "%~1"=="" (
  echo Usage: start-zotero-agent.cmd ^<zotero-dir^> [workbench-origin]
  exit /b 2
)
set "ORIGIN=%~2"
if "%ORIGIN%"=="" set "ORIGIN=http://127.0.0.1:5173"
python "%~dp0agent.py" --zotero-dir "%~1" --origin "%ORIGIN%"
