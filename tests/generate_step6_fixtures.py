"""Generate test assets for running Step 6 (video assembly) in isolation.

Usage:
    python -m tests.generate_step6_fixtures

Creates:
    tmp/background_cinematic.mp4   — minimal valid MP4 (colour bars, no audio)
    tmp/overlay_0_processed.png    — 4 test overlay images (918×600 with labels)
    tmp/overlay_1_processed.png
    tmp/overlay_2_processed.png
    tmp/overlay_3_processed.png

These match the paths expected by mock_state(up_to_step=5).
"""

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ── Directories ──────────────────────────────────────────────────

TMP = Path("tmp")
TMP.mkdir(exist_ok=True)


# ── Overlay images ───────────────────────────────────────────────

OVERLAY_WIDTH = 918   # 85% of 1080
OVERLAY_HEIGHT = 600

OVERLAY_LABELS = [
    "Federal Reserve",
    "AI Microchip",
    "Bitcoin Graph",
    "Trading Floor",
]

OVERLAY_COLOURS = [
    (30, 60, 120),    # dark blue
    (20, 100, 60),    # dark green
    (140, 90, 20),    # gold
    (100, 30, 30),    # dark red
]


def _generate_overlay(index: int) -> str:
    """Create a labelled test overlay PNG and return its path."""
    img = Image.new("RGBA", (OVERLAY_WIDTH, OVERLAY_HEIGHT), (*OVERLAY_COLOURS[index], 220))
    draw = ImageDraw.Draw(img)

    # Draw a border
    draw.rectangle(
        [4, 4, OVERLAY_WIDTH - 5, OVERLAY_HEIGHT - 5],
        outline=(255, 255, 255, 180),
        width=3,
    )

    # Draw label text
    label = f"Overlay {index}: {OVERLAY_LABELS[index]}"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((OVERLAY_WIDTH - tw) // 2, (OVERLAY_HEIGHT - th) // 2),
        label,
        fill=(255, 255, 255),
        font=font,
    )

    path = str(TMP / f"overlay_{index}_processed.png")
    img.save(path)
    return path


# ── Minimal MP4 ──────────────────────────────────────────────────
# Generates a tiny valid MP4 using raw ftyp + mdat + moov atoms.
# This won't play as a real video but is a structurally valid file
# that FFmpeg can probe. For actual rendering tests, install ffmpeg
# and use the --real flag.

def _write_mp4_box(f, box_type: bytes, data: bytes):
    """Write an MP4 box (size + type + data)."""
    f.write(struct.pack(">I", len(data) + 8))
    f.write(box_type)
    f.write(data)


def _generate_minimal_mp4() -> str:
    """Create a minimal valid MP4 file for testing."""
    path = str(TMP / "background_cinematic.mp4")

    with open(path, "wb") as f:
        # ftyp box
        ftyp_data = b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41"
        _write_mp4_box(f, b"ftyp", ftyp_data)

        # mdat box (empty media data)
        _write_mp4_box(f, b"mdat", b"\x00" * 64)

        # moov box (minimal — just enough structure)
        mvhd = struct.pack(
            ">I4sII",
            108,      # size
            b"mvhd",
            0,        # version + flags
            0,        # creation_time
        ) + b"\x00" * 96
        moov_data = mvhd
        _write_mp4_box(f, b"moov", moov_data)

    return path


def _generate_real_background() -> str:
    """Create a real 5-second background video using Pillow frames + ffmpeg.

    Falls back to minimal MP4 if ffmpeg is not available.
    """
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        print("  ffmpeg not found — using minimal MP4 stub")
        return _generate_minimal_mp4()

    # Generate a sequence of colour-gradient frames
    frames_dir = TMP / "bg_frames"
    frames_dir.mkdir(exist_ok=True)

    fps = 10
    duration_s = 5
    total_frames = fps * duration_s

    for i in range(total_frames):
        t = i / total_frames
        r = int(20 + 40 * t)
        g = int(30 + 20 * t)
        b = int(80 + 40 * t)
        img = Image.new("RGB", (1080, 1920), (r, g, b))
        draw = ImageDraw.Draw(img)
        draw.text((440, 940), f"BG {i:03d}", fill=(255, 255, 255))
        img.save(frames_dir / f"frame_{i:04d}.png")

    path = str(TMP / "background_cinematic.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-c:v", "libx264",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-t", str(duration_s),
            path,
        ],
        capture_output=True,
        timeout=60,
    )

    # Clean up frames
    for f in frames_dir.glob("*.png"):
        f.unlink()
    frames_dir.rmdir()

    return path


# ── Main ─────────────────────────────────────────────────────────

def generate_all(real_video: bool = False):
    """Generate all Step 6 test fixtures.

    Args:
        real_video: If True and ffmpeg is available, generate a real
                    5-second MP4 background. Otherwise use a minimal stub.
    """
    print("Generating Step 6 test fixtures...")

    # Overlays
    for i in range(4):
        p = _generate_overlay(i)
        print(f"  Created {p}")

    # Background video
    if real_video:
        p = _generate_real_background()
    else:
        p = _generate_minimal_mp4()
    print(f"  Created {p}")

    print("\nDone. You can now run the app and jump to Step 6.")
    print("Use:  streamlit run app.py -- --debug-step6")


if __name__ == "__main__":
    import sys
    real = "--real" in sys.argv
    generate_all(real_video=real)
