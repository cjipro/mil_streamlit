# Runbook — GPU driver clean-reinstall (RTX 5070 Ti Laptop)

**Purpose:** fix the recurring machine BSODs (`0x116` VIDEO_TDR_ERROR) by clean-wiping and reinstalling the NVIDIA display driver. This is the root-cause fix; the CPU-pin mitigation in `mil/inference/rag.py` only removes the daily pipeline as a *trigger*, it does not fix the GPU/driver fault.

**When to run:** the machine has hard-rebooted itself ≥1× and the [diagnosis](#appendix-a--re-confirm-its-still-the-gpu) confirms `0x116` (or repeated `0x133`) bugchecks rather than power loss. Full background: memory `project_gpu_tdr_crashes.md`.

**Time:** ~30–45 min. Requires a reboot into Safe Mode.

---

## Machine facts (as of 2026-05-24)

| | |
|---|---|
| Laptop | Acer **Predator PHN18-72** (hostname `AI-ACER`) |
| OS | Windows 11 Home, build 26200 |
| Discrete GPU | **NVIDIA GeForce RTX 5070 Ti Laptop GPU** (Blackwell) |
| iGPU | Intel Graphics (hybrid / Advanced Optimus) |
| Current driver | **577.13** (`32.0.15.7713`), dated 25 Aug 2025 — ~9 months old |
| Other NVIDIA SW | NVIDIA App 11.0.2.337, CUDA Toolkit 13.2 (standalone), Nsight |
| Free disk (C:) | ~1.5 TB |

---

## ⚠️ Pre-flight (do these BEFORE Safe Mode)

1. **Back up the device-encryption recovery key.** Win11 Home uses Device Encryption; a Safe-Boot driver swap can occasionally trigger a recovery-key prompt. Sign in at **account.microsoft.com/devices/recoverykey** (with the Microsoft account on this laptop) and save the key off-machine (phone/print). Skipping this is the one thing that can lock you out.
2. **Download the new driver now, while online** (Step A) so it's local before you go offline/Safe Mode.
3. **Download DDU now** (Step B) and extract it.
4. **Quiesce GPU workloads:** close Ollama, any Python/torch jobs, and temporarily disable the `MIL Daily` scheduled task so the pipeline can't fire mid-reinstall:
   ```powershell
   Disable-ScheduledTask -TaskName "MIL Daily"
   ```
   (Re-enable in Step D.)

---

## A. Get the right driver

Use the latest **Studio Driver** (more stable for CUDA / Ollama / torch workloads than Game Ready). Two routes:

- **NVIDIA App** (already installed) → **Drivers** tab → switch channel to **Studio** → **Download**. *Don't install yet — just download.*
- **Manual:** nvidia.com → Drivers → product **GeForce RTX 5070 Ti Laptop GPU**, Windows 11, Download Type **Studio (SD)**. Save the `.exe`.

Notes:
- If only **Game Ready** is offered, that's fine too — it's still a large step up from 577.13.
- The Acer has **Advanced Optimus**. NVIDIA's generic laptop driver supports it; if display-output switching misbehaves afterward, fall back to Acer's PHN18-72 driver from acer.com/support.

## B. Clean-wipe with DDU

1. Get **Display Driver Uninstaller (DDU)** from the official source (Wagnardsoft), extract.
2. Boot into **Safe Mode**: Settings → System → Recovery → Advanced startup → **Restart now** → Troubleshoot → Advanced options → Startup Settings → Restart → press **4**. (A recovery-key prompt here is why you saved the key.)
3. Run **DDU** → device type **GPU** → **NVIDIA** → **Clean and restart**.

> DDU removes only the **display driver** (and its bundled GPU/CUDA driver). It does **not** touch the standalone **CUDA Toolkit 13.2**, **Ollama**, or **PyTorch** — those keep working.

## C. Fresh install

1. After reboot, run the driver `.exe` from Step A.
2. Choose **Custom (Advanced)** → tick **Perform a clean installation**.
3. **Driver components only** is fine (skip GeForce-Experience extras); keep **PhysX**. The existing **NVIDIA App** stays.

## D. Verify & restore

1. Confirm the new version:
   ```powershell
   nvidia-smi
   # or:
   Get-CimInstance Win32_VideoController | Where-Object Name -match NVIDIA | Select-Object Name, DriverVersion, DriverDate
   ```
   It must no longer read **577.13**.
2. Re-enable the scheduled task:
   ```powershell
   Enable-ScheduledTask -TaskName "MIL Daily"
   ```
3. Optional smoke test: run `nvidia-smi` under a small GPU load (e.g. an Ollama prompt) and confirm it stays up.

---

## Post-install monitoring

For the next ~1–2 weeks, after any reboot run [Appendix A](#appendix-a--re-confirm-its-still-the-gpu) and check the **boot date** of any new `41` / `1001` event is *before* the driver-install date. No new `0x116` after the reinstall = fixed.

## If it STILL crashes on the fresh driver

Then it's leaning **hardware / thermal / power**, not driver:

1. **Analyze the minidumps** to name the faulting module (needs an **elevated** terminal — `C:\WINDOWS\Minidump` is ACL-locked):
   - Easiest: **NirSoft BlueScreenView** → open it, it lists each dump + the driver flagged "caused by".
   - Or WinDbg: `kd -z C:\WINDOWS\Minidump\<latest>.dmp` then `!analyze -v` (look for `nvlddmkm.sys`).
2. **Check temps under load** with **HWiNFO64** — rule out GPU thermal throttling/shutdown.
3. **Try a different driver branch** (DDU again → an older known-stable Studio release, or the Acer OEM driver).
4. **Acer warranty / support** — the PHN18-72 is a 2025 machine; repeated `0x116` with a clean driver is a hardware RMA candidate.

## Rollback

If the new driver introduces a *different* problem, DDU again and reinstall 577.13 (or the Acer OEM driver). Keep the old installer until the new one has soaked clean for a week.

---

## Appendix A — re-confirm it's still the GPU

Run (no elevation needed):

```powershell
# Unexpected reboots / crashes
Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,6008,1001} -MaxEvents 20 |
  Select-Object TimeCreated, Id, ProviderName | Format-Table -AutoSize

# Bugcheck codes (0x116 = VIDEO_TDR_ERROR, 0x133 = DPC_WATCHDOG_VIOLATION)
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; Id=1001} -MaxEvents 5 |
  Select-Object TimeCreated, Message | Format-List
```

## Appendix B — correlate a crash with the pipeline

A truncated `mil/data/run_auto_*.log` whose last write is within ~1 min of a reboot event = crashed mid-run. Historically all 3 such crashes died at the `all-MiniLM-L6-v2` embedding stage (now pinned to CPU, so this trigger is removed — but watch for crashes at the **Refuel-8B / Ollama** inference calls, which still use the GPU):

```powershell
Get-ChildItem 'C:\Users\hussa\while-sleeping\mil\data\run_auto_*.log' |
  Sort-Object LastWriteTime |
  Select-Object Name, LastWriteTime, @{n='KB';e={[int]($_.Length/1KB)}}
# A full clean run is ~110–120 KB; a ~25–40 KB log = truncated by a crash.
```

---

*Created 2026-05-24. Companion to memory `project_gpu_tdr_crashes.md` and the corrected 2026-05-06 entry in CLAUDE.md.*
