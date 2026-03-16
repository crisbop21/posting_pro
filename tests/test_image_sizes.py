"""Test overlay image processing with various image sizes."""

import os
import sys
import traceback
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from PIL import Image
from utils.image_utils import process_overlay
from tests.helpers import mock_state

# ── Test image definitions ──────────────────────────────────────
TEST_IMAGES = {
    "tiny_100x100": (100, 100),
    "normal_800x600": (800, 600),
    "large_4000x3000": (4000, 3000),
    "very_large_8000x6000": (8000, 6000),
    "tall_portrait_400x2000": (400, 2000),
    "wide_panorama_3000x200": (3000, 200),
}

TMP_DIR = PROJECT_ROOT / "tmp"
TMP_DIR.mkdir(exist_ok=True)


def generate_test_images() -> dict[str, str]:
    """Create test images of various sizes, return name -> path mapping."""
    paths = {}
    for name, (w, h) in TEST_IMAGES.items():
        path = TMP_DIR / f"test_{name}.png"
        img = Image.new("RGBA", (w, h), (50, 100, 200, 255))
        # Draw a simple cross so content is visible
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.line([(0, 0), (w, h)], fill=(255, 255, 255, 200), width=3)
        draw.line([(w, 0), (0, h)], fill=(255, 255, 255, 200), width=3)
        draw.text((10, 10), f"{w}x{h}", fill=(255, 255, 255))
        img.save(str(path))
        paths[name] = str(path)
        print(f"  Created {name}: {w}x{h} -> {path} ({path.stat().st_size:,} bytes)")
    return paths


def test_process_overlay(paths: dict[str, str]) -> dict[str, str]:
    """Run process_overlay on each test image. Return name -> processed path."""
    results = {}
    print("\n--- process_overlay() results ---")
    for name, path in paths.items():
        w, h = TEST_IMAGES[name]
        try:
            processed_path = process_overlay(path)
            processed = Path(processed_path)
            if not processed.exists():
                print(f"  FAIL  {name} ({w}x{h}): output file does not exist")
                continue

            # Check output dimensions and file size
            with Image.open(processed_path) as out_img:
                ow, oh = out_img.size
                file_size = processed.stat().st_size
                print(f"  OK    {name} ({w}x{h}) -> ({ow}x{oh}), "
                      f"file size: {file_size:,} bytes")
                results[name] = processed_path

        except Exception as e:
            print(f"  FAIL  {name} ({w}x{h}): {type(e).__name__}: {e}")
            traceback.print_exc()

    return results


def test_assembly(processed_paths: dict[str, str]):
    """Try to run the assembly step with test overlays.

    This is expected to fail (no ElevenLabs key), but we want to see
    whether it fails cleanly or crashes silently.
    """
    print("\n--- Assembly step test ---")

    # Use first 4 processed images (or all if fewer)
    overlay_list = list(processed_paths.values())[:4]
    # Pad to 4 if needed by repeating
    while len(overlay_list) < 4:
        overlay_list.append(overlay_list[0])

    state = mock_state(up_to_step=5)
    state["overlay_sequence"] = overlay_list

    # Ensure background video exists
    from utils.demo import _ensure_placeholder_video
    bg_path = _ensure_placeholder_video()
    state["background_video_path"] = bg_path

    print(f"  Background: {bg_path}")
    print(f"  Overlays: {len(overlay_list)} images")
    print(f"  Script length: {len(state.get('script', ''))} chars")

    try:
        from pipeline.assemble import run
        result = run(state)
        print(f"  UNEXPECTED SUCCESS: {result.get('final_video_path')}")
    except RuntimeError as e:
        print(f"  EXPECTED FAILURE (RuntimeError): {e}")
        print("  -> Assembly gives a CLEAR error message.")
    except Exception as e:
        print(f"  UNEXPECTED ERROR ({type(e).__name__}): {e}")
        traceback.print_exc()
        print("  -> Assembly does NOT give a clear error — it crashes with "
              "an unhandled exception.")


def main():
    print("=" * 60)
    print("Test: Overlay image processing with various sizes")
    print("=" * 60)

    print("\n--- Generating test images ---")
    paths = generate_test_images()

    processed = test_process_overlay(paths)

    print(f"\n--- Summary ---")
    print(f"  Total test images:       {len(TEST_IMAGES)}")
    print(f"  Successfully processed:  {len(processed)}")
    failed = set(TEST_IMAGES.keys()) - set(processed.keys())
    if failed:
        print(f"  Failed:                  {', '.join(sorted(failed))}")
    else:
        print(f"  Failed:                  none")

    if processed:
        test_assembly(processed)

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
