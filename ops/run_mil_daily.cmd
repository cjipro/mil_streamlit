@echo off
REM MIL daily wrapper — invoked by Task Scheduler.
REM Delegates to ops\run_mil_daily.ps1 which holds SetThreadExecutionState
REM to prevent Windows sleep mid-pipeline (root cause of the 2026-05-05
REM morning kill at Step 4).
REM Captures stdout + stderr to mil/data/run_auto_YYYYMMDD_HHMMSS.log
REM so autonomous runs produce a debuggable log alongside the authoritative
REM daily_run_log.jsonl entry written by run_daily.py Step 6.

cd /d C:\Users\hussa\while-sleeping
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
powershell -NoProfile -ExecutionPolicy Bypass -File "ops\run_mil_daily.ps1" -LogPath "mil\data\run_auto_%TS%.log"
exit /b %ERRORLEVEL%
