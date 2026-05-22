## cards_credit_apply_eligibility__dwell_after_error — Signal altitude

### Detector run

- **Pack:** `cards_credit_apply_eligibility__dwell_after_error` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:4e7b1c8a3d6f0529b2e5a8c1d4f7b0e3a6c9b2d5f8e1a4c7b0d3f6a9c2e5b8d1`

### Analytic parameters

```yaml
method: dwell_z_score_vs_screen_baseline
trigger:
  requires_prior_event: eligibility_error
  dwell_window_seconds: 45
  p_value_threshold: 0.01
baseline_source: rolling_28d_same_screen
baseline_n: 22108
```

### Per-session evidence (first 5 of 2214)

| session_id | dwell_s | error_code | cohort_tags | p_value |
|---|---:|---|---|---:|
| `s_3f1a82…` | 84 | `ELIGIBILITY_PRE_DECLINE` | age_18_24, thin_file | 0.0008 |
| `s_5c7e09…` | 112 | `INCOME_THRESHOLD_NOT_MET` | gig, age_25_34 | 0.0004 |
| `s_91a2f6…` | 67 | `ELIGIBILITY_PRE_DECLINE` | age_18_24, thin_file, new_to_credit | 0.002 |
| `s_b4d0c8…` | 96 | `CREDIT_AUTHORIZATION_DECLINED` | recent_job_change, age_25_34 | 0.001 |
| `s_e7f3a1…` | 78 | `ELIGIBILITY_PRE_DECLINE` | gig, age_35_54 | 0.003 |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:4e7b1c8a3d6f0529b2e5a8c1d4f7b0e3a6c9b2d5f8e1a4c7b0d3f6a9c2e5b8d1`
against `cards_credit_apply_eligibility__dwell_after_error` v0.1.0
on engine 1.0.0. Inputs are pinned by the chain; same inputs
produce byte-identical output.
