"""Step 1: Data gathering — live news or custom topic research."""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from utils.api_clients import claude, MARKETAUX_API_KEY, FINNHUB_API_KEY

MAX_RETRIES = 2
MIN_ARTICLES = 3


def _fetch_marketaux() -> list[dict]:
    """Fetch recent finance articles from Marketaux."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://api.marketaux.com/v1/news/all",
                params={
                    "filter_entities": "true",
                    "language": "en",
                    "published_after": yesterday,
                    "api_token": MARKETAUX_API_KEY,
                },
                timeout=15,
            )
            if resp.status_code == 429:
                return []  # hit daily cap — caller will fallback
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "source": a.get("source", ""),
                    "url": a.get("url", ""),
                    "published_at": a.get("published_at", ""),
                }
                for a in data.get("data", [])
            ]
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                return []
            time.sleep(2 ** attempt)
    return []


def _fetch_finnhub() -> list[dict]:
    """Fetch general market news from Finnhub as a fallback."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/news",
                params={
                    "category": "general",
                    "token": FINNHUB_API_KEY,
                },
                timeout=15,
            )
            resp.raise_for_status()
            articles = resp.json()
            return [
                {
                    "title": a.get("headline", ""),
                    "description": a.get("summary", ""),
                    "source": a.get("source", ""),
                    "url": a.get("url", ""),
                    "published_at": datetime.fromtimestamp(
                        a.get("datetime", 0), tz=timezone.utc
                    ).isoformat(),
                }
                for a in articles[:10]
            ]
        except (requests.RequestException, ValueError):
            if attempt == MAX_RETRIES:
                return []
            time.sleep(2 ** attempt)
    return []


def _research_custom_topic(topic: str) -> str:
    """Use Claude to research a custom topic and return a summary string."""
    skill = Path("skills/script_skill.md").read_text()

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=(
                    "You are a research assistant. Given a finance or AI topic, "
                    "produce a detailed factual briefing with key data points, "
                    "recent developments, and context. Include specific numbers, "
                    "dates, and sources where possible. Output plain text only."
                ),
                messages=[{"role": "user", "content": topic}],
            )
            return response.content[0].text
        except Exception:
            if attempt == MAX_RETRIES:
                raise RuntimeError("Could not research this topic.") from None
            time.sleep(2 ** attempt)
    return ""


def run(state: dict) -> dict:
    """Execute Step 1: gather raw data based on topic_mode.

    Args:
        state: Current session state dict.

    Returns:
        Updated state with raw_data populated.
    """
    mode = state.get("topic_mode")

    if mode == "live_news":
        articles = _fetch_marketaux()
        if len(articles) < MIN_ARTICLES:
            # Silent fallback to Finnhub — do not surface to user
            articles = _fetch_finnhub()
        if not articles:
            raise RuntimeError("Could not fetch any news articles.")
        state["raw_data"] = articles

    elif mode == "custom_topic":
        topic = state.get("custom_topic", "")
        if not topic.strip():
            raise RuntimeError("Please enter a topic before gathering data.")
        state["raw_data"] = _research_custom_topic(topic)

    else:
        raise RuntimeError("Please select a topic mode.")

    return state
