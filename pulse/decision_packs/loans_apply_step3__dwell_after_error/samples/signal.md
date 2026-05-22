## loans_apply_step3__dwell_after_error — Signal altitude

### Detector run

- **Pack:** `loans_apply_step3__dwell_after_error` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:9c1f4a7e8b3d0a52e6c9b2f1a8d4e7c3b6a9f5e2c8d1b4a7e0c3f6b9a2d5e8c1`

### Analytic parameters

```yaml
method: dwell_z_score_vs_screen_baseline
trigger:
  requires_prior_event: validation_error
  dwell_window_seconds: 60
  p_value_threshold: 0.01
baseline_source: rolling_28d_same_screen
baseline_n: 14902
```

### Per-session evidence (first 5 of 1847)

| session_id | dwell_s | error_code | cohort_tags | p_value |
|---|---:|---|---|---:|
| `s_2c8a91…` | 94 | `INCOME_DOC_FORMAT_REJECTED` | mobile, age_55_plus | 0.002 |
| `s_44b6e3…` | 132 | `INCOME_DOC_FORMAT_REJECTED` | mobile, age_55_plus, first_time | 0.0008 |
| `s_77d1f0…` | 71 | `EMPLOYMENT_DATE_RANGE_INVALID` | desktop, age_35_54 | 0.011 |
| `s_8e0c2b…` | 108 | `INCOME_DOC_FORMAT_REJECTED` | mobile, age_55_plus | 0.001 |
| `s_a3f9d4…` | 82 | `ADDRESS_LOOKUP_TIMEOUT` | mobile, age_55_plus, first_time | 0.004 |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:9c1f4a7e8b3d0a52e6c9b2f1a8d4e7c3b6a9f5e2c8d1b4a7e0c3f6b9a2d5e8c1`
against `loans_apply_step3__dwell_after_error` v0.1.0
on engine 1.0.0. Inputs are pinned by the chain; same inputs
produce byte-identical output.
