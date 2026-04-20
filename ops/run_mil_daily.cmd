@echo off
REM MIL daily wrapper — invoked by Task Scheduler.
REM Captures stdout + stderr to mil/data/run_auto_YYYYMMDD_HHMMSS.log
REM so autonomous runs produce a debuggable log alongside the authoritative
REM daily_run_log.jsonl entry written by run_daily.py Step 6.

cd /d C:\Users\hussa\while-sleeping
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
C:\Windows\py.exe run_daily.py > "mil\data\run_auto_%TS%.log" 2>&1
exit /b %ERRORLEVEL%
