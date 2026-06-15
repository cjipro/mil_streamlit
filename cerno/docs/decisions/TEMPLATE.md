# Decision entry template

Copy the block below, paste at the TOP of `DECISIONS.md`, replace the
placeholders. Allocate the next sequential `D-NNN` ID (look at the
current top entry and add one).

```
## D-NNN — YYYY-MM-DD — <Title>
**Status:** proposed | accepted | superseded
**Context:** <1–2 sentences — why this came up>
**Decision:** <1–2 sentences — what we chose>
**Consequences:** <what changes downstream>
**Implemented by:**
  - <file/path.py>::<function or class> (lines N–M)
  - <test/path.py>::<test_name>
**Supersedes:** D-NNN | none
```

## Rules

1. Never edit an existing entry. Supersede by adding a new entry that
   references it.
2. The `Implemented by:` field must cite at least one real file path
   that exists in the repo, or be marked `TBD in §X` if the decision is
   reached before the code exists.
3. Status flips from `proposed` → `accepted` when the implementation
   lands. From `accepted` → `superseded` only via a new entry.
4. IDs are strictly monotonic. No re-use.
