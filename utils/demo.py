"""Demo output loader — fills a single step with fixture data to skip API calls."""

import json
import shutil
import struct
import subprocess
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TMP_DIR = Path("tmp")
OUTPUTS_DIR = Path("outputs")


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def _load_json_fixture(name: str):
    return json.loads(_load_fixture(name))


def _ensure_placeholder_video() -> str:
    """Generate a minimal placeholder background video if it doesn't exist."""
    TMP_DIR.mkdir(exist_ok=True)
    path = TMP_DIR / "background_cinematic.mp4"

    if path.exists():
        return str(path)

    # Try ffmpeg first for a real playable video
    if shutil.which("ffmpeg"):
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "color=c=0x1e3c78:size=1080x1920:duration=5:rate=10",
                    "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
                    str(path),
                ],
                capture_output=True,
                timeout=30,
            )
            if path.exists():
                return str(path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: minimal valid MP4 structure
    with open(path, "wb") as f:
        ftyp_data = b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41"
        f.write(struct.pack(">I", len(ftyp_data) + 8))
        f.write(b"ftyp")
        f.write(ftyp_data)

        mdat = b"\x00" * 64
        f.write(struct.pack(">I", len(mdat) + 8))
        f.write(b"mdat")
        f.write(mdat)

        mvhd = struct.pack(">I4sII", 108, b"mvhd", 0, 0) + b"\x00" * 96
        f.write(struct.pack(">I", len(mvhd) + 8))
        f.write(b"moov")
        f.write(mvhd)

    return str(path)


def _ensure_placeholder_overlays() -> list:
    """Generate minimal placeholder overlay PNGs if they don't exist."""
    TMP_DIR.mkdir(exist_ok=True)

    paths = []
    colours = [
        (30, 60, 120),
        (20, 100, 60),
        (140, 90, 20),
        (100, 30, 30),
    ]
    labels = ["Federal Reserve", "AI Microchip", "Bitcoin Graph", "Trading Floor"]

    for i in range(4):
        p = TMP_DIR / f"overlay_{i}_processed.png"
        if not p.exists():
            try:
                from PIL import Image, ImageDraw, ImageFont

                img = Image.new("RGBA", (918, 600), (*colours[i], 220))
                draw = ImageDraw.Draw(img)
                draw.rectangle([4, 4, 913, 595], outline=(255, 255, 255, 180), width=3)
                label = f"DEMO Overlay {i}: {labels[i]}"
                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32
                    )
                except OSError:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), label, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text(
                    ((918 - tw) // 2, (600 - th) // 2),
                    label,
                    fill=(255, 255, 255),
                    font=font,
                )
                img.save(str(p))
            except ImportError:
                # Pillow not available — write a minimal 1x1 PNG
                _write_minimal_png(str(p))
        paths.append(str(p))

    return paths


def _write_minimal_png(path: str):
    """Write a minimal valid 1x1 white PNG (no Pillow needed)."""
    import zlib

    raw_row = b"\x00\xff\xff\xff"
    compressed = zlib.compress(raw_row)

    def _chunk(chunk_type, data):
        import struct as s
        c = chunk_type + data
        return s.pack(">I", len(data)) + c + s.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)))
        f.write(_chunk(b"IDAT", compressed))
        f.write(_chunk(b"IEND", b""))


def _ensure_placeholder_final_video() -> str:
    """Create a placeholder final video in outputs/."""
    OUTPUTS_DIR.mkdir(exist_ok=True)
    path = OUTPUTS_DIR / "demo-output-20260313.mp4"

    if not path.exists():
        # Reuse the background placeholder as the "final" video
        bg = _ensure_placeholder_video()
        shutil.copy2(bg, str(path))

    return str(path)


# ── Per-step demo data ──────────────────────────────────────────

def load_demo_step1() -> dict:
    """Demo data for Step 1: Gather Data."""
    return {
        "topic_mode": "live_news",
        "custom_topic": "",
        "raw_data": _load_json_fixture("marketaux_response.json")["data"],
        "step1_demo": True,
    }


def load_demo_step2() -> dict:
    """Demo data for Step 2: Fact-Check."""
    fc = _load_json_fixture("factcheck_response.json")
    return {
        "cleaned_data": fc["cleaned_data"],
        "factcheck_flags": fc["flags"],
        "step2_demo": True,
    }


def load_demo_step3() -> dict:
    """Demo data for Step 3: Write Script."""
    script = _load_fixture("script_response.txt")
    wc = len(script.split())
    return {
        "script": script,
        "word_count": wc,
        "estimated_duration_s": round((wc / 150) * 60),
        "step3_demo": True,
    }


def load_demo_step4() -> dict:
    """Demo data for Step 4: Generate Background."""
    bg_path = _ensure_placeholder_video()
    return {
        "visual_style": "cinematic",
        "background_video_path": bg_path,
        "step4_demo": True,
    }


def load_demo_step5() -> dict:
    """Demo data for Step 5: Source Images."""
    overlays = _ensure_placeholder_overlays()
    return {
        "overlay_sequence": overlays,
        "overlay_sources": ["pexels"] * len(overlays),
        "step5_demo": True,
    }


def load_demo_step6() -> dict:
    """Demo data for Step 6: Assemble Video."""
    video_path = _ensure_placeholder_final_video()
    return {
        "final_video_path": video_path,
        "assembly_running": False,
        "assembly_done": False,
        "assembly_error": None,
        "assembly_started_at": None,
        "step6_demo": True,
    }


# Map step numbers to loaders
DEMO_LOADERS = {
    1: load_demo_step1,
    2: load_demo_step2,
    3: load_demo_step3,
    4: load_demo_step4,
    5: load_demo_step5,
    6: load_demo_step6,
}


def load_demo(step: int) -> dict:
    """Load demo output for a specific step.

    Returns a dict of state keys to set. Also sets the step's
    approval flag and demo flag to True.
    """
    if step not in DEMO_LOADERS:
        raise ValueError(f"No demo data for step {step}")

    data = DEMO_LOADERS[step]()
    data[f"step{step}_approved"] = True
    return data
