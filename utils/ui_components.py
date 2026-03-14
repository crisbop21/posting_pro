"""Reusable Streamlit UI components for the pipeline wizard."""

import re

import streamlit as st


def step_card(step_number: int, title: str, description: str = ""):
    """Render a styled step header card."""
    st.markdown(
        f'<div class="step-card">'
        f"<h3>Step {step_number}: {title}</h3>"
        f"<p>{description}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def locked_step(step_number: int, title: str):
    """Render a locked (disabled) step placeholder."""
    st.markdown(
        f'<div class="step-locked">'
        f'<div class="step-card">'
        f"<h3>Step {step_number}: {title}</h3>"
        f"<p>Complete the previous step to unlock.</p>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _set_state(key: str, value):
    """Helper callback to set a session state key."""
    st.session_state[key] = value


def approval_bar(step_key: str, label: str = "Approve & continue"):
    """Render approve / regenerate buttons using on_click callbacks."""
    col1, col2 = st.columns([1, 1])
    with col1:
        st.button(
            f"✓ {label}",
            key=f"approve_{step_key}",
            type="primary",
            on_click=_set_state,
            args=(step_key, True),
        )
    with col2:
        st.button(
            "↻ Regenerate",
            key=f"regen_{step_key}",
            on_click=_set_state,
            args=(step_key, False),
        )


def image_card(image_path: str, caption: str = "", selected: bool = False):
    """Render a single image card with optional selection highlight."""
    cls = "image-card selected" if selected else "image-card"
    st.markdown(
        f'<div class="{cls}">'
        f'<img src="{image_path}" alt="{caption}">'
        f"<p>{caption}</p></div>",
        unsafe_allow_html=True,
    )


def demo_badge(step_number: int):
    """Show a small badge indicating this step used demo data."""
    st.markdown(
        f'<div class="demo-badge">DEMO DATA</div>',
        unsafe_allow_html=True,
    )


def word_count_display(count: int, min_words: int = 150, max_words: int = 320):
    """Show a word count indicator that turns green/red based on range."""
    if min_words <= count <= max_words:
        cls = "in-range"
    else:
        cls = "out-of-range"
    st.markdown(
        f'<span class="word-count {cls}">{count} words</span>',
        unsafe_allow_html=True,
    )


def _fmt_seconds(s: float) -> str:
    """Format seconds as M:SS."""
    m = int(s) // 60
    sec = int(s) % 60
    return f"{m}:{sec:02d}"


def beat_map_editor(estimated_duration_s: int, editable: bool = True):
    """Render an editable beat map timeline for overlay pacing.

    Reads and writes st.session_state["beat_map"]. Each beat entry gets
    slider controls for start position and duration. Shows a visual
    timeline bar beneath the controls.

    Args:
        estimated_duration_s: Estimated video duration for converting
            percentages to display seconds.
        editable: If False, show read-only display instead of sliders.
    """
    beat_map = st.session_state.get("beat_map")
    script = st.session_state.get("script", "")
    markers = re.findall(r"\[IMAGE:\s*(.+?)\]", script)

    with st.expander("Visual Pacing (beat map)", expanded=False):
        if not beat_map:
            st.caption(
                "No beat map generated. Overlays will be evenly distributed. "
                "Regenerate the script to create a beat map."
            )
            return

        if len(beat_map) != len(markers):
            st.warning(
                f"Beat map has {len(beat_map)} entries but script has "
                f"{len(markers)} image markers. Overlays will fall back "
                f"to even distribution."
            )
            return

        dur = max(estimated_duration_s, 1)
        updated = False

        # Visual timeline bar
        bar_segments = []
        for i, entry in enumerate(beat_map):
            left_pct = entry["start_pct"] * 100
            width_pct = entry["duration_pct"] * 100
            bar_segments.append(
                f'<div class="beat-segment" '
                f'style="left:{left_pct:.1f}%;width:{width_pct:.1f}%">'
                f"{i + 1}</div>"
            )
        bar_html = (
            '<div class="beat-timeline">'
            '<div class="beat-track">'
            + "".join(bar_segments)
            + "</div></div>"
        )
        st.markdown(bar_html, unsafe_allow_html=True)

        # Per-beat controls
        for i, entry in enumerate(beat_map):
            marker_label = markers[i] if i < len(markers) else f"Overlay {i + 1}"
            start_s = entry["start_pct"] * dur
            end_s = (entry["start_pct"] + entry["duration_pct"]) * dur

            st.markdown(
                f'<div class="beat-label">'
                f"<strong>{i + 1}.</strong> {marker_label}"
                f"</div>",
                unsafe_allow_html=True,
            )

            if editable:
                col1, col2 = st.columns(2)
                with col1:
                    new_start = st.slider(
                        f"Start",
                        min_value=0.0,
                        max_value=float(dur),
                        value=round(start_s, 1),
                        step=0.5,
                        format="%.1fs",
                        key=f"beat_start_{i}",
                    )
                with col2:
                    new_end = st.slider(
                        f"End",
                        min_value=0.0,
                        max_value=float(dur),
                        value=round(end_s, 1),
                        step=0.5,
                        format="%.1fs",
                        key=f"beat_end_{i}",
                    )

                new_start_pct = new_start / dur
                new_dur_pct = max(0.01, (new_end - new_start) / dur)

                if (abs(new_start_pct - entry["start_pct"]) > 0.001
                        or abs(new_dur_pct - entry["duration_pct"]) > 0.001):
                    beat_map[i]["start_pct"] = round(new_start_pct, 4)
                    beat_map[i]["duration_pct"] = round(new_dur_pct, 4)
                    updated = True
            else:
                st.caption(
                    f"{_fmt_seconds(start_s)} – {_fmt_seconds(end_s)} "
                    f"({end_s - start_s:.1f}s)"
                )

        if updated:
            st.session_state["beat_map"] = beat_map
