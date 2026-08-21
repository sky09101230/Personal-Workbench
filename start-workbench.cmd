@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%CD%\.venv\Scripts\python.exe"
set "TERMINAL=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"

if exist "%TERMINAL%" goto terminal_ready
where wt.exe >nul 2>&1 || goto missing_terminal
set "TERMINAL=wt.exe"

:terminal_ready
if not exist "%PYTHON%" goto missing_python
where npm.cmd >nul 2>&1 || goto missing_node
if not exist "apps\web\node_modules\.bin\vite.cmd" goto missing_web_dependencies
"%PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1 || goto missing_api_dependencies

set "ENV_FILE="
if exist ".env" set "ENV_FILE=--env-file .env"

"%TERMINAL%" -w new new-tab --title "Personal Workbench - API" --startingDirectory "%CD%" cmd.exe /k ""%PYTHON%" -m uvicorn app.main:app --app-dir apps\api --reload %ENV_FILE%" ; new-tab --title "Personal Workbench - Web" --startingDirectory "%CD%" cmd.exe /k "npm.cmd --prefix apps\web run dev -- --open"

echo Personal Workbench is starting.
echo The browser will open http://localhost:5173 automatically.
exit /b 0

:missing_terminal
echo Windows Terminal was not found.
echo Install Windows Terminal or enable its wt.exe app execution alias first.
goto failed

:missing_python
echo Python environment not found: .venv\Scripts\python.exe
echo Create the project virtual environment and install API dependencies first.
goto failed

:missing_node
echo npm.cmd was not found. Install Node.js first.
goto failed

:missing_web_dependencies
echo Web dependencies are missing.
echo Run: npm.cmd --prefix apps\web install
goto failed

:missing_api_dependencies
echo API dependencies are missing.
echo Run: .\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
goto failed

:failed
echo.
pause
exit /b 1
