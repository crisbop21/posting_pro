"""Tests for pipeline/gather.py — data gathering step."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_state, _load_json_fixture

MARKETAUX_FIXTURE = _load_json_fixture("marketaux_response.json")
FINNHUB_FIXTURE = _load_json_fixture("finnhub_response.json")


# ── Marketaux success ──────────────────────────────────────────────

@patch("pipeline.gather.requests.get")
@patch("pipeline.gather.st")
def test_gather_live_news_marketaux(mock_st, mock_get):
    """Marketaux returns 3+ articles — should use them directly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MARKETAUX_FIXTURE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    from pipeline.gather import run

    state = mock_state(up_to_step=0)
    state["topic_mode"] = "live_news"

    result = run(state)

    assert result["raw_data"] is not None
    assert isinstance(result["raw_data"], list)
    assert len(result["raw_data"]) == 3
    assert result["raw_data"][0]["title"] == "Fed Holds Interest Rates Steady Amid Inflation Concerns"


# ── Marketaux returns < 3 articles → Finnhub fallback ──────────────

@patch("pipeline.gather.requests.get")
@patch("pipeline.gather.st")
def test_gather_live_news_fallback_to_finnhub(mock_st, mock_get):
    """Marketaux returns fewer than 3 articles — should silently fall back to Finnhub."""
    marketaux_resp = MagicMock()
    marketaux_resp.status_code = 200
    marketaux_resp.json.return_value = {"data": [MARKETAUX_FIXTURE["data"][0]]}
    marketaux_resp.raise_for_status = MagicMock()

    finnhub_resp = MagicMock()
    finnhub_resp.status_code = 200
    finnhub_resp.json.return_value = FINNHUB_FIXTURE
    finnhub_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [marketaux_resp, finnhub_resp]

    from pipeline.gather import run

    state = mock_state(up_to_step=0)
    state["topic_mode"] = "live_news"

    result = run(state)

    assert result["raw_data"] is not None
    assert len(result["raw_data"]) >= 3
    # Finnhub articles have "headline" mapped to "title"
    assert result["raw_data"][0]["title"] == "S&P 500 Closes at Record High on Tech Rally"


# ── Marketaux 429 → Finnhub fallback ──────────────────────────────

@patch("pipeline.gather.requests.get")
@patch("pipeline.gather.st")
def test_gather_live_news_429_fallback(mock_st, mock_get):
    """Marketaux returns 429 — should silently fall back to Finnhub."""
    marketaux_resp = MagicMock()
    marketaux_resp.status_code = 429

    finnhub_resp = MagicMock()
    finnhub_resp.status_code = 200
    finnhub_resp.json.return_value = FINNHUB_FIXTURE
    finnhub_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [marketaux_resp, finnhub_resp]

    from pipeline.gather import run

    state = mock_state(up_to_step=0)
    state["topic_mode"] = "live_news"

    result = run(state)

    assert result["raw_data"] is not None
    assert len(result["raw_data"]) >= 3


# ── Custom topic mode ─────────────────────────────────────────────

@patch("pipeline.gather.claude")
@patch("pipeline.gather.st")
def test_gather_custom_topic(mock_st, mock_claude):
    """Custom topic mode should call Claude and return a research string."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Research summary about AI chip market trends.")]
    mock_claude.messages.create.return_value = mock_msg

    from pipeline.gather import run

    state = mock_state(up_to_step=0)
    state["topic_mode"] = "custom_topic"
    state["custom_topic"] = "AI chip market trends"

    result = run(state)

    assert result["raw_data"] is not None
    assert isinstance(result["raw_data"], str)
    assert "AI chip market" in result["raw_data"]
    mock_claude.messages.create.assert_called_once()


# ── Custom topic with empty string ────────────────────────────────

@patch("pipeline.gather.st")
def test_gather_custom_topic_empty(mock_st):
    """Empty custom topic should show an error and stop."""
    mock_st.stop.side_effect = SystemExit

    from pipeline.gather import run

    state = mock_state(up_to_step=0)
    state["topic_mode"] = "custom_topic"
    state["custom_topic"] = ""

    with pytest.raises(SystemExit):
        run(state)

    mock_st.error.assert_called_once()
