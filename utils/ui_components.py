"""Reusable Streamlit UI components for the pipeline wizard."""

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


def approval_bar(step_key: str, label: str = "Approve & continue"):
    """Render approve / regenerate buttons. Returns True if approved this click."""
    col1, col2 = st.columns([1, 1])
    approved = False
    with col1:
        if st.button(f"✓ {label}", key=f"approve_{step_key}", type="primary"):
            st.session_state[step_key] = True
            approved = True
    with col2:
        if st.button("↻ Regenerate", key=f"regen_{step_key}"):
            st.session_state[step_key] = False
            approved = False
    return approved


def image_card(image_path: str, caption: str = "", selected: bool = False):
    """Render a single image card with optional selection highlight."""
    cls = "image-card selected" if selected else "image-card"
    st.markdown(
        f'<div class="{cls}">'
        f'<img src="{image_path}" alt="{caption}">'
        f"<p>{caption}</p></div>",
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
