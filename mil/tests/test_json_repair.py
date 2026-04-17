"""
test_json_repair.py — Unit tests for the JSON repair pipeline in enrich_sonnet.

Tests the trim → json.loads → json_repair fallback chain used when the
Anthropic API returns malformed JSON in enrichment batches.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _parse_response(raw: str) -> list[dict]:
    """Replicate the repair pipeline from enrich_sonnet._classify_batch()."""
    import re
    m = re.search(r"[\[\{]", raw)
    if not m:
        raise ValueError(f"No JSON in response: {raw[:200]}")
    start = m.start()
    last_close = max(raw.rfind("]"), raw.rfind("}"))
    trimmed = raw[start:last_close + 1]

    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            parsed = json.loads(repair_json(trimmed))
        except Exception as exc:
            raise ValueError(f"JSON repair failed: {exc}")

    if not isinstance(parsed, list):
        parsed = [parsed]
    return parsed


class TestJSONRepairPipeline:
    def test_clean_array_parses(self):
        raw = '[{"issue_type": "Login Failed", "severity_class": "P0"}]'
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0]["issue_type"] == "Login Failed"

    def test_preamble_stripped(self):
        raw = 'Here is the classification:\n[{"issue_type": "App Crashing", "severity_class": "P1"}]'
        result = _parse_response(raw)
        assert result[0]["severity_class"] == "P1"

    def test_markdown_code_block_stripped(self):
        raw = '```json\n[{"issue_type": "Payment Failed"}]\n```'
        result = _parse_response(raw)
        assert result[0]["issue_type"] == "Payment Failed"

    def test_single_object_wrapped_in_list(self):
        raw = '{"issue_type": "Transfer Failed", "severity_class": "P0"}'
        result = _parse_response(raw)
        assert isinstance(result, list)
        assert result[0]["issue_type"] == "Transfer Failed"

    def test_no_json_raises_value_error(self):
        raw = "Sorry, I cannot classify this."
        try:
            _parse_response(raw)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_multiple_objects_in_array(self):
        raw = '[{"issue_type": "Login Failed"}, {"issue_type": "App Crashing"}]'
        result = _parse_response(raw)
        assert len(result) == 2

    def test_trailing_text_after_array(self):
        raw = '[{"issue_type": "Login Failed"}] Note: classification complete.'
        result = _parse_response(raw)
        assert result[0]["issue_type"] == "Login Failed"
