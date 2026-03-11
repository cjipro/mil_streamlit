# while-sleeping / CJI Pulse

Machine Execution Brief — Built for AI, Reviewed by Human

> "Customers experiencing difficulties on Step 3 of Loans journey, abandoning —
> likely 45+, likely vulnerable."
> — Day 90 Vision: this sentence must be expressible from CJI Pulse on Day 90

## One-command setup
docker-compose up --build

## One-command run
python run_daily.py --date YYYY-MM-DD

## Structure
manifests/   → canonical source of truth (system_manifest.yaml lives here)
contracts/   → data contract YAMLs (one per source table)
config/      → all configuration (model, trust tiers, simulation)
scripts/     → build, validate, generate scripts
agents/      → agent code
app/         → Streamlit dashboard
data/        → local data (gitignored — large files only)
tests/       → validation and test scripts
docs/        → governance and architecture docs
notebooks/   → exploratory notebooks (never source of truth)

## Governance
Manifest is source of truth. Jira and GitLab are views.
Branch naming: feature/KAN-XXX-short-description
No ticket is closed without dual closure (human done + AI-ready done).

## Programme Principles
- Every Friday: something deployed, board moved, technical problem solved
- Demotivation is #1 risk: short sprints, visible wins, scope protected
- Audit before architecture: Canonical Statement 04 is law
- AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.
