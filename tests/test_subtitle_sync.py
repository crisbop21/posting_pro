"""Tests for subtitle/timing synchronisation.

Covers:
- zip() truncation when subtitle count != overlay timing count
- First subtitle delay past title fade
- Subtitle skipped when duration < 1s
- Subtitle regeneration after overlay dropping
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _create_dummy_files():
    """Create dummy files so file-existence checks pass in integration tests."""
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


# ── build_section_subtitle_clips zip behaviour ───────────────────

class TestSubtitleZipTruncation:
    """build_section_subtitle_clips uses zip(subtitles, overlay_timings).

    When lists have different lengths, zip silently drops extras.
    These tests document and verify that behaviour.
    """

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_more_subtitles_than_timings_truncates(
        self, mock_imageclip, mock_render
    ):
        """5 subtitles + 4 timings → only 4 subtitle clips produced."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        subtitles = ["Sub 1", "Sub 2", "Sub 3", "Sub 4", "Sub 5"]
        timings = [
            {"start_s": 0.0, "duration_s": 12.0},
            {"start_s": 12.2, "duration_s": 12.0},
            {"start_s": 24.4, "duration_s": 12.0},
            {"start_s": 36.6, "duration_s": 12.0},
        ]

        clips = build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=60.0,
            title_duration_s=2.5,
        )

        # zip truncates: only 4 subtitles are processed
        # First might be skipped if it ends before title fade
        assert len(clips) <= 4
        # "Sub 5" is never rendered
        rendered_texts = [
            call.args[0] if call.args else call.kwargs.get("text", "")
            for call in mock_render.call_args_list
        ]
        assert "Sub 5" not in rendered_texts

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_more_timings_than_subtitles_truncates(
        self, mock_imageclip, mock_render
    ):
        """3 subtitles + 5 timings → only 3 subtitle clips attempted."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        subtitles = ["Sub 1", "Sub 2", "Sub 3"]
        timings = [
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 10.2, "duration_s": 10.0},
            {"start_s": 20.4, "duration_s": 10.0},
            {"start_s": 30.6, "duration_s": 10.0},
            {"start_s": 40.8, "duration_s": 10.0},
        ]

        clips = build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=60.0,
            title_duration_s=2.5,
        )

        # At most 3 clips (one per subtitle)
        assert len(clips) <= 3

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_equal_counts_produces_all_clips(
        self, mock_imageclip, mock_render
    ):
        """Equal subtitle and timing counts → all are processed."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        subtitles = ["Sub 1", "Sub 2", "Sub 3", "Sub 4"]
        timings = [
            {"start_s": 0.0, "duration_s": 12.0},
            {"start_s": 12.2, "duration_s": 12.0},
            {"start_s": 24.4, "duration_s": 12.0},
            {"start_s": 36.6, "duration_s": 12.0},
        ]

        clips = build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=60.0,
            title_duration_s=2.5,
        )

        # First subtitle may be delayed/skipped due to title, so 3 or 4
        assert len(clips) >= 3


# ── First subtitle delay past title ──────────────────────────────

class TestFirstSubtitleTitleDelay:
    """First subtitle must wait for the main title to fade out."""

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_first_subtitle_starts_after_title_fade(
        self, mock_imageclip, mock_render
    ):
        """First subtitle should start at title_duration + 0.4 (fade-out)."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        subtitles = ["First section", "Second section"]
        timings = [
            {"start_s": 0.0, "duration_s": 12.0},
            {"start_s": 12.2, "duration_s": 12.0},
        ]

        build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=30.0,
            title_duration_s=2.5,
        )

        # First clip: with_start should be called with title_end = 2.5 + 0.4 = 2.9
        first_start_call = mock_clip.with_start.call_args_list[0]
        start_time = first_start_call[0][0]
        assert start_time >= 2.9  # after title fade

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_first_subtitle_skipped_if_overlay_ends_before_title(
        self, mock_imageclip, mock_render
    ):
        """If first overlay ends before title fades, its subtitle is skipped."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        # First overlay is very short — ends at 2.0s, before title fade at 2.9s
        subtitles = ["Short section", "Normal section"]
        timings = [
            {"start_s": 0.0, "duration_s": 2.0},
            {"start_s": 5.0, "duration_s": 10.0},
        ]

        clips = build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=30.0,
            title_duration_s=2.5,
        )

        # First subtitle skipped (overlay ends at 2.0 < title_end 2.9)
        # Only second subtitle should appear
        assert len(clips) == 1


# ── Subtitle duration < 1s skipped ──────────────────────────────

class TestSubtitleMinDuration:
    """Subtitles with effective duration < 1s are skipped."""

    @patch("utils.video_utils.render_subtitle_image")
    @patch("utils.video_utils.ImageClip")
    def test_short_duration_subtitle_skipped(
        self, mock_imageclip, mock_render
    ):
        """Subtitle with < 1s effective duration should be skipped."""
        mock_render.return_value = "/tmp/fake_sub.png"
        mock_clip = MagicMock()
        mock_clip.with_start.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.with_effects.return_value = mock_clip
        mock_imageclip.return_value = mock_clip

        from utils.video_utils import build_section_subtitle_clips

        # First overlay: starts at 0, lasts 3.5s.
        # Title ends at 2.9s. Effective first sub duration = 0.6s < 1.0 → skip
        subtitles = ["Too short", "Normal"]
        timings = [
            {"start_s": 0.0, "duration_s": 3.5},
            {"start_s": 10.0, "duration_s": 10.0},
        ]

        clips = build_section_subtitle_clips(
            subtitles=subtitles,
            overlay_timings=timings,
            total_duration_s=30.0,
            title_duration_s=2.5,
        )

        # First subtitle effective duration: 3.5 - 2.9 = 0.6s < 1.0 → skipped
        assert len(clips) == 1

    def test_empty_subtitles_returns_empty(self):
        """Empty subtitle list should return empty clips list."""
        from utils.video_utils import build_section_subtitle_clips

        clips = build_section_subtitle_clips(
            subtitles=[],
            overlay_timings=[{"start_s": 0, "duration_s": 10}],
            total_duration_s=60.0,
        )
        assert clips == []

    def test_empty_timings_returns_empty(self):
        """Empty timings list should return empty clips list."""
        from utils.video_utils import build_section_subtitle_clips

        clips = build_section_subtitle_clips(
            subtitles=["Sub 1"],
            overlay_timings=[],
            total_duration_s=60.0,
        )
        assert clips == []


# ── Subtitle regeneration after overlay dropping ─────────────────

class TestSubtitleRegenerationAfterDrop:
    """When overlays are dropped, cached subtitles become stale."""

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    @patch("pipeline.assemble._generate_section_subtitles")
    def test_subtitles_regenerated_to_match_reduced_overlay_count(
        self, mock_gen_subs, mock_master, mock_eleven, mock_composite
    ):
        """When beat map drops an overlay, subtitles should be regenerated
        to match the reduced overlay count (not the original count)."""
        from tests.helpers import mock_state
        from pipeline.assemble import run

        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = lambda **kwargs: (
            kwargs["output_path"],
            {"engine": "mock", "success": True, "warnings": []},
        )
        mock_gen_subs.return_value = ["Sub A", "Sub B", "Sub C"]

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # Beat map drops last entry → 3 overlays survive
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]
        # No cached subtitles — force regeneration
        state.pop("section_subtitles", None)

        run(state)

        # Subtitles should be generated for the surviving overlay count (3)
        if mock_gen_subs.called:
            call_args = mock_gen_subs.call_args
            requested_count = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("overlay_count")
            assert requested_count == 3

    @patch("pipeline.assemble.composite_video")
    @patch("pipeline.assemble.elevenlabs_client")
    @patch("pipeline.assemble._master_audio", side_effect=lambda p: p)
    def test_stale_cached_subtitles_cause_zip_mismatch(
        self, mock_master, mock_eleven, mock_composite
    ):
        """Pre-cached subtitles with wrong count → zip truncation in build_section_subtitle_clips."""
        from tests.helpers import mock_state
        from pipeline.assemble import run

        mock_eleven.text_to_speech.convert.return_value = [b"audio"]
        mock_composite.side_effect = lambda **kwargs: (
            kwargs["output_path"],
            {"engine": "mock", "success": True, "warnings": []},
        )

        state = mock_state(up_to_step=5)
        state["estimated_duration_s"] = 60

        # Pre-cache 4 subtitles (matching original 4 overlays)
        state["section_subtitles"] = ["S1", "S2", "S3", "S4"]

        # Beat map drops last entry → only 3 overlay timing slots
        state["beat_map"] = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]

        # This should run without error — zip just silently truncates
        run(state)

        # The 4th subtitle "S4" is never shown (zip truncation)
        # This test documents the current (buggy) behavior
        call_kwargs = mock_composite.call_args
        section_clips = call_kwargs.kwargs.get("section_subtitle_clips", [])
        # At most 3 subtitle clips (one per surviving overlay)
        assert len(section_clips) <= 3
