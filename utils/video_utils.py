"""Ken Burns renderer, color grading, cropping, and FFmpeg video compositor."""

import json
import random
import subprocess
import tempfile
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

# Canvas dimensions for 9:16 vertical video
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
CAPTION_ZONE = 200  # bottom pixels reserved for captions

# Overlay timing
FADE_IN_S = 0.4
FADE_OUT_S = 0.3
MIN_OVERLAY_S = 4
MAX_OVERLAY_S = 18

# FFmpeg encoding settings
CRF = "23"
CODEC = "libx264"


def render_ken_burns(image_path: str, duration_s: float, output_path: str,
                     zoom_start: float = 1.0, zoom_end: float = 1.2,
                     fps: int = 30, direction: str = "zoom_in") -> str:
    """Generate a Ken Burns pan-and-zoom video from a still image.

    Args:
        image_path: Path to the source image.
        duration_s: Duration of the output video in seconds.
        output_path: Path for the output MP4 file.
        zoom_start: Starting zoom factor.
        zoom_end: Ending zoom factor.
        fps: Frames per second.
        direction: Animation direction — "zoom_in", "zoom_out", "pan_left", "pan_right".

    Returns:
        Path to the rendered video file.
    """
    total_frames = int(duration_s * fps)
    zoom_step = (zoom_end - zoom_start) / max(total_frames, 1)

    if direction == "zoom_out":
        # Reverse: start zoomed in, end at normal
        z_expr = f"if(eq(on,1),{zoom_end},{zoom_end}-(on-1)*{zoom_step})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == "pan_left":
        # Fixed zoom at midpoint, pan from right to left
        mid_zoom = (zoom_start + zoom_end) / 2
        z_expr = str(mid_zoom)
        x_expr = f"iw/zoom-iw/zoom*on/{total_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == "pan_right":
        # Fixed zoom at midpoint, pan from left to right
        mid_zoom = (zoom_start + zoom_end) / 2
        z_expr = str(mid_zoom)
        x_expr = f"iw/zoom*on/{total_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Default: zoom_in — original behavior
        z_expr = f"if(eq(on,1),{zoom_start},{zoom_start}+(on-1)*{zoom_step})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    # Randomize the Ken Burns direction so each render feels unique.
    # Pick a pan direction and whether we zoom in or out.
    zoom_step = (zoom_end - zoom_start) / max(total_frames, 1)
    pan_direction = random.choice(["center", "left_to_right", "right_to_left",
                                   "top_to_bottom", "bottom_to_top"])
    zoom_in = random.choice([True, False])
    if not zoom_in:
        zoom_start, zoom_end = zoom_end, zoom_start
        zoom_step = (zoom_end - zoom_start) / max(total_frames, 1)

    # Pan expressions — each moves the viewport gradually across the image
    pan_exprs = {
        "center": (
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        ),
        "left_to_right": (
            f"on/{total_frames}*(iw-iw/zoom)",
            "ih/2-(ih/zoom/2)",
        ),
        "right_to_left": (
            f"(1-on/{total_frames})*(iw-iw/zoom)",
            "ih/2-(ih/zoom/2)",
        ),
        "top_to_bottom": (
            "iw/2-(iw/zoom/2)",
            f"on/{total_frames}*(ih-ih/zoom)",
        ),
        "bottom_to_top": (
            "iw/2-(iw/zoom/2)",
            f"(1-on/{total_frames})*(ih-ih/zoom)",
        ),
    }
    x_expr, y_expr = pan_exprs[pan_direction]

    logger.info("Ken Burns style: pan=%s, zoom_in=%s", pan_direction, zoom_in)

    zp_filter = (
        f"zoompan="
        f"z='if(eq(on,1),{zoom_start},{zoom_start}+(on-1)*{zoom_step})':"
        f"d={total_frames}:"
        f"x='{x_expr}':"
        f"y='{y_expr}':"
        f"s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:"
        f"fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-i", image_path,
        "-vf", zp_filter,
        "-c:v", CODEC,
        "-preset", "veryfast",
        "-crf", CRF,
        "-pix_fmt", "yuv420p",
        "-movflags", "faststart",
        "-t", str(duration_s),
        output_path,
    ]

    logger.info("Ken Burns render: direction=%s, duration=%.1fs, output=%s",
                direction, duration_s, output_path)
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {stderr}")
    return output_path


def apply_color_grade(input_path: str, output_path: str, grade_params: dict) -> str:
    """Apply LUT-style color grading to a video using FFmpeg filters.

    Args:
        input_path: Path to the source video.
        output_path: Path for the graded output video.
        grade_params: Dict with keys: brightness, contrast, saturation, warmth, vignette.

    Returns:
        Path to the graded video file.
    """
    brightness = grade_params.get("brightness", 0.0)
    contrast = grade_params.get("contrast", 1.0)
    saturation = grade_params.get("saturation", 1.0)
    warmth = grade_params.get("warmth", 0.0)
    vignette = grade_params.get("vignette", False)

    filters = []

    # Core eq filter for brightness, contrast, saturation
    eq_parts = []
    eq_parts.append(f"brightness={brightness}")
    eq_parts.append(f"contrast={contrast}")
    eq_parts.append(f"saturation={saturation}")
    filters.append(f"eq={':'.join(eq_parts)}")

    # Warmth via color temperature shift (approximate with colorbalance)
    if warmth != 0.0:
        # Positive warmth = more red/yellow shadows, negative = more blue
        rs = max(min(warmth * 0.3, 1.0), -1.0)
        bs = max(min(-warmth * 0.3, 1.0), -1.0)
        filters.append(f"colorbalance=rs={rs}:bs={bs}")

    # Vignette
    if vignette:
        filters.append("vignette=PI/4")

    filter_chain = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-i", input_path,
        "-vf", filter_chain,
        "-c:v", CODEC,
        "-preset", "veryfast",
        "-crf", CRF,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "faststart",
        output_path,
    ]

    logger.info("Color grade: %s -> %s (params=%s)", input_path, output_path, grade_params)
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"Color grading failed (code {result.returncode}): {stderr}")
    return output_path


def crop_to_vertical(input_path: str, output_path: str,
                     target_w: int = CANVAS_WIDTH,
                     target_h: int = CANVAS_HEIGHT) -> str:
    """Smart-crop a video to 9:16 vertical from its center.

    Args:
        input_path: Path to the source video (typically landscape).
        output_path: Path for the cropped output video.
        target_w: Target width in pixels.
        target_h: Target height in pixels.

    Returns:
        Path to the cropped video file.
    """
    # Probe source dimensions
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        input_path,
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, timeout=30)
    if probe_result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {input_path}")

    streams = json.loads(probe_result.stdout)
    video_stream = next(
        (s for s in streams.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise RuntimeError(f"No video stream found in {input_path}")

    src_w = int(video_stream["width"])
    src_h = int(video_stream["height"])

    # Calculate crop: fit to 9:16 aspect from center
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider — crop width
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        # Source is taller or same — crop height
        crop_w = src_w
        crop_h = int(src_w / target_ratio)

    crop_filter = (
        f"crop={crop_w}:{crop_h}:(in_w-{crop_w})/2:(in_h-{crop_h})/2,"
        f"scale={target_w}:{target_h}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-i", input_path,
        "-vf", crop_filter,
        "-c:v", CODEC,
        "-preset", "veryfast",
        "-crf", CRF,
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "faststart",
        output_path,
    ]

    logger.info("Crop to vertical: %dx%d -> %dx%d, output=%s",
                src_w, src_h, target_w, target_h, output_path)
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"Crop failed (code {result.returncode}): {stderr}")
    return output_path


def render_green_screen(output_path: str, duration_s: float,
                        color_top: str = "#0a0a1a",
                        color_bottom: str = "#1a1a3a",
                        fps: int = 30) -> str:
    """Generate a gradient background video for green-screen style content.

    Creates a single gradient PNG then loops it into a video, which is
    far faster than computing a per-pixel blend across every frame.

    Args:
        output_path: Path for the output MP4 file.
        duration_s: Duration in seconds.
        color_top: Hex color for the top of the gradient.
        color_bottom: Hex color for the bottom of the gradient.
        fps: Frames per second.

    Returns:
        Path to the rendered video file.
    """
    parent = Path(output_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    gradient_png = str(parent / "_gradient_tmp.png")

    # Step 1: render a single gradient PNG (instant — one frame)
    png_filter = (
        f"color=c={color_top}:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}[top];"
        f"color=c={color_bottom}:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}[bottom];"
        f"[top][bottom]blend=all_expr='A*(1-Y/H)+B*(Y/H)'"
    )
    png_cmd = [
        "ffmpeg", "-y",
        "-frames:v", "1",
        "-filter_complex", png_filter,
        gradient_png,
    ]
    result = subprocess.run(png_cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"Gradient PNG generation failed (code {result.returncode}): {stderr}")

    # Step 2: loop the still image into a video with subtle noise
    vid_cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-loop", "1",
        "-i", gradient_png,
        "-vf", f"noise=alls=3:allf=t,format=yuv420p",
        "-c:v", CODEC,
        "-preset", "veryfast",
        "-crf", CRF,
        "-r", str(fps),
        "-t", str(duration_s),
        "-movflags", "faststart",
        output_path,
    ]

    logger.info("Green screen render: %s->%s, duration=%.1fs", color_top, color_bottom, duration_s)
    result = subprocess.run(vid_cmd, capture_output=True, timeout=180)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"Green screen render failed (code {result.returncode}): {stderr}")

    # Clean up temp PNG
    Path(gradient_png).unlink(missing_ok=True)
    return output_path


def _probe_media(file_path: str) -> dict:
    """Probe a media file for duration, dimensions, and format using ffprobe.

    Returns a dict with keys: duration_s, width, height, codec, pix_fmt.
    Missing fields are set to None.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", file_path],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return {"error": f"ffprobe exit code {result.returncode}"}

        data = json.loads(result.stdout)

        duration = None
        fmt = data.get("format", {})
        if fmt.get("duration"):
            duration = float(fmt["duration"])

        video_stream = next(
            (s for s in data.get("streams", [])
             if s.get("codec_type") == "video"), None
        )
        if video_stream:
            return {
                "duration_s": duration,
                "width": int(video_stream.get("width", 0)) or None,
                "height": int(video_stream.get("height", 0)) or None,
                "codec": video_stream.get("codec_name"),
                "pix_fmt": video_stream.get("pix_fmt"),
            }

        # Audio-only file
        audio_stream = next(
            (s for s in data.get("streams", [])
             if s.get("codec_type") == "audio"), None
        )
        return {
            "duration_s": duration,
            "width": None,
            "height": None,
            "codec": audio_stream.get("codec_name") if audio_stream else None,
            "pix_fmt": None,
        }
    except Exception as e:
        return {"error": str(e)}


def composite_video(background_path: str, audio_path: str,
                    overlay_sequence: list[dict], output_path: str,
                    darken: bool = True) -> str:
    """Composite overlays and audio onto the background video.

    Args:
        background_path: Path to the Ken Burns background video.
        audio_path: Path to the ElevenLabs voiceover audio.
        overlay_sequence: List of dicts with keys:
            - image_path: processed overlay image path
            - start_s: start time in seconds
            - duration_s: how long the overlay is shown
        output_path: Path for the final output MP4.
        darken: Whether to dim the background for foreground separation.

    Returns:
        Tuple of (output_path, diagnostics_dict).
    """
    # ------------------------------------------------------------------
    # Pre-flight: probe all inputs and collect diagnostics
    # ------------------------------------------------------------------
    warnings = []

    # Validate inputs exist
    for label, fpath in [("Background video", background_path),
                         ("Audio file", audio_path)]:
        if not Path(fpath).exists():
            raise RuntimeError(f"{label} not found: {fpath}")
    for i, ov in enumerate(overlay_sequence):
        if not Path(ov["image_path"]).exists():
            raise RuntimeError(f"Overlay image {i + 1} not found: {ov['image_path']}")

    # Probe background video
    bg_info = _probe_media(background_path)
    if bg_info.get("error"):
        warnings.append(f"Could not probe background: {bg_info['error']}")
    bg_duration = bg_info.get("duration_s")

    # Probe audio
    audio_info = _probe_media(audio_path)
    if audio_info.get("error"):
        warnings.append(f"Could not probe audio: {audio_info['error']}")
    audio_duration = audio_info.get("duration_s")

    # Probe each overlay image
    overlay_probes = []
    for i, ov in enumerate(overlay_sequence):
        probe = _probe_media(ov["image_path"])
        probe["index"] = i + 1
        probe["file"] = Path(ov["image_path"]).name
        overlay_probes.append(probe)
        if probe.get("error"):
            warnings.append(f"Overlay #{i+1} probe failed: {probe['error']}")

    # Timing sanity checks
    if overlay_sequence:
        last_end = overlay_sequence[-1]["start_s"] + overlay_sequence[-1]["duration_s"]
        if bg_duration and last_end > bg_duration + 1:
            warnings.append(
                f"Last overlay ends at {last_end:.1f}s but background is "
                f"only {bg_duration:.1f}s — overlays may be cut short"
            )
        if audio_duration and last_end > audio_duration + 1:
            warnings.append(
                f"Last overlay ends at {last_end:.1f}s but audio is "
                f"only {audio_duration:.1f}s — video will end with audio"
            )
        for i in range(1, len(overlay_sequence)):
            prev_end = (overlay_sequence[i-1]["start_s"]
                        + overlay_sequence[i-1]["duration_s"])
            curr_start = overlay_sequence[i]["start_s"]
            if curr_start < prev_end:
                warnings.append(
                    f"Overlays #{i} and #{i+1} overlap: "
                    f"#{i} ends at {prev_end:.2f}s, "
                    f"#{i+1} starts at {curr_start:.2f}s"
                )

    # ------------------------------------------------------------------
    # Build the FFmpeg filter complex
    # ------------------------------------------------------------------
    inputs = ["-i", background_path, "-i", audio_path]
    filter_parts = []

    # Darken the background so foreground overlays pop visually
    if darken:
        filter_parts.append("[0:v]eq=brightness=-0.15:saturation=0.85[bg]")
        prev_label = "bg"
    else:
        prev_label = "0:v"

    for i, overlay in enumerate(overlay_sequence):
        start = overlay["start_s"]
        duration = overlay["duration_s"]
        end = start + duration

        # Loop the still image so FFmpeg generates frames with proper
        # timestamps — without this the image is a single frame at t=0
        # and the fade filter never triggers for later overlays.
        inputs.extend(["-loop", "1", "-t", str(end), "-i", overlay["image_path"]])
        input_idx = i + 2  # 0=bg, 1=audio, 2+=overlays

        # Position overlay centred horizontally, above the caption zone
        y_pos = (CANVAS_HEIGHT - CAPTION_ZONE) // 2
        x_pos = f"(W-w)/2"

        # Fade in/out using absolute timestamps — the looped image stream
        # now has frames from t=0 to t=end so these times are reachable.
        fade_filter = (
            f"[{input_idx}:v]format=rgba,"
            f"fade=t=in:st={start}:d={FADE_IN_S}:alpha=1,"
            f"fade=t=out:st={end - FADE_OUT_S}:d={FADE_OUT_S}:alpha=1"
            f"[ov{i}]"
        )
        filter_parts.append(fade_filter)

        # eof_action=pass: when the overlay image stream reaches EOF,
        # keep passing the main input through instead of stopping the
        # entire filter chain. Without this, only the first overlay
        # renders because its stream EOF kills downstream outputs.
        overlay_filter = (
            f"[{prev_label}][ov{i}]overlay={x_pos}:y={y_pos}:"
            f"enable='between(t,{start},{end})':"
            f"eof_action=pass[tmp{i}]"
        )
        filter_parts.append(overlay_filter)
        prev_label = f"tmp{i}"

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        *inputs,
    ]

    if filter_complex:
        cmd.extend(["-filter_complex", filter_complex,
                     "-map", f"[{prev_label}]"])
    else:
        # No overlays — apply darkening as a simple video filter if enabled
        if darken:
            cmd.extend(["-vf", "eq=brightness=-0.15:saturation=0.85"])
        cmd.extend(["-map", "0:v"])

    cmd.extend([
        "-map", "1:a",
        "-c:v", CODEC,
        "-preset", "veryfast",
        "-crf", CRF,
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "faststart",
        "-shortest",
        output_path,
    ])

    # ------------------------------------------------------------------
    # Build diagnostics dict for UI debugging
    # ------------------------------------------------------------------
    diagnostics = {
        "overlay_count": len(overlay_sequence),
        "filter_complex": filter_complex if filter_complex else "(none)",
        "background": {
            "file": Path(background_path).name,
            "duration_s": bg_duration,
            "width": bg_info.get("width"),
            "height": bg_info.get("height"),
            "pix_fmt": bg_info.get("pix_fmt"),
        },
        "audio": {
            "file": Path(audio_path).name,
            "duration_s": audio_duration,
            "codec": audio_info.get("codec"),
        },
        "overlay_timings": [
            {
                "index": i + 1,
                "image": Path(ov["image_path"]).name,
                "start_s": ov["start_s"],
                "end_s": round(ov["start_s"] + ov["duration_s"], 2),
                "duration_s": ov["duration_s"],
                "loop_end_s": round(ov["start_s"] + ov["duration_s"], 2),
                "dimensions": (
                    f"{overlay_probes[i].get('width')}x"
                    f"{overlay_probes[i].get('height')}"
                    if i < len(overlay_probes)
                       and overlay_probes[i].get("width")
                    else "unknown"
                ),
            }
            for i, ov in enumerate(overlay_sequence)
        ],
        "warnings": warnings,
        "cmd": " ".join(cmd),
        "ffmpeg_stderr": "",
        "success": False,
    }

    # ------------------------------------------------------------------
    # Run FFmpeg
    # ------------------------------------------------------------------
    logger.info("Compositing %d overlays, output=%s", len(overlay_sequence), output_path)
    result = subprocess.run(cmd, capture_output=True, timeout=240)
    stderr_text = result.stderr.decode(errors="replace")
    diagnostics["ffmpeg_stderr"] = stderr_text[-3000:]
    diagnostics["success"] = result.returncode == 0

    # Parse stderr for common warning patterns
    stderr_lower = stderr_text.lower()
    if "discarding" in stderr_lower:
        warnings.append("FFmpeg discarded frames — possible stream sync issue")
    if "discarding initial" in stderr_lower:
        warnings.append("FFmpeg discarded initial timestamps — may affect overlay timing")
    if "discarding damaged" in stderr_lower:
        warnings.append("FFmpeg discarded damaged frames — possible corrupt input")
    if "error" in stderr_lower and result.returncode == 0:
        # FFmpeg succeeded but logged errors
        warnings.append("FFmpeg logged errors despite success — check stderr output")
    if "discarding" not in stderr_lower and "past duration" in stderr_lower:
        warnings.append("Frames past declared duration — input may be longer than expected")

    diagnostics["warnings"] = warnings

    if result.returncode != 0:
        diagnostics["success"] = False
        raise RuntimeError(
            f"ffmpeg exited with code {result.returncode}: "
            f"{diagnostics['ffmpeg_stderr'][-500:]}"
        )

    return output_path, diagnostics


def generate_slug(topic: str, max_length: int = 40) -> str:
    """Generate a URL-safe slug from a topic string.

    Args:
        topic: Raw topic string.
        max_length: Maximum slug length.

    Returns:
        Lowercase, hyphenated slug with special characters stripped.
    """
    slug = topic.lower().strip()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split())
    return slug[:max_length]
