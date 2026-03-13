"""Tests for pipeline/background.py — background generation step."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state


# ── Successful background generation ──────────────────────────────

@patch("pipeline.background.render_ken_burns")
@patch("pipeline.background.requests.get")
@patch("pipeline.background.openai_client")
@patch("pipeline.background.st")
def test_background_generation(mock_st, mock_openai, mock_requests_get, mock_ken_burns):
    """Should generate a DALL-E image and render a Ken Burns video."""
    # Mock DALL-E response
    mock_image = MagicMock()
    mock_image.url = "https://example.com/generated_image.png"
    mock_dalle_resp = MagicMock()
    mock_dalle_resp.data = [mock_image]
    mock_openai.images.generate.return_value = mock_dalle_resp

    # Mock image download
    mock_dl_resp = MagicMock()
    mock_dl_resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_dl_resp.raise_for_status = MagicMock()
    mock_requests_get.return_value = mock_dl_resp

    # Mock Ken Burns render
    mock_ken_burns.return_value = "tmp/background_cinematic.mp4"

    from pipeline.background import run

    state = mock_state(up_to_step=3)
    state["visual_style"] = "cinematic"

    # Ensure tmp dir exists
    Path("tmp").mkdir(exist_ok=True)

    result = run(state)

    assert result["background_video_path"] is not None
    assert "background_cinematic" in result["background_video_path"]
    mock_openai.images.generate.assert_called_once()
    mock_ken_burns.assert_called_once()

    # Verify DALL-E was called with correct size
    call_kwargs = mock_openai.images.generate.call_args
    assert call_kwargs.kwargs["size"] == "1024x1792"
    assert call_kwargs.kwargs["quality"] == "hd"


# ── Image saved to tmp/ ───────────────────────────────────────────

@patch("pipeline.background.render_ken_burns")
@patch("pipeline.background.requests.get")
@patch("pipeline.background.openai_client")
@patch("pipeline.background.st")
def test_background_image_saved_to_tmp(mock_st, mock_openai, mock_requests_get, mock_ken_burns):
    """Downloaded DALL-E image should be saved in tmp/."""
    mock_image = MagicMock()
    mock_image.url = "https://example.com/bg.png"
    mock_dalle_resp = MagicMock()
    mock_dalle_resp.data = [mock_image]
    mock_openai.images.generate.return_value = mock_dalle_resp

    mock_dl_resp = MagicMock()
    mock_dl_resp.content = b"\x89PNG" + b"\x00" * 50
    mock_dl_resp.raise_for_status = MagicMock()
    mock_requests_get.return_value = mock_dl_resp

    mock_ken_burns.return_value = "tmp/background_clean.mp4"

    from pipeline.background import run

    Path("tmp").mkdir(exist_ok=True)

    state = mock_state(up_to_step=3)
    state["visual_style"] = "clean"

    run(state)

    # Verify the image was written to disk
    assert Path("tmp/background_clean.png").exists()

    # Clean up
    Path("tmp/background_clean.png").unlink(missing_ok=True)


# ── No visual style should error ──────────────────────────────────

@patch("pipeline.background.st")
def test_background_no_style(mock_st):
    """Missing visual_style should show error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.background import run

    state = mock_state(up_to_step=3)
    state["visual_style"] = None

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()
