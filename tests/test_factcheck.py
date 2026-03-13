"""Tests for pipeline/factcheck.py — fact-checking step."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from tests.helpers import mock_state, _load_json_fixture, _load_fixture

FACTCHECK_FIXTURE = _load_json_fixture("factcheck_response.json")


# ── Successful JSON parse ─────────────────────────────────────────

@patch("pipeline.factcheck.claude")
@patch("pipeline.factcheck.st")
def test_factcheck_success(mock_st, mock_claude):
    """Valid JSON response should be parsed correctly."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(FACTCHECK_FIXTURE))]
    mock_claude.messages.create.return_value = mock_msg

    from pipeline.factcheck import run

    state = mock_state(up_to_step=1)

    result = run(state)

    assert result["cleaned_data"] is not None
    assert isinstance(result["cleaned_data"], str)
    assert len(result["cleaned_data"]) > 0
    assert isinstance(result["factcheck_flags"], list)
    assert len(result["factcheck_flags"]) == 4
    assert result["factcheck_flags"][0]["confidence"] == "high"


# ── JSON with markdown code fences ────────────────────────────────

@patch("pipeline.factcheck.claude")
@patch("pipeline.factcheck.st")
def test_factcheck_strips_markdown_fences(mock_st, mock_claude):
    """Response wrapped in ```json ... ``` should still parse."""
    fenced = f"```json\n{json.dumps(FACTCHECK_FIXTURE)}\n```"
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=fenced)]
    mock_claude.messages.create.return_value = mock_msg

    from pipeline.factcheck import run

    state = mock_state(up_to_step=1)

    result = run(state)

    assert result["cleaned_data"] is not None
    assert len(result["factcheck_flags"]) == 4


# ── Malformed JSON triggers repair ────────────────────────────────

@patch("pipeline.factcheck.claude")
@patch("pipeline.factcheck.st")
def test_factcheck_repair_on_malformed_json(mock_st, mock_claude):
    """Malformed initial response should trigger a repair call."""
    malformed_msg = MagicMock()
    malformed_msg.content = [MagicMock(text="{ broken json here")]

    repaired_msg = MagicMock()
    repaired_msg.content = [MagicMock(text=json.dumps(FACTCHECK_FIXTURE))]

    mock_claude.messages.create.side_effect = [malformed_msg, repaired_msg]

    from pipeline.factcheck import run

    state = mock_state(up_to_step=1)

    result = run(state)

    assert result["cleaned_data"] is not None
    assert len(result["factcheck_flags"]) == 4
    # Two calls: original + repair
    assert mock_claude.messages.create.call_count == 2


# ── No raw data should error ─────────────────────────────────────

@patch("pipeline.factcheck.st")
def test_factcheck_no_raw_data(mock_st):
    """Missing raw_data should show error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.factcheck import run

    state = mock_state(up_to_step=0)
    state["raw_data"] = None

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()
