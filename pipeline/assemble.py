"""Step 6: Video assembly — voiceover + background + overlays."""

import concurrent.futures
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from utils.api_clients import elevenlabs_client, ELEVENLABS_VOICE_ID, claude
from utils.assembly_context import AssemblyContext, CancelledError
from utils.styles import VISUAL_STYLES
from utils.video_utils import (
    build_accent_overlay_clips,
    build_section_subtitle_clips,
    build_title_clip,
    composite_video,
    generate_slug,
    DEFAULT_ACCENT_COLOR,
    TITLE_DEFAULT_DURATION,
    CANVAS_HEIGHT,
    CAPTION_ZONE,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
VOICEOVER_TIMEOUT_S = 90  # max seconds to wait for ElevenLabs


def _generate_voiceover(script: str, audio_path: str | None = None) -> str:
    """Generate ElevenLabs voiceover audio and save to tmp/.

    Args:
        script: Full script text (markers will be stripped).
        audio_path: Optional unique path for this run's audio file.
            When None, generates a unique path automatically.

    Returns:
        Path to the generated audio file.
    """
    # Strip [IMAGE: ...] markers and **accent** markers for clean voiceover
    clean_script = re.sub(r"\[IMAGE:\s*.+?\]", "", script).strip()
    clean_script = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_script)
    clean_script = re.sub(r"\s{2,}", " ", clean_script)

    Path("tmp").mkdir(exist_ok=True)
    if audio_path is None:
        audio_path = f"tmp/voiceover_{uuid.uuid4().hex[:8]}.mp3"

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


def _generate_section_subtitles(script: str, overlay_count: int) -> list[str]:
    """Use Claude to generate short section subtitles from the script.

    Splits the script by [IMAGE:] markers into sections and asks Claude
    to produce a punchy subtitle (3-6 words) for each section.

    Args:
        script: The full script text with [IMAGE:] markers.
        overlay_count: Number of image overlays (= number of subtitles needed).

    Returns:
        List of subtitle strings, one per overlay section.
    """
    # Split script into sections around [IMAGE:] markers
    sections = re.split(r"\[IMAGE:\s*.+?\]", script)
    # Filter out empty sections and strip whitespace
    sections = [s.strip() for s in sections if s.strip()]

    if not sections:
        return []

    # Build the prompt with all sections
    section_list = "\n".join(
        f"Section {i + 1}: {s[:200]}" for i, s in enumerate(sections[:overlay_count])
    )

    prompt = (
        f"Generate exactly {min(len(sections), overlay_count)} short subtitles "
        f"(3-6 words each) for these video sections. Each subtitle should capture "
        f"the key point of that section — punchy and informative, like a news ticker.\n\n"
        f"{section_list}\n\n"
        f"Return ONLY the subtitles, one per line, no numbering or punctuation at the end."
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system="You generate short, punchy section subtitles for finance/AI news videos. Keep each subtitle to 3-6 words. No numbering, no trailing punctuation.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            subtitles = [line.strip() for line in raw.splitlines() if line.strip()]
            # Pad or trim to match overlay count
            if len(subtitles) < overlay_count:
                subtitles.extend([""] * (overlay_count - len(subtitles)))
            return subtitles[:overlay_count]
        except Exception as e:
            if attempt == MAX_RETRIES:
                logger.warning("Section subtitle generation failed: %s", e)
                # Fallback: derive subtitles from IMAGE marker descriptions
                markers = re.findall(r"\[IMAGE:\s*(.+?)\]", script)
                fallback = [m.strip().title() for m in markers[:overlay_count]]
                if len(fallback) < overlay_count:
                    fallback.extend([""] * (overlay_count - len(fallback)))
                return fallback[:overlay_count]
            time.sleep(2 ** attempt)

    return []


def _beat_map_to_timings(beat_map: list[dict], total_duration_s: float,
                         min_s: float = 4.0, max_s: float = 18.0) -> list[dict]:
    """Convert percentage-based beat map to absolute second timings.

    Clamps each overlay duration to the composition skill's 4–18s range.
    Skips entries that cannot fit the minimum duration before the video ends.
    """
    timings = []
    for i, entry in enumerate(beat_map):
        start = entry["start_pct"] * total_duration_s
        duration = entry["duration_pct"] * total_duration_s
        duration = max(min_s, min(max_s, duration))
        # Ensure overlay doesn't run past the end of the video
        if start + duration > total_duration_s:
            remaining = total_duration_s - start
            if remaining < min_s:
                # Not enough room — skip this entry entirely
                logger.warning(
                    "Skipping beat map entry #%d at %.1fs: only %.1fs "
                    "remaining (min=%.1fs)",
                    i + 1, start, remaining, min_s,
                )
                continue
            duration = remaining
        timings.append({
            "start_s": round(start, 2),
            "duration_s": round(duration, 2),
        })
    return timings


def _compute_overlay_timing(overlay_count: int, total_duration_s: float) -> list[dict]:
    """Compute evenly spaced start times and durations for overlays.

    Each overlay gets an equal share of the video duration, clamped to
    the 4–18 second range defined in the composition skill.
    The first overlay always starts at t=0 for an instant visual hook.
    """
    if overlay_count == 0:
        return []

    gap = 0.2  # seconds between overlays — tighter pacing for dopamine
    available = total_duration_s - (gap * (overlay_count - 1))
    per_overlay = max(4.0, min(18.0, available / overlay_count))

    timings = []
    current_time = 0.0  # first overlay starts immediately (hook frame)

    for _ in range(overlay_count):
        if current_time + per_overlay > total_duration_s:
            break
        timings.append({
            "start_s": round(current_time, 2),
            "duration_s": round(per_overlay, 2),
        })
        current_time += per_overlay + gap

    return timings


def run(state: dict, ctx: AssemblyContext | None = None) -> dict:
    """Execute Step 6: assemble the final video.

    Args:
        state: Current session state dict with background_video_path,
               overlay_sequence, script, and estimated_duration_s.
        ctx: Optional AssemblyContext for thread-safe coordination,
             cancellation support, and unique temp file paths.
             When None, the function behaves identically to before
             (backwards-compatible for tests and direct calls).

    Returns:
        Updated state with final_video_path.
    """
    def _log(msg: str) -> None:
        print(msg)
        if ctx:
            ctx.log(msg)

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

    _log(f"[ASSEMBLE] Inputs OK — background={background}, "
         f"script_len={len(script)}, overlays={len(overlays)}, duration={duration}s")

    # --- Cancellation checkpoint: before voiceover ---
    if ctx:
        ctx.check_cancelled("pre-voiceover")

    # Generate voiceover (unique path per run to avoid collisions)
    _log("[ASSEMBLE] Generating voiceover...")
    vo_path = ctx.voiceover_path() if ctx else None
    audio_path = _generate_voiceover(script, audio_path=vo_path)
    _log(f"[ASSEMBLE] Voiceover saved to {audio_path}")

    # Use actual audio duration when available, fall back to estimate
    actual_duration = _get_audio_duration(audio_path)
    if actual_duration:
        _log(f"[ASSEMBLE] Actual audio duration: {actual_duration:.1f}s "
             f"(estimated: {duration}s)")
        duration = actual_duration

    # --- Cancellation checkpoint: before timing + composite ---
    if ctx:
        ctx.check_cancelled("pre-composite")

    # Use beat map for overlay timing if available, otherwise even distribution
    beat_map = state.get("beat_map")
    if beat_map and len(beat_map) == len(overlays):
        timings = _beat_map_to_timings(beat_map, duration)
        _log(f"[ASSEMBLE] Using beat map timing: {len(timings)} entries")
    else:
        timings = _compute_overlay_timing(len(overlays), duration)
        if beat_map:
            _log(f"[ASSEMBLE] Beat map count mismatch "
                 f"({len(beat_map)} vs {len(overlays)} overlays), "
                 f"using even distribution")
        _log(f"[ASSEMBLE] Overlay timings computed: {len(timings)} entries")

    # Build overlay sequence with timing and paths
    overlay_sequence = []
    for i, timing in enumerate(timings):
        if i < len(overlays):
            overlay_sequence.append({
                "image_path": overlays[i],
                "start_s": timing["start_s"],
                "duration_s": timing["duration_s"],
            })

    # Warn if some overlays were dropped due to insufficient timing slots
    if len(timings) < len(overlays):
        dropped = len(overlays) - len(timings)
        _log(f"[ASSEMBLE] WARNING: {dropped} overlay(s) dropped — only "
             f"{len(timings)} timing slot(s) for {len(overlays)} overlay(s). "
             f"Video duration ({duration:.1f}s) may be too short.")

    # Generate output path
    topic = state.get("custom_topic") or "finance-news"
    slug = generate_slug(topic)
    date_str = datetime.now().strftime("%Y%m%d")
    Path("outputs").mkdir(exist_ok=True)
    output_path = f"outputs/{slug}-{date_str}.mp4"

    # Build accent text overlays from **tagged** phrases in the script
    accent_color = state.get("accent_color")
    if not accent_color:
        style_name = state.get("visual_style")
        style_def = VISUAL_STYLES.get(style_name, {})
        accent_color = style_def.get("accent_color", DEFAULT_ACCENT_COLOR)
    _log(f"[ASSEMBLE] Accent color: {accent_color}")

    # Pass overlay timings so accent clips fill visual gaps
    overlay_timings_for_accents = [
        {"start_s": ov["start_s"], "duration_s": ov["duration_s"]}
        for ov in overlay_sequence
    ]
    accent_clips = build_accent_overlay_clips(
        script=script,
        total_duration_s=duration,
        accent_color=accent_color,
        overlay_timings=overlay_timings_for_accents,
    )
    _log(f"[ASSEMBLE] Built {len(accent_clips)} accent text clips")

    # Build title overlay clip if enabled
    title_clip_obj = None
    if state.get("title_enabled", True) and state.get("title_text", "").strip():
        title_clip_obj = build_title_clip(
            title_text=state["title_text"],
            total_duration_s=duration,
        )
        if title_clip_obj:
            _log(f"[ASSEMBLE] Title clip built: '{state['title_text']}'")
        else:
            _log("[ASSEMBLE] Title clip skipped (too short or empty)")
    else:
        _log("[ASSEMBLE] Title overlay disabled or empty")

    # Build section subtitle clips if enabled
    section_subtitle_clips = []
    if state.get("section_subtitles_enabled", True):
        subtitles = state.get("section_subtitles", [])
        if not subtitles and overlay_sequence:
            _log("[ASSEMBLE] Generating section subtitles via Claude...")
            subtitles = _generate_section_subtitles(script, len(overlay_sequence))
            state["section_subtitles"] = subtitles
            _log(f"[ASSEMBLE] Generated {len(subtitles)} section subtitles")

        if subtitles and overlay_timings_for_accents:
            title_dur = TITLE_DEFAULT_DURATION if title_clip_obj else 0.0
            section_subtitle_clips = build_section_subtitle_clips(
                subtitles=subtitles,
                overlay_timings=overlay_timings_for_accents,
                total_duration_s=duration,
                title_duration_s=title_dur,
            )
            _log(f"[ASSEMBLE] Built {len(section_subtitle_clips)} section subtitle clips")
    else:
        _log("[ASSEMBLE] Section subtitles disabled")

    # Convert accent hex color to RGB tuple for the progress bar
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    progress_bar_rgb = _hex_to_rgb(accent_color)

    # Composite the final video
    _log(f"[ASSEMBLE] Compositing video to {output_path}...")
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Check cancellation before the expensive composite step
            if ctx:
                ctx.check_cancelled("pre-ffmpeg-render")

            _result, diagnostics = composite_video(
                background_path=background,
                audio_path=audio_path,
                overlay_sequence=overlay_sequence,
                output_path=output_path,
                accent_text_clips=accent_clips,
                title_clip=title_clip_obj,
                section_subtitle_clips=section_subtitle_clips,
                progress_bar_color=progress_bar_rgb,
            )
            _log(f"[ASSEMBLE] Video composited successfully: {output_path}")
            state["final_video_path"] = output_path
            state["assembly_diagnostics"] = diagnostics
            return state

        except CancelledError:
            raise  # propagate cancellation — don't retry
        except Exception as e:
            _log(f"[ASSEMBLE] composite_video attempt {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not assemble the video: {e}") from e
            time.sleep(2 ** attempt)

    return state
