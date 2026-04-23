@echo off
rem ops\setup_tunnel.cmd — one-time Cloudflare Tunnel setup for sonar.cjipro.com
rem
rem Prereq: cloudflared installed system-wide.
rem         winget install --id Cloudflare.cloudflared -e
rem         (rerun this script after install)
rem
rem Runs: login (browser OAuth) → create → DNS route → patch config.yml →
rem       install as Windows service.

setlocal enableextensions enabledelayedexpansion

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo [setup_tunnel] cloudflared not found on PATH.
    echo Install it first:  winget install --id Cloudflare.cloudflared -e
    exit /b 1
)

set TUNNEL_NAME=ask-cji-pro
set CONFIG_PATH=%~dp0cloudflared\config.yml
set HOSTNAME=sonar.cjipro.com

echo.
echo === Step 1 / 4  login ===
cloudflared tunnel login
if errorlevel 1 goto fail

echo.
echo === Step 2 / 4  create tunnel %TUNNEL_NAME% ===
cloudflared tunnel create %TUNNEL_NAME%
if errorlevel 1 (
    echo   Tunnel %TUNNEL_NAME% may already exist — continuing.
)

echo.
echo === Step 3 / 4  route DNS %HOSTNAME% ===
cloudflared tunnel route dns %TUNNEL_NAME% %HOSTNAME%
if errorlevel 1 goto fail

echo.
echo === Step 4 / 4  patching %CONFIG_PATH% with tunnel UUID ===
for /f "tokens=1" %%A in ('cloudflared tunnel list ^| findstr /b /c:" " ^| findstr %TUNNEL_NAME%') do set TUNNEL_UUID=%%A
if "%TUNNEL_UUID%"=="" (
    echo   Could not auto-detect tunnel UUID. Run `cloudflared tunnel list` and
    echo   edit %CONFIG_PATH% manually (replace both REPLACE_WITH_TUNNEL_UUID).
    goto done
)
echo   tunnel UUID: %TUNNEL_UUID%

powershell -NoProfile -Command ^
  "(Get-Content '%CONFIG_PATH%') -replace 'REPLACE_WITH_TUNNEL_UUID', '%TUNNEL_UUID%' | Set-Content -Encoding utf8 '%CONFIG_PATH%'"
if errorlevel 1 goto fail

echo.
echo === Smoke test  cloudflared tunnel run %TUNNEL_NAME% (Ctrl-C to stop) ===
echo   cloudflared --config %CONFIG_PATH% tunnel run %TUNNEL_NAME%
echo.
echo To install as a Windows service (auto-start on boot):
echo   cloudflared --config %CONFIG_PATH% service install
echo.
echo Before accepting traffic: add a Cloudflare Access policy on %HOSTNAME%
echo in Zero Trust dashboard — otherwise the tunnel is open to the world.

:done
endlocal
exit /b 0

:fail
endlocal
echo [setup_tunnel] FAILED
exit /b 1
