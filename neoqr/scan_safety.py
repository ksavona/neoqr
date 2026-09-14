"""Automatic contrast/luminance enforcement so exported QR codes stay scannable
by standard readers (which require sufficiently dark modules on a light
background — inverted or low-contrast designs are unreliable on real devices)."""
from __future__ import annotations

from .palette import (
    contrast_ratio,
    hex_to_rgb,
    hsv_to_rgb,
    relative_luminance,
    rgb_to_hex,
    rgb_to_hsv,
)
from .style import QRStyle

MIN_CONTRAST = 4.0


def _darken_until_safe(hex_color: str, bg_rgb) -> str:
    rgb = hex_to_rgb(hex_color)
    h, s, v = rgb_to_hsv(rgb)
    for _ in range(40):
        rgb = hsv_to_rgb(h, s, v)
        if relative_luminance(rgb) < relative_luminance(bg_rgb) and contrast_ratio(rgb, bg_rgb) >= MIN_CONTRAST:
            break
        v = max(0.0, v - 0.03)
        if v <= 0.0:
            break
    return rgb_to_hex(rgb)


def _lighten_until_safe(bg_hex: str, fg_rgbs: list) -> str:
    rgb = hex_to_rgb(bg_hex)
    h, s, v = rgb_to_hsv(rgb)
    for _ in range(40):
        rgb = hsv_to_rgb(h, s, v)
        if all(contrast_ratio(fg, rgb) >= MIN_CONTRAST for fg in fg_rgbs):
            break
        v = min(1.0, v + 0.03)
        s = s * 0.9
        if v >= 1.0:
            break
    return rgb_to_hex(rgb)


def scan_check(style: QRStyle) -> tuple[bool, float]:
    """Return (is_safe, contrast_ratio) for the current fg/bg combination."""
    bg_rgb = hex_to_rgb(style.bg_color) if not style.transparent_bg else (255, 255, 255)
    fg_rgb = hex_to_rgb(style.fg_color)
    ratio = contrast_ratio(fg_rgb, bg_rgb)
    safe = ratio >= MIN_CONTRAST and relative_luminance(fg_rgb) < relative_luminance(bg_rgb)
    if style.fg_type != "solid":
        fg2_rgb = hex_to_rgb(style.fg_color2)
        ratio = min(ratio, contrast_ratio(fg2_rgb, bg_rgb))
        safe = safe and ratio >= MIN_CONTRAST and relative_luminance(fg2_rgb) < relative_luminance(bg_rgb)
    return safe, ratio


def make_scannable(style: QRStyle) -> QRStyle:
    """Return a corrected clone that is guaranteed to meet the contrast rules."""
    if not style.safe_mode:
        return style

    s = style.clone()
    bg_rgb = hex_to_rgb(s.bg_color) if not s.transparent_bg else (255, 255, 255)

    s.fg_color = _darken_until_safe(s.fg_color, bg_rgb)
    if s.fg_type != "solid":
        s.fg_color2 = _darken_until_safe(s.fg_color2, bg_rgb)
    if s.eye_frame_color:
        s.eye_frame_color = _darken_until_safe(s.eye_frame_color, bg_rgb)
    if s.eye_ball_color:
        s.eye_ball_color = _darken_until_safe(s.eye_ball_color, bg_rgb)

    if not s.transparent_bg:
        fg_rgbs = [hex_to_rgb(s.fg_color)]
        if s.fg_type != "solid":
            fg_rgbs.append(hex_to_rgb(s.fg_color2))
        s.bg_color = _lighten_until_safe(s.bg_color, fg_rgbs)

    return s
