## cards_credit_apply_eligibility__multi_back_press — Signal altitude

### Detector run

- **Pack:** `cards_credit_apply_eligibility__multi_back_press` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:a18c4f7b2e5d9036c1f4b7e0a3d6c9b2e5f8a1d4c7b0e3f6a9b2c5d8e1f4a7b0`

### Analytic parameters

```yaml
method: back_press_burst_detection
trigger:
  min_back_press_events: 3
  window_seconds: 300
discriminator:
  rule: inter_press_interval_under_seconds
  value: 20
baseline_n: 22108
```

### Per-session evidence (first 5 of 894)

| session_id | back_presses | burst_window_s | median_interval_s | fields_changed | exit_outcome |
|---|---:|---:|---:|---|---|
| `s_2a8f31…` | 6 | 88 | 8 | income_range_band, employment_duration_months | abandoned |
| `s_4c0b72…` | 5 | 124 | 11 | income_range_band | submitted_revised |
| `s_71d4e9…` | 7 | 96 | 7 | income_range_band, existing_credit_commitments | abandoned |
| `s_93f6a2…` | 4 | 142 | 14 | employment_duration_months | switched_to_assisted |
| `s_b0c8d5…` | 8 | 76 | 6 | income_range_band, employment_duration_months, residency_duration_years | abandoned |

### Inter-press interval distribution

```
 0– 5s | ██████████████████████ 318
 5–10s | █████████████████ 246
10–15s | ████████████ 173
15–20s | █████ 78
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
- `field_value_change_distribution`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:a18c4f7b2e5d9036c1f4b7e0a3d6c9b2e5f8a1d4c7b0e3f6a9b2c5d8e1f4a7b0`
against `cards_credit_apply_eligibility__multi_back_press` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
