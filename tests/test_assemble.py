"""Tests for pipeline/assemble.py — video assembly step."""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state


# ── Overlay timing computation ────────────────────────────────────

def test_overlay_timing_computation():
    """Timing should produce valid start times within duration bounds."""
    from pipeline.assemble import _compute_overlay_timing

    timings = _compute_overlay_timing(overlay_count=4, total_duration_s=60.0)

    assert len(timings) == 4
    for t in timings:
        assert 4.0 <= t["duration_s"] <= 18.0
        assert t["start_s"] >= 0

    # Overlays should not overlap (each starts after previous ends + gap)
    for i in range(1, len(timings)):
        prev_end = timings[i - 1]["start_s"] + timings[i - 1]["duration_s"]
        assert timings[i]["start_s"] >= prev_end + 0.4  # at least 0.4s gap


def test_overlay_timing_zero_overlays():
    """Zero overlays should return empty list."""
    from pipeline.assemble import _compute_overlay_timing

    timings = _compute_overlay_timing(overlay_count=0, total_duration_s=60.0)
    assert timings == []


def test_overlay_timing_single_overlay():
    """Single overlay should get reasonable duration."""
    from pipeline.assemble import _compute_overlay_timing

    timings = _compute_overlay_timing(overlay_count=1, total_duration_s=60.0)

    assert len(timings) == 1
    assert timings[0]["start_s"] == 0.0
    assert 4.0 <= timings[0]["duration_s"] <= 18.0


# ── Successful assembly ───────────────────────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
@patch("pipeline.assemble.st")
def test_assemble_success(mock_st, mock_eleven, mock_composite):
    """Full assembly should set final_video_path with correct naming."""
    # Mock ElevenLabs
    mock_eleven.text_to_speech.convert.return_value = [b"fake audio data"]

    # Mock FFmpeg composite
    mock_composite.return_value = "outputs/test-topic-20260313.mp4"

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    state = mock_state(up_to_step=5)
    state["custom_topic"] = "test topic"

    result = run(state)

    assert result["final_video_path"] is not None
    mock_eleven.text_to_speech.convert.assert_called_once()
    mock_composite.assert_called_once()


# ── Output path follows naming convention ─────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
@patch("pipeline.assemble.st")
def test_assemble_output_naming(mock_st, mock_eleven, mock_composite):
    """Output file should be outputs/{slug}-{YYYYMMDD}.mp4."""
    mock_eleven.text_to_speech.convert.return_value = [b"audio"]
    mock_composite.side_effect = lambda **kwargs: kwargs["output_path"]

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    state = mock_state(up_to_step=5)
    state["custom_topic"] = "AI Chip Market Trends 2026!"

    result = run(state)

    path = result["final_video_path"]
    filename = Path(path).name

    # Should match pattern: slug-YYYYMMDD.mp4
    assert re.match(r"^[a-z0-9-]+-\d{8}\.mp4$", filename), f"Bad filename: {filename}"
    assert filename.endswith(f"-{datetime.now().strftime('%Y%m%d')}.mp4")
    # Slug should be lowercase, no special chars
    slug_part = filename.rsplit("-", 1)[0]
    assert "!" not in slug_part
    assert slug_part == slug_part.lower()


# ── Voiceover strips IMAGE markers ────────────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
@patch("pipeline.assemble.st")
def test_assemble_voiceover_strips_markers(mock_st, mock_eleven, mock_composite):
    """The voiceover text sent to ElevenLabs should not contain [IMAGE:] markers."""
    mock_eleven.text_to_speech.convert.return_value = [b"audio"]
    mock_composite.side_effect = lambda **kwargs: kwargs["output_path"]

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    state = mock_state(up_to_step=5)

    run(state)

    call_kwargs = mock_eleven.text_to_speech.convert.call_args
    text_sent = call_kwargs.kwargs.get("text") or call_kwargs.args[0] if call_kwargs.args else ""
    if not text_sent:
        # Try keyword args
        text_sent = call_kwargs.kwargs.get("text", "")
    assert "[IMAGE:" not in text_sent


# ── No background should error ────────────────────────────────────

@patch("pipeline.assemble.st")
def test_assemble_no_background(mock_st):
    """Missing background_video_path should show error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.assemble import run

    state = mock_state(up_to_step=4)
    state["background_video_path"] = None

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()
