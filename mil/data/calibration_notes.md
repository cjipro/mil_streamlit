# MIL Calibration Notes

Ongoing retrospective checks — does the system output correspond to observable reality?
One entry per check. Takes 20 minutes. Run every 2 weeks from 2026-04-18.

---

## 2026-04-18 — Phase 0 Calibration Check

### CHR Anchor Distribution (Run #34)
| CHR ID | Findings | % |
|--------|----------|---|
| CHR-003 | 30 | 22% |
| CHR-002 | 25 | 18% |
| CHR-005 | 24 | 18% |
| CHR-004 | 15 | 11% |
| CHR-018 | 15 | 11% |
| CHR-006 | 13 | 10% |
| CHR-001 | 7 | 5% |
| CHR-014 | 3 | 2% |
| CHR-008/009/011/017 | 1 each | <1% |

**Verdict:** CHR-001 magnet fix confirmed. No single entry dominates. Spread is healthy.

### Churn Score Normalization Break
Runs 1–32: unnormalized scores (77–107). Run 33 (2026-04-18): normalized 0–100 via CHURN_SCORE_CAP=180, score=49.2.
**Any anomaly threshold built on historical data is invalid until 14+ normalized runs accumulate (~2026-05-02).**
Set anomaly alert after Run #47, using std dev from runs 33–46.

### 3-Row Retrospective (2026-04-18, looking back 14–30 days)

| Run date | Top Clark finding | Observable in next 14 days? |
|----------|-------------------|----------------------------|
| 2026-04-05 | NatWest CLARK-3 (Login Failed, CAC≈0.65) | [TO CHECK: NatWest App Store rating Apr 5–19] |
| 2026-04-10 | Barclays CLARK-2 (App Not Opening, CHR-004) | [TO CHECK: Barclays rating change Apr 10–24] |
| 2026-04-15 | NatWest CLARK-3 continued | [TO CHECK: DownDetector NatWest spikes Apr 15–29] |

**Action:** Hussain to fill in the "Observable" column from App Store history / DownDetector.
This is the first calibration baseline. Two weeks from now, check 2026-05-02 run findings.

---

## Next check due: 2026-05-02
