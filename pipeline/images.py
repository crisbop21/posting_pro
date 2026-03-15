"""Step 5: Image sourcing from Pexels with optional DALL-E swap."""

import re
import time
from pathlib import Path

import streamlit as st

from utils.api_clients import claude, openai_client, pexels, _ensure_pexels_auth
from utils.image_utils import search_pexels, download_image, process_overlay

MAX_RETRIES = 2


def _extract_image_markers(script: str) -> list[str]:
    """Extract [IMAGE: description] markers from the script."""
    return re.findall(r"\[IMAGE:\s*(.+?)\]", script)


def _generate_search_query(description: str) -> str:
    """Use Claude to turn a script image description into a short Pexels query."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=50,
                system=(
                    "Convert the following image description into a short, specific "
                    "Pexels search query (3-5 words). Return ONLY the query, nothing else."
                ),
                messages=[{"role": "user", "content": description}],
            )
            return response.content[0].text.strip().strip('"').strip("'")
        except Exception:
            if attempt == MAX_RETRIES:
                # Fall back to first few words of the description
                return " ".join(description.split()[:4])
            time.sleep(2 ** attempt)
    return " ".join(description.split()[:4])


def _generate_dalle_image(description: str) -> str | None:
    """Generate a fallback image with DALL-E when Pexels has no results."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=(
                    f"A clean, professional photograph for a finance video overlay: "
                    f"{description}. No text, no watermarks, landscape orientation."
                ),
                size="1792x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            path = download_image(image_url)
            if path:
                return process_overlay(path)
            return None
        except Exception:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2 ** attempt)
    return None


def run(state: dict) -> dict:
    """Execute Step 5: source overlay images for each script segment.

    Args:
        state: Current session state dict with script populated.

    Returns:
        Updated state with overlay_sequence (list of image paths).
    """
    script = state.get("script")
    if not script:
        raise RuntimeError("No script available. Complete Step 3 first.")

    markers = _extract_image_markers(script)
    if not markers:
        st.warning("No [IMAGE:] markers found in the script. Skipping image sourcing.")
        state["overlay_sequence"] = []
        return state

    overlay_sequence = []

    for description in markers:
        query = _generate_search_query(description)
        _ensure_pexels_auth()
        results = search_pexels(pexels, query)

        if results:
            # Download the first result and process it
            downloaded = download_image(results[0]["url"])
            if downloaded:
                processed = process_overlay(downloaded)
                overlay_sequence.append(processed)
                continue

        # Fallback to DALL-E if Pexels returns nothing usable
        dalle_path = _generate_dalle_image(description)
        if dalle_path:
            overlay_sequence.append(dalle_path)
        else:
            st.warning(f"Could not source an image for: {description}")

    state["overlay_sequence"] = overlay_sequence
    return state
