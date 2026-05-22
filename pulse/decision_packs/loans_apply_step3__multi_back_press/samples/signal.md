## loans_apply_step3__multi_back_press — Signal altitude

### Detector run

- **Pack:** `loans_apply_step3__multi_back_press` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:b27d8f4a1c5e9032d6a8f1b4c7e0d3a6b9c2e5f8a1d4b7c0e3f6a9b2c5e8d1f4`

### Analytic parameters

```yaml
method: back_press_burst_detection
trigger:
  min_back_press_events: 3
  window_seconds: 300
discriminator:
  rule: inter_press_interval_under_seconds
  value: 20
baseline_n: 14902
```

### Per-session evidence (first 5 of 612)

| session_id | back_presses | burst_window_s | median_interval_s | exit_outcome |
|---|---:|---:|---:|---|
| `s_4a8e21…` | 6 | 73 | 9 | abandoned |
| `s_71c0f3…` | 4 | 112 | 14 | abandoned |
| `s_92b7d6…` | 5 | 88 | 11 | back_to_step_2_then_forward |
| `s_a3e0c4…` | 4 | 64 | 8 | abandoned |
| `s_d6f1a9…` | 7 | 95 | 7 | switched_to_assisted |

### Inter-press interval distribution

```
 0– 5s | ████████████████████ 287
 5–10s | ████████████████ 224
10–15s | ████████ 118
15–20s | ████ 63
20–30s |  (excluded — discriminator)
```

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `inter_press_interval_distribution`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:b27d8f4a1c5e9032d6a8f1b4c7e0d3a6b9c2e5f8a1d4b7c0e3f6a9b2c5e8d1f4`
against `loans_apply_step3__multi_back_press` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
