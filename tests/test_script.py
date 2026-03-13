"""Tests for pipeline/script.py — script generation step."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state, _load_fixture

SCRIPT_FIXTURE = _load_fixture("script_response.txt")


# ── Successful script generation ──────────────────────────────────

@patch("pipeline.script.claude")
@patch("pipeline.script.st")
def test_script_generation(mock_st, mock_claude):
    """Should generate a script with word count in the 150-320 range."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=SCRIPT_FIXTURE)]
    mock_claude.messages.create.return_value = mock_msg

    from pipeline.script import run

    state = mock_state(up_to_step=2)

    result = run(state)

    assert result["script"] is not None
    assert isinstance(result["script"], str)
    assert len(result["script"]) > 0
    assert 150 <= result["word_count"] <= 320
    assert result["estimated_duration_s"] > 0


# ── Duration estimate is reasonable ───────────────────────────────

@patch("pipeline.script.claude")
@patch("pipeline.script.st")
def test_script_duration_estimate(mock_st, mock_claude):
    """Duration should be based on ~150 words per minute."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=SCRIPT_FIXTURE)]
    mock_claude.messages.create.return_value = mock_msg

    from pipeline.script import run

    state = mock_state(up_to_step=2)

    result = run(state)

    word_count = result["word_count"]
    expected_duration = round((word_count / 150) * 60)
    assert result["estimated_duration_s"] == expected_duration
    # Under 2 minutes for a script in the 150-320 word range
    assert result["estimated_duration_s"] <= 130


# ── Missing cleaned_data should error ─────────────────────────────

@patch("pipeline.script.st")
def test_script_no_cleaned_data(mock_st):
    """Missing cleaned_data should show error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.script import run

    state = mock_state(up_to_step=1)
    state["cleaned_data"] = None

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()


# ── Retries on API failure ────────────────────────────────────────

@patch("pipeline.script.time.sleep")
@patch("pipeline.script.claude")
@patch("pipeline.script.st")
def test_script_retries_on_failure(mock_st, mock_claude, mock_sleep):
    """Should retry on API failure and succeed on second attempt."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=SCRIPT_FIXTURE)]

    mock_claude.messages.create.side_effect = [
        Exception("API timeout"),
        mock_msg,
    ]

    from pipeline.script import run

    state = mock_state(up_to_step=2)

    result = run(state)

    assert result["script"] is not None
    assert mock_claude.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)  # 2^0 = 1
