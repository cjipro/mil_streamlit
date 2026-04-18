# MIL Autonomy Success Criteria

Written: 2026-04-18  
Review date: 2026-04-27 (7 days after autonomy begins)

---

## First 7 Autonomous Days — Pass / Fail

| Metric | Pass | Fail |
|--------|------|------|
| Pipeline completion rate | ≥ 6/7 days complete (status=CLEAN or PARTIAL) | < 6/7 days |
| Silent failures | 0 unlogged exceptions across all steps | Any `except: pass` fires without a log entry |
| CHR anchor rate | ≥ 95% of findings anchored to a CHR entry | < 95% anchored |
| Churn score variance | Day-over-day delta ≤ 2× std dev (threshold set at Run #47) | > 2× std dev on any single day |
| Clark tier stability | No same-day CLARK-3 flip (escalate then downgrade within one run) | Flip occurs |

---

## How to Check on 2026-04-27

```sql
-- Pipeline completion rate
SELECT COUNT(*) FILTER (WHERE status IN ('CLEAN','PARTIAL')) as passed,
       COUNT(*) as total
FROM daily_runs
WHERE date >= '2026-04-20';

-- CHR anchor rate
SELECT
    COUNT(*) FILTER (WHERE chronicle_id IS NOT NULL AND chronicle_id != '') as anchored,
    COUNT(*) as total
FROM findings
WHERE run_date >= '2026-04-20';

-- Churn score day-over-day deltas
SELECT date,
       churn_risk_score,
       ABS(churn_risk_score - LAG(churn_risk_score) OVER (ORDER BY date)) as delta
FROM daily_runs
WHERE date >= '2026-04-20'
ORDER BY date;

-- Clark tier flips (same-day escalate+downgrade)
SELECT DATE(timestamp) as day, COUNT(*) as events, competitor
FROM clark_log
WHERE DATE(timestamp) >= '2026-04-20'
GROUP BY day, competitor
HAVING COUNT(*) > 2;
```

---

## Anomaly Threshold — Set After Run #47

Churn score was normalised at Run #33. Need 14+ normalised scores before setting a principled threshold.

Run #47 expected: ~2026-05-01. After that run:

```sql
SELECT
    AVG(ABS(churn_risk_score - LAG(churn_risk_score) OVER (ORDER BY date))) as mean_delta,
    STDEV(ABS(churn_risk_score - LAG(churn_risk_score) OVER (ORDER BY date))) as std_delta
FROM daily_runs
WHERE date >= '2026-04-18';
```

Set `ANOMALY_THRESHOLD = mean_delta + 2 * std_delta` in `mil/config/thresholds.yaml`.  
Add `WARN_ANOMALY` to run log if exceeded (Phase 3.1).

---

## QLoRA Routing Swap Gate

Do not swap fine-tuned model into enrichment route unless:

1. `py mil/tests/evaluate_enrichment.py --model qwen3-mil-ft` exits 0
2. P0/P1 agreement rate beats Haiku baseline recorded on 2026-04-19
3. issue_type accuracy ≥ 85% and severity accuracy ≥ 90%

If gate fails: retain Haiku. Re-evaluate after further training epochs.
