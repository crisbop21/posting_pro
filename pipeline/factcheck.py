"""Step 2: Fact-checking via Claude."""

import json
import time
from pathlib import Path

import anthropic

from utils.api_clients import claude

MAX_RETRIES = 2
DELIMITER = "---CLEANED_DATA---"


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


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    return cleaned.strip()


def _parse_response(text: str) -> dict:
    """Parse the delimiter-separated fact-check response.

    Expected format:
        <JSON array of flags>
        ---CLEANED_DATA---
        <plain text cleaned data>
    """
    if DELIMITER not in text:
        # Fallback: try parsing as the old single-JSON format
        cleaned = _strip_fences(text)
        result = json.loads(cleaned)
        return result

    parts = text.split(DELIMITER, 1)
    flags_text = _strip_fences(parts[0])
    cleaned_data = parts[1].strip()

    flags = json.loads(flags_text)

    return {"flags": flags, "cleaned_data": cleaned_data}


def run(state: dict) -> dict:
    """Execute Step 2: fact-check raw data and produce cleaned output.

    Args:
        state: Current session state dict with raw_data populated.

    Returns:
        Updated state with cleaned_data and factcheck_flags.
    """
    raw_data = state.get("raw_data")
    if raw_data is None:
        raise RuntimeError("No data to fact-check. Complete Step 1 first.")

    skill = Path("skills/factcheck_prompt.md").read_text()
    input_text = _build_input(raw_data)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4000,
                system=skill,
                messages=[{"role": "user", "content": input_text}],
            )
            raw_response = response.content[0].text
            result = _parse_response(raw_response)

            state["factcheck_flags"] = result.get("flags", [])
            state["cleaned_data"] = result.get("cleaned_data", "")
            return state

        except anthropic.BadRequestError as e:
            # Billing / credit errors should not be retried
            if "credit" in str(e).lower() or "balance" in str(e).lower():
                raise RuntimeError(
                    f"Insufficient API credits: {e}"
                ) from e
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Fact-checking failed after {MAX_RETRIES + 1} attempts: {e}"
                ) from e
            time.sleep(2 ** attempt)

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Fact-checking failed after {MAX_RETRIES + 1} attempts: {e}"
                ) from e
            time.sleep(2 ** attempt)

    return state
