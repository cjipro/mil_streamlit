@echo off
rem ops\run_tunnel.cmd — foreground run of the Ask CJI Pro tunnel.
rem Use for testing. For production, register as a Windows service:
rem   cloudflared --config ops\cloudflared\config.yml service install

setlocal
cd /d %~dp0\..

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo cloudflared not on PATH. Install:
    echo   winget install --id Cloudflare.cloudflared -e
    exit /b 1
)

cloudflared --config ops\cloudflared\config.yml tunnel run ask-cji-pro

endlocal
