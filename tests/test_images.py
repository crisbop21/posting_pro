"""Tests for pipeline/images.py — image sourcing step."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state, _load_fixture

SCRIPT_FIXTURE = _load_fixture("script_response.txt")


# ── Extract image markers ─────────────────────────────────────────

def test_extract_image_markers():
    """Should extract all [IMAGE: ...] markers from a script."""
    from pipeline.images import _extract_image_markers

    markers = _extract_image_markers(SCRIPT_FIXTURE)

    assert len(markers) == 4
    assert "Federal Reserve building exterior" in markers[0]
    assert "AI microchip" in markers[1]
    assert "Bitcoin" in markers[2]
    assert "stock market" in markers[3]


# ── Pexels search returns 4 candidates ────────────────────────────

@patch("pipeline.images.process_overlay")
@patch("pipeline.images.download_image")
@patch("pipeline.images.search_pexels")
@patch("pipeline.images.claude")
@patch("pipeline.images.st")
def test_images_pexels_success(mock_st, mock_claude, mock_search, mock_download, mock_process):
    """Each segment should get images from Pexels (4 candidates searched)."""
    # Mock Claude query generation
    mock_query_msg = MagicMock()
    mock_query_msg.content = [MagicMock(text="federal reserve building")]
    mock_claude.messages.create.return_value = mock_query_msg

    # Mock Pexels returning 4 results
    mock_search.return_value = [
        {"id": i, "url": f"https://example.com/img{i}.jpg", "src": {}, "photographer": "Test"}
        for i in range(4)
    ]

    mock_download.return_value = "tmp/downloaded.jpg"
    mock_process.return_value = "tmp/processed.png"

    from pipeline.images import run

    state = mock_state(up_to_step=4)
    state["script"] = SCRIPT_FIXTURE

    result = run(state)

    assert len(result["overlay_sequence"]) == 4
    # search_pexels called once per marker
    assert mock_search.call_count == 4
    # Each search requested with the session
    for c in mock_search.call_args_list:
        assert c.args[1] is not None  # query string


# ── Pexels fails → DALL-E fallback ────────────────────────────────

@patch("pipeline.images._generate_dalle_image")
@patch("pipeline.images.download_image")
@patch("pipeline.images.search_pexels")
@patch("pipeline.images.claude")
@patch("pipeline.images.st")
def test_images_dalle_fallback(mock_st, mock_claude, mock_search, mock_download, mock_dalle):
    """When Pexels returns empty, should fall back to DALL-E."""
    mock_query_msg = MagicMock()
    mock_query_msg.content = [MagicMock(text="bitcoin coin")]
    mock_claude.messages.create.return_value = mock_query_msg

    mock_search.return_value = []  # Pexels returns nothing
    mock_dalle.return_value = "tmp/dalle_fallback.png"

    from pipeline.images import run

    state = mock_state(up_to_step=4)
    state["script"] = SCRIPT_FIXTURE

    result = run(state)

    assert len(result["overlay_sequence"]) == 4
    assert mock_dalle.call_count == 4  # All 4 markers fell back to DALL-E


# ── No script should error ────────────────────────────────────────

@patch("pipeline.images.st")
def test_images_no_script(mock_st):
    """Missing script should show error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.images import run

    state = mock_state(up_to_step=3)
    state["script"] = None

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()


# ── No markers returns empty list ─────────────────────────────────

@patch("pipeline.images.st")
def test_images_no_markers(mock_st):
    """Script with no [IMAGE:] markers should return empty overlay_sequence."""
    from pipeline.images import run

    state = mock_state(up_to_step=4)
    state["script"] = "A script with no image markers at all."

    result = run(state)

    assert result["overlay_sequence"] == []
