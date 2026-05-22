## cards_credit_apply_eligibility__abandon_before_submit — Signal altitude

### Detector run

- **Pack:** `cards_credit_apply_eligibility__abandon_before_submit` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:6c9e2f5a8b1d4c7e0f3a6b9c2e5d8f1a4b7c0e3f6a9b2c5d8e1f4a7b0c3e6d9f`

### Analytic parameters

```yaml
method: terminal_abandonment_detection
trigger:
  requires_prior_field_completion: [income_range_band, employment_status, residency_duration_years]
  requires_dwell_above_percentile: 90
  requires_exit_without_event: eligibility_check_submitted
exclusions:
  session_returned_within_seconds: 1800
baseline_n: 22108
```

### Per-session evidence (first 5 of 1486)

| session_id | time_on_step_s | final_field | field_value_state | prior_errors | 24h_return | 7d_return |
|---|---:|---|---|---:|---|---|
| `s_1a4e87…` | 312 | `credit_authorization_consent` | unchecked | 0 | false | false |
| `s_3c8f02…` | 198 | `credit_authorization_consent` | unchecked | 1 | false | true |
| `s_5d6b41…` | 421 | `existing_credit_commitments` | partial | 0 | true | true |
| `s_82a0e9…` | 267 | `credit_authorization_consent` | unchecked | 0 | false | false |
| `s_b7c3d4…` | 354 | `income_range_band` | filled | 2 | false | false |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `final_field_focus_distribution`
- `24h_return_rate`
- `7d_return_rate`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:6c9e2f5a8b1d4c7e0f3a6b9c2e5d8f1a4b7c0e3f6a9b2c5d8e1f4a7b0c3e6d9f`
against `cards_credit_apply_eligibility__abandon_before_submit` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
