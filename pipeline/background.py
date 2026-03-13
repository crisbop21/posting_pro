"""Step 4: Ken Burns background generation via DALL-E."""

import logging
import shutil
import time
from pathlib import Path

import requests
import streamlit as st

from utils.api_clients import openai_client
from utils.styles import VISUAL_STYLES
from utils.video_utils import render_ken_burns

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def run(state: dict) -> dict:
    """Execute Step 4: generate a background image and render Ken Burns video.

    Args:
        state: Current session state dict with visual_style and
               estimated_duration_s populated.

    Returns:
        Updated state with background_video_path.
    """
    style_key = state.get("visual_style")
    if not style_key or style_key not in VISUAL_STYLES:
        st.error("Please select a visual style.")
        st.stop()

    # Pre-flight: check that ffmpeg is available
    if not shutil.which("ffmpeg"):
        st.error(
            "FFmpeg is not installed on this system. "
            "Please install it (e.g. `apt-get install ffmpeg`) and try again."
        )
        st.stop()

    duration = state.get("estimated_duration_s", 60)
    topic = state.get("custom_topic") or "finance and AI trends"

    style = VISUAL_STYLES[style_key]
    prompt = style["dalle_prompt"].format(topic=topic)

    # Generate the background image with DALL-E
    image_path = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1792",
                quality="hd",
                n=1,
            )
            image_url = response.data[0].url

            # Download the image locally
            img_resp = requests.get(image_url, timeout=60)
            img_resp.raise_for_status()

            Path("tmp").mkdir(exist_ok=True)
            image_path = f"tmp/background_{style_key}.png"
            with open(image_path, "wb") as f:
                f.write(img_resp.content)
            break

        except Exception as e:
            logger.exception("DALL-E image generation failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                st.error(
                    f"Could not generate the background image: {e}. "
                    "Use the Retry button to try again."
                )
                st.stop()
            time.sleep(2 ** attempt)

    # Render Ken Burns video from the still image
    Path("tmp").mkdir(exist_ok=True)
    output_path = f"tmp/background_{style_key}.mp4"

    for attempt in range(MAX_RETRIES + 1):
        try:
            render_ken_burns(
                image_path=image_path,
                duration_s=duration,
                output_path=output_path,
            )
            state["background_video_path"] = output_path
            return state

        except Exception as e:
            logger.exception("Ken Burns render failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                st.error(
                    f"Could not render the background video: {e}. "
                    "Use the Retry button to try again."
                )
                st.stop()
            time.sleep(2 ** attempt)

    return state
