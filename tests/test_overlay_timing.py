"""Tests for overlay timing — beat map conversion and even distribution.

Covers:
- Beat map entry dropping when entries overflow video duration
- Beat map clamping to [4, 18] second range
- Even distribution with too many overlays for short videos
- Edge cases: boundary conditions, single overlay, zero overlays
"""

import pytest

from pipeline.assemble import _beat_map_to_timings, _compute_overlay_timing


# ── Beat map: last entry exceeds duration ────────────────────────

class TestBeatMapDropping:
    """Beat map entries that can't fit min_s are silently dropped."""

    def test_last_entry_exceeds_duration(self):
        """Last entry starts at 95% of a 60s video — redistributes all entries."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "intro"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "mid"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "body"},
            {"start_pct": 0.75, "duration_pct": 0.15, "marker": "wrap"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "outro"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        # All 5 entries should get timing slots after redistribution
        assert len(timings) == 5
        for t in timings:
            assert t["start_s"] + t["duration_s"] <= 60.0

    def test_multiple_entries_overflow(self):
        """Multiple entries near the end trigger redistribution for all."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.30, "marker": "first"},
            {"start_pct": 0.90, "duration_pct": 0.10, "marker": "late1"},
            {"start_pct": 0.96, "duration_pct": 0.10, "marker": "late2"},
            {"start_pct": 0.99, "duration_pct": 0.10, "marker": "late3"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=50.0)

        # All 4 entries should get timing slots after redistribution
        assert len(timings) == 4
        for t in timings:
            assert t["start_s"] + t["duration_s"] <= 50.0

    def test_entry_exactly_at_min_boundary(self):
        """Entry with exactly 4.0s remaining should NOT be skipped."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.5, "marker": "first"},
            # At 60s total: starts at 56s, 4s remaining == min_s
            {"start_pct": 56.0 / 60.0, "duration_pct": 0.2, "marker": "exact"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        assert len(timings) == 2
        # Second entry should have exactly 4.0s duration (clamped)
        assert timings[1]["duration_s"] == 4.0

    def test_entry_just_under_min_remaining(self):
        """Entry with 3.9s remaining triggers redistribution — both get time."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.3, "marker": "first"},
            # starts at 56.1s → 3.9s remaining < 4.0s min → triggers redistrib
            {"start_pct": 56.1 / 60.0, "duration_pct": 0.2, "marker": "tight"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        assert len(timings) == 2
        for t in timings:
            assert t["start_s"] + t["duration_s"] <= 60.0

    def test_no_entries_dropped_after_redistribution(self):
        """Redistribution should ensure all entries get timing slots."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.20, "marker": "a"},
            {"start_pct": 0.25, "duration_pct": 0.20, "marker": "b"},
            {"start_pct": 0.50, "duration_pct": 0.20, "marker": "c"},
            {"start_pct": 0.95, "duration_pct": 0.10, "marker": "d"},
            {"start_pct": 0.98, "duration_pct": 0.10, "marker": "e"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=60.0)

        # All 5 entries should get slots after redistribution
        assert len(timings) == 5
        for t in timings:
            assert t["start_s"] + t["duration_s"] <= 60.0


# ── Beat map: clamping ───────────────────────────────────────────

class TestBeatMapClamping:
    """Duration clamping to the [4, 18] second range."""

    def test_clamp_to_max_18s(self):
        """Duration pct yielding 25s should be clamped to 18s."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.50, "marker": "long"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=50.0)

        assert len(timings) == 1
        assert timings[0]["duration_s"] == 18.0

    def test_clamp_to_min_4s(self):
        """Duration pct yielding 2s should be clamped up to 4s."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.04, "marker": "short"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=50.0)

        assert len(timings) == 1
        assert timings[0]["duration_s"] == 4.0

    def test_clamp_to_min_then_overflow_redistributes(self):
        """Entry at 48s of 50s video: clamped to 4s → overflow → redistributes.

        After clamping to 4s, start(48) + duration(4) = 52 > 50.
        Remaining = 2s < 4s → triggers redistribution for both entries.
        """
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.2, "marker": "first"},
            {"start_pct": 0.96, "duration_pct": 0.02, "marker": "tiny"},
        ]
        timings = _beat_map_to_timings(beat_map, total_duration_s=50.0)

        # Both entries should get slots after redistribution
        assert len(timings) == 2
        for t in timings:
            assert t["start_s"] + t["duration_s"] <= 50.0

    def test_within_range_no_clamping(self):
        """Duration within [4, 18] should pass through unchanged."""
        beat_map = [
            {"start_pct": 0.0, "duration_pct": 0.10, "marker": "normal"},
        ]
        # 0.10 * 80s = 8s → within range
        timings = _beat_map_to_timings(beat_map, total_duration_s=80.0)

        assert len(timings) == 1
        assert timings[0]["duration_s"] == 8.0


# ── Even distribution ────────────────────────────────────────────

class TestEvenDistribution:
    """Even distribution fallback when beat map is absent or mismatched."""

    def test_all_overlays_fit(self):
        """4 overlays in 60s — all should get timing slots."""
        timings = _compute_overlay_timing(overlay_count=4, total_duration_s=60.0)

        assert len(timings) == 4
        for t in timings:
            assert 4.0 <= t["duration_s"] <= 18.0
            assert t["start_s"] + t["duration_s"] <= 60.0

    def test_too_many_overlays_for_short_video(self):
        """10 overlays in 30s — durations reduced below 4s to fit all."""
        timings = _compute_overlay_timing(overlay_count=10, total_duration_s=30.0)

        # All 10 overlays should get timing slots (at reduced duration)
        assert len(timings) == 10
        for t in timings:
            assert t["duration_s"] > 0
            assert t["start_s"] + t["duration_s"] <= 30.0

    def test_very_short_video(self):
        """15s video with 5 overlays — durations reduced to fit all."""
        timings = _compute_overlay_timing(overlay_count=5, total_duration_s=15.0)

        # All 5 overlays should get timing slots (at reduced duration)
        assert len(timings) == 5
        for t in timings:
            assert t["duration_s"] > 0
            assert t["start_s"] + t["duration_s"] <= 15.0

    def test_single_overlay_fills_duration(self):
        """Single overlay should get max 18s or the full duration."""
        timings = _compute_overlay_timing(overlay_count=1, total_duration_s=60.0)

        assert len(timings) == 1
        assert timings[0]["start_s"] == 0.0
        assert timings[0]["duration_s"] == 18.0  # clamped to max

    def test_single_overlay_short_video(self):
        """Single overlay in a 10s video should get 10s (clamped to [4, 18])."""
        timings = _compute_overlay_timing(overlay_count=1, total_duration_s=10.0)

        assert len(timings) == 1
        assert timings[0]["start_s"] == 0.0
        assert timings[0]["duration_s"] == 10.0

    def test_first_overlay_starts_at_zero(self):
        """First overlay must start at t=0 for instant hook."""
        timings = _compute_overlay_timing(overlay_count=3, total_duration_s=60.0)

        assert timings[0]["start_s"] == 0.0

    def test_no_overlap_between_overlays(self):
        """Overlays should not overlap — each starts after previous ends."""
        timings = _compute_overlay_timing(overlay_count=5, total_duration_s=90.0)

        for i in range(1, len(timings)):
            prev_end = timings[i - 1]["start_s"] + timings[i - 1]["duration_s"]
            assert timings[i]["start_s"] >= prev_end

    def test_zero_overlays(self):
        """Zero overlays should return empty list."""
        timings = _compute_overlay_timing(overlay_count=0, total_duration_s=60.0)
        assert timings == []
