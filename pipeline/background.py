"""Step 4: Background generation with multiple mode support.

Supports four background modes:
- ai_generated: DALL-E image + Ken Burns animation
- stock_broll: Pexels video footage, cropped to vertical, color graded
- green_screen: Gradient background for overlay-focused content
- hybrid: Stock B-roll base with AI-generated accent overlay
"""

import json
import logging
import shutil
import time
from pathlib import Path

import requests

from utils.api_clients import claude, openai_client, pexels
from utils.styles import VISUAL_STYLES
from utils.video_utils import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    apply_color_grade,
    crop_to_vertical,
    render_green_screen,
    render_ken_burns,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"


def search_broll(query: str, per_page: int = 15) -> list:
    """Search Pexels for b-roll videos matching a keyword.

    Returns a list of dicts with id, image (thumbnail), url, duration, width, height.
    """
    results = []
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = pexels.get(PEXELS_VIDEO_URL, params={
                "query": query,
                "per_page": per_page,
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for video in data.get("videos", []):
                # Find the best video file (>= 480p)
                best_file = None
                for vf in video.get("video_files", []):
                    if vf.get("height", 0) >= 480 and vf.get("link"):
                        best_file = vf
                        break
                if best_file:
                    results.append({
                        "id": video.get("id"),
                        "image": video.get("image", ""),
                        "url": best_file["link"],
                        "duration": video.get("duration", 0),
                        "width": best_file.get("width", 0),
                        "height": best_file.get("height", 0),
                    })
            return results

        except Exception as e:
            logger.warning("Pexels video search failed (attempt %d): %s", attempt + 1, e)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not search Pexels for b-roll: {e}") from e
            time.sleep(2 ** attempt)

    return results


def fetch_broll_by_url(video_url: str, state: dict) -> str:
    """Download a specific Pexels video by URL and crop to vertical. Returns video path."""
    Path("tmp").mkdir(exist_ok=True)
    raw_path = "tmp/stock_broll_raw.mp4"

    for attempt in range(MAX_RETRIES + 1):
        try:
            dl_resp = requests.get(video_url, timeout=120, stream=True)
            dl_resp.raise_for_status()
            with open(raw_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            break
        except Exception as e:
            logger.exception("B-roll download failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not download b-roll video: {e}") from e
            time.sleep(2 ** attempt)

    cropped_path = "tmp/stock_broll_cropped.mp4"
    crop_to_vertical(raw_path, cropped_path)
    return cropped_path


def _recommend_mode(state: dict) -> dict:
    """Ask Claude to recommend the best background mode for this script.

    Returns:
        Dict with recommended_mode, pexels_queries, ken_burns_pattern, reasoning.
    """
    script = state.get("script", "")
    style_key = state.get("visual_style", "cinematic")
    topic = state.get("custom_topic") or "finance and AI trends"

    skill = Path("skills/background_skill.md").read_text()

    user_message = (
        f"Visual style: {style_key}\n"
        f"Topic: {topic}\n\n"
        f"Script:\n{script}"
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                system=skill,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0]
            recommendation = json.loads(raw)

            # Validate required keys
            valid_modes = {"ai_generated", "stock_broll", "green_screen", "hybrid"}
            if recommendation.get("recommended_mode") not in valid_modes:
                recommendation["recommended_mode"] = "ai_generated"
            if not isinstance(recommendation.get("pexels_queries"), list):
                recommendation["pexels_queries"] = ["finance technology"]
            if not isinstance(recommendation.get("ken_burns_pattern"), list):
                recommendation["ken_burns_pattern"] = ["zoom_in", "pan_left", "zoom_out"]

            return recommendation

        except Exception as e:
            logger.exception("Background recommendation failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                # Fallback to safe defaults
                logger.warning("Using fallback recommendation after %d failures", MAX_RETRIES + 1)
                return {
                    "recommended_mode": "ai_generated",
                    "pexels_queries": ["finance technology"],
                    "ken_burns_pattern": ["zoom_in", "pan_left", "zoom_out"],
                    "reasoning": "Fallback: could not get Claude recommendation.",
                }
            time.sleep(2 ** attempt)

    # Unreachable, but satisfies type checkers
    return {"recommended_mode": "ai_generated", "pexels_queries": [], "ken_burns_pattern": ["zoom_in"], "reasoning": ""}


def _get_ken_burns_direction(state: dict) -> str:
    """Pick a Ken Burns direction from the recommendation pattern."""
    rec = state.get("background_recommendation") or {}
    pattern = rec.get("ken_burns_pattern", ["zoom_in"])
    valid = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
    # Cycle through the pattern; use first valid entry
    for d in pattern:
        if d in valid:
            return d
    return "zoom_in"


def _generate_ai_background(state: dict) -> str:
    """Generate background via DALL-E image + Ken Burns. Returns video path."""
    style_key = state["visual_style"]
    style = VISUAL_STYLES[style_key]
    prompt = _generate_optimized_prompt(state, style, topic)

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

    output_path = f"tmp/background_{style_key}_raw.mp4"
    for attempt in range(MAX_RETRIES + 1):
        try:
            render_ken_burns(
                image_path=image_path,
                duration_s=duration,
                output_path=output_path,
                direction=direction,
            )
            return output_path
        except Exception as e:
            logger.exception("Ken Burns render failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not render the background video: {e}") from e
            time.sleep(2 ** attempt)

    return output_path


def _fetch_stock_broll(state: dict) -> str:
    """Fetch stock video from Pexels, crop to vertical. Returns video path."""
    rec = state.get("background_recommendation") or {}
    queries = rec.get("pexels_queries", ["finance technology"])
    duration = state.get("estimated_duration_s", 60)

    # Add broad fallback queries in case Claude's specific ones return no results
    fallback_queries = ["business technology", "city skyline timelapse", "abstract motion background"]
    all_queries = list(queries) + [q for q in fallback_queries if q not in queries]

    video_url = None
    for query in all_queries:
        try:
            # Note: Pexels Videos API does not support 'orientation' param
            # (only the Photos API does). Use per_page and pick the best file.
            resp = pexels.get(PEXELS_VIDEO_URL, params={
                "query": query,
                "per_page": 15,
            }, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            videos = data.get("videos", [])
            logger.info("Pexels returned %d videos for query '%s'", len(videos), query)

            if videos:
                # Pick the first video with a usable file (>= 480p)
                for video in videos:
                    for vf in video.get("video_files", []):
                        height = vf.get("height", 0)
                        width = vf.get("width", 0)
                        if height >= 480 and vf.get("link"):
                            video_url = vf["link"]
                            logger.info(
                                "Selected video file: %dx%d from video id %s",
                                width, height, video.get("id"),
                            )
                            break
                    if video_url:
                        break

            if video_url:
                logger.info("Pexels video found for query '%s'", query)
                break
            else:
                logger.warning("No suitable video files for query '%s'", query)
        except Exception as e:
            logger.warning("Pexels search failed for '%s': %s", query, e)
            continue

    if not video_url:
        raise RuntimeError(
            "Could not find suitable stock footage on Pexels. "
            "Try a different background mode or topic."
        )

    # Download the video
    Path("tmp").mkdir(exist_ok=True)
    raw_path = "tmp/stock_broll_raw.mp4"
    for attempt in range(MAX_RETRIES + 1):
        try:
            dl_resp = requests.get(video_url, timeout=120, stream=True)
            dl_resp.raise_for_status()
            with open(raw_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            break
        except Exception as e:
            logger.exception("Stock video download failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not download stock video: {e}") from e
            time.sleep(2 ** attempt)

    # Crop to 9:16 vertical
    cropped_path = "tmp/stock_broll_cropped.mp4"
    crop_to_vertical(raw_path, cropped_path)

    return cropped_path


def _render_green_screen_bg(state: dict) -> str:
    """Generate a gradient background video. Returns video path."""
    style_key = state["visual_style"]
    style = VISUAL_STYLES[style_key]
    duration = state.get("estimated_duration_s", 60)
    colors = style.get("green_screen_colors", ("#0a0a1a", "#1a1a3a"))

    Path("tmp").mkdir(exist_ok=True)
    output_path = f"tmp/green_screen_{style_key}.mp4"

    render_green_screen(
        output_path=output_path,
        duration_s=duration,
        color_top=colors[0],
        color_bottom=colors[1],
    )

    return output_path


def _build_hybrid(state: dict) -> str:
    """Build hybrid background: stock B-roll base + AI accent overlay. Returns video path."""
    # Get the stock B-roll base
    stock_path = _fetch_stock_broll(state)

    # Generate a smaller AI accent image
    style_key = state["visual_style"]
    style = VISUAL_STYLES[style_key]
    topic = state.get("custom_topic") or "finance and AI trends"

    accent_prompt = (
        f"A semi-transparent abstract accent graphic with soft glow and light particles. "
        f"Theme: {topic}. Style: {style['label'].lower()}. "
        f"Dark background that blends when overlaid. 9:16 vertical. "
        f"No text, no people, no logos."
    )

    Path("tmp").mkdir(exist_ok=True)
    accent_path = "tmp/hybrid_accent.png"

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=accent_prompt,
                size="1024x1792",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            img_resp = requests.get(image_url, timeout=60)
            img_resp.raise_for_status()
            with open(accent_path, "wb") as f:
                f.write(img_resp.content)
            break
        except Exception as e:
            logger.exception("Hybrid accent generation failed (attempt %d)", attempt + 1)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not generate accent overlay: {e}") from e
            time.sleep(2 ** attempt)

    # Composite accent over stock base with low opacity
    output_path = "tmp/hybrid_background.mp4"
    import subprocess
    filter_complex = (
        f"[1:v]scale={CANVAS_WIDTH}:{CANVAS_HEIGHT},format=rgba,"
        f"colorchannelmixer=aa=0.3[accent];"
        f"[0:v][accent]overlay=0:0:shortest=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-i", stock_path,
        "-i", accent_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=180)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"Hybrid composite failed: {stderr}")

    return output_path


def run(state: dict) -> dict:
    """Execute Step 4: generate an optimized background video.

    Dispatches to the appropriate handler based on background_mode.
    If no mode is selected, uses Claude's recommendation.

    Args:
        state: Current session state dict.

    Returns:
        Updated state with background_video_path.
    """
    style_key = state.get("visual_style")
    if not style_key or style_key not in VISUAL_STYLES:
        raise RuntimeError("Please select a visual style before generating a background.")

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg is not installed on this system. "
            "Ensure `ffmpeg` is listed in packages.txt and redeploy."
        )

    # Get or use existing recommendation
    if state.get("background_recommendation") is None:
        state["background_recommendation"] = _recommend_mode(state)

    # Determine which mode to use
    mode = state.get("background_mode")
    if not mode:
        mode = state["background_recommendation"]["recommended_mode"]
        state["background_mode"] = mode

    # Dispatch to the appropriate handler
    mode_handlers = {
        "ai_generated": _generate_ai_background,
        "stock_broll": _fetch_stock_broll,
        "green_screen": _render_green_screen_bg,
        "hybrid": _build_hybrid,
    }

    handler = mode_handlers.get(mode)
    if not handler:
        raise RuntimeError(f"Unknown background mode: {mode}")

    raw_path = handler(state)

    # Apply color grading
    style = VISUAL_STYLES[style_key]
    grade_params = style.get("color_grade")
    if grade_params:
        Path("tmp").mkdir(exist_ok=True)
        graded_path = f"tmp/background_{style_key}_graded.mp4"
        try:
            apply_color_grade(raw_path, graded_path, grade_params)
            state["background_video_path"] = graded_path
        except Exception as e:
            logger.warning("Color grading failed, using ungraded video: %s", e)
            state["background_video_path"] = raw_path
    else:
        state["background_video_path"] = raw_path

    return state
