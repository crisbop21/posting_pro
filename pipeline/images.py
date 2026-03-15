"""Step 5: Image sourcing — Pexels web images by default."""

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


def _search_pexels_for_marker(description: str) -> str | None:
    """Search Pexels for a single image marker and return a processed path."""
    query = _generate_search_query(description)
    _ensure_pexels_auth()
    results = search_pexels(pexels, query)

    if results:
        downloaded = download_image(results[0]["url"])
        if downloaded:
            return process_overlay(downloaded)
    return None


def _generate_dalle_image(description: str) -> str | None:
    """Generate an image with DALL-E for a given description."""
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

    Uses Pexels web search as the default source. Each slot can later
    be individually swapped with DALL-E or an uploaded image via the UI.

    Args:
        state: Current session state dict with script populated.

    Returns:
        Updated state with overlay_sequence and overlay_sources.
    """
    script = state.get("script")
    if not script:
        raise RuntimeError("No script available. Complete Step 3 first.")

    markers = _extract_image_markers(script)
    if not markers:
        st.warning("No [IMAGE:] markers found in the script. Skipping image sourcing.")
        state["overlay_sequence"] = []
        state["overlay_sources"] = []
        return state

    overlay_sequence = []
    overlay_sources = []

    for description in markers:
        path = _search_pexels_for_marker(description)
        if path:
            overlay_sequence.append(path)
            overlay_sources.append("pexels")
        else:
            # Placeholder — slot exists but no image found
            overlay_sequence.append("")
            overlay_sources.append("missing")
            st.warning(f"No web image found for: {description}")

    state["overlay_sequence"] = overlay_sequence
    state["overlay_sources"] = overlay_sources
    return state
