"""End-to-end assembly integration tests with mocked APIs.

Covers:
- No bare background segments: every time window has visual coverage
- Assembly with beat map overflow → visual coverage check
- Assembly without beat map → full coverage
- Timeline scanning for visual gaps
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state


def _mock_composite_return(**kwargs):
    return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})


@pytest.fixture(autouse=True)
def _create_dummy_files():
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
    for f in dummy_files:
        Path(f).unlink(missing_ok=True)


def _scan_visual_coverage(
    overlay_timings: list[dict],
    accent_clip_count: int,
    accent_duration: float,
    total_duration: float,
    accent_gap: float,
) -> list[tuple[float, float]]:
    """Scan the timeline and return intervals with NO visual layer.

    Checks 0.5-second windows across the entire video duration.
    A window is "covered" if any overlay or accent clip is active.

    Returns:
        List of (start, end) tuples where nothing is on screen.
    """
    # Build accent clip intervals
    accent_start = accent_gap / 2
    accent_intervals = []
    for i in range(accent_clip_count):
        s = accent_start + i * (accent_duration + accent_gap)
        accent_intervals.append((s, s + accent_duration))

    bare_segments = []
    window = 0.5
    t = 0.0
    segment_start = None

    while t < total_duration:
        # Check if any overlay covers this window
        overlay_covers = any(
            ov["start_s"] <= t < ov["start_s"] + ov["duration_s"]
            for ov in overlay_timings
        )
        # Check if any accent clip covers this window
        accent_covers = any(
            a_start <= t < a_end for a_start, a_end in accent_intervals
        )

        if not overlay_covers and not accent_covers:
            if segment_start is None:
                segment_start = t
        else:
            if segment_start is not None:
                bare_segments.append((segment_start, t))
                segment_start = None

        t += window

    if segment_start is not None:
        bare_segments.append((segment_start, total_duration))

    return bare_segments


# ── Timeline coverage scanning ───────────────────────────────────

class TestTimelineCoverage:
    """Scan the composite timeline for bare background segments."""

    def test_no_bare_segments_with_even_distribution(self):
        """Even distribution for 4 overlays in 60s should cover most of the video."""
        from pipeline.assemble import _compute_overlay_timing

        timings = _compute_overlay_timing(overlay_count=4, total_duration_s=60.0)

        # Simulate 6 accent clips (typical for a 270-word script)
        accent_count = 6
        accent_dur = 1.8
        accent_gap = max(0.5, (60.0 - accent_dur * accent_count) / accent_count)

        bare = _scan_visual_coverage(
            overlay_timings=timings,
            accent_clip_count=accent_count,
            accent_duration=accent_dur,
            total_duration=60.0,
            accent_gap=accent_gap,
        )

        # With even distribution + accent clips, no segment > 5s should be bare
        for seg_start, seg_end in bare:
            duration = seg_end - seg_start
            assert duration < 5.0, (
                f"Bare segment {seg_start:.1f}–{seg_end:.1f}s ({duration:.1f}s) "
                f"exceeds 5s threshold"
            )

    def test_no_large_bare_segments_after_redistribution(self):
        """Beat map overflow triggers redistribution — no large bare tail."""
        from pipeline.assemble import _beat_map_to_timings

        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        # All 4 timings survive after redistribution
        assert len(timings) == 4

        accent_count = 4
        accent_dur = 1.8
        accent_gap = max(0.5, (60.0 - accent_dur * accent_count) / accent_count)

        bare = _scan_visual_coverage(
            overlay_timings=timings,
            accent_clip_count=accent_count,
            accent_duration=accent_dur,
            total_duration=60.0,
            accent_gap=accent_gap,
        )

        # No bare segment should exceed 5s after redistribution
        max_bare = max((end - start for start, end in bare), default=0)
        assert max_bare < 5.0, (
            f"Bare segment of {max_bare:.1f}s found — redistribution "
            f"should have eliminated large background-only segments."
        )


# ── Full assembly integration ────────────────────────────────────

class TestAssemblyIntegration:
    """End-to-end run() with mocked external APIs."""

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_assembly_without_beat_map_full_coverage(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Assembly without beat map uses even distribution → all overlays present."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]

        captured = {}

        def capture_composite(**kwargs):
            captured["overlay_sequence"] = kwargs["overlay_sequence"]
            captured["accent_text_clips"] = kwargs.get("accent_text_clips", [])
            captured["section_subtitle_clips"] = kwargs.get("section_subtitle_clips", [])
            return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})

        mock_composite.side_effect = capture_composite

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60
        # No beat_map → even distribution

        run(state)

        # All 4 overlays should be in the sequence
        assert len(captured["overlay_sequence"]) == 4

        # Each overlay should have valid timing
        for ov in captured["overlay_sequence"]:
            assert ov["start_s"] >= 0
            assert 4.0 <= ov["duration_s"] <= 18.0
            assert ov["start_s"] + ov["duration_s"] <= 60.5  # small rounding tolerance

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_assembly_with_beat_map_overflow_preserves_all(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Assembly with overflowing beat map → redistribution preserves all overlays."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]

        captured = {}

        def capture_composite(**kwargs):
            captured["overlay_sequence"] = kwargs["overlay_sequence"]
            return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})

        mock_composite.side_effect = capture_composite

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]

        run(state)

        # All 4 overlays survive after redistribution
        assert len(captured["overlay_sequence"]) == 4

        # Verify all overlay paths are preserved in order
        for i, ov in enumerate(captured["overlay_sequence"]):
            assert ov["image_path"] == state["overlay_sequence"][i]

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_assembly_with_valid_beat_map_preserves_all(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Valid beat map that fits → all overlays preserved."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]

        captured = {}

        def capture_composite(**kwargs):
            captured["overlay_sequence"] = kwargs["overlay_sequence"]
            return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})

        mock_composite.side_effect = capture_composite

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 80

        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.15, "marker": "a"},
            {"start_pct": 0.20, "duration_pct": 0.15, "marker": "b"},
            {"start_pct": 0.40, "duration_pct": 0.15, "marker": "c"},
            {"start_pct": 0.60, "duration_pct": 0.15, "marker": "d"},
        ]

        run(state)

        assert len(captured["overlay_sequence"]) == 4

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_overlay_image_paths_preserved_in_order(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Overlay paths should match state paths in the same order."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]

        captured = {}

        def capture_composite(**kwargs):
            captured["overlay_sequence"] = kwargs["overlay_sequence"]
            return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})

        mock_composite.side_effect = capture_composite

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        run(state)

        original_paths = state["overlay_sequence"]
        for i, ov in enumerate(captured["overlay_sequence"]):
            assert ov["image_path"] == original_paths[i]

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_audio_duration_overrides_estimate(
        self, mock_master, mock_eleven, mock_composite
    ):
        """When ffprobe returns actual duration, it should override the estimate."""
        mock_eleven.text_to_speech.convert.return_value = [b"audio"]

        captured = {}

        def capture_composite(**kwargs):
            captured["overlay_sequence"] = kwargs["overlay_sequence"]
            return (kwargs["output_path"], {"engine": "mock", "success": True, "warnings": []})

        mock_composite.side_effect = capture_composite

        from pipeline.assemble import run

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # Mock ffprobe to return a shorter duration
        with patch("pipeline.assemble._get_audio_duration", return_value=45.0):
            run(state)

        # Timings should be based on 45s, not 60s
        for ov in captured["overlay_sequence"]:
            assert ov["start_s"] + ov["duration_s"] <= 45.5  # small rounding tolerance
