## international_beneficiary_setup__multi_back_press — Signal altitude

### Detector run

- **Pack:** `international_beneficiary_setup__multi_back_press` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:c5a1e8b4d7f20396a2c5e8b1d4f7a0c3e6b9d2f5a8c1e4b7d0a3f6c9b2e5a8d1`

### Analytic parameters

```yaml
method: back_press_burst_detection
trigger:
  min_back_press_events: 3
  window_seconds: 300
discriminator:
  rule: inter_press_interval_under_seconds
  value: 20
baseline_n: 7884
```

### Per-session evidence (first 5 of 387)

| session_id | back_presses | burst_window_s | median_interval_s | exit_outcome |
|---|---:|---:|---:|---|
| `s_1e7a92…` | 7 | 84 | 7 | abandoned |
| `s_44c3f0…` | 5 | 121 | 12 | back_to_corridor_then_forward |
| `s_8b09e4…` | 6 | 96 | 8 | abandoned |
| `s_a2d7c1…` | 4 | 71 | 9 | switched_to_assisted |
| `s_f50b38…` | 8 | 108 | 6 | back_to_corridor_then_forward |

### Inter-press interval distribution

```
 0– 5s | ████████████████████ 178
 5–10s | ██████████████ 124
10–15s |  ███████ 61
15–20s |  ███ 24
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
`sha256:c5a1e8b4d7f20396a2c5e8b1d4f7a0c3e6b9d2f5a8c1e4b7d0a3f6c9b2e5a8d1`
against `international_beneficiary_setup__multi_back_press` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
