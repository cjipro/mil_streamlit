## investments_premier_portfolio_overview__abandon_before_submit — Signal altitude

### Detector run

- **Pack:** `investments_premier_portfolio_overview__abandon_before_submit` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:4f8b2c5e1a7d09c36b0e3a6d9f2c5b8e1a4d7c0f3b6e9a2c5d8f1b4e7a0c3d6f`

### Analytic parameters

```yaml
method: terminal_abandonment_detection
trigger:
  requires_entry_intent_signal: true
  requires_dwell_above_percentile: 90
  requires_exit_without_event: ['trade_initiated', 'advisor_message_sent', 'report_downloaded']
exclusions:
  session_returned_within_seconds: 1800
  advised_phone_handoff_within_24h_excluded: true
baseline_n: 11247
```

### Per-session evidence (first 5 of 287)

| session_id | entry_intent | inferred_action | time_on_screen_s | drilldowns | holdings_opened | 24h_return | advised_phone_24h |
|---|---|---|---:|---:|---:|---|---|
| `s_4b8e21…` | push_portfolio_drop | `trade_initiated` | 318 | 5 | 3 | true | false |
| `s_7c0a93…` | holding_search | `trade_initiated` | 247 | 2 | 4 | false | false |
| `s_91d3f7…` | push_portfolio_drop | `advisor_message_sent` | 521 | 7 | 2 | true | false |
| `s_a6e4c0…` | chart_drilldown_amount_focus | `trade_initiated` | 184 | 6 | 1 | false | false |
| `s_d2f8b5…` | advisor_email_deep_link | `report_downloaded` | 409 | 3 | 0 | true | false |

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `entry_intent_distribution`
- `inferred_action_distribution`
- `24h_return_rate`
- `advised_phone_handoff_rate`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:4f8b2c5e1a7d09c36b0e3a6d9f2c5b8e1a4d7c0f3b6e9a2c5d8f1b4e7a0c3d6f`
against `investments_premier_portfolio_overview__abandon_before_submit` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
