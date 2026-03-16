"""Step 1: Data gathering — live news or custom topic research."""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from utils.api_clients import claude, MARKETAUX_API_KEY, FINNHUB_API_KEY

MAX_RETRIES = 2
MIN_ARTICLES = 3


def _fetch_marketaux(search: str = "") -> list[dict]:
    """Fetch recent finance articles from Marketaux.

    Args:
        search: Optional keyword filter. When provided, only articles
                matching these terms are returned.
    """
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    params = {
        "filter_entities": "true",
        "language": "en",
        "published_after": three_days_ago,
        "api_token": MARKETAUX_API_KEY,
    }
    if search:
        params["search"] = search
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://api.marketaux.com/v1/news/all",
                params=params,
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/news",
                params={
                    "category": "general",
                    "minId": 0,
                    "token": FINNHUB_API_KEY,
                },
                timeout=15,
            )
            resp.raise_for_status()
            articles = resp.json()
            recent = [
                a for a in articles
                if datetime.fromtimestamp(
                    a.get("datetime", 0), tz=timezone.utc
                ) >= cutoff
            ]
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
                for a in recent[:10]
            ]
        except (requests.RequestException, ValueError):
            if attempt == MAX_RETRIES:
                return []
            time.sleep(2 ** attempt)
    return []


def _research_custom_topic(topic: str) -> str:
    """Use Claude with web search to research a custom topic."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                system=(
                    "You are a research assistant. Given a finance or AI topic, "
                    "produce a detailed factual briefing with key data points, "
                    "recent developments, and context. Include specific numbers, "
                    "dates, and sources where possible. Output plain text only."
                ),
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": topic}],
            )
            # Extract text blocks from the response (skip web search tool-use blocks)
            text_parts = [
                block.text for block in response.content
                if block.type == "text"
            ]
            return "\n".join(text_parts)
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

        # Hybrid gather: Claude research + real news articles on the topic
        research = _research_custom_topic(topic)

        # Search Marketaux filtered by the custom topic keywords
        articles = _fetch_marketaux(search=topic)
        if len(articles) < MIN_ARTICLES:
            # Silent fallback to Finnhub (unfiltered) — better than nothing
            articles = _fetch_finnhub()

        state["raw_data"] = {
            "research": research,
            "articles": articles,
        }

    else:
        raise RuntimeError("Please select a topic mode.")

    return state
