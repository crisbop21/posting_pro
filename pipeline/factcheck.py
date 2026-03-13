"""Step 2: Fact-checking via Claude."""

import json
import time
from pathlib import Path

import streamlit as st

from utils.api_clients import claude

MAX_RETRIES = 2


def _build_input(raw_data) -> str:
    """Convert raw_data (list of dicts or string) to a single text block."""
    if isinstance(raw_data, list):
        parts = []
        for article in raw_data:
            parts.append(
                f"Title: {article.get('title', '')}\n"
                f"Source: {article.get('source', '')}\n"
                f"Published: {article.get('published_at', '')}\n"
                f"Description: {article.get('description', '')}\n"
            )
        return "\n---\n".join(parts)
    return str(raw_data)


def _parse_response(text: str) -> dict:
    """Parse the fact-check JSON response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove markdown code fences
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


def _repair_json(raw_text: str) -> dict:
    """Ask Claude to fix malformed JSON output."""
    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=(
            "The following text was supposed to be valid JSON with keys "
            '"flags" (array of {claim, confidence, note}) and "cleaned_data" (string). '
            "Fix it and return ONLY valid JSON, nothing else."
        ),
        messages=[{"role": "user", "content": raw_text}],
    )
    return _parse_response(response.content[0].text)


def run(state: dict) -> dict:
    """Execute Step 2: fact-check raw data and produce cleaned output.

    Args:
        state: Current session state dict with raw_data populated.

    Returns:
        Updated state with cleaned_data and factcheck_flags.
    """
    raw_data = state.get("raw_data")
    if raw_data is None:
        st.error("No data to fact-check. Complete Step 1 first.")
        st.stop()

    skill = Path("skills/factcheck_prompt.md").read_text()
    input_text = _build_input(raw_data)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=3000,
                system=skill,
                messages=[{"role": "user", "content": input_text}],
            )
            raw_response = response.content[0].text

            try:
                result = _parse_response(raw_response)
            except (json.JSONDecodeError, KeyError):
                result = _repair_json(raw_response)

            state["factcheck_flags"] = result.get("flags", [])
            state["cleaned_data"] = result.get("cleaned_data", "")
            return state

        except Exception:
            if attempt == MAX_RETRIES:
                st.error(
                    "Could not complete fact-checking. "
                    "Use the Retry button to try again."
                )
                st.stop()
            time.sleep(2 ** attempt)

    return state
