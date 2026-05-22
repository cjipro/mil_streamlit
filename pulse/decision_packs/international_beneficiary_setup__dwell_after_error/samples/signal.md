## international_beneficiary_setup__dwell_after_error — Signal altitude

### Detector run

- **Pack:** `international_beneficiary_setup__dwell_after_error` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:a4d7e1c8b2f5036a9c1e4b7d0a3f6c9b2e5a8d1c4f7b0e3a6d9c2f5b8e1a4d7c`

### Analytic parameters

```yaml
method: dwell_z_score_vs_screen_baseline
trigger:
  requires_prior_event: validation_error
  dwell_window_seconds: 90
  p_value_threshold: 0.01
baseline_source: rolling_28d_same_screen
baseline_n: 7884
```

### Per-session evidence (first 5 of 924)

| session_id | dwell_s | error_code | cohort_tags | p_value |
|---|---:|---|---|---:|
| `s_e8b2a1…` | 168 | `SWIFT_BIC_INVALID` | first_time_intl, non_english_ui | 0.001 |
| `s_3f7c04…` | 211 | `NAME_LATIN_CHARS_REQUIRED` | first_time_intl, non_english_ui, age_55_plus | 0.0004 |
| `s_60a9d2…` | 124 | `IBAN_CHECKSUM_FAIL` | repeat_intl, english_ui | 0.008 |
| `s_8c1e47…` | 287 | `COUNTRY_SANCTIONS_HOLD` | repeat_intl, high_risk_corridor | 0.0002 |
| `s_b3d0f5…` | 152 | `SWIFT_BIC_INVALID` | first_time_intl, non_english_ui | 0.002 |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `sanctions_screening_decision_log_ref`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:a4d7e1c8b2f5036a9c1e4b7d0a3f6c9b2e5a8d1c4f7b0e3a6d9c2f5b8e1a4d7c`
against `international_beneficiary_setup__dwell_after_error` v0.1.0
on engine 1.0.0. Inputs are pinned by the chain; same inputs
produce byte-identical output.
