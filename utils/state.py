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
    "script_direction": "",       # user's angle/focus instruction (pre-generation)
    "script_feedback": "",        # user's feedback for regeneration
    "script_history": [],         # list of previous script versions for context
    "beat_map": None,             # list of {"marker": str, "start_pct": float, "duration_pct": float} or None

    # Step 4 — Background generation
    "visual_style": None,         # "cinematic" | "clean" | "vintage" | "dynamic" | "hypnotic"
    "background_video_path": None,
    "background_mode": None,              # "ai_generated" | "stock_broll" | "green_screen" | "hybrid"
    "background_recommendation": None,    # dict from Claude recommendation
    "broll_search_results": [],           # list of Pexels video dicts from manual search
    "broll_selected_url": None,           # URL of user-selected B-Roll video file

    # Step 5 — Image sourcing
    "overlay_sequence": [],       # list of image paths in script order
    "overlay_sources": [],        # list of "pexels" | "dalle" | "upload" per slot
    "accent_color": None,         # hex color for accent text (auto from visual style, or user override)

    # Step 6 — Video assembly
    "title_text": "",              # title overlay text (auto-generated or user-edited)
    "title_enabled": True,         # whether to render the title overlay
    "final_video_path": None,

    # Assembly diagnostics (populated after video render)
    "assembly_diagnostics": None,

    # Assembly thread tracking
    "assembly_running": False,
    "assembly_done": False,
    "assembly_error": None,
    "assembly_started_at": None,
    "assembly_gen_id": 0,          # generation ID to discard stale threads

    # Demo output flags (True when step was filled with demo data)
    "step1_demo": False,
    "step2_demo": False,
    "step3_demo": False,
    "step4_demo": False,
    "step5_demo": False,
    "step6_demo": False,
}


def init_state():
    """Initialise session state with defaults. Safe to call on every rerun."""
    for key, default in DEFAULT_STATE.items():
        st.session_state.setdefault(key, default)
