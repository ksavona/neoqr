"""'Logo integration' mode — reproduces the artwork inside the QR (like the
classic KFC/brand artistic QR codes). Every module — and each eye ring/ball
and the border — is filled with ONE solid color: the true area-average of
the real artwork pixels it covers (via box-filter downsampling, so there's
no per-pixel grain), optionally hue/saturation shifted and blended with an
overlay tint, then pushed darker (if it started light) or lighter (if it
started dark already, so it never crushes to black) by user-adjustable
percentages. Safe Mode checks the actual resulting color and nudges it
further if needed so it keeps scanning."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .palette import hex_to_rgb, relative_luminance

MIN_DIAMETER_RATIO = 0.82  # even the lightest artwork spot keeps modules readable
MAX_DIAMETER_RATIO = 1.02

# shapes cover different fractions of their own bounding square, so their
# radius/size is boosted to keep the same average ink coverage per module
SHAPE_AREA_FACTORS = {"square": 1.0, "circle": 1.15, "star": 1.85, "plus": 1.55}
DOT_SHAPES = ["circle", "square", "star", "plus"]
OVERLAY_MODES = ["none", "multiply", "darken", "lighten", "screen", "overlay", "hue", "color"]


def build_artwork_grid(logo_path: str, size: int):
    """Return (luminance_grid, color_grid): the TRUE area-average color of
    the artwork under each QR module, computed with box-filter downsampling
    (a real average of every covered pixel, not a resampled guess)."""
    art = Image.open(logo_path).convert("RGB")
    w, h = art.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    art = art.crop((left, top, left + side, top + side)).resize((size, size), Image.Resampling.BOX)
    pixels = art.load()

    lum_grid = [[0.0] * size for _ in range(size)]
    color_grid = [[(0, 0, 0)] * size for _ in range(size)]
    for r in range(size):
        for c in range(size):
            rgb = pixels[c, r]
            color_grid[r][c] = rgb
            lum_grid[r][c] = relative_luminance(rgb)
    return lum_grid, color_grid


def average_color(logo_path: str) -> tuple:
    """The single area-average color of the whole artwork."""
    art = Image.open(logo_path).convert("RGB")
    return art.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))


def module_diameter_ratio(lum: float) -> float:
    """Darker artwork underneath -> a touch bigger, always big enough to read."""
    return MIN_DIAMETER_RATIO + (MAX_DIAMETER_RATIO - MIN_DIAMETER_RATIO) * (1.0 - lum)


def star_points(cx: float, cy: float, r_outer: float, points: int = 5, inner_ratio: float = 0.42):
    r_inner = r_outer * inner_ratio
    step = math.pi / points
    start = -math.pi / 2
    pts = []
    for i in range(points * 2):
        r = r_outer if i % 2 == 0 else r_inner
        theta = start + i * step
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return pts


def plus_points(cx: float, cy: float, r: float, thickness_ratio: float = 0.36):
    t = r * thickness_ratio
    offsets = [
        (-t, -r), (t, -r), (t, -t), (r, -t), (r, t), (t, t),
        (t, r), (-t, r), (-t, t), (-r, t), (-r, -t), (-t, -t),
    ]
    return [(cx + dx, cy + dy) for dx, dy in offsets]


# ------------------------------------------------------------------ numpy --
def rgb_to_hsv_np(rgb: np.ndarray):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    v = maxc
    delta = maxc - minc
    safe_delta = np.where(delta == 0, 1.0, delta)
    s = np.where(maxc == 0, 0.0, delta / np.where(maxc == 0, 1.0, maxc))
    rc = (maxc - r) / safe_delta
    gc = (maxc - g) / safe_delta
    bc = (maxc - b) / safe_delta
    h = np.zeros_like(maxc)
    h = np.where(maxc == r, bc - gc, h)
    h = np.where(maxc == g, 2.0 + rc - bc, h)
    h = np.where(maxc == b, 4.0 + gc - rc, h)
    h = (h / 6.0) % 1.0
    h = np.where(delta == 0, 0.0, h)
    return h, s, v


def hsv_to_rgb_np(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = (i.astype(np.int64) % 6)
    conditions = [i == k for k in range(6)]
    r = np.select(conditions, [v, q, p, p, t, v])
    g = np.select(conditions, [t, v, v, q, p, p])
    b = np.select(conditions, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def apply_hue_sat_np(arr: np.ndarray, hue_shift_deg: float, sat_shift_pct: float) -> np.ndarray:
    """arr: float32 HxWx3 in 0..1 RGB."""
    if not hue_shift_deg and not sat_shift_pct:
        return arr
    h, s, v = rgb_to_hsv_np(arr)
    if hue_shift_deg:
        h = (h + hue_shift_deg / 360.0) % 1.0
    if sat_shift_pct:
        factor = max(0.0, 1.0 + sat_shift_pct / 100.0)
        s = np.clip(s * factor, 0.0, 1.0)
    return np.clip(hsv_to_rgb_np(h, s, v), 0.0, 1.0)


def blend_np(a: np.ndarray, tint_rgb, mode: str) -> np.ndarray:
    """a: float32 HxWx3 in 0..1. tint_rgb: 0..255 tuple. Photoshop-style blend
    of the sampled artwork (`a`, the base) with a solid color tint."""
    if mode == "none":
        return a
    b = np.asarray(tint_rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    b = np.broadcast_to(b, a.shape)
    if mode == "multiply":
        out = a * b
    elif mode == "darken":
        out = np.minimum(a, b)
    elif mode == "lighten":
        out = np.maximum(a, b)
    elif mode == "screen":
        out = 1.0 - (1.0 - a) * (1.0 - b)
    elif mode == "overlay":
        out = np.where(a < 0.5, 2.0 * a * b, 1.0 - 2.0 * (1.0 - a) * (1.0 - b))
    elif mode in ("hue", "color"):
        ah, asat, av = rgb_to_hsv_np(a)
        bh, bsat, _bv = rgb_to_hsv_np(b)
        if mode == "hue":
            out = hsv_to_rgb_np(bh, asat, av)
        else:
            out = hsv_to_rgb_np(bh, bsat, av)
    else:
        out = a
    return np.clip(out, 0.0, 1.0)


def apply_brightness_lut_np(
    arr: np.ndarray, darken_percent: float, lighten_percent: float, threshold_percent: float = 50.0
) -> np.ndarray:
    """Darken/lighten each PIXEL (not each channel independently, which would
    shift hue) based on its own luminance vs. the threshold: pixels lighter
    than the threshold get multiplied darker by `darken_percent`; pixels
    darker than the threshold get lightened toward white by
    `lighten_percent`. Scaling all 3 channels by the same factor keeps the
    original hue intact."""
    d = max(0.0, min(1.0, darken_percent / 100.0))
    l = max(0.0, min(1.0, lighten_percent / 100.0))
    t = max(0.0, min(1.0, threshold_percent / 100.0))
    lum = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
    is_light = (lum >= t)[..., None]
    darkened = arr * (1.0 - d)
    lightened = arr + (1.0 - arr) * l
    return np.where(is_light, darkened, lightened)


def style_ink_array(raw_arr: np.ndarray, style) -> np.ndarray:
    """Full color pipeline for one 'ink' layer: hue/saturation -> overlay
    blend -> darken/lighten. `raw_arr` is float32 HxWx3 in 0..1."""
    styled = apply_hue_sat_np(raw_arr, style.hue_shift, style.saturation_shift)
    styled = blend_np(styled, hex_to_rgb(style.fg_color), style.overlay_mode)
    return apply_brightness_lut_np(styled, style.darken_percent, style.lighten_percent, style.threshold_percent)


def style_ink_color(rgb, style) -> tuple:
    """Scalar version of style_ink_array, for renderers (like SVG) that work
    with flat fills rather than per-pixel arrays."""
    arr = np.asarray(rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    out = style_ink_array(arr, style)[0, 0]
    return tuple(int(v) for v in np.clip(out * 255.0, 0, 255))


def enforce_dark_color(rgb, max_lum: float = 0.12):
    lum = relative_luminance(rgb)
    if lum <= max_lum or lum <= 0:
        return rgb
    factor = max_lum / lum
    return tuple(int(min(255, max(0, v * factor))) for v in rgb)


def white_overlay_opacity(rgb, min_lum: float = 0.88) -> float:
    """0..1 opacity for a white overlay to bring `rgb` up to at least min_lum."""
    lum = relative_luminance(rgb)
    if lum >= min_lum or lum >= 1.0:
        return 0.0
    return min(1.0, (min_lum - lum) / (1.0 - lum))

