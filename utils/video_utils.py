"""Ken Burns renderer, color grading, cropping, accent text renderer, and MoviePy video compositor."""

import json
import math
import random
import re
import subprocess
import tempfile
from pathlib import Path

import logging

from PIL import Image, ImageDraw, ImageFile, ImageFont

# Allow PIL to load truncated/incomplete images instead of raising OSError
ImageFile.LOAD_TRUNCATED_IMAGES = True
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    vfx,
)

logger = logging.getLogger(__name__)

# Canvas dimensions for 9:16 vertical video
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
CAPTION_ZONE = 300  # bottom pixels reserved for captions (TikTok UI covers ~300px)

# Overlay timing
FADE_IN_S = 0.4
FADE_OUT_S = 0.3
MIN_OVERLAY_S = 4
MAX_OVERLAY_S = 18

# Spring-physics entrance animation
SPRING_DURATION_S = 0.5  # total spring animation time
SPRING_SCALE_START = 0.95  # initial scale (slightly smaller)
SPRING_SCALE_OVERSHOOT = 1.02  # overshoot peak
SPRING_SCALE_END = 1.0  # settle at 100%

# FFmpeg encoding settings
CRF = "23"
CODEC = "libx264"


def _spring_scale(t: float, duration: float = SPRING_DURATION_S) -> float:
    """Return a scale factor with spring-physics easing (95% → 102% → 100%).

    Uses a damped oscillation: starts small, overshoots the target, then
    settles. The curve hits ~1.02 around 60% of the duration, then eases
    back to exactly 1.0.

    Used for image overlay entrance animations. After the spring duration
    completes, returns exactly 1.0.
    """
    if t >= duration:
        return SPRING_SCALE_END
    p = t / duration
    # Damped spring: 1 - e^(-decay*p) * cos(freq*p)
    # Tuned so overshoot peaks at ~1.02 and settles to 1.0
    decay = 6.0
    freq = math.pi  # one half-oscillation over the duration
    spring = 1.0 - math.exp(-decay * p) * math.cos(freq * p)
    # spring goes 0 → overshoot → ~1.0
    # Map: 0.95 at spring=0, target range = 0.95 to (0.95 + amplitude)
    amplitude = SPRING_SCALE_OVERSHOOT - SPRING_SCALE_START  # 0.07
    return SPRING_SCALE_START + amplitude * spring


def render_ken_burns(image_path: str, duration_s: float, output_path: str,
                     zoom_start: float = 1.0, zoom_end: float = 1.2,
                     fps: int = 30, direction: str | None = None) -> str:
    """Generate a Ken Burns pan-and-zoom video from a still image.

    Args:
        image_path: Path to the source image.
        duration_s: Duration of the output video in seconds.
        output_path: Path for the output MP4 file.
        zoom_start: Starting zoom factor.
        zoom_end: Ending zoom factor.
        fps: Frames per second.
        direction: Explicit direction override — "zoom_in", "zoom_out",
            "pan_left", "pan_right".  When None (default), a random
            pan direction and zoom are chosen for variety.

    Returns:
        Path to the rendered video file.
    """
    total_frames = int(duration_s * fps)

    # Map explicit direction to internal pan + zoom_in flag
    _direction_map = {
        "zoom_in": ("center", True),
        "zoom_out": ("center", False),
        "pan_left": ("right_to_left", True),
        "pan_right": ("left_to_right", True),
    }

    if direction and direction in _direction_map:
        pan_direction, zoom_in = _direction_map[direction]
    else:
        # Randomize for variety when no explicit direction is given
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


# ---------------------------------------------------------------------------
# Accent text rendering (PIL-based)
# ---------------------------------------------------------------------------

# Default accent colour — overridden by the visual style's accent_color
DEFAULT_ACCENT_COLOR = "#FF6B35"
ACCENT_FONT_SIZE = 80
ACCENT_FONT_BOLD_SIZE = 96
ACCENT_TEXT_COLOR = "#FFFFFF"
ACCENT_BG_ALPHA = 180  # 0–255 background pill opacity
ACCENT_PADDING_X = 48
ACCENT_PADDING_Y = 24
ACCENT_MAX_WIDTH = 920  # max text block width (px), inside 1080 canvas


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a sans-serif font at the given size, with bold weight if available."""
    # Try common paths in order of preference
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    # Fallback — PIL default (bitmap, not great but works)
    return ImageFont.load_default()


def parse_accent_phrases(script: str) -> list[dict]:
    """Extract **accent-tagged** phrases and their positions from a script.

    Returns a list of dicts:
        {"phrase": "...", "index": int}
    where index is the order of occurrence (0-based).
    """
    return [
        {"phrase": m.group(1), "index": i}
        for i, m in enumerate(re.finditer(r"\*\*(.+?)\*\*", script))
    ]


def render_accent_text_image(
    text: str,
    accent_color: str = DEFAULT_ACCENT_COLOR,
    output_path: str | None = None,
) -> str:
    """Render a single accent phrase as a transparent PNG with a pill background.

    The text is drawn in the accent colour on a semi-transparent dark pill,
    centred for compositing onto the video canvas.

    Args:
        text: The accent phrase to render (plain text, no ** markers).
        accent_color: Hex colour for the text.
        output_path: Where to save the PNG.  Auto-generated if None.

    Returns:
        Path to the rendered PNG image.
    """
    font = _load_font(ACCENT_FONT_BOLD_SIZE, bold=True)
    regular_font = _load_font(ACCENT_FONT_SIZE, bold=False)

    # Measure text bounding box
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Word-wrap if text is too wide
    if text_w > ACCENT_MAX_WIDTH:
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            test_bbox = draw.textbbox((0, 0), test, font=font)
            if test_bbox[2] - test_bbox[0] <= ACCENT_MAX_WIDTH:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        wrapped_text = "\n".join(lines)

        # Re-measure
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        wrapped_text = text

    # Create image with padding (pill shape)
    img_w = text_w + ACCENT_PADDING_X * 2
    img_h = text_h + ACCENT_PADDING_Y * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background (dark pill)
    pill_radius = min(24, img_h // 2)
    draw.rounded_rectangle(
        [(0, 0), (img_w - 1, img_h - 1)],
        radius=pill_radius,
        fill=(10, 10, 20, ACCENT_BG_ALPHA),
    )

    # Draw text in accent colour
    draw.multiline_text(
        (ACCENT_PADDING_X, ACCENT_PADDING_Y),
        wrapped_text,
        font=font,
        fill=accent_color,
        align="center",
    )

    if output_path is None:
        Path("tmp").mkdir(exist_ok=True)
        output_path = tempfile.mktemp(suffix=".png", dir="tmp")

    img.save(output_path, "PNG")
    return output_path


def _compute_gap_intervals(
    overlay_timings: list[dict],
    total_duration_s: float,
) -> list[tuple[float, float]]:
    """Return (start, end) intervals where no image overlay is on screen.

    Args:
        overlay_timings: List of dicts with ``start_s`` and ``duration_s``.
        total_duration_s: Master video duration in seconds.

    Returns:
        List of (gap_start, gap_end) tuples sorted chronologically.
    """
    if not overlay_timings:
        return [(0.0, total_duration_s)]

    sorted_ovs = sorted(overlay_timings, key=lambda o: o["start_s"])
    gaps: list[tuple[float, float]] = []

    # Gap before the first overlay
    if sorted_ovs[0]["start_s"] > 0.2:
        gaps.append((0.0, sorted_ovs[0]["start_s"]))

    # Gaps between consecutive overlays
    for i in range(len(sorted_ovs) - 1):
        end_current = sorted_ovs[i]["start_s"] + sorted_ovs[i]["duration_s"]
        start_next = sorted_ovs[i + 1]["start_s"]
        if start_next - end_current > 0.2:
            gaps.append((end_current, start_next))

    # Gap after the last overlay
    last_end = sorted_ovs[-1]["start_s"] + sorted_ovs[-1]["duration_s"]
    if total_duration_s - last_end > 0.2:
        gaps.append((last_end, total_duration_s))

    return gaps


def _time_in_gap(t_start: float, t_end: float,
                 gaps: list[tuple[float, float]]) -> bool:
    """Check whether the interval [t_start, t_end] falls mostly inside a gap."""
    mid = (t_start + t_end) / 2
    return any(g_start <= mid <= g_end for g_start, g_end in gaps)


def build_accent_overlay_clips(
    script: str,
    total_duration_s: float,
    accent_color: str = DEFAULT_ACCENT_COLOR,
    overlay_timings: list[dict] | None = None,
) -> list:
    """Parse accent phrases from script and create timed ImageClip overlays.

    Each accent phrase becomes a short text overlay that appears at evenly
    spaced intervals throughout the video.  When overlay timing information
    is provided, accent clips that fall during gaps between image overlays
    are promoted to the centre of the safe zone (where images normally
    appear) so there is always visual activity on screen.  Clips that
    coincide with an image overlay stay in the caption zone.

    Args:
        script: The full script text with **accent** markers.
        total_duration_s: Master video duration in seconds.
        accent_color: Hex color for accent text.
        overlay_timings: Optional list of dicts with ``start_s`` and
            ``duration_s`` for each image overlay.  Used to detect gaps.

    Returns:
        List of MoviePy ImageClip objects positioned and timed, ready for
        compositing.
    """
    phrases = parse_accent_phrases(script)
    if not phrases:
        return []

    clips = []
    count = len(phrases)

    # Space accent overlays evenly across the video duration
    # Each gets ~3 seconds on screen
    accent_duration = 1.8
    gap = max(0.5, (total_duration_s - accent_duration * count) / max(count, 1))
    current_time = gap / 2  # start after a brief intro

    # Pre-compute gap intervals between image overlays
    gaps = (
        _compute_gap_intervals(overlay_timings, total_duration_s)
        if overlay_timings
        else []
    )

    # Two possible Y positions
    caption_y = CANVAS_HEIGHT - CAPTION_ZONE - 60  # just above TikTok UI zone
    safe_zone_centre_y = (CANVAS_HEIGHT - CAPTION_ZONE) // 2  # image area

    for phrase_info in phrases:
        if current_time + accent_duration > total_duration_s:
            break

        # Render the text image
        img_path = render_accent_text_image(
            text=phrase_info["phrase"],
            accent_color=accent_color,
        )

        # Position in image area during gaps, caption zone otherwise
        in_gap = _time_in_gap(current_time, current_time + accent_duration, gaps)
        y_final = safe_zone_centre_y if in_gap else caption_y

        # Slide-up reveal: text rises 20px over 0.3s while fading in
        slide_distance = 20
        slide_duration = 0.3

        def _make_slide_pos(y_end, dist=slide_distance, dur=slide_duration):
            def pos(t):
                progress = min(t / dur, 1.0)
                # Ease-out: decelerates into final position
                eased = 1.0 - (1.0 - progress) ** 2
                y = y_end + dist * (1.0 - eased)
                return ("center", y)
            return pos

        clip = (
            ImageClip(img_path)
            .with_start(current_time)
            .with_duration(accent_duration)
            .with_position(_make_slide_pos(y_final))
            .with_effects([
                vfx.CrossFadeIn(0.3),
                vfx.CrossFadeOut(0.25),
            ])
        )
        clips.append(clip)

        logger.info(
            "Accent text '%s' at %.1fs–%.1fs (position=%s)",
            phrase_info["phrase"],
            current_time,
            current_time + accent_duration,
            "image_area" if in_gap else "caption_zone",
        )

        current_time += accent_duration + gap

    return clips


# ---------------------------------------------------------------------------
# Title text rendering (PIL-based → ImageClip)
# ---------------------------------------------------------------------------

TITLE_FONT_SIZE = 96
TITLE_MAX_WIDTH = 900  # max text block width (px)
TITLE_PADDING_X = 60
TITLE_PADDING_Y = 40
TITLE_BG_ALPHA = 160  # background pill opacity
TITLE_DEFAULT_DURATION = 2.5  # seconds on screen — faster hook turnover


def render_title_image(
    text: str,
    font_color: str = "#FFFFFF",
    bg_color: tuple = (10, 10, 20),
    output_path: str | None = None,
) -> str:
    """Render a title card as a transparent PNG with a pill background.

    The title is drawn in the chosen colour on a semi-transparent dark pill,
    centred for compositing onto the video canvas.

    Args:
        text: The title string to render.
        font_color: Hex colour for the title text.
        bg_color: RGB tuple for the pill background.
        output_path: Where to save the PNG.  Auto-generated if None.

    Returns:
        Path to the rendered PNG image.
    """
    font = _load_font(TITLE_FONT_SIZE, bold=True)

    # Measure text bounding box
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Word-wrap if text is too wide
    if text_w > TITLE_MAX_WIDTH:
        words = text.split()
        lines: list[str] = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            test_bbox = draw.textbbox((0, 0), test, font=font)
            if test_bbox[2] - test_bbox[0] <= TITLE_MAX_WIDTH:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        wrapped_text = "\n".join(lines)

        # Re-measure
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        wrapped_text = text

    # Create image with padding (pill shape)
    img_w = text_w + TITLE_PADDING_X * 2
    img_h = text_h + TITLE_PADDING_Y * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background
    pill_radius = min(28, img_h // 2)
    draw.rounded_rectangle(
        [(0, 0), (img_w - 1, img_h - 1)],
        radius=pill_radius,
        fill=(*bg_color, TITLE_BG_ALPHA),
    )

    # Draw text
    draw.multiline_text(
        (TITLE_PADDING_X, TITLE_PADDING_Y),
        wrapped_text,
        font=font,
        fill=font_color,
        align="center",
    )

    if output_path is None:
        Path("tmp").mkdir(exist_ok=True)
        output_path = tempfile.mktemp(suffix="_title.png", dir="tmp")

    img.save(output_path, "PNG")
    return output_path


def build_title_clip(
    title_text: str,
    total_duration_s: float,
    font_color: str = "#FFFFFF",
    duration_s: float = TITLE_DEFAULT_DURATION,
) -> ImageClip | None:
    """Create a timed ImageClip title overlay for the video intro.

    The title appears centred in the upper third of the safe zone,
    fades in and out, and displays for the given duration starting at
    the beginning of the video.

    Args:
        title_text: The title string to display.
        total_duration_s: Master video duration (used to clamp).
        font_color: Hex colour for the title text.
        duration_s: How long the title stays on screen.

    Returns:
        A MoviePy ImageClip positioned and timed, or None if title_text
        is empty.
    """
    if not title_text or not title_text.strip():
        return None

    duration_s = min(duration_s, total_duration_s - 0.5)
    if duration_s <= 0:
        return None

    img_path = render_title_image(text=title_text.strip(), font_color=font_color)

    # Position: centred horizontally, upper third of the safe zone
    # Safe zone = top to (CANVAS_HEIGHT - CAPTION_ZONE)
    safe_zone_h = CANVAS_HEIGHT - CAPTION_ZONE
    title_y = int(safe_zone_h * 0.18)  # ~18% down from top

    clip = (
        ImageClip(img_path)
        .with_start(0.0)  # instant hook — no delay
        .with_duration(duration_s)
        .with_position(("center", title_y))
        .with_effects([
            vfx.CrossFadeOut(0.4),
        ])
    )

    logger.info("Title clip '%s' at 0.0s–%.1fs (hard cut)", title_text, duration_s)
    return clip


# ---------------------------------------------------------------------------
# Section subtitle rendering (PIL-based → ImageClip)
# ---------------------------------------------------------------------------

SUBTITLE_FONT_SIZE = 64
SUBTITLE_MAX_WIDTH = 860  # slightly narrower than title for visual hierarchy
SUBTITLE_PADDING_X = 44
SUBTITLE_PADDING_Y = 28
SUBTITLE_BG_ALPHA = 140  # slightly more transparent than title pill


def render_subtitle_image(
    text: str,
    font_color: str = "#FFFFFF",
    bg_color: tuple = (10, 10, 20),
    output_path: str | None = None,
) -> str:
    """Render a section subtitle as a transparent PNG with a pill background.

    Similar to the title renderer but with smaller font and lighter pill
    to create a visual hierarchy: title > section subtitle > accent text.

    Args:
        text: The subtitle string to render.
        font_color: Hex colour for the subtitle text.
        bg_color: RGB tuple for the pill background.
        output_path: Where to save the PNG.  Auto-generated if None.

    Returns:
        Path to the rendered PNG image.
    """
    font = _load_font(SUBTITLE_FONT_SIZE, bold=True)

    # Measure text bounding box
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Word-wrap if text is too wide
    if text_w > SUBTITLE_MAX_WIDTH:
        words = text.split()
        lines: list[str] = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            test_bbox = draw.textbbox((0, 0), test, font=font)
            if test_bbox[2] - test_bbox[0] <= SUBTITLE_MAX_WIDTH:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        wrapped_text = "\n".join(lines)

        # Re-measure
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        wrapped_text = text

    # Create image with padding (pill shape)
    img_w = text_w + SUBTITLE_PADDING_X * 2
    img_h = text_h + SUBTITLE_PADDING_Y * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background
    pill_radius = min(24, img_h // 2)
    draw.rounded_rectangle(
        [(0, 0), (img_w - 1, img_h - 1)],
        radius=pill_radius,
        fill=(*bg_color, SUBTITLE_BG_ALPHA),
    )

    # Draw text
    draw.multiline_text(
        (SUBTITLE_PADDING_X, SUBTITLE_PADDING_Y),
        wrapped_text,
        font=font,
        fill=font_color,
        align="center",
    )

    if output_path is None:
        Path("tmp").mkdir(exist_ok=True)
        output_path = tempfile.mktemp(suffix="_subtitle.png", dir="tmp")

    img.save(output_path, "PNG")
    return output_path


def build_section_subtitle_clips(
    subtitles: list[str],
    overlay_timings: list[dict],
    total_duration_s: float,
    title_duration_s: float = TITLE_DEFAULT_DURATION,
    font_color: str = "#FFFFFF",
) -> list:
    """Create timed ImageClip overlays for section subtitles.

    Each subtitle corresponds to one image overlay section. The subtitle
    appears at the same vertical position as the main title (upper area)
    and is timed to match the overlay it belongs to.  The first subtitle
    is delayed until after the main title fades out.

    Args:
        subtitles: List of subtitle strings, one per overlay section.
        overlay_timings: List of dicts with ``start_s`` and ``duration_s``
            for each image overlay.
        total_duration_s: Master video duration in seconds.
        title_duration_s: How long the main title stays on screen.
            First subtitle starts after this.
        font_color: Hex colour for the subtitle text.

    Returns:
        List of MoviePy ImageClip objects positioned and timed.
    """
    if not subtitles or not overlay_timings:
        return []

    clips = []
    safe_zone_h = CANVAS_HEIGHT - CAPTION_ZONE
    subtitle_y = int(safe_zone_h * 0.18)  # same position as title

    for i, (sub_text, timing) in enumerate(zip(subtitles, overlay_timings)):
        if not sub_text or not sub_text.strip():
            continue

        start = timing["start_s"]
        duration = timing["duration_s"]

        # For the first overlay, delay subtitle until after the main title fades
        if i == 0:
            title_end = title_duration_s + 0.4  # title duration + fade-out
            if start + duration <= title_end:
                # Overlay ends before title fades — skip subtitle for this one
                continue
            # Shift start to after title fade, shorten duration accordingly
            start = title_end
            duration = timing["start_s"] + timing["duration_s"] - start

        # Ensure subtitle doesn't exceed video duration
        if start + duration > total_duration_s:
            duration = max(0, total_duration_s - start)
        if duration < 1.0:
            continue

        img_path = render_subtitle_image(
            text=sub_text.strip(),
            font_color=font_color,
        )

        clip = (
            ImageClip(img_path)
            .with_start(start)
            .with_duration(duration)
            .with_position(("center", subtitle_y))
            .with_effects([
                vfx.CrossFadeIn(0.4),
                vfx.CrossFadeOut(0.3),
            ])
        )
        clips.append(clip)

        logger.info(
            "Section subtitle '%s' at %.1fs–%.1fs",
            sub_text, start, start + duration,
        )

    return clips


PROGRESS_BAR_HEIGHT = 6  # pixels
PROGRESS_BAR_Y = 48  # below phone status bar / dynamic island


def build_progress_bar_clip(
    total_duration_s: float,
    color_rgb: tuple[int, int, int] = (255, 107, 53),
    height: int = PROGRESS_BAR_HEIGHT,
) -> VideoClip:
    """Create a thin progress bar that fills left-to-right over the video.

    The bar sits at the very top of the frame (y=0) and grows from
    width=0 to width=CANVAS_WIDTH over the full video duration.

    Args:
        total_duration_s: Video duration in seconds.
        color_rgb: RGB tuple for the bar color (typically the accent color).
        height: Bar height in pixels.

    Returns:
        A MoviePy VideoClip ready for compositing.
    """
    import numpy as np  # local import — only needed for frame generation

    def make_frame(t):
        frame = np.zeros((height, CANVAS_WIDTH, 3), dtype=np.uint8)
        filled_w = int((t / total_duration_s) * CANVAS_WIDTH)
        if filled_w > 0:
            frame[:, :filled_w, :] = color_rgb
        return frame

    return (
        VideoClip(make_frame, duration=total_duration_s)
        .with_position((0, PROGRESS_BAR_Y))
    )


def composite_video(background_path: str, audio_path: str,
                    overlay_sequence: list[dict], output_path: str,
                    darken: bool = True,
                    accent_text_clips: list | None = None,
                    title_clip: ImageClip | None = None,
                    section_subtitle_clips: list | None = None,
                    progress_bar_color: tuple[int, int, int] | None = None) -> str:
    """Composite overlays and audio onto the background video using MoviePy.

    Each overlay is an independent ImageClip layer with its own start time,
    duration, position, and fade effects.  MoviePy composites all layers
    in Python then encodes once via FFmpeg — no fragile filter chains.

    Args:
        background_path: Path to the Ken Burns background video.
        audio_path: Path to the ElevenLabs voiceover audio.
        overlay_sequence: List of dicts with keys:
            - image_path: processed overlay image path
            - start_s: start time in seconds
            - duration_s: how long the overlay is shown
        output_path: Path for the final output MP4.
        darken: Whether to dim the background for foreground separation.
        accent_text_clips: Optional list of pre-built MoviePy ImageClip
            objects for accent text overlays.  These are layered on top
            of everything else (highest z-order).
        section_subtitle_clips: Optional list of pre-built MoviePy ImageClip
            objects for section subtitles.  Layered between the title and
            accent text overlays.

    Returns:
        Tuple of (output_path, diagnostics_dict).
    """
    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    import traceback as _tb
    warnings = []
    print("[COMPOSITE] === Starting composite_video ===")
    print(f"[COMPOSITE] background={background_path}")
    print(f"[COMPOSITE] audio={audio_path}")
    print(f"[COMPOSITE] overlays={len(overlay_sequence)}, darken={darken}")
    print(f"[COMPOSITE] output={output_path}")

    for label, fpath in [("Background video", background_path),
                         ("Audio file", audio_path)]:
        if not Path(fpath).exists():
            raise RuntimeError(f"{label} not found: {fpath}")
    for i, ov in enumerate(overlay_sequence):
        if not Path(ov["image_path"]).exists():
            raise RuntimeError(f"Overlay image {i + 1} not found: {ov['image_path']}")
    print("[COMPOSITE] All input files validated OK")

    # ------------------------------------------------------------------
    # Build MoviePy clip layers
    # ------------------------------------------------------------------
    try:
        print("[COMPOSITE] Loading background video...")
        bg_clip = VideoFileClip(background_path)
        print(f"[COMPOSITE] Background loaded: {bg_clip.duration:.1f}s, "
              f"{bg_clip.size}")

        print("[COMPOSITE] Loading audio...")
        audio_clip = AudioFileClip(audio_path)
        print(f"[COMPOSITE] Audio loaded: {audio_clip.duration:.1f}s")
    except Exception as e:
        print(f"[COMPOSITE] FAILED loading inputs: {e}")
        print(_tb.format_exc())
        raise

    # Use audio duration as the master clock
    master_duration = audio_clip.duration
    bg_duration = bg_clip.duration

    try:
        if bg_duration < master_duration:
            n_loops = int(master_duration / bg_duration) + 1
            print(f"[COMPOSITE] Looping background {n_loops}x to cover "
                  f"{master_duration:.1f}s")
            from moviepy import concatenate_videoclips
            bg_clip = concatenate_videoclips([bg_clip] * n_loops)
        bg_clip = bg_clip.subclipped(0, master_duration)
        print(f"[COMPOSITE] Background trimmed to {master_duration:.1f}s")

        if darken:
            print("[COMPOSITE] Applying darken (MultiplyColor 0.85)...")
            bg_clip = bg_clip.with_effects([vfx.MultiplyColor(0.85)])
            print("[COMPOSITE] Darken applied")
    except Exception as e:
        print(f"[COMPOSITE] FAILED preparing background: {e}")
        print(_tb.format_exc())
        raise

    clips = [bg_clip]

    # Safe zone spans from top of canvas to CAPTION_ZONE above the bottom
    safe_zone_height = CANVAS_HEIGHT - CAPTION_ZONE  # 1620 px

    overlay_details = []
    for i, ov in enumerate(overlay_sequence):
        start = ov["start_s"]
        duration = ov["duration_s"]

        # Clamp overlay to not exceed master duration
        if start + duration > master_duration:
            duration = max(0, master_duration - start)
            warnings.append(
                f"Overlay #{i+1} clamped to {duration:.1f}s "
                f"(would exceed audio duration)"
            )
        if duration <= 0:
            warnings.append(f"Overlay #{i+1} skipped — starts after audio ends")
            continue

        try:
            # First overlay: hard-cut at t=0 (no fade-in) for an instant hook
            is_first = (i == 0)
            fade_in = 0.0 if is_first else FADE_IN_S

            print(f"[COMPOSITE] Building overlay #{i+1}: "
                  f"{Path(ov['image_path']).name}, "
                  f"start={start:.1f}s, dur={duration:.1f}s"
                  f"{' (HOOK — hard cut)' if is_first else ''}")

            # Centre the overlay vertically in the safe zone based on
            # its actual height so images of any size are properly placed.
            _img_for_size = Image.open(ov["image_path"])
            _img_h = _img_for_size.height
            _img_for_size.close()
            overlay_y = max(0, (safe_zone_height - _img_h) // 2)

            # Spring entrance: only resize during the 0.5s spring window,
            # then hold at native resolution for the remainder. This avoids
            # the expensive per-frame resize for the entire clip duration.
            if duration > SPRING_DURATION_S:
                spring_clip = (
                    ImageClip(ov["image_path"])
                    .with_duration(SPRING_DURATION_S)
                    .with_effects([vfx.Resize(lambda t: _spring_scale(t))])
                )
                static_clip = (
                    ImageClip(ov["image_path"])
                    .with_duration(duration - SPRING_DURATION_S)
                )
                from moviepy import concatenate_videoclips
                img_clip = concatenate_videoclips([spring_clip, static_clip])
                # Apply fade effects to the combined clip
                fade_effects = [vfx.CrossFadeOut(FADE_OUT_S)]
                if fade_in > 0:
                    fade_effects.insert(0, vfx.CrossFadeIn(fade_in))
                img_clip = (
                    img_clip
                    .with_start(start)
                    .with_position(("center", overlay_y))
                    .with_effects(fade_effects)
                )
            else:
                # Short clip: spring covers the full duration
                effects = [
                    vfx.Resize(lambda t, d=duration: _spring_scale(t, d)),
                    vfx.CrossFadeOut(FADE_OUT_S),
                ]
                if fade_in > 0:
                    effects.insert(0, vfx.CrossFadeIn(fade_in))
                img_clip = (
                    ImageClip(ov["image_path"])
                    .with_start(start)
                    .with_duration(duration)
                    .with_position(("center", overlay_y))
                    .with_effects(effects)
                )

            clips.append(img_clip)
            print(f"[COMPOSITE] Overlay #{i+1} added OK")
        except Exception as e:
            print(f"[COMPOSITE] FAILED building overlay #{i+1}: {e}")
            print(_tb.format_exc())
            warnings.append(f"Overlay #{i+1} failed to load: {e}")
            continue

        overlay_details.append({
            "index": i + 1,
            "image": Path(ov["image_path"]).name,
            "start_s": start,
            "end_s": round(start + duration, 2),
            "duration_s": round(duration, 2),
            "status": "composited",
        })

    # Timing sanity checks
    for i in range(1, len(overlay_sequence)):
        prev_end = overlay_sequence[i-1]["start_s"] + overlay_sequence[i-1]["duration_s"]
        curr_start = overlay_sequence[i]["start_s"]
        if curr_start < prev_end:
            warnings.append(
                f"Overlays #{i} and #{i+1} overlap: "
                f"#{i} ends at {prev_end:.2f}s, #{i+1} starts at {curr_start:.2f}s"
            )

    # ------------------------------------------------------------------
    # Add title overlay
    # ------------------------------------------------------------------
    if title_clip is not None:
        print("[COMPOSITE] Adding title clip")
        clips.append(title_clip)

    # ------------------------------------------------------------------
    # Add section subtitle clips (between title and accent text)
    # ------------------------------------------------------------------
    if section_subtitle_clips:
        print(f"[COMPOSITE] Adding {len(section_subtitle_clips)} section subtitle clips")
        clips.extend(section_subtitle_clips)

    # ------------------------------------------------------------------
    # Add accent text overlays (highest z-order — on top of everything)
    # ------------------------------------------------------------------
    if accent_text_clips:
        print(f"[COMPOSITE] Adding {len(accent_text_clips)} accent text clips")
        clips.extend(accent_text_clips)

    # ------------------------------------------------------------------
    # Add progress bar (topmost z-order — above everything)
    # ------------------------------------------------------------------
    if progress_bar_color is not None:
        progress_clip = build_progress_bar_clip(
            total_duration_s=master_duration,
            color_rgb=progress_bar_color,
        )
        clips.append(progress_clip)
        print(f"[COMPOSITE] Progress bar added (color={progress_bar_color})")

    # ------------------------------------------------------------------
    # Composite and render
    # ------------------------------------------------------------------
    print(f"[COMPOSITE] Creating CompositeVideoClip with {len(clips)} layers...")
    try:
        final = CompositeVideoClip(clips, size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        final = final.with_audio(audio_clip)
        final = final.subclipped(0, master_duration)
        print(f"[COMPOSITE] CompositeVideoClip built: "
              f"{final.duration:.1f}s, {final.size}")
    except Exception as e:
        print(f"[COMPOSITE] FAILED building composite: {e}")
        print(_tb.format_exc())
        raise

    logger.info(
        "MoviePy compositing %d overlays (%.1fs), output=%s",
        len(overlay_sequence), master_duration, output_path,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    print(f"[COMPOSITE] Starting write_videofile to {output_path}...")
    try:
        final.write_videofile(
            output_path,
            codec=CODEC,
            audio_codec="aac",
            audio_bitrate="192k",
            fps=30,
            threads=4,
            preset="ultrafast",
            ffmpeg_params=["-crf", CRF, "-pix_fmt", "yuv420p",
                           "-movflags", "faststart"],
            logger=None,
        )
        print(f"[COMPOSITE] write_videofile completed OK")
    except Exception as e:
        print(f"[COMPOSITE] FAILED write_videofile: {e}")
        print(_tb.format_exc())
        raise
    finally:
        # Clean up MoviePy resources
        print("[COMPOSITE] Closing MoviePy clips...")
        final.close()
        bg_clip.close()
        audio_clip.close()

        # Clean up temp PNGs generated by accent text and title renderers.
        # These use tempfile.mktemp() patterns in tmp/ and accumulate on
        # every assembly run if not cleaned up.
        _tmp_dir = Path("tmp")
        if _tmp_dir.exists():
            _cleaned = 0
            for pattern in ("tmp*_title.png", "tmp*_subtitle.png"):
                for png in _tmp_dir.glob(pattern):
                    try:
                        png.unlink()
                        _cleaned += 1
                    except OSError:
                        pass
            for png in _tmp_dir.glob("tmp*.png"):
                # Only remove files that look like tempfile-generated accent PNGs
                # (tempfile.mktemp produces names like tmpXXXXXXXX.png)
                if png.stem.startswith("tmp") and "_processed" not in png.name:
                    try:
                        png.unlink()
                        _cleaned += 1
                    except OSError:
                        pass
            if _cleaned:
                print(f"[COMPOSITE] Cleaned up {_cleaned} temp PNG(s)")

    output_size = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"[COMPOSITE] Output file: {output_size:.1f} MB")
    print("[COMPOSITE] === composite_video complete ===")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    diagnostics = {
        "engine": "moviepy",
        "overlay_count": len(overlay_sequence),
        "background": {
            "file": Path(background_path).name,
            "duration_s": round(bg_duration, 2),
        },
        "audio": {
            "file": Path(audio_path).name,
            "duration_s": round(master_duration, 2),
        },
        "overlay_timings": overlay_details,
        "darken": darken,
        "title_overlay": title_clip is not None,
        "section_subtitles": len(section_subtitle_clips) if section_subtitle_clips else 0,
        "warnings": warnings,
        "success": True,
    }

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
