"""Step 6: Video assembly — voiceover + background + overlays."""

import concurrent.futures
import re
import time
from datetime import datetime
from pathlib import Path

from utils.api_clients import elevenlabs_client, ELEVENLABS_VOICE_ID
from utils.video_utils import composite_video, generate_slug, CANVAS_HEIGHT, CAPTION_ZONE

MAX_RETRIES = 1
VOICEOVER_TIMEOUT_S = 90  # max seconds to wait for ElevenLabs


def _generate_voiceover(script: str) -> str:
    """Generate ElevenLabs voiceover audio and save to tmp/.

    Returns:
        Path to the generated audio file.
    """
    # Strip [IMAGE: ...] markers from the script for clean voiceover
    clean_script = re.sub(r"\[IMAGE:\s*.+?\]", "", script).strip()
    clean_script = re.sub(r"\s{2,}", " ", clean_script)

    Path("tmp").mkdir(exist_ok=True)
    audio_path = "tmp/voiceover.mp3"

    def _call_elevenlabs():
        audio = elevenlabs_client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=clean_script,
            model_id="eleven_multilingual_v2",
        )
        with open(audio_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        return audio_path

    for attempt in range(MAX_RETRIES + 1):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_call_elevenlabs)
                return future.result(timeout=VOICEOVER_TIMEOUT_S)

        except concurrent.futures.TimeoutError:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "Voiceover generation timed out. The ElevenLabs API "
                    "did not respond within the allowed time."
                )
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not generate the voiceover: {e}") from e
            time.sleep(2 ** attempt)

    return audio_path


def _compute_overlay_timing(overlay_count: int, total_duration_s: float) -> list[dict]:
    """Compute evenly spaced start times and durations for overlays.

    Each overlay gets an equal share of the video duration, clamped to
    the 4–18 second range defined in the composition skill.
    """
    if overlay_count == 0:
        return []

    gap = 0.5  # seconds between overlays
    available = total_duration_s - (gap * (overlay_count - 1))
    per_overlay = max(4.0, min(18.0, available / overlay_count))

    timings = []
    current_time = 0.0

    for _ in range(overlay_count):
        if current_time + per_overlay > total_duration_s:
            break
        timings.append({
            "start_s": round(current_time, 2),
            "duration_s": round(per_overlay, 2),
        })
        current_time += per_overlay + gap

    return timings


def run(state: dict) -> dict:
    """Execute Step 6: assemble the final video.

    Args:
        state: Current session state dict with background_video_path,
               overlay_sequence, script, and estimated_duration_s.

    Returns:
        Updated state with final_video_path.
    """
    background = state.get("background_video_path")
    if not background:
        raise RuntimeError("No background video. Complete Step 4 first.")
    if not Path(background).exists():
        raise RuntimeError(
            f"Background video file missing: {background}. "
            "Re-run Step 4 to regenerate it."
        )

    script = state.get("script")
    if not script:
        raise RuntimeError("No script available. Complete Step 3 first.")

    overlays = state.get("overlay_sequence", [])
    missing = [p for p in overlays if not Path(p).exists()]
    if missing:
        raise RuntimeError(
            f"{len(missing)} overlay image(s) missing. "
            "Re-run Step 5 to regenerate them."
        )
    duration = state.get("estimated_duration_s", 60)

    # Generate voiceover
    audio_path = _generate_voiceover(script)

    # Compute overlay timing
    timings = _compute_overlay_timing(len(overlays), duration)

    # Build overlay sequence with timing and paths
    overlay_sequence = []
    for i, timing in enumerate(timings):
        if i < len(overlays):
            overlay_sequence.append({
                "image_path": overlays[i],
                "start_s": timing["start_s"],
                "duration_s": timing["duration_s"],
            })

    # Generate output path
    topic = state.get("custom_topic") or "finance-news"
    slug = generate_slug(topic)
    date_str = datetime.now().strftime("%Y%m%d")
    Path("outputs").mkdir(exist_ok=True)
    output_path = f"outputs/{slug}-{date_str}.mp4"

    # Composite the final video
    for attempt in range(MAX_RETRIES + 1):
        try:
            composite_video(
                background_path=background,
                audio_path=audio_path,
                overlay_sequence=overlay_sequence,
                output_path=output_path,
            )
            state["final_video_path"] = output_path
            return state

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not assemble the video: {e}") from e
            time.sleep(2 ** attempt)

    return state
