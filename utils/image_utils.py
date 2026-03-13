"""Pexels image search, download, and processing utilities."""

import tempfile
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

MAX_RETRIES = 2
PEXELS_BASE_URL = "https://api.pexels.com/v1/search"


def search_pexels(session: requests.Session, query: str, per_page: int = 4,
                  orientation: str = "landscape") -> list[dict]:
    """Search Pexels and return a list of photo dicts.

    Args:
        session: Authenticated requests.Session (from api_clients.pexels).
        query: Short, specific search query.
        per_page: Number of results to return.
        orientation: Image orientation filter.

    Returns:
        List of photo dicts with keys: id, url, src, photographer.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(
                PEXELS_BASE_URL,
                params={
                    "query": query,
                    "per_page": per_page,
                    "orientation": orientation,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "id": photo["id"],
                    "url": photo["src"]["large"],
                    "src": photo["src"],
                    "photographer": photo["photographer"],
                }
                for photo in data.get("photos", [])
            ]
        except (requests.RequestException, KeyError):
            if attempt == MAX_RETRIES:
                return []
            time.sleep(2 ** attempt)
    return []


def download_image(url: str, dest_dir: str | None = None) -> str | None:
    """Download an image to a local temp file and return the path.

    Args:
        url: Direct image URL.
        dest_dir: Directory to save into. Uses tmp/ if None.

    Returns:
        Path to the downloaded file, or None on failure.
    """
    dest = Path(dest_dir) if dest_dir else Path("tmp")
    dest.mkdir(parents=True, exist_ok=True)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            suffix = ".jpg"
            tmp_file = tempfile.NamedTemporaryFile(
                dir=str(dest), suffix=suffix, delete=False
            )
            tmp_file.write(resp.content)
            tmp_file.close()
            return tmp_file.name
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2 ** attempt)
    return None


def process_overlay(image_path: str, max_width: int = 918,
                    corner_radius: int = 24, shadow_offset: int = 8) -> str:
    """Apply rounded corners and drop shadow to an overlay image.

    The processed image is saved next to the original with a '_processed' suffix.

    Args:
        image_path: Path to the source image.
        max_width: Maximum width in pixels (85% of 1080).
        corner_radius: Radius for rounded corners.
        shadow_offset: Pixel offset for the drop shadow.

    Returns:
        Path to the processed image file.
    """
    img = Image.open(image_path).convert("RGBA")

    # Resize to max_width while preserving aspect ratio
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Rounded corners mask
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius=corner_radius, fill=255)
    img.putalpha(mask)

    # Drop shadow
    shadow_size = (img.width + shadow_offset * 2, img.height + shadow_offset * 2)
    shadow = Image.new("RGBA", shadow_size, (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 80))
    shadow_layer.putalpha(mask)
    shadow.paste(shadow_layer, (shadow_offset, shadow_offset))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_offset))
    shadow.paste(img, (0, 0), img)

    # Save processed image
    out_path = Path(image_path).with_stem(Path(image_path).stem + "_processed")
    out_path = out_path.with_suffix(".png")
    shadow.save(str(out_path), "PNG")
    return str(out_path)
