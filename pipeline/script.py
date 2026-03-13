"""Step 3: Script generation via Claude."""

import time
from pathlib import Path

from utils.api_clients import claude

MAX_RETRIES = 2
WORDS_PER_MINUTE = 150


def run(state: dict) -> dict:
    """Execute Step 3: generate a voiceover script from cleaned data.

    Args:
        state: Current session state dict with cleaned_data populated.

    Returns:
        Updated state with script, word_count, and estimated_duration_s.
    """
    cleaned_data = state.get("cleaned_data")
    if not cleaned_data:
        raise RuntimeError("No fact-checked data available. Complete Step 2 first.")

    skill = Path("skills/script_skill.md").read_text()

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=skill,
                messages=[{"role": "user", "content": cleaned_data}],
            )
            script = response.content[0].text.strip()
            word_count = len(script.split())
            duration_s = round((word_count / WORDS_PER_MINUTE) * 60)

            state["script"] = script
            state["word_count"] = word_count
            state["estimated_duration_s"] = duration_s
            return state

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not generate the script: {e}") from e
            time.sleep(2 ** attempt)

    return state
