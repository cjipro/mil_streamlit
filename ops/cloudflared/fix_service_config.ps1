$ErrorActionPreference = 'Continue'
$log = 'C:\Users\hussa\while-sleeping\ops\cloudflared\fix_service.log'
"=== fix-binpath run at $(Get-Date -Format o) ===" | Out-File $log -Append

try {
    Stop-Service cloudflared -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $binPath = '"C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "C:\Users\hussa\while-sleeping\ops\cloudflared\config.yml" tunnel run'
    "setting binPath = $binPath" | Out-File $log -Append

    & sc.exe config cloudflared binPath= $binPath 2>&1 | Out-File $log -Append
    & sc.exe qc cloudflared 2>&1 | Out-File $log -Append

    Start-Service cloudflared
    "start-service issued" | Out-File $log -Append
    Start-Sleep -Seconds 4

    & sc.exe query cloudflared 2>&1 | Out-File $log -Append
} catch {
    "ERROR: $_" | Out-File $log -Append
}
"=== done ===" | Out-File $log -Append
