"""AI Social Video Pipeline — Streamlit entry point."""

import threading
import time
from pathlib import Path

import streamlit as st

from utils.state import DEFAULT_STATE, init_state
from utils.styles import BACKGROUND_MODES, VISUAL_STYLES
from utils.demo import load_demo
from utils.ui_components import (
    _set_state,
    approval_bar,
    beat_map_editor,
    demo_badge,
    locked_step,
    step_card,
    word_count_display,
)

# ---------------------------------------------------------------------------
# Page config and CSS injection
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Video Pipeline",
    page_icon="🎬",
    layout="wide",
)

css = Path(".streamlit/custom_style.css").read_text()
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# State initialisation
# ---------------------------------------------------------------------------
init_state()

# ---------------------------------------------------------------------------
# Debug: pre-load state to jump to a specific step
# Usage:  streamlit run app.py -- --debug-step6
# ---------------------------------------------------------------------------
import sys

if "--debug-step6" in sys.argv and not st.session_state.get("_debug_loaded"):
    from tests.helpers import mock_state
    _debug = mock_state(up_to_step=5)
    for k, v in _debug.items():
        st.session_state[k] = v
    st.session_state["_debug_loaded"] = True

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("AI Social Video Pipeline")
st.caption("Finance & AI short-form vertical videos — fully orchestrated.")

def _apply_demo(step: int):
    """Load demo data for a step into session state."""
    data = load_demo(step)
    for k, v in data.items():
        if k in DEFAULT_STATE:
            st.session_state[k] = v


def _select_broll_clip(url: str):
    """Callback: select a b-roll clip by URL."""
    st.session_state["broll_selected_url"] = url


# ===================================================================
# STEP 1 — Gather Data
# ===================================================================
step_card(1, "Gather Data", "Fetch live news or research a custom topic.")

mode = st.radio(
    "Topic mode",
    options=["live_news", "custom_topic"],
    format_func=lambda m: {"live_news": "Live Finance News", "custom_topic": "Custom Topic"}[m],
    index=0 if st.session_state.get("topic_mode") != "custom_topic" else 1,
    key="radio_topic_mode",
    horizontal=True,
)
st.session_state["topic_mode"] = mode

if mode == "custom_topic":
    st.session_state["custom_topic"] = st.text_input(
        "Enter your topic",
        value=st.session_state.get("custom_topic", ""),
        key="input_custom_topic",
    )

_col_run1, _col_demo1 = st.columns([1, 1])
with _col_run1:
    if st.button("Gather Data", key="btn_gather", type="primary"):
        try:
            with st.spinner("Gathering data..."):
                from pipeline.gather import run as gather_run

                state = {k: st.session_state[k] for k in st.session_state}
                state = gather_run(state)
                for k, v in state.items():
                    if k in DEFAULT_STATE:
                        st.session_state[k] = v
            st.rerun()
        except Exception as e:
            msg = str(e).rstrip(". ")
            st.error(
                f"Could not gather data: {msg}. "
                "Click **Gather Data** to try again."
            )
with _col_demo1:
    if st.button("Use Demo Output", key="btn_demo_1"):
        _apply_demo(1)
        st.rerun()

# Show gathered data preview
if st.session_state.get("raw_data") is not None:
    raw = st.session_state["raw_data"]
    with st.expander("Preview gathered data", expanded=False):
        if isinstance(raw, dict):
            # Hybrid format: research + articles
            research = raw.get("research", "")
            articles = raw.get("articles", [])
            if research:
                st.subheader("Research Briefing")
                st.write(research)
            if articles:
                st.subheader(f"Related News ({len(articles)} articles)")
                for article in articles:
                    st.markdown(f"**{article.get('title', 'Untitled')}**")
                    st.caption(f"{article.get('source', '')} — {article.get('published_at', '')}")
                    st.write(article.get("description", ""))
                    st.divider()
        elif isinstance(raw, list):
            for article in raw:
                st.markdown(f"**{article.get('title', 'Untitled')}**")
                st.caption(f"{article.get('source', '')} — {article.get('published_at', '')}")
                st.write(article.get("description", ""))
                st.divider()
        else:
            st.write(raw)

    if st.session_state.get("step1_demo"):
        demo_badge(1)

    if not st.session_state["step1_approved"]:
        approval_bar("step1_approved", "Approve data & continue")
    else:
        st.success("Step 1 approved.")

# ===================================================================
# STEP 2 — Fact-Check
# ===================================================================
if not st.session_state["step1_approved"]:
    locked_step(2, "Fact-Check")
else:
    step_card(2, "Fact-Check", "Review flagged claims and edit the cleaned data.")

    # Run fact-check if not yet done
    if st.session_state.get("cleaned_data") is None:
        _col_run2, _col_demo2 = st.columns([1, 1])
        with _col_run2:
            if st.button("Run Fact-Check", key="btn_factcheck", type="primary"):
                try:
                    with st.spinner("Fact-checking with Claude..."):
                        from pipeline.factcheck import run as factcheck_run

                        state = {k: st.session_state[k] for k in st.session_state}
                        state = factcheck_run(state)
                        for k, v in state.items():
                            if k in DEFAULT_STATE:
                                st.session_state[k] = v
                    st.rerun()
                except Exception as e:
                    msg = str(e).rstrip(". ")
                    st.error(
                        f"Could not complete fact-checking: {msg}. "
                        "Click **Run Fact-Check** to try again."
                    )
        with _col_demo2:
            if st.button("Use Demo Output", key="btn_demo_2"):
                _apply_demo(2)
                st.rerun()
    else:
        # Display fact-check flags
        flags = st.session_state.get("factcheck_flags", [])
        if flags:
            st.subheader("Flagged claims")
            for flag in flags:
                confidence = flag.get("confidence", "medium")
                st.markdown(
                    f'<div class="factcheck-flag {confidence}">'
                    f'<strong>{confidence.upper()}</strong>: {flag.get("claim", "")}<br>'
                    f'<em>{flag.get("note", "")}</em></div>',
                    unsafe_allow_html=True,
                )

        # Editable cleaned data
        st.subheader("Cleaned data")
        edited = st.text_area(
            "Edit the fact-checked content below:",
            value=st.session_state["cleaned_data"],
            height=300,
            key="input_cleaned_data",
        )
        st.session_state["cleaned_data"] = edited

        if st.session_state.get("step2_demo"):
            demo_badge(2)

        if not st.session_state["step2_approved"]:
            approval_bar("step2_approved", "Approve & continue")
        else:
            st.success("Step 2 approved.")

# ===================================================================
# STEP 3 — Write Script
# ===================================================================
if not st.session_state["step2_approved"]:
    locked_step(3, "Write Script")
else:
    step_card(3, "Write Script", "Generate a voiceover script from the cleaned data.")

    # --- Creative direction (always visible before approval) ---
    if not st.session_state["step3_approved"]:
        st.session_state["script_direction"] = st.text_input(
            "Creative direction (optional)",
            value=st.session_state.get("script_direction", ""),
            placeholder="e.g. Focus on retail investor impact, or take a contrarian angle",
            key="input_script_direction",
        )

    if st.session_state.get("script") is None:
        _col_run3, _col_demo3 = st.columns([1, 1])
        with _col_run3:
            if st.button("Generate Script", key="btn_script", type="primary"):
                try:
                    with st.spinner("Writing script with Claude..."):
                        from pipeline.script import run as script_run

                        state = {k: st.session_state[k] for k in st.session_state}
                        state = script_run(state)
                        for k, v in state.items():
                            if k in DEFAULT_STATE:
                                st.session_state[k] = v
                    st.rerun()
                except Exception as e:
                    msg = str(e).rstrip(". ")
                    st.error(
                        f"Could not generate the script: {msg}. "
                        "Click **Generate Script** to try again."
                    )
        with _col_demo3:
            if st.button("Use Demo Output", key="btn_demo_3"):
                _apply_demo(3)
                st.rerun()
    else:
        # Word count display
        word_count_display(st.session_state["word_count"])
        st.caption(
            f"Estimated duration: {st.session_state['estimated_duration_s']}s "
            f"(~{st.session_state['estimated_duration_s'] // 60}m "
            f"{st.session_state['estimated_duration_s'] % 60}s)"
        )

        # Beat map editor — editable before approval, read-only after
        beat_map_editor(
            estimated_duration_s=st.session_state["estimated_duration_s"],
            editable=not st.session_state["step3_approved"],
        )

        # Editable script
        edited_script = st.text_area(
            "Edit the script below:",
            value=st.session_state["script"],
            height=350,
            key="input_script",
        )
        if edited_script != st.session_state["script"]:
            st.session_state["script"] = edited_script
            st.session_state["word_count"] = len(edited_script.split())
            st.session_state["estimated_duration_s"] = round(
                (st.session_state["word_count"] / 150) * 60
            )

        # --- Feedback-based regeneration ---
        if not st.session_state["step3_approved"]:
            st.divider()
            st.subheader("Regenerate with feedback")
            feedback = st.text_area(
                "What should change?",
                value="",
                placeholder="e.g. Too technical — simplify the middle section, or make the hook more dramatic",
                key="input_script_feedback",
                height=100,
            )
            if st.button("Regenerate Script", key="btn_regenerate_script"):
                if not feedback.strip():
                    st.warning("Please enter feedback before regenerating.")
                else:
                    st.session_state["script_feedback"] = feedback
                    try:
                        with st.spinner("Revising script based on feedback..."):
                            from pipeline.script import run as script_run

                            state = {k: st.session_state[k] for k in st.session_state}
                            state = script_run(state)
                            for k, v in state.items():
                                if k in DEFAULT_STATE:
                                    st.session_state[k] = v
                        st.rerun()
                    except Exception as e:
                        msg = str(e).rstrip(". ")
                        st.error(
                            f"Could not regenerate the script: {msg}. "
                            "Try again."
                        )

            # Show revision history count
            history = st.session_state.get("script_history", [])
            if history:
                st.caption(f"Script version: {len(history) + 1} (revised {len(history)} time(s))")

        if st.session_state.get("step3_demo"):
            demo_badge(3)

        if not st.session_state["step3_approved"]:
            approval_bar("step3_approved", "Approve script & continue")
        else:
            st.success("Step 3 approved.")

# ===================================================================
# STEP 4 — Generate Background
# ===================================================================
if not st.session_state["step3_approved"]:
    locked_step(4, "Generate Background")
else:
    step_card(4, "Generate Background", "Choose a visual style, get a mode recommendation, and generate your background.")

    # --- Visual style selector ---
    style_options = list(VISUAL_STYLES.keys())
    style_labels = {k: f"{v['label']} — {v['description']}" for k, v in VISUAL_STYLES.items()}

    current_idx = 0
    if st.session_state.get("visual_style") in style_options:
        current_idx = style_options.index(st.session_state["visual_style"])

    selected_style = st.radio(
        "Visual style",
        options=style_options,
        format_func=lambda s: style_labels[s],
        index=current_idx,
        key="radio_visual_style",
        horizontal=True,
    )
    st.session_state["visual_style"] = selected_style

    # --- Analyze Script for mode recommendation ---
    st.divider()
    rec = st.session_state.get("background_recommendation")

    if rec is None:
        if st.button("Analyze Script", key="btn_analyze_bg", type="secondary"):
            try:
                with st.spinner("Claude is analyzing your script for the best background mode..."):
                    from pipeline.background import _recommend_mode

                    state = {k: st.session_state[k] for k in st.session_state}
                    recommendation = _recommend_mode(state)
                    st.session_state["background_recommendation"] = recommendation
                    st.session_state["background_mode"] = recommendation["recommended_mode"]
                st.rerun()
            except Exception as e:
                msg = str(e).rstrip(". ")
                st.error(f"Could not analyze script: {msg}. Try again.")
    else:
        # Show recommendation
        st.info(
            f"**Recommended mode: {BACKGROUND_MODES.get(rec['recommended_mode'], {}).get('label', rec['recommended_mode'])}** "
            f"— {rec.get('reasoning', '')}"
        )

        # Show Pexels queries for stock modes
        if rec.get("pexels_queries"):
            st.caption(f"Search queries: {', '.join(rec['pexels_queries'])}")

    # --- Background mode selector ---
    mode_options = list(BACKGROUND_MODES.keys())
    mode_labels = {k: f"{v['label']} — {v['description']}" for k, v in BACKGROUND_MODES.items()}

    current_mode_idx = 0
    if st.session_state.get("background_mode") in mode_options:
        current_mode_idx = mode_options.index(st.session_state["background_mode"])

    selected_mode = st.radio(
        "Background mode",
        options=mode_options,
        format_func=lambda m: mode_labels[m],
        index=current_mode_idx,
        key="radio_background_mode",
        horizontal=True,
    )
    st.session_state["background_mode"] = selected_mode

    # Note if user overrides the recommendation
    if rec and selected_mode != rec.get("recommended_mode"):
        st.caption(
            f"You selected **{BACKGROUND_MODES[selected_mode]['label']}** "
            f"(Claude recommended {BACKGROUND_MODES[rec['recommended_mode']]['label']})"
        )

    # --- Search B-Roll (for stock_broll and hybrid modes) ---
    if selected_mode in ("stock_broll", "hybrid"):
        st.divider()
        st.subheader("Search B-Roll 🔗")
        st.caption("Search for specific b-roll footage by keyword. Pick a clip and it will be used as your background.")

        _col_kw, _col_btn_search = st.columns([4, 1])
        with _col_kw:
            broll_keyword = st.text_input("Search keyword", value="", key="broll_search_keyword")
        with _col_btn_search:
            st.markdown("<br>", unsafe_allow_html=True)
            search_clicked = st.button("Search B-Roll", key="btn_search_broll")

        if search_clicked and broll_keyword.strip():
            try:
                with st.spinner("Searching Pexels for b-roll..."):
                    from pipeline.background import search_pexels_videos

                    results = search_pexels_videos(broll_keyword.strip())
                    st.session_state["broll_search_results"] = results
                    st.session_state["broll_selected_url"] = None
                st.rerun()
            except Exception as e:
                msg = str(e).rstrip(". ")
                st.error(f"Search failed: {msg}. Try again.")

        # Display search results
        results = st.session_state.get("broll_search_results", [])
        if results:
            st.write(f"**{len(results)} clips found.** Select one to use as your background.")
            cols = st.columns(min(len(results), 4))
            for i, clip in enumerate(results):
                with cols[i % 4]:
                    if clip.get("image"):
                        st.image(clip["image"], width="stretch")
                    st.caption(f"{clip.get('duration', '?')}s · {clip.get('width', '?')}×{clip.get('height', '?')}")
                    st.button(
                        "Use this clip",
                        key=f"btn_broll_{i}",
                        on_click=_select_broll_clip,
                        args=(clip["video_url"],),
                    )

            if st.session_state.get("broll_selected_url"):
                st.success("B-roll clip selected. Click **Generate Background** to download and process it.")
        elif search_clicked:
            st.warning("No results found. Try a different keyword.")

        st.divider()

    # --- Generate button ---
    st.divider()
    _col_run4, _col_demo4 = st.columns([1, 1])
    with _col_run4:
        if st.button("Generate Background", key="btn_background", type="primary"):
            try:
                mode_label = BACKGROUND_MODES.get(selected_mode, {}).get("label", selected_mode)
                with st.spinner(f"Generating {mode_label} background..."):
                    from pipeline.background import run as background_run

                    state = {k: st.session_state[k] for k in st.session_state}
                    state = background_run(state)
                    for k, v in state.items():
                        if k in DEFAULT_STATE:
                            st.session_state[k] = v
                st.rerun()
            except Exception as e:
                msg = str(e).rstrip(". ")
                st.error(
                    f"Could not generate the background: {msg}. "
                    "Click **Generate Background** to try again."
                )
    with _col_demo4:
        if st.button("Use Demo Output", key="btn_demo_4"):
            _apply_demo(4)
            st.rerun()

    # Preview
    bg_path = st.session_state.get("background_video_path")
    if bg_path and Path(bg_path).exists():
        st.video(bg_path)

        if st.session_state.get("step4_demo"):
            demo_badge(4)

        if not st.session_state["step4_approved"]:
            approval_bar("step4_approved", "Approve background & continue")
        else:
            st.success("Step 4 approved.")

# ===================================================================
# STEP 5 — Source Images
# ===================================================================
if not st.session_state["step4_approved"]:
    locked_step(5, "Source Images")
else:
    step_card(5, "Source Images", "Find overlay images for each script segment.")

    if not st.session_state.get("overlay_sequence"):
        _col_run5, _col_demo5 = st.columns([1, 1])
        with _col_run5:
            if st.button("Search Web Images", key="btn_images", type="primary"):
                try:
                    with st.spinner("Searching Pexels for images..."):
                        from pipeline.images import run as images_run

                        state = {k: st.session_state[k] for k in st.session_state}
                        state = images_run(state)
                        for k, v in state.items():
                            if k in DEFAULT_STATE:
                                st.session_state[k] = v
                    st.rerun()
                except Exception as e:
                    msg = str(e).rstrip(". ")
                    st.error(
                        f"Could not source images: {msg}. "
                        "Click **Search Web Images** to try again."
                    )
        with _col_demo5:
            if st.button("Use Demo Output", key="btn_demo_5"):
                _apply_demo(5)
                st.rerun()
    else:
        overlays = st.session_state["overlay_sequence"]
        sources = st.session_state.get("overlay_sources", ["pexels"] * len(overlays))

        # Ensure sources list matches overlays length
        while len(sources) < len(overlays):
            sources.append("pexels")
        st.session_state["overlay_sources"] = sources

        import re as _re
        _markers = _re.findall(r"\[IMAGE:\s*(.+?)\]", st.session_state.get("script", ""))

        st.write(f"{len(overlays)} overlay image(s) sourced.")

        # Display image grid with per-slot swap controls
        cols = st.columns(min(len(overlays), 3)) if overlays else []
        for i, img_path in enumerate(overlays):
            with cols[i % len(cols)]:
                # Source badge
                _src = sources[i] if i < len(sources) else "pexels"
                _badge = {"pexels": "WEB", "dalle": "DALL-E", "upload": "UPLOAD", "missing": "MISSING"}.get(_src, _src.upper())
                st.caption(f"**{_badge}** — Overlay {i + 1}")

                if img_path and Path(img_path).exists():
                    try:
                        st.image(img_path, width="stretch")
                    except Exception:
                        st.warning(f"Image for slot {i + 1} is corrupt. Use swap options below to replace it.")
                else:
                    st.warning(f"No image for slot {i + 1}.")

                # --- Swap options ---
                swap_choice = st.selectbox(
                    f"Swap #{i + 1}",
                    options=["—", "Search web", "Generate DALL-E", "Upload"],
                    key=f"swap_choice_{i}",
                    label_visibility="collapsed",
                )

                if swap_choice == "Search web":
                    _marker_desc = _markers[i] if i < len(_markers) else ""
                    _custom_q = st.text_input(
                        "Search query",
                        value=_marker_desc,
                        key=f"web_query_{i}",
                        placeholder="e.g. stock market graph",
                    )
                    if st.button("Search", key=f"btn_web_search_{i}"):
                        if _custom_q.strip():
                            try:
                                with st.spinner("Searching Pexels..."):
                                    from pipeline.images import _search_pexels_for_marker
                                    new_path = _search_pexels_for_marker(_custom_q.strip())
                                    if new_path:
                                        st.session_state["overlay_sequence"][i] = new_path
                                        st.session_state["overlay_sources"][i] = "pexels"
                                        st.rerun()
                                    else:
                                        st.error("No results. Try a different query.")
                            except Exception as e:
                                st.error(f"Search failed: {e}")

                elif swap_choice == "Generate DALL-E":
                    _marker_desc = _markers[i] if i < len(_markers) else ""
                    if st.button("Generate", key=f"btn_dalle_{i}"):
                        if _marker_desc:
                            try:
                                with st.spinner(f"Generating DALL-E image..."):
                                    from pipeline.images import _generate_dalle_image
                                    new_path = _generate_dalle_image(_marker_desc)
                                    if new_path:
                                        st.session_state["overlay_sequence"][i] = new_path
                                        st.session_state["overlay_sources"][i] = "dalle"
                                        st.rerun()
                                    else:
                                        st.error("DALL-E generation failed.")
                            except Exception as e:
                                st.error(f"DALL-E failed: {e}")
                        else:
                            st.error("No image marker description available for this slot.")

                elif swap_choice == "Upload":
                    replacement = st.file_uploader(
                        f"Upload image for slot {i + 1}",
                        type=["png", "jpg", "jpeg", "webp"],
                        key=f"upload_replace_{i}",
                        label_visibility="collapsed",
                    )
                    if replacement is not None:
                        from utils.image_utils import process_overlay

                        Path("tmp").mkdir(exist_ok=True)
                        save_path = f"tmp/replace_overlay_{i}_{replacement.name}"
                        with open(save_path, "wb") as f:
                            f.write(replacement.getbuffer())
                        processed = process_overlay(save_path)
                        st.session_state["overlay_sequence"][i] = processed
                        st.session_state["overlay_sources"][i] = "upload"
                        del st.session_state[f"upload_replace_{i}"]
                        st.rerun()

        if st.session_state.get("step5_demo"):
            demo_badge(5)

        if not st.session_state["step5_approved"]:
            approval_bar("step5_approved", "Approve images & continue")
        else:
            st.success("Step 5 approved.")

# ===================================================================
# STEP 6 — Assemble Video
# ===================================================================
if not st.session_state["step5_approved"]:
    locked_step(6, "Assemble Video")
else:
    step_card(6, "Assemble Video", "Generate voiceover and composite the final video.")

    # --- Title overlay controls ---
    st.subheader("Title Overlay")

    # Auto-populate title from topic if empty
    if not st.session_state.get("title_text"):
        topic = st.session_state.get("custom_topic", "")
        if topic:
            st.session_state["title_text"] = topic.strip().title()

    title_enabled = st.checkbox(
        "Show title text on video",
        value=st.session_state.get("title_enabled", True),
        key="chk_title_enabled",
    )
    st.session_state["title_enabled"] = title_enabled

    if title_enabled:
        title_text = st.text_input(
            "Title text",
            value=st.session_state.get("title_text", ""),
            placeholder="e.g. Fed Cuts Rates Again",
            key="input_title_text",
        )
        st.session_state["title_text"] = title_text

    st.divider()

    # --- Pre-flight validation ---
    def _preflight_checks() -> list[dict]:
        """Validate all assembly inputs. Returns list of {check, ok, detail}."""
        checks = []

        # Background video
        bg = st.session_state.get("background_video_path")
        if not bg:
            checks.append({"check": "Background video path", "ok": False, "detail": "Not set — complete Step 4"})
        elif not Path(bg).exists():
            checks.append({"check": "Background video file", "ok": False, "detail": f"File missing: {bg}"})
        else:
            size_mb = Path(bg).stat().st_size / (1024 * 1024)
            checks.append({"check": "Background video", "ok": True, "detail": f"{bg} ({size_mb:.1f} MB)"})

        # Script
        script = st.session_state.get("script")
        if not script:
            checks.append({"check": "Script", "ok": False, "detail": "No script — complete Step 3"})
        else:
            wc = len(script.split())
            checks.append({"check": "Script", "ok": True, "detail": f"{wc} words"})

        # Overlays
        overlays = st.session_state.get("overlay_sequence", [])
        if not overlays:
            checks.append({"check": "Overlay images", "ok": False, "detail": "No overlays — complete Step 5"})
        else:
            missing = [p for p in overlays if not Path(p).exists()]
            if missing:
                checks.append({"check": "Overlay images", "ok": False, "detail": f"{len(missing)} file(s) missing: {missing}"})
            else:
                checks.append({"check": "Overlay images", "ok": True, "detail": f"{len(overlays)} image(s), all present"})

        # ffmpeg/ffprobe available
        import shutil
        for tool in ["ffmpeg", "ffprobe"]:
            found = shutil.which(tool)
            checks.append({"check": tool, "ok": bool(found), "detail": found or "NOT FOUND — install ffmpeg"})

        # ElevenLabs API
        try:
            from utils.api_clients import elevenlabs_client, ELEVENLABS_VOICE_ID
            checks.append({"check": "ElevenLabs client", "ok": elevenlabs_client is not None, "detail": f"Voice: {ELEVENLABS_VOICE_ID}" if elevenlabs_client else "Client not initialised"})
        except Exception as e:
            checks.append({"check": "ElevenLabs client", "ok": False, "detail": str(e)})

        return checks

    # Maximum time (seconds) before we consider assembly stuck
    ASSEMBLY_TIMEOUT_S = 900  # 15 minutes — MoviePy composites frame-by-frame

    if st.session_state.get("final_video_path") is None:
        if st.session_state["assembly_running"]:
            # Show elapsed time as progress feedback
            started = st.session_state.get("assembly_started_at")
            if started:
                elapsed = time.time() - started
                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                st.info(
                    f"Assembling video... {mins}m {secs}s elapsed. "
                    f"MoviePy composites frame-by-frame — this can take several minutes."
                )
                progress_frac = min(elapsed / ASSEMBLY_TIMEOUT_S, 0.99)
                st.progress(progress_frac)
            else:
                st.info("Assembling video...")

            # Capture debug log from thread into session state for display
            _result = st.session_state.get("_assembly_result", {})
            _live_log = _result.get("log", [])
            if _live_log:
                st.session_state["assembly_debug_log"] = list(_live_log)
                with st.expander("Assembly debug log", expanded=False):
                    st.code("\n".join(_live_log), language="text")

            # Poll for completion via the shared result dict (thread-safe)
            if _result.get("done"):
                st.session_state["assembly_running"] = False
                st.session_state["assembly_started_at"] = None
                # Persist the debug log from the thread
                if _result.get("log"):
                    st.session_state["assembly_debug_log"] = list(_result["log"])
                if _result.get("error"):
                    st.session_state["assembly_error"] = _result["error"]
                elif _result.get("state"):
                    # Copy results from the thread's snapshot back into session state,
                    # but skip assembly tracking keys to avoid overwriting the
                    # reset we just did above.
                    _assembly_tracking_keys = {
                        "assembly_running", "assembly_done", "assembly_error",
                        "assembly_started_at", "assembly_gen_id",
                    }
                    for k, v in _result["state"].items():
                        if k in DEFAULT_STATE and k not in _assembly_tracking_keys:
                            st.session_state[k] = v
                else:
                    st.session_state["assembly_error"] = (
                        "Assembly finished but produced no output."
                    )
                st.rerun()
            elif started and (time.time() - started) > ASSEMBLY_TIMEOUT_S:
                st.session_state["assembly_running"] = False
                st.session_state["assembly_error"] = (
                    "Video assembly timed out after 15 minutes. "
                    "This may indicate a problem with the inputs."
                )
                st.session_state["assembly_gen_id"] = (
                    st.session_state.get("assembly_gen_id", 0) + 1
                )
                st.rerun()
            else:
                time.sleep(2)
                st.rerun()
        else:
            # Show persisted error from a previous failed attempt
            _prev_err = st.session_state.get("assembly_error")
            if _prev_err:
                st.error("Assembly failed. Click **Assemble Video** to try again.")
                with st.expander("Error details", expanded=True):
                    st.code(_prev_err, language="text")
                _prev_log = st.session_state.get("assembly_debug_log", [])
                if _prev_log:
                    with st.expander("Debug log from last attempt", expanded=False):
                        st.code("\n".join(_prev_log), language="text")

            # Show pre-flight checks
            with st.expander("Pre-flight checks", expanded=False):
                checks = _preflight_checks()
                all_ok = all(c["ok"] for c in checks)
                for c in checks:
                    icon = "✅" if c["ok"] else "❌"
                    st.text(f"  {icon} {c['check']}: {c['detail']}")
                if all_ok:
                    st.success("All checks passed — ready to assemble.")
                else:
                    st.error("Some checks failed. Fix the issues above before assembling.")

            _col_run6, _col_demo6 = st.columns([1, 1])
            with _col_run6:
                if st.button("Assemble Video", key="btn_assemble", type="primary"):
                    # Run pre-flight and block if critical checks fail
                    checks = _preflight_checks()
                    failed = [c for c in checks if not c["ok"]]
                    if failed:
                        for c in failed:
                            st.error(f"**{c['check']}:** {c['detail']}")
                        st.stop()

                    _setup_ok = False
                    try:
                        # Import the assembly module eagerly (on the main thread)
                        # so that utils.api_clients initialisation happens here,
                        # not inside the background thread where st.warning()
                        # would crash.
                        from pipeline.assemble import run as assemble_run

                        gen_id = st.session_state.get("assembly_gen_id", 0) + 1
                        st.session_state["assembly_gen_id"] = gen_id
                        st.session_state["assembly_running"] = True
                        st.session_state["assembly_done"] = False
                        st.session_state["assembly_error"] = None
                        st.session_state["assembly_started_at"] = time.time()
                        st.session_state["assembly_debug_log"] = []

                        state_snapshot = {k: st.session_state[k] for k in st.session_state}

                        # Shared result dict — thread writes here, main thread reads
                        # debug_log is a shared list the thread appends to
                        _debug_log = []
                        _result = {"done": False, "error": None, "state": None, "log": _debug_log}

                        def _log(msg, _log_list=_debug_log):
                            import datetime as _dt
                            ts = _dt.datetime.now().strftime("%H:%M:%S")
                            _log_list.append(f"[{ts}] {msg}")

                        def _assemble_in_background(
                            _snapshot=state_snapshot,
                            _res=_result,
                            _run=assemble_run,
                            _log_fn=_log,
                        ):
                            import traceback as _tb
                            try:
                                _log_fn("Starting assembly run...")
                                _log_fn(f"Background: {_snapshot.get('background_video_path')}")
                                _log_fn(f"Overlays: {len(_snapshot.get('overlay_sequence', []))} image(s)")
                                _log_fn(f"Script length: {len((_snapshot.get('script') or '').split())} words")
                                _log_fn(f"Title: {'enabled' if _snapshot.get('title_enabled') else 'disabled'} — '{_snapshot.get('title_text', '')}'")

                                updated = _run(_snapshot)
                                _log_fn(f"Done. final_video_path={updated.get('final_video_path')}")
                                _res["state"] = updated
                            except Exception as e:
                                full_tb = _tb.format_exc()
                                _log_fn(f"ERROR: {e}")
                                _log_fn(f"TRACEBACK:\n{full_tb}")
                                _res["error"] = f"{e}\n\nTraceback:\n{full_tb}"
                            finally:
                                _res["done"] = True

                        thread = threading.Thread(target=_assemble_in_background, daemon=True)
                        st.session_state["_assembly_result"] = _result
                        thread.start()
                        _setup_ok = True
                    except Exception as e:
                        st.session_state["assembly_running"] = False
                        st.session_state["assembly_started_at"] = None
                        import traceback as _tb
                        full_tb = _tb.format_exc()
                        st.session_state["assembly_debug_log"] = [
                            f"SETUP ERROR: {e}",
                            f"TRACEBACK:\n{full_tb}",
                        ]
                        msg = str(e).rstrip(". ")
                        st.error(
                            f"Could not start video assembly: {msg}. "
                            "Click **Assemble Video** to try again."
                        )
                    if _setup_ok:
                        st.rerun()
            with _col_demo6:
                if st.button("Use Demo Output", key="btn_demo_6"):
                    _apply_demo(6)
                    st.rerun()
    else:
        # Show the assembled video
        video_path = st.session_state["final_video_path"]
        if Path(video_path).exists():
            st.video(video_path)

            # --- Frame preview: extract a still at ~1s for quick verification ---
            preview_path = "tmp/_preview_frame.png"
            try:
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "1", "-i", video_path,
                     "-frames:v", "1", "-q:v", "2", preview_path],
                    capture_output=True, timeout=10,
                )
                if Path(preview_path).exists():
                    with st.expander("Frame Preview (1s mark)", expanded=True):
                        st.image(preview_path, caption="Composite at t=1s — verify title and overlays are visible", width="stretch")
            except Exception:
                pass  # non-critical — skip silently
        else:
            st.warning("Video file not found. You may need to reassemble.")

        # Assembly diagnostics panel
        diag = st.session_state.get("assembly_diagnostics")
        if diag:
            # Show warnings prominently outside the expander
            diag_warnings = diag.get("warnings", [])
            if diag_warnings:
                for w in diag_warnings:
                    st.warning(w)

            with st.expander("Assembly Diagnostics", expanded=bool(diag_warnings)):
                engine = diag.get("engine", "ffmpeg")
                st.markdown(
                    f"**Status:** {'Success' if diag.get('success') else 'Failed'} "
                    f"| **Engine:** {engine}"
                )

                # Input info
                bg = diag.get("background", {})
                aud = diag.get("audio", {})
                st.markdown("**Inputs:**")
                st.text(
                    f"  Background: {bg.get('file', '?')}  "
                    f"{bg.get('duration_s', '?')}s"
                )
                st.text(
                    f"  Audio:      {aud.get('file', '?')}  "
                    f"{aud.get('duration_s', '?')}s"
                )
                st.text(f"  Darken:     {diag.get('darken', '?')}")
                st.text(f"  Title:      {'Yes' if diag.get('title_overlay') else 'No'}")

                # Overlay timing table
                timings = diag.get("overlay_timings", [])
                st.markdown(
                    f"**Overlays: {diag.get('overlay_count', 0)}**"
                )
                if timings:
                    timing_source = "beat map" if st.session_state.get("beat_map") else "even distribution"
                    st.caption(f"Source: {timing_source}")
                    for t in timings:
                        status = t.get("status", "")
                        st.text(
                            f"  #{t['index']}  {t['image']:<30s}  "
                            f"{t['start_s']:>6.2f}s – {t['end_s']:>6.2f}s  "
                            f"({t['duration_s']:.1f}s)  {status}"
                        )

        if st.session_state.get("step6_demo"):
            demo_badge(6)

        if not st.session_state["step6_approved"]:
            # Custom approval bar for Step 6: "Reassemble" resets assembly
            # output so the user can return to the Assemble Video button.
            col_approve, col_reassemble = st.columns([1, 1])
            with col_approve:
                st.button(
                    "✓ Approve video & continue",
                    key="approve_step6_approved",
                    type="primary",
                    on_click=_set_state,
                    args=("step6_approved", True),
                )
            with col_reassemble:
                def _reassemble_step6():
                    st.session_state["step6_approved"] = False
                    st.session_state["final_video_path"] = None
                    st.session_state["assembly_diagnostics"] = None
                    st.session_state["assembly_running"] = False
                    st.session_state["assembly_done"] = False
                    st.session_state["assembly_error"] = None
                    st.session_state["assembly_started_at"] = None

                st.button(
                    "↻ Reassemble",
                    key="regen_step6_approved",
                    on_click=_reassemble_step6,
                )
        else:
            st.success("Step 6 approved.")

# ===================================================================
# STEP 7 — Download
# ===================================================================
if not st.session_state["step6_approved"]:
    locked_step(7, "Download")
else:
    step_card(7, "Download", "Your video is ready.")

    try:
        from pipeline.export import run as export_run

        state = {k: st.session_state[k] for k in st.session_state}
        export_run(state)

        video_path = st.session_state["final_video_path"]
        video_file = Path(video_path)

        st.success(f"Video saved to: `{video_path}`")

        with open(video_file, "rb") as f:
            st.download_button(
                label="Download MP4",
                data=f,
                file_name=video_file.name,
                mime="video/mp4",
                type="primary",
            )
    except Exception as e:
        msg = str(e).rstrip(". ")
        st.error(
            f"Could not prepare the video for download: {msg}. "
            "You may need to reassemble in Step 6."
        )
