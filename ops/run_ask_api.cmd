@echo off
rem run_ask_api.cmd — launch the Ask CJI Pro HTTP API
rem Default bind 127.0.0.1:8765 (local only). Expose publicly via cloudflared.
rem
rem Logs: mil\data\ask_api_YYYYMMDD_HHMMSS.log

setlocal

cd /d %~dp0\..

set STAMP=%DATE:~-4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set STAMP=%STAMP: =0%
set LOG=mil\data\ask_api_%STAMP%.log

echo [%STAMP%] Starting Ask CJI Pro API
echo Logging to %LOG%

py -m mil.chat.api_server --host 127.0.0.1 --port 8765 > %LOG% 2>&1

endlocal
