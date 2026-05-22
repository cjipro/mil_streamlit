## international_beneficiary_setup__abandon_before_submit — Signal altitude

### Detector run

- **Pack:** `international_beneficiary_setup__abandon_before_submit` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:d8b1f4a7c2e509360a3d6b9c2e5f8a1d4c7b0e3f6a9d2c5b8e1a4f7c0b3d6e9a`

### Analytic parameters

```yaml
method: terminal_abandonment_detection
trigger:
  requires_prior_step_completion: [corridor_select, beneficiary_entry]
  requires_dwell_above_percentile: 90
  requires_exit_without_event: payment_initiated
exclusions:
  session_returned_within_seconds: 1800
baseline_n: 7884
```

### Per-session evidence (first 5 of 718)

| session_id | time_on_step_s | final_field | field_value_state | prior_errors | 24h_return |
|---|---:|---|---|---:|---|
| `s_d72c08…` | 384 | `intermediary_bank_swift` | empty | 0 | true |
| `s_4f1b93…` | 521 | `sanctions_disclosure_modal` | viewed_not_acknowledged | 1 | true |
| `s_8a0e27…` | 248 | `beneficiary_address_line2` | partial | 0 | false |
| `s_2c5f60…` | 612 | `intermediary_bank_swift` | empty | 2 | true |
| `s_b91a4e…` | 437 | `fee_breakdown_disclosure` | expanded | 0 | false |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `final_field_focus_distribution`
- `sanctions_screening_decision_log_ref`
- `24h_return_rate`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:d8b1f4a7c2e509360a3d6b9c2e5f8a1d4c7b0e3f6a9d2c5b8e1a4f7c0b3d6e9a`
against `international_beneficiary_setup__abandon_before_submit` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
