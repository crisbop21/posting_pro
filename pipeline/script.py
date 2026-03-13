"""Step 3: Script generation via Claude."""

import re
import time
from pathlib import Path

from utils.api_clients import claude

MAX_RETRIES = 2
WORDS_PER_MINUTE = 150


def _build_user_message(state: dict) -> str:
    """Build the user message from cleaned data, direction, and feedback."""
    cleaned_data = state.get("cleaned_data", "")
    direction = state.get("script_direction", "").strip()
    feedback = state.get("script_feedback", "").strip()
    history = state.get("script_history", [])

    parts = [cleaned_data]

    if direction:
        parts.append(
            f"\n\n=== CREATIVE DIRECTION ===\n"
            f"The user wants the script to focus on: {direction}"
        )

    if history and feedback:
        # Include the most recent previous script so Claude can refine
        previous_script = history[-1]
        parts.append(
            f"\n\n=== PREVIOUS SCRIPT ===\n{previous_script}"
            f"\n\n=== USER FEEDBACK ===\n{feedback}\n"
            f"Revise the script above based on this feedback. "
            f"Keep what works, fix what the user asked to change."
        )

    return "\n".join(parts)


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
    user_message = _build_user_message(state)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                system=skill,
                messages=[{"role": "user", "content": user_message}],
            )
            script = response.content[0].text.strip()

            # Ensure at least one [IMAGE: ...] marker exists — the
            # overlay pipeline depends on these to source visuals.
            if not re.search(r"\[IMAGE:\s*.+?\]", script):
                repair = claude.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=2000,
                    system=skill,
                    messages=[
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": script},
                        {"role": "user", "content": (
                            "This script is missing [IMAGE: description] markers. "
                            "Rewrite it with 3–6 image markers placed throughout "
                            "the script as required by the rules. Return ONLY the "
                            "revised script."
                        )},
                    ],
                )
                script = repair.content[0].text.strip()

            word_count = len(script.split())
            duration_s = round((word_count / WORDS_PER_MINUTE) * 60)

            # Save current script to history before replacing
            if state.get("script"):
                history = list(state.get("script_history", []))
                history.append(state["script"])
                state["script_history"] = history

            state["script"] = script
            state["word_count"] = word_count
            state["estimated_duration_s"] = duration_s
            # Clear feedback after successful regeneration
            state["script_feedback"] = ""
            return state

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not generate the script: {e}") from e
            time.sleep(2 ** attempt)

    return state
