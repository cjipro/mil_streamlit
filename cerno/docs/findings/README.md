# Findings log

Working memory of the analytical work. One file per substantive
analysis session, named `YYYY-MM-DD.md` (or `YYYY-MM-DD-N.md` if there
are multiple sessions in a day).

## Discipline

1. **Sanitised aggregates only.** Counts, distributions, percentiles,
   qualitative observations. Never raw rows, never identifiers, never
   PII.
2. **3–5 bullets per analysis.** Tight. The findings log is a memory
   layer, not a report — it carries forward the signal that future
   sessions need.
3. **Per-finding context.** Each bullet should be standalone: name the
   what, the where (e.g., §3.2), the magnitude, and any decision it
   triggers.
4. **Findings can trigger decisions.** When a finding leads to a
   load-bearing decision (parameter lock, algorithm choice, schema
   change), the agent emits a `Decision to log:` block in the same
   response. The operator appends to
   [`../decisions/DECISIONS.md`](../decisions/DECISIONS.md).

## Template

See [`TEMPLATE.md`](TEMPLATE.md). Copy → fill in → commit.

## Findings vs decisions

| Findings | Decisions |
|---|---|
| Time-stamped observations | Architectural / parametric locks |
| One file per day, append within | One log, append-only |
| "The cascade rate is 4%" | "We use Cox via statsmodels.PHReg" |
| Sanitised | Cites code + tests |
