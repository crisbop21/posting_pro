"""Ken Burns renderer and FFmpeg video compositor."""

import subprocess
import tempfile
from pathlib import Path

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
                     fps: int = 30) -> str:
    """Generate a Ken Burns pan-and-zoom video from a still image.

    Args:
        image_path: Path to the source image.
        duration_s: Duration of the output video in seconds.
        output_path: Path for the output MP4 file.
        zoom_start: Starting zoom factor.
        zoom_end: Ending zoom factor.
        fps: Frames per second.

    Returns:
        Path to the rendered video file.
    """
    total_frames = int(duration_s * fps)

    # FFmpeg zoompan filter for smooth Ken Burns effect
    # zoompan: z increases linearly from zoom_start to zoom_end
    # x and y pan slowly from center
    zp_filter = (
        f"zoompan="
        f"z='if(eq(on,1),{zoom_start},{zoom_start}+(on-1)*{(zoom_end - zoom_start) / max(total_frames, 1)})':"
        f"d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:"
        f"fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-vf", zp_filter,
        "-c:v", CODEC,
        "-crf", CRF,
        "-pix_fmt", "yuv420p",
        "-movflags", "faststart",
        "-t", str(duration_s),
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {stderr}")
    return output_path


def composite_video(background_path: str, audio_path: str,
                    overlay_sequence: list[dict], output_path: str) -> str:
    """Composite overlays and audio onto the background video.

    Args:
        background_path: Path to the Ken Burns background video.
        audio_path: Path to the ElevenLabs voiceover audio.
        overlay_sequence: List of dicts with keys:
            - image_path: processed overlay image path
            - start_s: start time in seconds
            - duration_s: how long the overlay is shown
        output_path: Path for the final output MP4.

    Returns:
        Path to the composited video file.
    """
    # Build the FFmpeg filter complex for overlays
    inputs = ["-i", background_path, "-i", audio_path]
    filter_parts = []
    prev_label = "0:v"

    for i, overlay in enumerate(overlay_sequence):
        inputs.extend(["-i", overlay["image_path"]])
        input_idx = i + 2  # 0=bg, 1=audio, 2+=overlays

        start = overlay["start_s"]
        duration = overlay["duration_s"]
        end = start + duration

        # Position overlay centred horizontally, above the caption zone
        y_pos = (CANVAS_HEIGHT - CAPTION_ZONE) // 2
        x_pos = f"(W-w)/2"

        # Fade in/out with enable window
        fade_filter = (
            f"[{input_idx}:v]format=rgba,"
            f"fade=t=in:st={start}:d={FADE_IN_S}:alpha=1,"
            f"fade=t=out:st={end - FADE_OUT_S}:d={FADE_OUT_S}:alpha=1"
            f"[ov{i}]"
        )
        filter_parts.append(fade_filter)

        overlay_filter = (
            f"[{prev_label}][ov{i}]overlay={x_pos}:y={y_pos}:"
            f"enable='between(t,{start},{end})'[tmp{i}]"
        )
        filter_parts.append(overlay_filter)
        prev_label = f"tmp{i}"

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-map", "1:a",
        "-c:v", CODEC,
        "-crf", CRF,
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "faststart",
        "-shortest",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True, timeout=240)
    return output_path


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
