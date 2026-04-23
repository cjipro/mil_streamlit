@echo off
setlocal
set LOG=C:\Users\hussa\while-sleeping\ops\cloudflared\fix_service.log
echo === fix-binpath cmd run at %DATE% %TIME% === >> "%LOG%"

net stop cloudflared >> "%LOG%" 2>&1
timeout /t 2 /nobreak > nul

sc config cloudflared binPath= "\"C:\Program Files (x86)\cloudflared\cloudflared.exe\" --config \"C:\Users\hussa\while-sleeping\ops\cloudflared\config.yml\" tunnel run" >> "%LOG%" 2>&1
sc qc cloudflared >> "%LOG%" 2>&1

net start cloudflared >> "%LOG%" 2>&1
timeout /t 4 /nobreak > nul
sc query cloudflared >> "%LOG%" 2>&1

echo === done === >> "%LOG%"
endlocal
