## investments_premier_portfolio_overview__multi_back_press — Signal altitude

### Detector run

- **Pack:** `investments_premier_portfolio_overview__multi_back_press` v0.1.0
- **Synthesis mode:** `deterministic`
- **Engine version:** 1.0.0
- **Detection emitted at:** `2026-05-17T08:14:22Z`
- **Lineage anchor:** `sha256:7b3e9c1f4a8d2056e0b3d6a9c2f5e8b1d4a7c0f3e6b9d2a5c8f1b4e7a0d3c6f9`

### Analytic parameters

```yaml
method: back_press_burst_detection
trigger:
  min_back_press_events: 3
  window_seconds: 300
discriminator:
  rule: inter_press_interval_under_seconds
  value: 20
baseline_n: 11247
```

### Per-session evidence (first 5 of 384)

| session_id | back_presses | burst_window_s | median_interval_s | filter_state | exit_outcome |
|---|---:|---:|---:|---|---|
| `s_2e7a91…` | 5 | 87 | 11 | filter_active_prior_session | abandoned |
| `s_6c1f43…` | 4 | 124 | 16 | time_range_mismatch | filter_cleared_continued |
| `s_91b8d0…` | 6 | 98 | 9 | filter_active_prior_session | switched_to_mobile_app |
| `s_a4e0c7…` | 4 | 71 | 12 | filter_active_prior_session | advisor_message_initiated |
| `s_d8f3b6…` | 7 | 145 | 14 | both | abandoned |

### Inter-press interval distribution

```
 0– 5s | ████████████ 92
 5–10s | ██████████████████ 138
10–15s | ███████████ 84
15–20s | █████ 41
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
- `filter_state_at_burst_distribution`

### Reproducibility

Re-derive this output by replaying the lineage chain from
`sha256:7b3e9c1f4a8d2056e0b3d6a9c2f5e8b1d4a7c0f3e6b9d2a5c8f1b4e7a0d3c6f9`
against `investments_premier_portfolio_overview__multi_back_press` v0.1.0
on engine 1.0.0. Same inputs → byte-identical output.
