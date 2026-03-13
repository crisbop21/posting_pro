"""AI Social Video Pipeline — Streamlit entry point."""

import threading
import time
from pathlib import Path

import streamlit as st

from utils.state import DEFAULT_STATE, init_state
from utils.styles import VISUAL_STYLES
from utils.ui_components import (
    approval_bar,
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
# Header
# ---------------------------------------------------------------------------
st.title("AI Social Video Pipeline")
st.caption("Finance & AI short-form vertical videos — fully orchestrated.")

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

if st.button("Gather Data", key="btn_gather", type="primary"):
    with st.spinner("Gathering data..."):
        from pipeline.gather import run as gather_run

        state = {k: st.session_state[k] for k in st.session_state}
        state = gather_run(state)
        for k, v in state.items():
            if k in DEFAULT_STATE:
                st.session_state[k] = v
    st.rerun()

# Show gathered data preview
if st.session_state.get("raw_data") is not None:
    raw = st.session_state["raw_data"]
    with st.expander("Preview gathered data", expanded=False):
        if isinstance(raw, list):
            for article in raw:
                st.markdown(f"**{article.get('title', 'Untitled')}**")
                st.caption(f"{article.get('source', '')} — {article.get('published_at', '')}")
                st.write(article.get("description", ""))
                st.divider()
        else:
            st.write(raw)

    if not st.session_state["step1_approved"]:
        if approval_bar("step1_approved", "Approve data & continue"):
            st.rerun()
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
                st.error(
                    f"Could not complete fact-checking: {e}. "
                    "Click **Run Fact-Check** to try again."
                )
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

        if not st.session_state["step2_approved"]:
            if approval_bar("step2_approved", "Approve & continue"):
                st.rerun()
        else:
            st.success("Step 2 approved.")

# ===================================================================
# STEP 3 — Write Script
# ===================================================================
if not st.session_state["step2_approved"]:
    locked_step(3, "Write Script")
else:
    step_card(3, "Write Script", "Generate a voiceover script from the cleaned data.")

    if st.session_state.get("script") is None:
        if st.button("Generate Script", key="btn_script", type="primary"):
            with st.spinner("Writing script with Claude..."):
                from pipeline.script import run as script_run

                state = {k: st.session_state[k] for k in st.session_state}
                state = script_run(state)
                for k, v in state.items():
                    if k in DEFAULT_STATE:
                        st.session_state[k] = v
            st.rerun()
    else:
        # Word count display
        word_count_display(st.session_state["word_count"])
        st.caption(
            f"Estimated duration: {st.session_state['estimated_duration_s']}s "
            f"(~{st.session_state['estimated_duration_s'] // 60}m "
            f"{st.session_state['estimated_duration_s'] % 60}s)"
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

        if not st.session_state["step3_approved"]:
            if approval_bar("step3_approved", "Approve script & continue"):
                st.rerun()
        else:
            st.success("Step 3 approved.")

# ===================================================================
# STEP 4 — Generate Background
# ===================================================================
if not st.session_state["step3_approved"]:
    locked_step(4, "Generate Background")
else:
    step_card(4, "Generate Background", "Choose a visual style and generate a Ken Burns background.")

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

    if st.button("Generate Background", key="btn_background", type="primary"):
        with st.spinner("Generating background image and rendering Ken Burns video..."):
            from pipeline.background import run as background_run

            state = {k: st.session_state[k] for k in st.session_state}
            state = background_run(state)
            for k, v in state.items():
                if k in DEFAULT_STATE:
                    st.session_state[k] = v
        st.rerun()

    # Preview
    bg_path = st.session_state.get("background_video_path")
    if bg_path and Path(bg_path).exists():
        st.video(bg_path)

        if not st.session_state["step4_approved"]:
            if approval_bar("step4_approved", "Approve background & continue"):
                st.rerun()
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
        if st.button("Source Images", key="btn_images", type="primary"):
            with st.spinner("Searching for images..."):
                from pipeline.images import run as images_run

                state = {k: st.session_state[k] for k in st.session_state}
                state = images_run(state)
                for k, v in state.items():
                    if k in DEFAULT_STATE:
                        st.session_state[k] = v
            st.rerun()
    else:
        overlays = st.session_state["overlay_sequence"]
        st.write(f"{len(overlays)} overlay image(s) sourced.")

        # Display image grid
        cols = st.columns(min(len(overlays), 3)) if overlays else []
        for i, img_path in enumerate(overlays):
            with cols[i % len(cols)]:
                if Path(img_path).exists():
                    st.image(img_path, caption=f"Overlay {i + 1}", use_container_width=True)

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

        if not st.session_state["step5_approved"]:
            if approval_bar("step5_approved", "Approve images & continue"):
                st.rerun()
        else:
            st.success("Step 5 approved.")

# ===================================================================
# STEP 6 — Assemble Video
# ===================================================================
if not st.session_state["step5_approved"]:
    locked_step(6, "Assemble Video")
else:
    step_card(6, "Assemble Video", "Generate voiceover and composite the final video.")

    # Track assembly progress in session state
    st.session_state.setdefault("assembly_running", False)
    st.session_state.setdefault("assembly_error", None)

    if st.session_state.get("final_video_path") is None:
        if st.session_state["assembly_running"]:
            st.info("Assembling video... this may take a minute.")
            progress = st.progress(0)

            # Poll for completion
            if st.session_state.get("assembly_done"):
                st.session_state["assembly_running"] = False
                if st.session_state.get("assembly_error"):
                    st.error(st.session_state["assembly_error"])
                    st.session_state["assembly_error"] = None
                else:
                    st.rerun()
            else:
                time.sleep(2)
                st.rerun()
        else:
            if st.button("Assemble Video", key="btn_assemble", type="primary"):
                st.session_state["assembly_running"] = True
                st.session_state["assembly_done"] = False
                st.session_state["assembly_error"] = None

                def _assemble_in_background():
                    try:
                        from pipeline.assemble import run as assemble_run

                        state = {k: st.session_state[k] for k in st.session_state}
                        state = assemble_run(state)
                        for k, v in state.items():
                            if k in DEFAULT_STATE:
                                st.session_state[k] = v
                    except Exception as e:
                        st.session_state["assembly_error"] = str(e)
                    finally:
                        st.session_state["assembly_done"] = True

                thread = threading.Thread(target=_assemble_in_background, daemon=True)
                thread.start()
                st.rerun()
    else:
        # Show the assembled video
        video_path = st.session_state["final_video_path"]
        if Path(video_path).exists():
            st.video(video_path)
        else:
            st.warning("Video file not found. You may need to reassemble.")

        if not st.session_state["step6_approved"]:
            if approval_bar("step6_approved", "Approve video & continue"):
                st.rerun()
        else:
            st.success("Step 6 approved.")

# ===================================================================
# STEP 7 — Download
# ===================================================================
if not st.session_state["step6_approved"]:
    locked_step(7, "Download")
else:
    step_card(7, "Download", "Your video is ready.")

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
