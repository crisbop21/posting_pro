"""Step 7: Export — validate and serve the final video for download."""

from pathlib import Path

import streamlit as st


def run(state: dict) -> dict:
    """Execute Step 7: validate the final video exists and is ready.

    The actual download button is rendered in app.py. This module
    validates that the file is present and non-empty.

    Args:
        state: Current session state dict with final_video_path.

    Returns:
        Unchanged state (validation only).
    """
    video_path = state.get("final_video_path")

    if not video_path:
        st.error("No video has been assembled. Complete Step 6 first.")
        st.stop()

    path = Path(video_path)
    if not path.exists():
        st.error(
            "The video file is missing. It may have been cleaned up. "
            "Use the Retry button on Step 6 to reassemble."
        )
        st.stop()

    if path.stat().st_size == 0:
        st.error(
            "The video file is empty. Something went wrong during assembly. "
            "Use the Retry button on Step 6 to reassemble."
        )
        st.stop()

    return state
