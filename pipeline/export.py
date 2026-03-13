"""Step 7: Export — validate and serve the final video for download."""

from pathlib import Path


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
        raise RuntimeError("No video has been assembled. Complete Step 6 first.")

    path = Path(video_path)
    if not path.exists():
        raise RuntimeError(
            "The video file is missing. It may have been cleaned up. "
            "Reassemble in Step 6."
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            "The video file is empty. Something went wrong during assembly. "
            "Reassemble in Step 6."
        )

    return state
