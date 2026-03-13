"""Step 4: Ken Burns background generation via DALL-E."""

import logging
import shutil
import time
from pathlib import Path

import requests

from utils.api_clients import claude, openai_client
from utils.styles import VISUAL_STYLES
from utils.video_utils import render_ken_burns

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _generate_optimized_prompt(state: dict, style: dict, topic: str) -> str:
    """Use Claude with the background skill to craft a topic-aware DALL-E prompt.

    Falls back to the static template in styles.py if Claude fails.
    """
    skill = Path("skills/background_skill.md").read_text()
    script = state.get("script", "")

    style_key = state.get("visual_style", "cinematic")
    style_brief = style.get("style_brief", style.get("description", ""))

    user_message = (
        f"=== TOPIC ===\n{topic}\n\n"
        f"=== VISUAL STYLE ===\n{style_key}: {style_brief}\n\n"
        f"=== SCRIPT ===\n{script}"
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                system=skill,
                messages=[{"role": "user", "content": user_message}],
            )
            prompt = response.content[0].text.strip()
            if len(prompt) > 20:
                logger.info("Claude-generated DALL-E prompt: %s", prompt[:120])
                return prompt
        except Exception:
            logger.exception("Claude prompt generation failed (attempt %d)", attempt + 1)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

    # Fallback to static template
    logger.warning("Falling back to static DALL-E prompt template")
    return style["dalle_prompt"].format(topic=topic)


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
        raise RuntimeError("Please select a visual style before generating a background.")

    # Pre-flight: check that ffmpeg is available
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg is not installed on this system. "
            "Ensure `ffmpeg` is listed in packages.txt and redeploy"
        )

    duration = state.get("estimated_duration_s", 60)
    topic = state.get("custom_topic") or "finance and AI trends"

    style = VISUAL_STYLES[style_key]
    prompt = _generate_optimized_prompt(state, style, topic)

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
                raise RuntimeError(f"Could not generate the background image: {e}") from e
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
                raise RuntimeError(f"Could not render the background video: {e}") from e
            time.sleep(2 ** attempt)

    return state
