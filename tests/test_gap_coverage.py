"""Tests for gap detection and accent text coverage.

Covers:
- _compute_gap_intervals: gaps before, between, and after overlays
- _time_in_gap: midpoint check for accent clip positioning
- Accent text insufficient to cover large gaps
- Edge cases: no overlays, continuous overlays
"""

import pytest

from utils.video_utils import _compute_gap_intervals, _time_in_gap


# ── Gap detection ────────────────────────────────────────────────

class TestComputeGapIntervals:
    """_compute_gap_intervals finds time ranges with no image overlay."""

    def test_gap_after_last_overlay(self):
        """Last overlay ends at 50s, video is 65s → gap (50, 65)."""
        timings = [
            {"start_s": 0.0, "duration_s": 15.0},
            {"start_s": 15.2, "duration_s": 15.0},
            {"start_s": 30.4, "duration_s": 19.6},  # ends at 50s
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=65.0)

        # Gap after last overlay: 50.0 → 65.0
        assert any(g[0] >= 49.9 and g[1] == 65.0 for g in gaps)

    def test_gap_before_first_overlay(self):
        """First overlay starts at 5s → gap (0, 5) detected."""
        timings = [
            {"start_s": 5.0, "duration_s": 10.0},
            {"start_s": 15.2, "duration_s": 10.0},
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=30.0)

        # Gap before first: 0 → 5
        assert any(g[0] == 0.0 and g[1] == 5.0 for g in gaps)

    def test_gap_between_overlays(self):
        """Large gap between two overlays should be detected."""
        timings = [
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 25.0, "duration_s": 10.0},  # 15s gap
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=40.0)

        # Gap between: 10.0 → 25.0
        assert any(
            abs(g[0] - 10.0) < 0.01 and abs(g[1] - 25.0) < 0.01
            for g in gaps
        )

    def test_no_gap_when_continuous(self):
        """Back-to-back overlays with 0.2s gaps → no gaps returned."""
        timings = [
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 10.1, "duration_s": 10.0},  # 0.1s gap < 0.2 threshold
            {"start_s": 20.1, "duration_s": 9.9},   # ends at 30.0
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=30.0)

        assert gaps == []

    def test_no_overlays_entire_video_is_gap(self):
        """No overlays at all → entire video is one gap."""
        gaps = _compute_gap_intervals([], total_duration_s=60.0)

        assert len(gaps) == 1
        assert gaps[0] == (0.0, 60.0)

    def test_single_overlay_gaps_around_it(self):
        """Single overlay in the middle → gaps before and after."""
        timings = [
            {"start_s": 20.0, "duration_s": 10.0},  # 20-30s
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=60.0)

        # Gap before: 0 → 20
        assert any(g[0] == 0.0 and g[1] == 20.0 for g in gaps)
        # Gap after: 30 → 60
        assert any(g[0] == 30.0 and g[1] == 60.0 for g in gaps)

    def test_gap_threshold_exactly_0_2(self):
        """Gap of exactly 0.2s should NOT be reported (threshold is > 0.2)."""
        timings = [
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 10.2, "duration_s": 10.0},  # exactly 0.2s gap
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=20.2)

        # Only gap > 0.2 is reported — exactly 0.2 is not
        between_gaps = [g for g in gaps if g[0] >= 9.9 and g[1] <= 10.3]
        assert len(between_gaps) == 0

    def test_gap_just_over_threshold(self):
        """Gap of 0.3s (> 0.2) should be reported."""
        timings = [
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 10.3, "duration_s": 10.0},  # 0.3s gap
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=20.3)

        # 0.3s gap should be detected
        between_gaps = [g for g in gaps if 9.9 <= g[0] <= 10.1]
        assert len(between_gaps) == 1

    def test_unsorted_timings_handled(self):
        """Timings provided out of order should still produce correct gaps."""
        timings = [
            {"start_s": 20.0, "duration_s": 10.0},
            {"start_s": 0.0, "duration_s": 10.0},
            {"start_s": 40.0, "duration_s": 10.0},
        ]
        gaps = _compute_gap_intervals(timings, total_duration_s=60.0)

        # Should detect gaps: 10→20, 30→40, 50→60
        assert len(gaps) == 3


# ── Time-in-gap check ────────────────────────────────────────────

class TestTimeInGap:
    """_time_in_gap checks if an interval's midpoint falls inside a gap."""

    def test_fully_inside_gap(self):
        """Clip entirely within a gap → True."""
        gaps = [(10.0, 25.0)]
        assert _time_in_gap(12.0, 14.0, gaps) is True

    def test_fully_outside_gap(self):
        """Clip entirely outside any gap → False."""
        gaps = [(10.0, 25.0)]
        assert _time_in_gap(0.0, 2.0, gaps) is False

    def test_midpoint_inside_gap(self):
        """Clip straddles gap boundary but midpoint is inside → True."""
        gaps = [(10.0, 25.0)]
        # Clip: 8→14, midpoint = 11 → inside gap
        assert _time_in_gap(8.0, 14.0, gaps) is True

    def test_midpoint_outside_gap(self):
        """Clip straddles gap boundary but midpoint is outside → False."""
        gaps = [(10.0, 25.0)]
        # Clip: 6→12, midpoint = 9 → outside gap
        assert _time_in_gap(6.0, 12.0, gaps) is False

    def test_no_gaps(self):
        """No gaps → always False."""
        assert _time_in_gap(5.0, 7.0, []) is False

    def test_multiple_gaps(self):
        """Check against multiple gap intervals."""
        gaps = [(5.0, 10.0), (20.0, 30.0), (45.0, 60.0)]
        # midpoint = 7.5 → in first gap
        assert _time_in_gap(6.0, 9.0, gaps) is True
        # midpoint = 15 → not in any gap
        assert _time_in_gap(14.0, 16.0, gaps) is False
        # midpoint = 25 → in second gap
        assert _time_in_gap(24.0, 26.0, gaps) is True
        # midpoint = 50 → in third gap
        assert _time_in_gap(48.0, 52.0, gaps) is True


# ── Accent text gap coverage ─────────────────────────────────────

class TestAccentTextGapCoverage:
    """Accent text clips are spaced ~1.8s each and cannot cover large gaps."""

    def test_accent_clips_are_sparse(self):
        """Verify accent clips leave significant uncovered time in gaps."""
        # Simulate: 4 accent phrases in a 60s video with a 15s gap at the end
        total = 60.0
        accent_duration = 1.8
        phrases_count = 4
        gap_duration = 15.0  # seconds of background-only

        # Each accent clip covers 1.8s; gap_duration / accent_duration
        # = 8.3 clips needed to fully cover, but we only have 4 total
        # spread across the entire 60s video
        gap_start = total - gap_duration  # 45s
        gap_end = total  # 60s

        # Calculate how many accent clips could fall in the gap
        gap_between_accents = max(
            0.5,
            (total - accent_duration * phrases_count) / max(phrases_count, 1),
        )
        start_time = gap_between_accents / 2

        clips_in_gap = 0
        covered_time = 0.0
        for i in range(phrases_count):
            clip_start = start_time + i * (accent_duration + gap_between_accents)
            clip_end = clip_start + accent_duration
            if clip_start < gap_end and clip_end > gap_start:
                overlap = min(clip_end, gap_end) - max(clip_start, gap_start)
                covered_time += overlap
                clips_in_gap += 1

        # Most of the 15s gap is uncovered
        uncovered = gap_duration - covered_time
        assert uncovered > 10.0, (
            f"Expected >10s uncovered, got {uncovered:.1f}s. "
            f"Accent clips cannot fill a {gap_duration}s gap."
        )

    def test_redistribution_eliminates_large_tail_gap(self):
        """After redistribution, the tail gap should be small or eliminated."""
        from pipeline.assemble import _beat_map_to_timings

        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        # All 4 entries should survive after redistribution
        assert len(timings) == 4

        gaps = _compute_gap_intervals(timings, total_duration_s=60.0)

        # Tail gap should be small (< 2s) — overlays now cover the full duration
        tail_gaps = [g for g in gaps if g[1] == 60.0]
        if tail_gaps:
            tail_gap_duration = tail_gaps[0][1] - tail_gaps[0][0]
            assert tail_gap_duration < 2.0, (
                f"Tail gap is {tail_gap_duration:.1f}s — redistribution "
                f"should have eliminated the large background-only segment."
            )
