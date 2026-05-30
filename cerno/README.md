# Cerno

In-bank deployment of the Pulse friction-detection engine. Observes
customer-journey friction on session telemetry, quantifies its cost in
downstream demand failure (calls / chat / NPS), prioritises agentic-AI
introduction candidates.

Classical ML + statistics + SQL at runtime — auditable,
procurement-passable for a regulated UK bank. No LLM in the runtime path.

## Quick start

```
make setup        # create data/ manifests/ findings/
make doctor       # confirm Python 3.11 + libs + paths
make test         # run unit tests
make safety       # confirm import-time safety gate fires clean
```

The bank edge node has the dependencies pre-installed. `make setup` does
not pip install. If a library is missing, that is an environment issue
to escalate, not something `cerno` will resolve at runtime.

## Memory layer

The project carries state across sessions in three files:

- [`STATE.md`](STATE.md) — session-priming pager
- [`docs/decisions/DECISIONS.md`](docs/decisions/DECISIONS.md) — append-only decision log
- [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — live snapshot of patterns + parameters

See [`SCAFFOLDING.md`](SCAFFOLDING.md) for what got built and why.

## Bindings

Source-specific column names and paths are bound at runtime via
environment or a YAML file (`cerno/settings.py::Settings`). Generic
placeholders only in code and committed files:

```
[identity_col] [timestamp_col] [opcode_col] [status_col]
[success_sentinel] [payload_col] [parquet_path]
```

## Layout

```
cerno/
  src/cerno/         # the package: primitives, safety, IO, lineage
  scripts/           # runnable utilities (doctor)
  tests/             # unit tests
  docs/              # CONVENTIONS, decisions, findings
  data/              # (gitignored) extract / ma_d / ma_s / marts
  manifests/         # (gitignored) manifest copies + run log
  findings/          # (gitignored) findings working memory
```
