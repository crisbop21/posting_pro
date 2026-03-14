"""Step 6: Video assembly — voiceover + background + overlays."""

import concurrent.futures
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from utils.api_clients import elevenlabs_client, ELEVENLABS_VOICE_ID
from utils.video_utils import composite_video, generate_slug, CANVAS_HEIGHT, CAPTION_ZONE

logger = logging.getLogger(__name__)

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


def _get_audio_duration(audio_path: str) -> float | None:
    """Probe the duration of an audio file using ffprobe.

    Returns duration in seconds, or None if probing fails.
    """
    import json
    import subprocess

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", audio_path],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return float(info["format"]["duration"])
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", audio_path, e)
    return None


def _beat_map_to_timings(beat_map: list[dict], total_duration_s: float,
                         min_s: float = 4.0, max_s: float = 18.0) -> list[dict]:
    """Convert percentage-based beat map to absolute second timings.

    Clamps each overlay duration to the composition skill's 4–18s range.
    """
    timings = []
    for entry in beat_map:
        start = entry["start_pct"] * total_duration_s
        duration = entry["duration_pct"] * total_duration_s
        duration = max(min_s, min(max_s, duration))
        # Ensure overlay doesn't run past the end of the video
        if start + duration > total_duration_s:
            duration = max(min_s, total_duration_s - start)
        timings.append({
            "start_s": round(start, 2),
            "duration_s": round(duration, 2),
        })
    return timings


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

    print(f"[ASSEMBLE] Inputs OK — background={background}, "
          f"script_len={len(script)}, overlays={len(overlays)}, duration={duration}s")

    # Generate voiceover
    print("[ASSEMBLE] Generating voiceover...")
    audio_path = _generate_voiceover(script)
    print(f"[ASSEMBLE] Voiceover saved to {audio_path}")

    # Use actual audio duration when available, fall back to estimate
    actual_duration = _get_audio_duration(audio_path)
    if actual_duration:
        print(f"[ASSEMBLE] Actual audio duration: {actual_duration:.1f}s "
              f"(estimated: {duration}s)")
        duration = actual_duration

    # Use beat map for overlay timing if available, otherwise even distribution
    beat_map = state.get("beat_map")
    if beat_map and len(beat_map) == len(overlays):
        timings = _beat_map_to_timings(beat_map, duration)
        print(f"[ASSEMBLE] Using beat map timing: {len(timings)} entries")
    else:
        timings = _compute_overlay_timing(len(overlays), duration)
        if beat_map:
            print(f"[ASSEMBLE] Beat map count mismatch "
                  f"({len(beat_map)} vs {len(overlays)} overlays), "
                  f"using even distribution")
        print(f"[ASSEMBLE] Overlay timings computed: {len(timings)} entries")

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
    print(f"[ASSEMBLE] Compositing video to {output_path}...")
    for attempt in range(MAX_RETRIES + 1):
        try:
            _result, diagnostics = composite_video(
                background_path=background,
                audio_path=audio_path,
                overlay_sequence=overlay_sequence,
                output_path=output_path,
            )
            print(f"[ASSEMBLE] Video composited successfully: {output_path}")
            state["final_video_path"] = output_path
            state["assembly_diagnostics"] = diagnostics
            return state

        except Exception as e:
            print(f"[ASSEMBLE] composite_video attempt {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not assemble the video: {e}") from e
            time.sleep(2 ** attempt)

    return state
