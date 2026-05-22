## investments_premier_portfolio_overview__dwell_after_error — Signal altitude

### Detector run

- **Pack:** `investments_premier_portfolio_overview__dwell_after_error` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:1e7a4c0b9d2f5836a1c4e7b0d3f6a9c2e5b8d1f4a7c0e3b6d9f2a5c8e1b4d7f0`

### Analytic parameters

```yaml
method: dwell_z_score_vs_screen_baseline
trigger:
  requires_prior_event: validation_error
  dwell_window_seconds: 60
  p_value_threshold: 0.01
baseline_source: rolling_28d_same_screen
baseline_n: 11247
negative_class_discriminator:
  fire_only_if: no_suppression_signal_present AND error_type IN [data_load_failed, account_authorization_lost]
  suppression_signals:
    - {signal: scroll_depth_pct, threshold: 60, direction: above}
    - {signal: chart_drilldowns_in_session, threshold: 2, direction: above_or_equal}
    - {signal: return_within_7_days, threshold: true, direction: equals}
```

### Per-session evidence (first 5 of 1247 candidates)

`suppressed_by` lists the discriminator rule(s) that suppressed firing; an
empty list means the session fired (none did at cell 10 in this run).

| session_id | dwell_s | error_code | scroll_pct | drilldowns | ret_7d | suppressed_by | fired |
|---|---:|---|---:|---:|---|---|---|
| `s_3e9a14…` | 168 | `FILTER_NO_RESULTS` | 82 | 4 | true | scroll_depth_pct, chart_drilldowns_in_session, return_within_7_days | false |
| `s_5c2b07…` | 124 | `DATE_RANGE_EMPTY` | 71 | 3 | true | scroll_depth_pct, chart_drilldowns_in_session, return_within_7_days | false |
| `s_8a4d63…` | 211 | `FILTER_NO_RESULTS` | 88 | 5 | true | scroll_depth_pct, chart_drilldowns_in_session, return_within_7_days | false |
| `s_b1f8e0…` | 97 | `TRANSIENT_LOAD_HICCUP` | 64 | 2 | false | scroll_depth_pct, chart_drilldowns_in_session | false |
| `s_d0c5a2…` | 305 | `DATE_RANGE_EMPTY` | 91 | 7 | true | scroll_depth_pct, chart_drilldowns_in_session, return_within_7_days | false |

### Non-fire decision log (summary)

- Candidates evaluated: **1,247**
- Fired: **0**
- Suppressed by `scroll_depth_pct > 60`: 1,041
- Suppressed by `chart_drilldowns_in_session >= 2`: 894
- Suppressed by `return_within_7_days == true`: 885
- Excluded by `fire_only_if` error-type allowlist: 1,247 (no candidate's prior event was in `{data_load_failed, account_authorization_lost}`)

A correct cell-10 detector reports `fired_sessions == 0` (or very close). The
non-fire decision log is the audit artefact that proves the detector saw
each candidate and applied the discriminator deterministically. Note that
even if the engagement-signal suppression were ignored, the `fire_only_if`
allowlist would have suppressed all 1,247 anyway — the discriminator has two
independent layers of defence against false positives on cell 10.

### Audit bundle

The following are pinned to the audit bundle stamped at this detection's
lineage row:

- `lineage_chain`
- `analytic_inputs_hash`
- `cohort_split_breakdown`
- `threshold_config_hash`
- `suppression_signal_distribution`
- `non_fire_decision_log`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:1e7a4c0b9d2f5836a1c4e7b0d3f6a9c2e5b8d1f4a7c0e3b6d9f2a5c8e1b4d7f0`
against `investments_premier_portfolio_overview__dwell_after_error` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
