"""Color science helpers: hex<->rgb, harmony palettes, contrast checks."""
from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*[max(0, min(255, int(v))) for v in rgb[:3]])


def rgb_to_hsv(rgb):
    r, g, b = [v / 255 for v in rgb[:3]]
    return colorsys.rgb_to_hsv(r, g, b)


def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))
    return int(r * 255), int(g * 255), int(b * 255)


def relative_luminance(rgb) -> float:
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = [lin(c) for c in rgb[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb1, rgb2) -> float:
    l1, l2 = relative_luminance(rgb1), relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def is_scannable(fg_rgb, bg_rgb, min_ratio: float = 2.5) -> bool:
    """QR scanners need modules clearly distinguishable from background."""
    return contrast_ratio(fg_rgb, bg_rgb) >= min_ratio


@dataclass
class Palette:
    name: str
    foreground: str
    background: str
    accent: str = ""


def _clamp_for_scan(fg_hsv, bg_hsv):
    """Push foreground dark/saturated and background light so scanners cope."""
    fh, fs, fv = fg_hsv
    bh, bs, bv = bg_hsv
    fv = min(fv, 0.55)
    bv = max(bv, 0.82)
    return (fh, min(fs * 1.1, 1.0), fv), (bh, bs * 0.35, bv)


def generate_palettes(base_hex: str) -> list[Palette]:
    """Generate auto colour palettes (complementary, analogous, triadic, mono, split)."""
    h, s, v = rgb_to_hsv(hex_to_rgb(base_hex))
    s = max(s, 0.55)
    v = max(v, 0.5)

    def make(name, fg_h, fg_s, fg_v, bg_h, bg_s, bg_v):
        fg_hsv, bg_hsv = _clamp_for_scan((fg_h, fg_s, fg_v), (bg_h, bg_s, bg_v))
        return Palette(
            name=name,
            foreground=rgb_to_hex(hsv_to_rgb(*fg_hsv)),
            background=rgb_to_hex(hsv_to_rgb(*bg_hsv)),
            accent=rgb_to_hex(hsv_to_rgb((fg_h + 0.5) % 1.0, s, min(v + 0.2, 1.0))),
        )

    palettes = [
        make("Complementary", h, s, v, (h + 0.5) % 1.0, s * 0.4, 0.95),
        make("Analogous", h, s, v, (h + 0.08) % 1.0, s * 0.3, 0.93),
        make("Triadic", h, s, v, (h + 1 / 3) % 1.0, s * 0.35, 0.94),
        make("Split-Complementary", h, s, v, (h + 0.42) % 1.0, s * 0.35, 0.94),
        make("Monochrome", h, s * 0.9, max(v - 0.35, 0.1), h, s * 0.12, 0.96),
        make("Neon Inverse", h, min(s + 0.2, 1), 0.35, h, 0.15, 0.08),
    ]
    return palettes


def random_neon_hex() -> str:
    h = random.random()
    return rgb_to_hex(hsv_to_rgb(h, random.uniform(0.6, 1.0), random.uniform(0.55, 0.95)))
