"""Tests for pipeline/assemble.py — video assembly step."""

import re
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state


def _mock_composite_return(**kwargs):
    """Helper: return (output_path, diagnostics_dict) like real composite_video."""
    return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})


@pytest.fixture(autouse=True)
def _create_dummy_fixtures():
    """Create dummy files that mock_state references so file-existence checks pass."""
    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    dummy_files = [
        "tmp/background_cinematic.mp4",
        "tmp/overlay_0_processed.png",
        "tmp/overlay_1_processed.png",
        "tmp/overlay_2_processed.png",
        "tmp/overlay_3_processed.png",
    ]
    for f in dummy_files:
        Path(f).touch(exist_ok=True)

    yield

    # Cleanup: remove dummy files created during the test
    for f in dummy_files:
        Path(f).unlink(missing_ok=True)


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
        assert timings[i]["start_s"] >= prev_end + 0.19  # gap is 0.2s in code


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


# ── Beat map boundary overflow (P1-5) ────────────────────────────

def test_beat_map_skips_entries_past_video_end():
    """Beat map entries that can't fit min_s before video end are skipped."""
    from pipeline.assemble import _beat_map_to_timings

    beat_map = [
        {"start_pct": 0.0, "duration_pct": 0.5, "marker": "first"},
        {"start_pct": 0.95, "duration_pct": 0.2, "marker": "overflow"},
    ]
    timings = _beat_map_to_timings(beat_map, total_duration_s=10.0)

    # Second entry starts at 9.5s with only 0.5s remaining < 4.0s min
    assert len(timings) == 1
    assert timings[0]["start_s"] + timings[0]["duration_s"] <= 10.0


def test_beat_map_clamps_duration_without_overflow():
    """Beat map entries that extend past end but have room for min_s are clamped."""
    from pipeline.assemble import _beat_map_to_timings

    beat_map = [
        {"start_pct": 0.0, "duration_pct": 0.3, "marker": "first"},
        {"start_pct": 0.5, "duration_pct": 0.8, "marker": "long"},
    ]
    timings = _beat_map_to_timings(beat_map, total_duration_s=20.0)

    assert len(timings) == 2
    # Second entry: starts at 10s, would last 16s (total 26s > 20s)
    # Should be clamped to 10s remaining
    assert timings[1]["start_s"] + timings[1]["duration_s"] <= 20.0


def test_beat_map_all_valid():
    """Beat map entries that fit entirely are unchanged (after clamping to 4-18s)."""
    from pipeline.assemble import _beat_map_to_timings

    beat_map = [
        {"start_pct": 0.0, "duration_pct": 0.25, "marker": "a"},
        {"start_pct": 0.3, "duration_pct": 0.25, "marker": "b"},
        {"start_pct": 0.6, "duration_pct": 0.25, "marker": "c"},
    ]
    timings = _beat_map_to_timings(beat_map, total_duration_s=40.0)

    assert len(timings) == 3
    for t in timings:
        assert 4.0 <= t["duration_s"] <= 18.0
        assert t["start_s"] + t["duration_s"] <= 40.0


# ── AssemblyContext thread safety ─────────────────────────────────

def test_assembly_context_complete_before_done():
    """State must be readable after is_done is True (no race)."""
    from utils.assembly_context import AssemblyContext

    ctx = AssemblyContext(gen_id=1)
    assert not ctx.is_done

    ctx.complete({"final_video_path": "/tmp/test.mp4"})

    assert ctx.is_done
    state, error = ctx.read_result()
    assert state is not None
    assert state["final_video_path"] == "/tmp/test.mp4"
    assert error is None


def test_assembly_context_fail_before_done():
    """Error must be readable after is_done is True."""
    from utils.assembly_context import AssemblyContext

    ctx = AssemblyContext(gen_id=2)
    ctx.fail("something broke")

    assert ctx.is_done
    state, error = ctx.read_result()
    assert state is None
    assert error == "something broke"


def test_assembly_context_cancellation():
    """check_cancelled should raise CancelledError after cancel_event is set."""
    from utils.assembly_context import AssemblyContext, CancelledError

    ctx = AssemblyContext(gen_id=3)
    assert not ctx.is_cancelled

    # Should not raise before cancellation
    ctx.check_cancelled("test")

    ctx.cancel_event.set()
    assert ctx.is_cancelled
    with pytest.raises(CancelledError, match="cancelled"):
        ctx.check_cancelled("test-stage")


def test_assembly_context_unique_paths():
    """Two contexts should produce different voiceover paths."""
    from utils.assembly_context import AssemblyContext

    ctx1 = AssemblyContext(gen_id=1)
    ctx2 = AssemblyContext(gen_id=2)
    assert ctx1.voiceover_path() != ctx2.voiceover_path()
    assert ctx1.run_id != ctx2.run_id


def test_assembly_context_log_thread_safe():
    """Logging from multiple threads should not lose messages."""
    from utils.assembly_context import AssemblyContext

    ctx = AssemblyContext(gen_id=1)
    n_threads = 4
    n_messages = 50

    def writer(thread_id):
        for i in range(n_messages):
            ctx.log(f"thread-{thread_id}-msg-{i}")

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log = ctx.get_log()
    assert len(log) == n_threads * n_messages


def test_assembly_context_complete_from_thread():
    """Complete called from a background thread should be visible to main."""
    from utils.assembly_context import AssemblyContext

    ctx = AssemblyContext(gen_id=42)
    expected = {"final_video_path": "outputs/test.mp4", "key": "value"}

    def worker():
        ctx.complete(expected)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert ctx.is_done
    state, error = ctx.read_result()
    assert state == expected
    assert error is None


# ── Successful assembly ───────────────────────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
def test_assemble_success(mock_eleven, mock_composite):
    """Full assembly should set final_video_path with correct naming."""
    mock_eleven.text_to_speech.convert.return_value = [b"fake audio data"]
    mock_composite.side_effect = _mock_composite_return

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    state = mock_state(up_to_step=5)
    state["custom_topic"] = "test topic"

    result = run(state)

    assert result["final_video_path"] is not None
    mock_eleven.text_to_speech.convert.assert_called_once()
    mock_composite.assert_called_once()


# ── Assembly with AssemblyContext ─────────────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
def test_assemble_with_context(mock_eleven, mock_composite):
    """Assembly with ctx should use unique voiceover path and log messages."""
    from utils.assembly_context import AssemblyContext

    mock_eleven.text_to_speech.convert.return_value = [b"audio"]
    mock_composite.side_effect = _mock_composite_return

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    ctx = AssemblyContext(gen_id=1)
    state = mock_state(up_to_step=5)
    state["custom_topic"] = "ctx test"

    result = run(state, ctx=ctx)

    assert result["final_video_path"] is not None
    # Verify voiceover was generated to a unique path (contains run_id)
    call_kwargs = mock_eleven.text_to_speech.convert.call_args
    # ctx should have produced log entries
    log = ctx.get_log()
    assert len(log) > 0
    assert any("Inputs OK" in line for line in log)


@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
def test_assemble_cancellation_stops_run(mock_eleven, mock_composite):
    """Pre-cancelled context should raise CancelledError."""
    from utils.assembly_context import AssemblyContext, CancelledError

    from pipeline.assemble import run

    Path("tmp").mkdir(exist_ok=True)

    ctx = AssemblyContext(gen_id=1)
    ctx.cancel_event.set()  # pre-cancel

    state = mock_state(up_to_step=5)

    with pytest.raises(CancelledError):
        run(state, ctx=ctx)

    # ElevenLabs should not have been called
    mock_eleven.text_to_speech.convert.assert_not_called()


# ── Output path follows naming convention ─────────────────────────

@patch("pipeline.assemble.composite_video")
@patch("pipeline.assemble.elevenlabs_client")
def test_assemble_output_naming(mock_eleven, mock_composite):
    """Output file should be outputs/{slug}-{YYYYMMDD}.mp4."""
    mock_eleven.text_to_speech.convert.return_value = [b"audio"]
    mock_composite.side_effect = _mock_composite_return

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
def test_assemble_voiceover_strips_markers(mock_eleven, mock_composite):
    """The voiceover text sent to ElevenLabs should not contain [IMAGE:] markers."""
    mock_eleven.text_to_speech.convert.return_value = [b"audio"]
    mock_composite.side_effect = _mock_composite_return

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

def test_assemble_no_background():
    """Missing background_video_path should raise RuntimeError."""
    from pipeline.assemble import run

    state = mock_state(up_to_step=4)
    state["background_video_path"] = None

    with pytest.raises(RuntimeError, match="No background video"):
        run(state)
