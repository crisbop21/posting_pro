"""Tests for overlay sequence building — timing-to-overlay alignment.

Covers:
- Overlay sequence length matches timing count after beat map processing
- Dropped overlays when beat map skips entries
- Fallback to even distribution on beat map count mismatch
- Full run() integration with mocked APIs
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state


def _mock_composite_return(**kwargs):
    return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})


@pytest.fixture(autouse=True)
def _create_dummy_files():
    """Create dummy files so file-existence checks pass."""
    Path("tmp").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    dummy_files = [
        "tmp/background_cinematic.mp4",
        "tmp/overlay_0_processed.png",
        "tmp/overlay_1_processed.png",
        "tmp/overlay_2_processed.png",
        "tmp/overlay_3_processed.png",
        "tmp/overlay_4_processed.png",
    ]
    for f in dummy_files:
        Path(f).touch(exist_ok=True)
    yield
    for f in dummy_files:
        Path(f).unlink(missing_ok=True)


# ── Overlay sequence matches timing count ────────────────────────

class TestOverlaySequenceAlignment:
    """The overlay_sequence built in run() must align with timings."""

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_all_overlays_get_timing_slots_no_beat_map(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Without beat map, all overlays should get timing slots (60s video)."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = _mock_composite_return

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60
        overlays_count = len(state["overlay_sequence"])

        run(state)

        # Check the overlay_sequence passed to composite_video
        call_kwargs = mock_composite.call_args
        actual_seq = call_kwargs.kwargs.get("overlay_sequence") or call_kwargs[1].get(
            "overlay_sequence", call_kwargs[0][2]
        )
        assert len(actual_seq) == overlays_count

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_beat_map_drops_reduce_sequence_length(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Beat map that drops entries → overlay_sequence shorter than overlays."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = _mock_composite_return

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # 4 overlays, 4 beat map entries — last one overflows
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]

        run(state)

        call_kwargs = mock_composite.call_args
        actual_seq = call_kwargs.kwargs.get("overlay_sequence") or call_kwargs[0][2]
        # Entry d starts at 57s with 3s remaining → dropped
        assert len(actual_seq) == 3

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_beat_map_count_mismatch_falls_back_to_even(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Beat map with wrong count triggers even distribution fallback."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = _mock_composite_return

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # 4 overlays but only 3 beat map entries → mismatch
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.25, "marker": "a"},
            {"start_pct": 0.30, "duration_pct": 0.25, "marker": "b"},
            {"start_pct": 0.60, "duration_pct": 0.25, "marker": "c"},
        ]

        run(state)

        call_kwargs = mock_composite.call_args
        actual_seq = call_kwargs.kwargs.get("overlay_sequence") or call_kwargs[0][2]
        # Falls back to even distribution: all 4 overlays should fit in 60s
        assert len(actual_seq) == 4

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_valid_beat_map_preserves_all_overlays(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Well-formed beat map should keep all overlays in the sequence."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = _mock_composite_return

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 80

        # All entries fit comfortably in 80s
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.15, "marker": "a"},
            {"start_pct": 0.20, "duration_pct": 0.15, "marker": "b"},
            {"start_pct": 0.40, "duration_pct": 0.15, "marker": "c"},
            {"start_pct": 0.60, "duration_pct": 0.15, "marker": "d"},
        ]

        run(state)

        call_kwargs = mock_composite.call_args
        actual_seq = call_kwargs.kwargs.get("overlay_sequence") or call_kwargs[0][2]
        assert len(actual_seq) == 4


# ── Dropped overlays are logged ──────────────────────────────────

class TestDroppedOverlayLogging:
    """When overlays are dropped, the assembly should log a warning."""

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_dropped_overlays_logged_via_context(
        self, mock_master, mock_eleven, mock_composite
    ):
        """AssemblyContext should capture the WARNING log about dropped overlays."""
        from utils.assembly_context import AssemblyContext

        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = _mock_composite_return

        from pipeline.assemble import run

        ctx = AssemblyContext(gen_id=1)
        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # Beat map with overflow entry
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]

        run(state, ctx=ctx)

        log = ctx.get_log()
        assert any("dropped" in line.lower() or "WARNING" in line for line in log)
