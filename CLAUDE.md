# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

- **Project:** CJI Pulse / while-sleeping
- **Private project** — no employer references
- **Mission:** Daily customer journey intelligence platform
- **Day 90 vision:** "Customers experiencing difficulties on Step 3 of Loans journey, abandoning — likely 45+, likely vulnerable. In last 3 days 5 customers said App journey sucks."

## Environment Rules

- Windows machine — always use `py` not `python`
- Git Bash for git commands
- Claude Code for all development tasks
- Repo: `C:\Users\hussa\while-sleeping`

## Build Rules

- Manifest is source of truth — `system_manifest.yaml`
- Dual closure rule: validator passes AND human closes ticket in Jira UI manually
- Never close Jira tickets programmatically
- Always validate before committing
- Commit manifest status update after every ticket

## Current Sprint Status

Sprint 1 — 8 tickets BUILT:
- KAN-10: GitLab repo (BUILT)
- KAN-17: system_manifest.yaml (BUILT, commit 377a4be)
- KAN-19: telemetry_spec.yaml (BUILT, commit 021a8a9)
- KAN-01G: graduated_trust_tiers.yaml (BUILT, commit d630986)
- KAN-01H: hypothesis_library.yaml (BUILT, commit dd89e32)
- KAN-13: audit_findings.yaml (BUILT, commit fe492e2)
- KAN-18: build_from_manifest.py (BUILT, commit bb47a21)
- KAN-12: Docker environment (BUILT)

**Next ticket:** KAN-16 — Create all Jira tickets

## Key Manifests

| File | Purpose |
|------|---------|
| `manifests/system_manifest.yaml` | 73 components, source of truth |
| `manifests/telemetry_spec.yaml` | Error spec — all pipelines must use |
| `manifests/graduated_trust_tiers.yaml` | Trust model, `law_for: narrative-agent, governance-agent` |
| `manifests/hypothesis_library.yaml` | 23 hypotheses — 16 APPROVED, 7 PENDING |

## Model Config

- **Primary:** `claude-sonnet-4-6`
- **Local:** `qwen2.5-coder:14b` via Ollama at `http://localhost:11434`
- **Use local for:** yaml generation, file creation, validation scripts
- **Use Claude for:** architecture decisions, governance review, complex reasoning

## Model Routing Rules

- Use Sonnet (claude-sonnet-4-6) for: multi-file logic, CLI tools with flags,
  telemetry compliance, anything reading multiple manifests
- Use Qwen (local) for: simple YAML scaffolds, single-file templates,
  validation scripts under 50 lines
- Default to Sonnet when in doubt — switch to Qwen only for clearly simple tasks

## Programme Principles

1. Every Friday: something deployed, board moved, technical problem solved
2. Manifest is source of truth — Jira is a view, never the source
3. Audit before architecture
4. Semantic telemetry on every failure
5. Build for future agents — all config machine-readable YAML
6. One command to run everything: `python run_daily.py --date YYYY-MM-DD`
7. AI is easy to demo. It is hard to ship. Day 90 is a shipping proof, not a demo.
