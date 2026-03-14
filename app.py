"""AI Social Video Pipeline — Streamlit entry point."""

import threading
import time
from pathlib import Path

import streamlit as st

from utils.state import DEFAULT_STATE, init_state
from utils.styles import BACKGROUND_MODES, VISUAL_STYLES
from utils.demo import load_demo
from utils.ui_components import (
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
                        st.image(clip["image"], use_container_width=True)
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
            if st.button("Source Images", key="btn_images", type="primary"):
                try:
                    with st.spinner("Searching for images..."):
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
                        "Click **Source Images** to try again."
                    )
        with _col_demo5:
            if st.button("Use Demo Output", key="btn_demo_5"):
                _apply_demo(5)
                st.rerun()
    else:
        overlays = st.session_state["overlay_sequence"]
        st.write(f"{len(overlays)} overlay image(s) sourced.")

        # Display image grid
        cols = st.columns(min(len(overlays), 3)) if overlays else []
        for i, img_path in enumerate(overlays):
            with cols[i % len(cols)]:
                if Path(img_path).exists():
                    st.image(img_path, caption=f"Overlay {i + 1}", width="stretch")

                    # Per-slot DALL-E swap button
                    if st.button(f"Swap #{i + 1} with DALL-E", key=f"swap_dalle_{i}"):
                        import re

                        from pipeline.images import _generate_dalle_image, _extract_image_markers

                        markers = _extract_image_markers(st.session_state.get("script", ""))
                        if i < len(markers):
                            with st.spinner(f"Generating replacement for overlay {i + 1}..."):
                                new_path = _generate_dalle_image(markers[i])
                                if new_path:
                                    st.session_state["overlay_sequence"][i] = new_path
                                    st.rerun()
                                else:
                                    st.error("Could not generate a replacement image.")

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

    # Maximum time (seconds) before we consider assembly stuck
    ASSEMBLY_TIMEOUT_S = 900  # 15 minutes — MoviePy composites frame-by-frame

    if st.session_state.get("final_video_path") is None:
        if st.session_state["assembly_running"]:
            st.info("Assembling video... this may take a minute.")

            # Show elapsed time as progress feedback
            started = st.session_state.get("assembly_started_at")
            if started:
                elapsed = time.time() - started
                progress_frac = min(elapsed / ASSEMBLY_TIMEOUT_S, 0.99)
                st.progress(progress_frac)

            # Poll for completion via the shared result dict (thread-safe)
            _result = st.session_state.get("_assembly_result", {})
            if _result.get("done"):
                st.session_state["assembly_running"] = False
                if _result.get("error"):
                    err_msg = _result["error"].rstrip(". ")
                    st.error(
                        f"{err_msg}. "
                        "Click **Assemble Video** to try again."
                    )
                elif _result.get("state"):
                    # Copy results from the thread's snapshot back into session state
                    for k, v in _result["state"].items():
                        if k in DEFAULT_STATE:
                            st.session_state[k] = v
                    st.rerun()
                else:
                    st.error(
                        "Assembly finished but produced no output. "
                        "Click **Assemble Video** to try again."
                    )
            elif started and (time.time() - started) > ASSEMBLY_TIMEOUT_S:
                st.session_state["assembly_running"] = False
                st.session_state["assembly_gen_id"] = (
                    st.session_state.get("assembly_gen_id", 0) + 1
                )
                st.error(
                    "Video assembly timed out after 15 minutes. "
                    "This may indicate a problem with the inputs. "
                    "Click **Assemble Video** to try again."
                )
            else:
                time.sleep(2)
                st.rerun()
        else:
            _col_run6, _col_demo6 = st.columns([1, 1])
            with _col_run6:
                if st.button("Assemble Video", key="btn_assemble", type="primary"):
                    gen_id = st.session_state.get("assembly_gen_id", 0) + 1
                    st.session_state["assembly_gen_id"] = gen_id
                    st.session_state["assembly_running"] = True
                    st.session_state["assembly_done"] = False
                    st.session_state["assembly_error"] = None
                    st.session_state["assembly_started_at"] = time.time()

                    # --- Option A: snapshot state on the MAIN thread ---
                    state_snapshot = {k: st.session_state[k] for k in st.session_state}

                    # Diagnostic: confirm snapshot has required keys
                    print(f"[ASSEMBLE] Snapshot keys: {len(state_snapshot)}")
                    print(f"[ASSEMBLE] background_video_path: {state_snapshot.get('background_video_path')}")
                    print(f"[ASSEMBLE] script length: {len(state_snapshot.get('script') or '')}")
                    print(f"[ASSEMBLE] overlay_sequence count: {len(state_snapshot.get('overlay_sequence', []))}")

                    # Shared result dict — thread writes here, main thread reads
                    _result = {"done": False, "error": None, "state": None}

                    def _assemble_in_background(_snapshot=state_snapshot, _res=_result):
                        try:
                            from pipeline.assemble import run as assemble_run

                            print("[ASSEMBLE-THREAD] Starting assembly run...")
                            updated = assemble_run(_snapshot)
                            print(f"[ASSEMBLE-THREAD] Done. final_video_path={updated.get('final_video_path')}")
                            _res["state"] = updated
                        except Exception as e:
                            print(f"[ASSEMBLE-THREAD] ERROR: {e}")
                            _res["error"] = str(e)
                        finally:
                            _res["done"] = True

                    thread = threading.Thread(target=_assemble_in_background, daemon=True)
                    # Stash result dict in session state so the polling loop can read it
                    st.session_state["_assembly_result"] = _result
                    thread.start()
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
            approval_bar("step6_approved", "Approve video & continue")
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
