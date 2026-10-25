@echo off
rem Start the server (used by Task Scheduler at boot). ASCII-only on purpose: cmd reads this file with the
rem console code page, so Thai text in a .cmd file can corrupt it.
rem Always runs from the project root because schtasks cannot set a working directory, while .env and
rem uploads\ are resolved relative to the project root.
rem Override the port with:  set PORT=8766 && scripts\start-server.cmd
cd /d "%~dp0.."
if "%PORT%"=="" set PORT=8000
if not exist logs mkdir logs
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --log-level info >> "logs\server.log" 2>&1
