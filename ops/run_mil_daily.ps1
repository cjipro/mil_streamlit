# MIL daily wrapper — keeps Windows awake while the pipeline runs.
# Invoked by ops/run_mil_daily.cmd (which is what Task Scheduler points at).
# Stops Windows entering sleep / hibernate while python is executing,
# so a missed cron-fire scenario (Run #84..85, 2026-05-05 morning) where
# the laptop slept mid-Step 4 cannot recur.

param(
    [Parameter(Mandatory = $true)][string]$LogPath
)

# SetThreadExecutionState bindings.
# ES_CONTINUOUS       = 0x80000000  — flags persist for life of thread
# ES_SYSTEM_REQUIRED  = 0x00000001  — system stays awake
Add-Type -Name PowerMgmt -Namespace Win32 -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

[void][Win32.PowerMgmt]::SetThreadExecutionState(0x80000001)

$exitCode = 1
try {
    # cmd /c keeps the > 2>&1 redirection unbuffered (avoids the PS object-pipe
    # buffering trap that would only flush the log on process exit).
    & cmd /c "C:\Windows\py.exe run_daily.py > `"$LogPath`" 2>&1"
    $exitCode = $LASTEXITCODE
}
finally {
    # ES_CONTINUOUS alone clears the request — normal sleep policy resumes.
    [void][Win32.PowerMgmt]::SetThreadExecutionState(0x80000000)
}

exit $exitCode
