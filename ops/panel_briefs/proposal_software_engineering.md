# Engineering Posture — `app.cjipro.com/engineering`

## Anchoring principle

Abstractions are minimal, load-bearing contracts are explicit and testable, and every architectural coupling is defensible at IT-review depth.

## On the page: 5 sections

### 1. Zero Entanglement — Production Validation

**Philosophy:** The MIL pipeline imports nothing from internal systems; internal systems never import MIL code. One-way data exit via `mil/outputs/mil_findings.json` only. This is enforced by a hard-fail build validator.

**Falsifiable claim:** `python scripts/validate_mil_import_rule.py` succeeds on every commit. Violation = build fails, exit code 1. No exceptions, no warnings-treated-as-pass.

**Drill-down:** `scripts/validate_mil_import_rule.py` + `mil/MIL_SCHEMA.yaml`

---

### 2. Adapter Swappability — GitHubPages / Local / Null

**Philosophy:** Publishers don't know where their output lives. In production: GitHub Pages. In clone ops: HDFS, local filesystem, or no-op. Adapters are swappable by YAML, not code changes.

**Falsifiable claim:** `mil/publish/adapters.py` defines `PublishAdapter` base class + three implementations. `publish_config.yaml` selects adapter + config. No hardcoded publish targets in caller code.

**Drill-down:** `mil/publish/adapters.py` + `mil/config/publish_config.yaml`

---

### 3. Defense-in-Depth Deny-List (MIL-110)

**Philosophy:** Public GitHub Pages repo refuses to accept sensitive paths (auth/, runbooks, CLAUDE.md, .py files, secrets.yaml). Caller can't accidentally publish source code or credentials. Policy is regex-matched on every write.

**Falsifiable claim:** 56 test cases in `mil/tests/test_publish_deny_list.py` verify legitimate briefing paths pass, sensitive paths fail. GitHubPagesAdapter calls `assert_publishable()` before every commit.

**Drill-down:** `mil/publish/adapters.py` (lines 56–77) + `mil/tests/test_publish_deny_list.py`

---

### 4. Cookie Spec as Code

**Philosophy:** Session cookie contract (name, domain, SameSite, Max-Age, HttpOnly) is a machine-enforced invariant. This spec is dual-represented: `COOKIE_SPEC.md` (human) + `cookie_spec.ts` (machine). Drift between them is a bug. Changes require coordinated deploys to both issuer (magic_link) and validator (edge_bouncer).

**Falsifiable claim:** `mil/auth/magic_link/test/cookie_spec.test.ts` isolates all cookie invariants and fails on violation. `edge_bouncer` JWKS cache TTL, validation logic, and session lifetime are co-documented in `MIL-64 — __Secure-cjipro-session`.

**Drill-down:** `mil/auth/COOKIE_SPEC.md` + `mil/auth/magic_link/src/cookie_spec.ts` + `mil/auth/magic_link/test/cookie_spec.test.ts`

---

### 5. Five Workers, TypeScript, vitest — 300+ Tests

**Philosophy:** Edge compute is production-grade: types enforced, every request path tested, every deploy has a runbook. No vanilla JS, no mock-free integration tests.

**Falsifiable claim:** 5 Workers deployed to production: edge_bouncer, magic_link, app_cjipro, sonar_redirect, approvals. 37 test files + 41 Python pipeline tests = 300+ assertions. All TypeScript, all vitest. Every material rollout has a `ops/runbooks/mil-NN_*.md` playbook.

**Drill-down:** `mil/auth/{edge_bouncer,magic_link,app_cjipro,sonar_redirect,approvals}/test/*.test.ts` + `ops/runbooks/mil-{59,60,62,82,110}_*.md`

---

### 6. Self-Hosted, No CDN Entanglement (MIL-136/157/158)

**Philosophy:** Fonts are bundled WOFF2 served from cjipro.com, not Google Fonts CDN. This removes a bank-corp-proxy redirection blocker and guarantees reachability inside air-gapped networks. Source of truth: a single YAML + fetch script.

**Falsifiable claim:** `mil/publish/fonts_pipeline/fetch_fonts.py` downloads fonts once, generates Worker-side TS module with absolute URLs. Tests verify Inter, Source Serif 4, Plus Jakarta Sans, DM Mono are present in both site + briefing CSS. No CDN fallback.

**Drill-down:** `mil/publish/fonts_pipeline/fetch_fonts.py` + `mil/tests/test_fonts_pipeline.py`

---

### 7. Two-Repo Contract: Private MIL / Public Briefing

**Philosophy:** `mil_streamlit` (GitHub, private) is the system of record. Rendered briefings push to `mil-briefing` (GitHub, public). Dual-push to both GitHub + GitLab (read-mirror) ensures fork-resistance. No manual rebase recovery — it's in the playbook.

**Falsifiable claim:** Every successful publish invokes `git push github` + `git push gitlab` atomically. If GitLab rebase conflict occurs, `ops/runbooks/mil-110_repo_split.md` has step-by-step recovery. No auto-rebase.

**Drill-down:** `mil/publish/adapters.py` (GitHubPagesAdapter.publish) + `ops/runbooks/mil-110_repo_split.md`

---

## Section to cut

**Generic "Engineering Principles":** Many platforms ship a page of "We value reliability, automation, testing, security." This audience built those pages. Instead, we show three things they'll instantly audit: the validator (hard-fail import rule), the deny-list (regex + test count), the spec-as-code (COOKIE_SPEC.md ↔ code). These are defensible *because* they're specific, measurable, and falsifiable.

---

## One non-obvious claim

**Secrets are never in publish paths, because the deny-list catches them at the API boundary, not at the filesystem.** Most platforms protect secrets via .gitignore + CI gate. We reject secrets *by name pattern* before the adapter touches the disk. This is bank-side defense-in-depth: Caller bug → adapter hard-fail before a GitHub commit is even staged. IT review sees a wall of regex patterns and a regression-test suite, not a hope that CI gates work.

---

## The one sentence that earns trust or distrust at first scan

*"V1 publisher is load-bearing for V2/V3/V4 patches; MIL-125 queues retirement is in flight, and the paper trail is in `mil/CHRONICLE.md` with open tickets."*

This sentence:
- Admits the coupling (no handwaving).
- Names the work to fix it (MIL-125).
- Points to the evidence (CHRONICLE.md).
- Signals the team knows the debt is there and is planning to retire it.

If this audience spots it and sees *no* MIL-125, or CHRONICLE.md contradicts the claim, trust evaporates.

---

## Trade-off note: Show the coupling, not hide it

Rather than:
> "Our publish system is fully modular and decoupled."

Propose:
> "V1 publisher reads the live HTML and re-publishes it with V2/V3/V4 patches applied. This is a known coupling. MIL-125 will move to a queue-based model so V4 can publish standalone. Timeline: Q2 2026. Until then: Single source of truth in V1's output. Monitored in runbook MIL-110."

The second version earns more trust because it's *honest about the constraint and has a plan*. A bank IT reviewer has seen too many platforms hide their load-bearing debt. Seeing it named, measured, and scheduled is a signal that the team is in control, not in denial.

