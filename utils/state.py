"""Session state schema and initialisation for the video pipeline."""

import streamlit as st

DEFAULT_STATE = {
    # Step approval flags
    "step1_approved": False,
    "step2_approved": False,
    "step3_approved": False,
    "step4_approved": False,
    "step5_approved": False,
    "step6_approved": False,

    # Step 1 — Data gathering
    "topic_mode": None,           # "live_news" | "custom_topic" | "mode_3"
    "custom_topic": "",
    "raw_data": None,             # list of article dicts or research string

    # Step 2 — Fact-checking
    "cleaned_data": None,         # string — fact-checked and user-edited
    "factcheck_flags": [],        # list of {claim, confidence, note}

    # Step 3 — Script generation
    "script": None,               # final approved script string
    "word_count": 0,
    "estimated_duration_s": 0,

    # Step 4 — Background generation
    "visual_style": None,         # "cinematic" | "clean" | "vintage" | "dynamic"
    "background_video_path": None,

    # Step 5 — Image sourcing
    "overlay_sequence": [],       # list of image paths in script order

    # Step 6 — Video assembly
    "final_video_path": None,

    # Assembly thread tracking
    "assembly_running": False,
    "assembly_done": False,
    "assembly_error": None,
    "assembly_started_at": None,
}


def init_state():
    """Initialise session state with defaults. Safe to call on every rerun."""
    for key, default in DEFAULT_STATE.items():
        st.session_state.setdefault(key, default)
