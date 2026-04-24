# MIL-62 corp-proxy smoke tester — PowerShell version (Windows corp laptops)
#
# Universal availability on Windows — no need for WSL / git-bash / Python.
# Same scope as mil62_smoke.sh: automates S1 + S2 + pre-flight login
# Worker health checks from a corp-network machine, and prints a
# pre-formatted results row.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ops\mil62_smoke.ps1 -Bank Barclays -Tester HX
#
# S3-S7 require manual browser interaction and cannot be automated.

param(
    [string]$Bank   = "UNKNOWN",
    [string]$Tester = "??"
)

$ErrorActionPreference = "Continue"
$CJIPRO = "https://cjipro.com"
$LOGIN  = "https://login.cjipro.com"
$DateStamp = Get-Date -Format "yyyy-MM-dd"

$PASS = "[PASS]"
$FAIL = "[FAIL]"

$overallOk = $true

function Test-Endpoint {
    param([string]$Label, [int]$ExpectedCode, [string]$Url, [string]$BodyPattern = "")

    try {
        $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction SilentlyContinue -UseBasicParsing
        $code = $resp.StatusCode
        $body = $resp.Content
    } catch {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            $body = ""
        } else {
            $code = 0
            $body = ""
        }
    }

    $ok = ($code -eq $ExpectedCode)
    if ($BodyPattern -and -not ($body -match $BodyPattern)) { $ok = $false }

    if ($ok) {
        Write-Host ("  {0} {1,-30} HTTP {2} ({3} bytes)" -f $PASS, $Label, $code, $body.Length)
    } else {
        Write-Host ("  {0} {1,-30} HTTP {2}  -- expected {3}" -f $FAIL, $Label, $code, $ExpectedCode) -ForegroundColor Red
        $script:overallOk = $false
    }
}

Write-Host "======================================================================"
Write-Host "MIL-62 Corp-Proxy Smoke -- $Bank ($Tester) -- $DateStamp"
Write-Host "======================================================================"
Write-Host ""
Write-Host "--- Pre-flight (login Worker health) ---"
Test-Endpoint -Label "pre-flight: /healthz" -ExpectedCode 200 -Url "$LOGIN/healthz" -BodyPattern "^ok"

# Check that /  redirects to api.workos.com/user_management/authorize
try {
    $r = Invoke-WebRequest -Uri "$LOGIN/" -MaximumRedirection 0 -ErrorAction SilentlyContinue -UseBasicParsing
    $loc = $r.Headers.Location
} catch {
    $loc = $_.Exception.Response.Headers.Location
}
if ($loc -like "*api.workos.com/user_management/authorize*") {
    Write-Host "  $PASS pre-flight: /  -> authorize    redirects to api.workos.com/user_management/authorize"
} else {
    Write-Host "  $FAIL pre-flight: /  -> authorize    UNEXPECTED redirect: $loc" -ForegroundColor Red
    $overallOk = $false
}

Write-Host ""
Write-Host "--- S1: Landing page reachable ---"
Test-Endpoint -Label "S1: cjipro.com/"      -ExpectedCode 200 -Url "$CJIPRO/" -BodyPattern "<title>"

# Check for Cloudflare challenge page
try {
    $land = Invoke-WebRequest -Uri "$CJIPRO/" -TimeoutSec 10 -UseBasicParsing
    if ($land.Content -match "cloudflare challenge|checking your browser|/cdn-cgi/challenge") {
        Write-Host "  $FAIL S1: CF challenge detected in body -- proxy is intercepting" -ForegroundColor Red
        $overallOk = $false
    }
} catch {}

Write-Host ""
Write-Host "--- S2: Trust signals reachable ---"
Test-Endpoint -Label "S2: /privacy/"                  -ExpectedCode 200 -Url "$CJIPRO/privacy/"                  -BodyPattern "privacy"
Test-Endpoint -Label "S2: /.well-known/security.txt"  -ExpectedCode 200 -Url "$CJIPRO/.well-known/security.txt"  -BodyPattern "Contact"

Write-Host ""
Write-Host "======================================================================"
Write-Host "  AUTOMATED SCENARIOS RESULT"
Write-Host "======================================================================"
if ($overallOk) {
    Write-Host "  All automated checks PASSED." -ForegroundColor Green
    Write-Host ""
    Write-Host "  S3-S7 require manual browser testing. Please:"
    Write-Host "    1. Open $CJIPRO/briefing-v4/ in a fresh InPrivate window."
    Write-Host "    2. If redirected to $LOGIN/, enter your corp email."
    Write-Host "    3. Check corp inbox for a magic-link email from WorkOS."
    Write-Host "    4. Click it from the corp browser -- should land on briefing-v4."
    Write-Host "    5. DevTools -> Application -> Cookies -> cjipro.com -> confirm"
    Write-Host "       __Secure-cjipro-session is present."
    Write-Host "    6. Reply with results for S3/S4/S5/S6/S7 + the S8 JWT decode"
    Write-Host "       (see runbook)."
} else {
    Write-Host "  One or more automated checks FAILED." -ForegroundColor Red
    Write-Host "  Pre-automated scenarios cannot proceed -- raise the failures with"
    Write-Host "  Hussain before attempting manual steps."
}

Write-Host ""
Write-Host "======================================================================"
Write-Host "  RESULTS ROW (paste into ops/runbooks/mil-62_corp_proxy_matrix.md):"
Write-Host "======================================================================"
$s1s2 = if ($overallOk) { "[PASS] | [PASS]" } else { "[FAIL] | [FAIL]" }
$ovr  = if ($overallOk) { "(warn) partial" } else { "[FAIL]" }
Write-Host ("| {0,-8} | {1,-6} | {2} | {3} | ?   | ?   | ?   | ?   | ?   | ?   | {4} |" -f $Bank, $Tester, $DateStamp, $s1s2, $ovr)
Write-Host ""
Write-Host "Tip: '?' cells are for manual S3-S8 -- fill in as you complete them."
Write-Host "======================================================================"

if (-not $overallOk) { exit 1 } else { exit 0 }
