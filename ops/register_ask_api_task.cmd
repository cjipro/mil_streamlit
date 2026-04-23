@echo off
setlocal
set LOG=C:\Users\hussa\while-sleeping\ops\register_ask_api_task.log
echo === register Ask CJI Pro API task %DATE% %TIME% === >> "%LOG%"

schtasks /Create /TN "Ask CJI Pro API" /TR "C:\Users\hussa\while-sleeping\ops\run_ask_api.cmd" /SC ONLOGON /RU hussa /RL LIMITED /F >> "%LOG%" 2>&1
schtasks /Query /TN "Ask CJI Pro API" /V /FO LIST >> "%LOG%" 2>&1

echo === done === >> "%LOG%"
endlocal
