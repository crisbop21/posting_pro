"""Test helpers — mock state builder and common utilities."""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    """Load a fixture file as a string."""
    return (FIXTURES_DIR / name).read_text()


def _load_json_fixture(name: str):
    """Load a fixture file as parsed JSON."""
    return json.loads(_load_fixture(name))


# Pre-built realistic data for each step
_STEP_DATA = {
    1: {
        "topic_mode": "live_news",
        "custom_topic": "",
        "raw_data": _load_json_fixture("marketaux_response.json")["data"],
    },
    2: {
        "cleaned_data": _load_json_fixture("factcheck_response.json")["cleaned_data"],
        "factcheck_flags": _load_json_fixture("factcheck_response.json")["flags"],
    },
    3: {
        "script": _load_fixture("script_response.txt"),
        "word_count": len(_load_fixture("script_response.txt").split()),
        "estimated_duration_s": round(
            (len(_load_fixture("script_response.txt").split()) / 150) * 60
        ),
    },
    4: {
        "visual_style": "cinematic",
        "background_video_path": "tmp/background_cinematic.mp4",
    },
    5: {
        "overlay_sequence": [
            "tmp/overlay_0_processed.png",
            "tmp/overlay_1_processed.png",
            "tmp/overlay_2_processed.png",
            "tmp/overlay_3_processed.png",
        ],
    },
    6: {
        "final_video_path": "outputs/fed-nvidia-bitcoin-20260313.mp4",
    },
}


def mock_state(up_to_step: int = 0) -> dict:
    """Return a state dict with steps 1..up_to_step pre-approved.

    Populates realistic fixture data for all completed steps.

    Args:
        up_to_step: Number of steps to pre-approve (0-6).

    Returns:
        A dict matching the schema in utils/state.py.
    """
    state = {
        "step1_approved": False,
        "step2_approved": False,
        "step3_approved": False,
        "step4_approved": False,
        "step5_approved": False,
        "step6_approved": False,
        "topic_mode": None,
        "custom_topic": "",
        "raw_data": None,
        "cleaned_data": None,
        "factcheck_flags": [],
        "script": None,
        "word_count": 0,
        "estimated_duration_s": 0,
        "visual_style": None,
        "background_video_path": None,
        "overlay_sequence": [],
        "final_video_path": None,
        "assembly_running": False,
        "assembly_done": False,
        "assembly_error": None,
        "assembly_started_at": None,
    }

    for step in range(1, up_to_step + 1):
        if step <= 6:
            state[f"step{step}_approved"] = True
        if step in _STEP_DATA:
            state.update(_STEP_DATA[step])

    return state
