## loans_apply_step3__abandon_before_submit — Signal altitude

### Detector run

- **Pack:** `loans_apply_step3__abandon_before_submit` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:f3a8c1b6e9d4527a0c8e1b4f7a0d3c6b9e2f5a8d1b4c7e0f3a6b9c2e5d8f1a4b`

### Analytic parameters

```yaml
method: terminal_abandonment_detection
trigger:
  requires_prior_step_completion: [step1, step2]
  requires_dwell_above_percentile: 90
  requires_exit_without_event: submit_clicked
exclusions:
  session_returned_within_seconds: 1800
baseline_n: 14902
```

### Per-session evidence (first 5 of 1103)

| session_id | time_on_step_s | final_field | field_value_state | prior_errors | 24h_return |
|---|---:|---|---|---:|---|
| `s_c91a47…` | 421 | `monthly_outgoings_total` | empty | 0 | true |
| `s_2f8b30…` | 287 | `monthly_outgoings_total` | partial | 1 | false |
| `s_5d4e91…` | 612 | `employer_address_line1` | empty | 2 | true |
| `s_88a0c2…` | 198 | `loan_purpose_other_text` | partial | 0 | false |
| `s_a1f6e3…` | 503 | `monthly_outgoings_total` | empty | 1 | true |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `final_field_focus_distribution`
- `24h_return_rate`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:f3a8c1b6e9d4527a0c8e1b4f7a0d3c6b9e2f5a8d1b4c7e0f3a6b9c2e5d8f1a4b`
against `loans_apply_step3__abandon_before_submit` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
