"""
validate_PULSE-12.py — PULSE-12 Docker environment health check
Verifies all 4 services are reachable and reports PASS/FAIL per service.

Services checked:
  - PostgreSQL : localhost:5432  (database=cjipulse, user=cjipulse_user)
  - Streamlit  : http://localhost:8501
  - Jupyter    : http://localhost:8888
  - Ollama     : http://localhost:11434  (model=qwen2.5-coder:14b)
"""

import sys
import json
import socket
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Telemetry helper — per manifests/telemetry_spec.yaml
# ---------------------------------------------------------------------------

def emit_telemetry(step_id, input_reference, output_summary, error_code,
                   error_class, retryability, business_impact_tier,
                   downstream_dependency_impact, manifest_spec_reference,
                   recovery_strategy_reference):
    telemetry = {
        "step_id": step_id,
        "input_reference": input_reference,
        "output_summary": output_summary,
        "error_code": error_code,
        "error_class": error_class,
        "retryability": retryability,
        "business_impact_tier": business_impact_tier,
        "downstream_dependency_impact": downstream_dependency_impact,
        "manifest_spec_reference": manifest_spec_reference,
        "recovery_strategy_reference": recovery_strategy_reference,
    }
    print(json.dumps(telemetry, indent=2), file=sys.stderr)


# ---------------------------------------------------------------------------
# Individual service checks
# ---------------------------------------------------------------------------

def check_tcp(host, port, label, timeout=5):
    """Check a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{label}: PASS — TCP {host}:{port} reachable"
    except OSError as e:
        return False, f"{label}: FAIL — TCP {host}:{port} unreachable ({e})"


def check_http(url, label, timeout=8, expected_status=None):
    """Check an HTTP endpoint returns a response."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "validate_PULSE-12/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if expected_status and status not in expected_status:
                return False, f"{label}: FAIL — {url} returned HTTP {status} (expected one of {expected_status})"
            return True, f"{label}: PASS — {url} returned HTTP {status}"
    except urllib.error.HTTPError as e:
        # Some services return non-200 on root but are still alive
        return True, f"{label}: PASS — {url} responded HTTP {e.code} (service alive)"
    except urllib.error.URLError as e:
        return False, f"{label}: FAIL — {url} unreachable ({e.reason})"
    except Exception as e:
        return False, f"{label}: FAIL — {url} error ({e})"


def check_ollama_model(base_url, model_name, label, timeout=8):
    """Check Ollama /api/tags and confirm model is available."""
    url = f"{base_url}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "validate_PULSE-12/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            if any(model_name in m for m in models):
                return True, f"{label}: PASS — {base_url} reachable, model '{model_name}' available"
            else:
                available = ", ".join(models) if models else "none"
                return False, f"{label}: FAIL — {base_url} reachable but model '{model_name}' not found (available: {available})"
    except urllib.error.URLError as e:
        return False, f"{label}: FAIL — {base_url} unreachable ({e.reason})"
    except Exception as e:
        return False, f"{label}: FAIL — {base_url} error ({e})"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print()
    print("validate_PULSE-12.py — PULSE-12 Docker environment health check")
    print("=" * 62)
    print()

    results = []

    # 1. PostgreSQL — TCP check (psycopg2 not required)
    ok, msg = check_tcp("localhost", 5432, "PostgreSQL")
    results.append((ok, msg, "validate_PULSE-12.check_postgres"))

    # 2. Streamlit — HTTP check
    ok, msg = check_http("http://localhost:8501", "Streamlit")
    results.append((ok, msg, "validate_PULSE-12.check_streamlit"))

    # 3. Jupyter — HTTP check
    ok, msg = check_http("http://localhost:8888", "Jupyter")
    results.append((ok, msg, "validate_PULSE-12.check_jupyter"))

    # 4. Ollama — HTTP + model check
    ok, msg = check_ollama_model("http://localhost:11434", "qwen2.5-coder:14b", "Ollama")
    results.append((ok, msg, "validate_PULSE-12.check_ollama"))

    # Print results
    for ok, msg, _ in results:
        print(f"  {'[PASS]' if ok else '[FAIL]'}  {msg.split(': ', 1)[1] if ': ' in msg else msg}")

    print()

    failures = [(ok, msg, sid) for ok, msg, sid in results if not ok]
    passes = sum(1 for ok, _, _ in results if ok)

    print(f"  Services reachable : {passes} / {len(results)}")
    print()

    if failures:
        print(f"  RESULT: FAIL — {len(failures)} service(s) unreachable")
        print()
        for ok, msg, step_id in failures:
            service_label = msg.split(":")[0]
            emit_telemetry(
                step_id=step_id,
                input_reference="docker-compose.yml",
                output_summary=f"{service_label} health check failed — service unreachable at configured port",
                error_code="PIPELINE-002",
                error_class="PIPELINE",
                retryability="backoff",
                business_impact_tier="P1",
                downstream_dependency_impact="All pipelines requiring this service are blocked",
                manifest_spec_reference="manifests/system_manifest.yaml#PULSE-12",
                recovery_strategy_reference="manifests/system_manifest.yaml#PULSE-12.recovery_patterns",
            )
        sys.exit(1)
    else:
        print("  RESULT: PASS — all 4 services reachable")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
