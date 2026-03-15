"""Ken Burns renderer, color grading, cropping, accent text renderer, and MoviePy video compositor."""

import json
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
    VideoFileClip,
    vfx,
)

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


# ---------------------------------------------------------------------------
# Accent text rendering (PIL-based)
# ---------------------------------------------------------------------------

# Default accent colour — overridden by the visual style's accent_color
DEFAULT_ACCENT_COLOR = "#FF6B35"
ACCENT_FONT_SIZE = 64
ACCENT_FONT_BOLD_SIZE = 68
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


def build_accent_overlay_clips(
    script: str,
    total_duration_s: float,
    accent_color: str = DEFAULT_ACCENT_COLOR,
) -> list:
    """Parse accent phrases from script and create timed ImageClip overlays.

    Each accent phrase becomes a short text overlay that appears in the
    caption zone (bottom 200 px) at evenly spaced intervals throughout the
    video. They fade in/out and display for 2.5–3.5 seconds each.

    Args:
        script: The full script text with **accent** markers.
        total_duration_s: Master video duration in seconds.
        accent_color: Hex color for accent text.

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
    accent_duration = 3.0
    gap = max(0.5, (total_duration_s - accent_duration * count) / max(count, 1))
    current_time = gap / 2  # start after a brief intro

    # Caption zone: bottom 200 px, center the text vertically in it
    caption_y = CANVAS_HEIGHT - CAPTION_ZONE + 30  # 30px below top of caption zone

    for phrase_info in phrases:
        if current_time + accent_duration > total_duration_s:
            break

        # Render the text image
        img_path = render_accent_text_image(
            text=phrase_info["phrase"],
            accent_color=accent_color,
        )

        clip = (
            ImageClip(img_path)
            .with_start(current_time)
            .with_duration(accent_duration)
            .with_position(("center", caption_y))
            .with_effects([
                vfx.CrossFadeIn(0.3),
                vfx.CrossFadeOut(0.25),
            ])
        )
        clips.append(clip)

        logger.info(
            "Accent text '%s' at %.1fs–%.1fs",
            phrase_info["phrase"],
            current_time,
            current_time + accent_duration,
        )

        current_time += accent_duration + gap

    return clips


# ---------------------------------------------------------------------------
# Title text rendering (PIL-based → ImageClip)
# ---------------------------------------------------------------------------

TITLE_FONT_SIZE = 80
TITLE_MAX_WIDTH = 900  # max text block width (px)
TITLE_PADDING_X = 60
TITLE_PADDING_Y = 40
TITLE_BG_ALPHA = 160  # background pill opacity
TITLE_DEFAULT_DURATION = 4.0  # seconds on screen


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
        .with_start(0.3)  # slight delay after video start
        .with_duration(duration_s)
        .with_position(("center", title_y))
        .with_effects([
            vfx.CrossFadeIn(0.5),
            vfx.CrossFadeOut(0.4),
        ])
    )

    logger.info("Title clip '%s' at 0.3s–%.1fs", title_text, 0.3 + duration_s)
    return clip


def composite_video(background_path: str, audio_path: str,
                    overlay_sequence: list[dict], output_path: str,
                    darken: bool = True,
                    accent_text_clips: list | None = None,
                    title_clip: ImageClip | None = None) -> str:
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

    # Vertical centre of the safe zone (above the 200 px caption area)
    safe_zone_centre_y = (CANVAS_HEIGHT - CAPTION_ZONE) // 2

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
            print(f"[COMPOSITE] Building overlay #{i+1}: "
                  f"{Path(ov['image_path']).name}, "
                  f"start={start:.1f}s, dur={duration:.1f}s")
            img_clip = (
                ImageClip(ov["image_path"])
                .with_start(start)
                .with_duration(duration)
                .with_position(("center", safe_zone_centre_y))
                .with_effects([
                    vfx.CrossFadeIn(FADE_IN_S),
                    vfx.CrossFadeOut(FADE_OUT_S),
                ])
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
    # Add title overlay (above accent text)
    # ------------------------------------------------------------------
    if title_clip is not None:
        print("[COMPOSITE] Adding title clip")
        clips.append(title_clip)

    # ------------------------------------------------------------------
    # Add accent text overlays (highest z-order — on top of everything)
    # ------------------------------------------------------------------
    if accent_text_clips:
        print(f"[COMPOSITE] Adding {len(accent_text_clips)} accent text clips")
        clips.extend(accent_text_clips)

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
