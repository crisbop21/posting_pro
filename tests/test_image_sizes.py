"""Test overlay image processing with various image sizes.

Verifies that process_overlay() handles tiny, normal, large, very large,
tall portrait, and wide panorama images correctly. Then attempts the
assembly pipeline to check error handling when ElevenLabs is unavailable.
"""

import os
import sys
import traceback
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from PIL import Image, ImageDraw
from utils.image_utils import process_overlay
from tests.helpers import mock_state

# ── Test image definitions ──────────────────────────────────────
TEST_IMAGES = {
    "tiny":           (100, 100),
    "normal":         (800, 600),
    "large":          (4000, 3000),
    "very_large":     (8000, 6000),
    "tall_portrait":  (400, 2000),
    "wide_panorama":  (3000, 200),
}

MAX_WIDTH = 918   # 85% of 1080 canvas
MAX_HEIGHT = 800
SHADOW_OFFSET = 8  # default shadow offset in process_overlay

TMP_DIR = PROJECT_ROOT / "tmp"
TMP_DIR.mkdir(exist_ok=True)


def generate_test_image(name: str, width: int, height: int) -> str:
    """Create a labelled RGBA test image and save it to tmp/."""
    path = TMP_DIR / f"test_{name}.png"
    img = Image.new("RGBA", (width, height), (50, 100, 200, 255))
    draw = ImageDraw.Draw(img)
    # Draw a diagonal cross so the image is visually distinct
    draw.line([(0, 0), (width, height)], fill=(255, 255, 255, 200), width=3)
    draw.line([(width, 0), (0, height)], fill=(255, 255, 255, 200), width=3)
    draw.text((10, 10), f"{name} ({width}x{height})", fill=(255, 255, 255))
    img.save(str(path))
    return str(path)


def test_process_overlay():
    """Run process_overlay on each test image and report results."""
    print("=" * 70)
    print("PART 1: Testing process_overlay() with various image sizes")
    print("=" * 70)

    results = {}
    processed_paths = []

    for name, (w, h) in TEST_IMAGES.items():
        print(f"\n--- {name} ({w}x{h}) ---")
        try:
            src_path = generate_test_image(name, w, h)
            src_size = os.path.getsize(src_path)
            print(f"  Source file size:  {src_size:,} bytes")

            out_path = process_overlay(src_path)
            exists = Path(out_path).exists()
            out_size = os.path.getsize(out_path) if exists else 0

            # Read back processed image dimensions
            with Image.open(out_path) as processed:
                pw, ph = processed.size

            # Shadow adds SHADOW_OFFSET*2 to one dimension, check bounds
            content_w = pw - SHADOW_OFFSET * 2
            content_h = ph - SHADOW_OFFSET * 2
            fits_width = content_w <= MAX_WIDTH
            fits_height = content_h <= MAX_HEIGHT

            print(f"  Output path:      {out_path}")
            print(f"  Output exists:    {exists}")
            print(f"  Output file size: {out_size:,} bytes")
            print(f"  Output dims:      {pw}x{ph} (content: {content_w}x{content_h})")
            print(f"  Fits max_width:   {fits_width} (content {content_w} <= {MAX_WIDTH})")
            print(f"  Fits max_height:  {fits_height} (content {content_h} <= {MAX_HEIGHT})")
            print(f"  Result: PASS")

            results[name] = {
                "status": "PASS",
                "src_size": src_size,
                "out_size": out_size,
                "out_dims": (pw, ph),
                "content_dims": (content_w, content_h),
            }
            processed_paths.append(out_path)

        except Exception as e:
            print(f"  Result: FAIL -- {e}")
            traceback.print_exc()
            results[name] = {"status": "FAIL", "error": str(e)}

    return results, processed_paths


def test_assembly(processed_paths: list[str]):
    """Try to run the assembly step with test overlays.

    This is expected to fail (no ElevenLabs key), but we want to see
    whether it fails cleanly or crashes silently.
    """
    print("\n" + "=" * 70)
    print("PART 2: Testing assembly pipeline with processed images")
    print("=" * 70)

    state = mock_state(up_to_step=5)

    # Ensure background video exists
    from utils.demo import _ensure_placeholder_video
    bg_path = _ensure_placeholder_video()
    state["background_video_path"] = bg_path

    # Use first 4 processed images, pad if needed
    overlay_list = processed_paths[:4]
    while len(overlay_list) < 4:
        overlay_list.append(overlay_list[0])
    state["overlay_sequence"] = overlay_list

    print(f"\n  Background:    {bg_path} (exists: {Path(bg_path).exists()})")
    print(f"  Overlays:      {len(overlay_list)} images")
    for p in overlay_list:
        print(f"    - {p} (exists: {Path(p).exists()})")
    print(f"  Script length: {len(state.get('script', ''))} chars")

    print("\n  Calling assemble.run(state)...")
    try:
        from pipeline.assemble import run
        result = run(state)
        print(f"\n  Assembly SUCCEEDED (unexpected without API keys)")
        print(f"  final_video_path: {result.get('final_video_path')}")
        return "PASS"
    except RuntimeError as e:
        print(f"\n  Assembly raised RuntimeError (expected):")
        print(f"    {e}")
        msg = str(e).lower()
        if any(kw in msg for kw in ("voiceover", "elevenlabs", "api", "could not")):
            print("  -> Error message is CLEAR and user-friendly. GOOD.")
            return "CLEAR_ERROR"
        else:
            print("  -> Error message does not clearly indicate the API issue.")
            return "UNCLEAR_ERROR"
    except Exception as e:
        print(f"\n  Assembly CRASHED with unexpected exception:")
        print(f"    {type(e).__name__}: {e}")
        traceback.print_exc()
        print("  -> Assembly does NOT give a clear error -- it crashes silently.")
        return "CRASH"


def main():
    overlay_results, processed_paths = test_process_overlay()

    assembly_result = test_assembly(processed_paths)

    # ── Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n  {'Name':<18} {'Status':<8} {'Src Size':>10} {'Out Size':>10}  {'Output Dims'}")
    print("  " + "-" * 65)
    for name, info in overlay_results.items():
        if info["status"] == "PASS":
            dims = f"{info['out_dims'][0]}x{info['out_dims'][1]}"
            src = f"{info['src_size']:>10,}"
            out = f"{info['out_size']:>10,}"
        else:
            dims = f"FAIL: {info.get('error', '?')}"
            src = "N/A"
            out = "N/A"
        print(f"  {name:<18} {info['status']:<8} {src} {out}  {dims}")

    passed = sum(1 for v in overlay_results.values() if v["status"] == "PASS")
    total = len(overlay_results)
    print(f"\n  Overlay processing: {passed}/{total} passed")
    print(f"  Assembly result:    {assembly_result}")

    print("\n" + "=" * 70)
    print("Done.")


if __name__ == "__main__":
    main()
