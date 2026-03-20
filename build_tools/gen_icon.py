#!/usr/bin/env python3
"""
build_tools/gen_icon.py
========================
Generate GhostScripter-K1-K2 application icons from the project artwork
matching the cyberpunk / ghost aesthetic.

Produces:
    resources/icons/ghostscripter.png  (256×256  — main PNG)
    resources/icons/ghostscripter.ico  (multi-size ICO: 16,32,48,64,128,256)

Called automatically by build.py, but can also be run standalone:
    python build_tools/gen_icon.py

If no source artwork is present, falls back to a programmatic icon.
"""

from __future__ import annotations

import math
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "resources" / "icons"

# Source artwork variants committed alongside this script
# v3 is the best match (hooded ghost, neon green eyes, matrix rain)
SOURCE_VARIANTS = [
    ICONS_DIR / "ghostscripter_v3_1024.png",     # v3: hooded ghost, neon green eyes, matrix rain
    ICONS_DIR / "ghostscripter_new_1024.png",     # v2 fallback
    ICONS_DIR / "ghostscripter_flux_1024.png",   # v1 fallback
]


# ─────────────────────────────────────────────────────────────────
# Icon processing from source artwork
# ─────────────────────────────────────────────────────────────────

def _process_artwork(src_path: Path, size: int):
    """
    Load source artwork and process it into a clean icon at `size`×`size`.
    Applies:
      - Centre-crop to square
      - Resize with LANCZOS
      - Slight contrast boost
      - Rounded-corner mask
      - Neon green glow border
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    except ImportError:
        return None

    img = Image.open(src_path).convert("RGBA")

    # Centre-crop to square
    w, h = img.size
    sq = min(w, h)
    left = (w - sq) // 2
    top  = (h - sq) // 2
    img = img.crop((left, top, left + sq, top + sq))

    # Resize to target size
    img = img.resize((size, size), Image.LANCZOS)

    # Boost contrast slightly to sharpen the dark/neon contrast
    enhancer = ImageEnhance.Contrast(img.convert("RGB"))
    img_rgb = enhancer.enhance(1.25)

    # Boost saturation (make greens pop more)
    enhancer2 = ImageEnhance.Color(img_rgb)
    img_rgb = enhancer2.enhance(1.4)
    img = img_rgb.convert("RGBA")

    # Apply rounded-corner mask
    radius = size // 8
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    img.putalpha(mask)

    # Add neon green glow border
    border_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_img)
    glow_color = (0, 255, 70, 180)   # neon green, semi-transparent
    bw = max(1, size // 64)          # border width scales with size
    for i in range(bw):
        alpha = int(180 * (1 - i / bw))
        border_draw.rounded_rectangle(
            [i, i, size - i, size - i],
            radius=max(1, radius - i),
            outline=(0, 255 - i * 10, 70, alpha),
            width=1,
        )
    img = Image.alpha_composite(img, border_img)

    return img


# ─────────────────────────────────────────────────────────────────
# Fallback: programmatic cyberpunk icon
# ─────────────────────────────────────────────────────────────────

def _draw_icon_programmatic(size: int):
    """
    Fallback programmatic icon — dark hooded ghost with neon green eyes
    and Matrix-style scanlines. Used only when no artwork PNG is found.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("  [WARN] Pillow not installed — cannot generate icon.", flush=True)
        return None

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size
    pad = s // 14

    # ── Background: rounded pure black ──────────────────────────
    draw.rounded_rectangle(
        [pad, pad, s - pad, s - pad],
        radius=s // 8,
        fill=(0, 0, 0, 255),
    )

    # ── Matrix rain (vertical green chars) ───────────────────────
    rng = random.Random(42)  # deterministic seed
    n_cols = s // 8
    for col in range(n_cols):
        x = col * 8 + pad
        n_chars = rng.randint(3, 8)
        for row in range(n_chars):
            y = pad + row * 8
            if y + 8 > s - pad:
                break
            brightness = rng.randint(40, 160)
            alpha = rng.randint(60, 120)
            draw.rectangle([x, y, x + 5, y + 6],
                           fill=(0, brightness, 0, alpha))

    # ── Hood shape (dark grey) ──────────────────────────────────
    cx, cy = s // 2, int(s * 0.45)
    hood_r = int(s * 0.35)

    # Outer hood arc
    draw.ellipse(
        [cx - hood_r, cy - hood_r, cx + hood_r, cy + hood_r],
        fill=(18, 20, 18, 255),
        outline=(0, 200, 50, 200),
        width=max(1, s // 64),
    )

    # Inner face oval (black void)
    face_rx = int(hood_r * 0.58)
    face_ry = int(hood_r * 0.55)
    draw.ellipse(
        [cx - face_rx, cy - int(face_ry * 0.6), cx + face_rx, cy + face_ry],
        fill=(0, 0, 0, 255),
    )

    # ── Glowing eyes ─────────────────────────────────────────────
    eye_y = cy - int(hood_r * 0.05)
    eye_sep = int(face_rx * 0.45)
    eye_r = max(2, s // 24)

    for ex in [cx - eye_sep, cx + eye_sep]:
        # Outer glow halos (multiple expanding rings)
        for halo in range(4, 0, -1):
            hr = eye_r + halo * max(1, s // 48)
            ha = 30 * halo
            draw.ellipse(
                [ex - hr, eye_y - hr, ex + hr, eye_y + hr],
                fill=(0, min(255, 60 + halo * 40), 0, ha),
            )
        # Bright core
        draw.ellipse(
            [ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
            fill=(0, 255, 70, 255),
        )
        # Pure white hot spot
        hw = max(1, eye_r // 2)
        draw.ellipse(
            [ex - hw, eye_y - hw, ex + hw, eye_y + hw],
            fill=(200, 255, 200, 255),
        )

    # ── Green scanline overlay ────────────────────────────────────
    for y in range(pad, s - pad, 4):
        draw.line([(pad, y), (s - pad, y)], fill=(0, 40, 0, 20))

    # ── RGB chromatic aberration border ──────────────────────────
    border_colors = [
        (255, 0,   0,   60),   # red
        (0,   255, 70,  120),  # green
        (0,   50,  255, 60),   # blue
    ]
    for i, col in enumerate(border_colors):
        offset = i - 1
        draw.rounded_rectangle(
            [pad + offset, pad + offset,
             s - pad + offset, s - pad + offset],
            radius=s // 8,
            outline=col,
            width=max(1, s // 80),
        )

    return img


# ─────────────────────────────────────────────────────────────────
# ICO builder
# ─────────────────────────────────────────────────────────────────

def _build_ico(images: list) -> bytes:
    """
    Build a Windows ICO binary from a list of (size, PIL Image) tuples.
    Format: ICONDIR header + ICONDIRENTRY[] + PNG data blobs.
    Uses PNG-compressed entries for sizes > 48 (Vista+ ICO).
    """
    import io

    n = len(images)
    # ICONDIR header: reserved(2) + type(2) + count(2)
    header = struct.pack("<HHH", 0, 1, n)

    entry_size = 16
    data_start = 6 + n * entry_size

    entries = []
    blobs   = []
    offset  = data_start

    for size, img in sorted(images, key=lambda x: x[0]):
        # Convert to RGBA for clean export
        rgba = img.convert("RGBA")

        buf = io.BytesIO()
        if size <= 48:
            # BMP-style (32-bit) for small sizes
            rgba.save(buf, format="PNG")
        else:
            # PNG-compressed for large sizes (Vista+)
            rgba.save(buf, format="PNG")
        blob = buf.getvalue()

        w = size if size < 256 else 0
        h = size if size < 256 else 0
        # ICONDIRENTRY: width(1) height(1) colorcount(1) reserved(1)
        #               planes(2) bitcount(2) bytesinres(4) imageoffset(4)
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32,
                            len(blob), offset)
        entries.append(entry)
        blobs.append(blob)
        offset += len(blob)

    return header + b"".join(entries) + b"".join(blobs)


# ─────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────

def generate_icons():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 64, 128, 256]

    # Find source artwork
    src = None
    for variant in SOURCE_VARIANTS:
        if variant.exists():
            src = variant
            print(f"  Using source: {src.name}", flush=True)
            break

    # Build each size
    icon_images = []
    for size in sizes:
        if src:
            img = _process_artwork(src, size)
        else:
            img = None

        if img is None:
            print(f"  Falling back to programmatic icon at {size}px", flush=True)
            img = _draw_icon_programmatic(size)

        if img is not None:
            icon_images.append((size, img))
            print(f"  Generated {size}×{size}", flush=True)

    if not icon_images:
        print("  [ERROR] No images generated.", flush=True)
        return False

    # Save 256×256 PNG
    png256 = dict(icon_images).get(256)
    if png256:
        out_png = ICONS_DIR / "ghostscripter.png"
        png256.convert("RGBA").save(str(out_png), "PNG")
        print(f"  Saved PNG: {out_png}", flush=True)

    # Build and save ICO
    ico_data = _build_ico(icon_images)
    out_ico = ICONS_DIR / "ghostscripter.ico"
    out_ico.write_bytes(ico_data)
    print(f"  Saved ICO: {out_ico} ({len(ico_data):,} bytes)", flush=True)

    return True


if __name__ == "__main__":
    print("Generating GhostScripter icons...", flush=True)
    ok = generate_icons()
    sys.exit(0 if ok else 1)
