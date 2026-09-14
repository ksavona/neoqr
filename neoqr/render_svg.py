"""SVG (vector) renderer — mirrors render_png.py so PNG/SVG exports match."""
from __future__ import annotations

import base64
import io
import math
import os

from . import matrix as matrix_mod
from .artistic import (
    SHAPE_AREA_FACTORS,
    average_color,
    build_artwork_grid,
    enforce_dark_color,
    module_diameter_ratio,
    plus_points,
    star_points,
    style_ink_color,
    white_overlay_opacity,
)
from .geometry import get_neighbors, rounding_for_module
from .logo import prepare_logo
from .palette import rgb_to_hex
from .render_png import make_gradient_fn
from .style import QRStyle


def _rounded_rect_path(x0, y0, x1, y1, tl, tr, br, bl, radius):
    r = radius
    p = [f"M{x0 + (r if tl else 0):.3f},{y0:.3f}"]
    p.append(f"L{x1 - (r if tr else 0):.3f},{y0:.3f}")
    p.append(f"A{r:.3f},{r:.3f} 0 0 1 {x1:.3f},{y0 + (r if tr else 0):.3f}" if tr else f"L{x1:.3f},{y0:.3f}")
    p.append(f"L{x1:.3f},{y1 - (r if br else 0):.3f}")
    p.append(f"A{r:.3f},{r:.3f} 0 0 1 {x1 - (r if br else 0):.3f},{y1:.3f}" if br else f"L{x1:.3f},{y1:.3f}")
    p.append(f"L{x0 + (r if bl else 0):.3f},{y1:.3f}")
    p.append(f"A{r:.3f},{r:.3f} 0 0 1 {x0:.3f},{y1 - (r if bl else 0):.3f}" if bl else f"L{x0:.3f},{y1:.3f}")
    p.append(f"L{x0:.3f},{y0 + (r if tl else 0):.3f}")
    p.append(f"A{r:.3f},{r:.3f} 0 0 1 {x0 + (r if tl else 0):.3f},{y0:.3f}" if tl else f"L{x0:.3f},{y0:.3f}")
    p.append("Z")
    return " ".join(p)


def _shape_el(shape, x0, y0, x1, y1, fill):
    w = x1 - x0
    if shape == "circle":
        cx, cy, rr = (x0 + x1) / 2, (y0 + y1) / 2, w / 2
        return f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{rr:.3f}" fill="{fill}"/>'
    if shape == "rounded":
        d = _rounded_rect_path(x0, y0, x1, y1, True, True, True, True, w * 0.28)
        return f'<path d="{d}" fill="{fill}"/>'
    if shape == "leaf":
        d = _rounded_rect_path(x0, y0, x1, y1, True, False, True, False, w * 0.5)
        return f'<path d="{d}" fill="{fill}"/>'
    return f'<rect x="{x0:.3f}" y="{y0:.3f}" width="{w:.3f}" height="{w:.3f}" fill="{fill}"/>'


def _dot_shape_el(shape, cx, cy, r, fill):
    """A flat-filled ink shape — the fill color already reflects the sampled
    artwork pixel run through hue/saturation/overlay/darken-lighten."""
    r *= SHAPE_AREA_FACTORS.get(shape, 1.0)
    r = min(r, 0.485)  # never bleed into a neighboring module
    if r <= 0.02:
        return ""
    if shape == "square":
        return f'<rect x="{cx - r:.3f}" y="{cy - r:.3f}" width="{r * 2:.3f}" height="{r * 2:.3f}" fill="{fill}"/>'
    if shape == "star":
        pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in star_points(cx, cy, r))
        return f'<polygon points="{pts}" fill="{fill}"/>'
    if shape == "plus":
        pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in plus_points(cx, cy, r))
        return f'<polygon points="{pts}" fill="{fill}"/>'
    return f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" fill="{fill}"/>'


def _gradient_defs(style: QRStyle, q: int, size: int) -> tuple[str, str]:
    """Return (defs_xml, fill_reference)."""
    if style.fg_type == "solid":
        return "", style.fg_color
    gid = "fgGrad"
    c1, c2 = style.fg_color, style.fg_color2
    if style.fg_type == "radial":
        cx = cy = q + size / 2
        r = size * 0.7071
        defs = (
            f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
            f'cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}">'
            f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
            f"</radialGradient>"
        )
    else:
        theta = math.radians(style.gradient_angle)
        x1 = q + size * (0.5 - 0.5 * math.cos(theta))
        y1 = q + size * (0.5 - 0.5 * math.sin(theta))
        x2 = q + size * (0.5 + 0.5 * math.cos(theta))
        y2 = q + size * (0.5 + 0.5 * math.sin(theta))
        defs = (
            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
            f'x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}">'
            f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
            f"</linearGradient>"
        )
    return defs, f"url(#{gid})"


def render_svg(qr_matrix, style: QRStyle) -> str:
    size = len(qr_matrix)
    q = style.quiet_zone
    total = size + q * 2

    gradient_fn = make_gradient_fn(style)
    defs_xml, fg_fill = _gradient_defs(style, q, size)

    zones = matrix_mod.compute_eye_zones(size)
    eye_mask = zones.eye_mask

    parts: list[str] = []
    bg_hex = style.bg_color

    artwork_active = (
        style.logo_mode == "integration" and style.logo_path and os.path.exists(style.logo_path)
    )

    bg_rgb = None
    if artwork_active:
        bg_rgb = average_color(style.logo_path)
        if style.safe_mode:
            op = white_overlay_opacity(bg_rgb)
            if op > 0:
                bg_rgb = tuple(int(v * (1 - op) + 255 * op) for v in bg_rgb)
        if not style.transparent_bg:
            parts.append(f'<rect x="0" y="0" width="{total}" height="{total}" fill="{rgb_to_hex(bg_rgb)}"/>')
    elif not style.transparent_bg:
        parts.append(f'<rect x="0" y="0" width="{total}" height="{total}" fill="{bg_hex}"/>')

    module_group = [f'<g fill="{fg_fill}">']
    dots_group: list[str] = []
    artwork_group: list[str] = []
    lum_grid = color_grid = None
    if artwork_active:
        lum_grid, color_grid = build_artwork_grid(style.logo_path, size)

    for r in range(size):
        for c in range(size):
            if eye_mask[r][c]:
                continue
            bit = qr_matrix[r][c]
            x0, y0 = q + c, q + r
            x1, y1 = x0 + 1, y0 + 1

            if artwork_active:
                if not bit:
                    if not style.transparent_bg:
                        fill = color_grid[r][c]
                        if style.safe_mode:
                            op = white_overlay_opacity(fill)
                            if op > 0:
                                fill = tuple(int(v * (1 - op) + 255 * op) for v in fill)
                        module_group.append(f'<rect x="{x0}" y="{y0}" width="1" height="1" fill="{rgb_to_hex(fill)}"/>')
                    continue
                lum = lum_grid[r][c]
                diameter_ratio = module_diameter_ratio(lum)
                cx, cy, rr = x0 + 0.5, y0 + 0.5, diameter_ratio * 0.5
                ink = style_ink_color(color_grid[r][c], style)
                if style.safe_mode:
                    ink = enforce_dark_color(ink)
                el = _dot_shape_el(style.dot_shape, cx, cy, rr, rgb_to_hex(ink))
                if el:
                    artwork_group.append(el)
                continue

            if not bit:
                continue

            if style.module_shape == "dots":
                pad = 0.06
                cx, cy, rr = x0 + 0.5, y0 + 0.5, 0.5 - pad
                dots_group.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{rr:.3f}"/>')
                continue

            if style.module_shape == "plus":
                cx, cy = x0 + 0.5, y0 + 0.5
                pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in plus_points(cx, cy, 0.48))
                dots_group.append(f'<polygon points="{pts}"/>')
                continue

            n = get_neighbors(qr_matrix, r, c)
            tl, tr, br, bl, ratio = rounding_for_module(style.module_shape, r, c, n)
            if ratio <= 0:
                module_group.append(f'<rect x="{x0}" y="{y0}" width="1" height="1"/>')
            else:
                radius = ratio * 0.5
                d = _rounded_rect_path(x0, y0, x1, y1, tl, tr, br, bl, radius)
                module_group.append(f'<path d="{d}"/>')
    if dots_group:
        module_group.append(f'<g>{"".join(dots_group)}</g>')
    module_group.append("</g>")
    parts.append("".join(module_group))
    if artwork_group:
        parts.append(f'<g>{"".join(artwork_group)}</g>')

    # --- eyes ---
    for orow, ocol in matrix_mod.eye_origins(size):
        cxf, cyf = (ocol + 3.5) / size, (orow + 3.5) / size
        if artwork_active:
            sample = color_grid[orow + 3][ocol + 3]
            ink = style_ink_color(sample, style)
            if style.safe_mode:
                ink = enforce_dark_color(ink)
            frame_color = style.eye_frame_color or rgb_to_hex(ink)
            ball_color = style.eye_ball_color or rgb_to_hex(ink)
            hole_opacity = max(white_overlay_opacity(sample), 0.12) if style.safe_mode else 0.0
            hole_color = "#ffffff" if hole_opacity > 0 else "none"
        else:
            frame_color = style.eye_frame_color or rgb_to_hex(gradient_fn(cxf, cyf))
            ball_color = style.eye_ball_color or rgb_to_hex(gradient_fn(cxf, cyf))
            hole_color = bg_hex if not style.transparent_bg else "none"
            hole_opacity = 1.0

        ox0, oy0 = q + ocol, q + orow
        parts.append(_shape_el(style.eye_frame_shape, ox0, oy0, ox0 + 7, oy0 + 7, frame_color))
        if hole_color != "none":
            hole_el = _shape_el(style.eye_frame_shape, ox0 + 1, oy0 + 1, ox0 + 6, oy0 + 6, hole_color)
            if artwork_active and hole_opacity < 1.0:
                hole_el = hole_el[:-2] + f' fill-opacity="{hole_opacity:.3f}"/>'
            parts.append(hole_el)
        parts.append(_shape_el(style.eye_ball_shape, ox0 + 2, oy0 + 2, ox0 + 5, oy0 + 5, ball_color))

    # --- logo ---
    if style.logo_path and os.path.exists(style.logo_path) and style.logo_mode == "middle":
        target_units = size * style.logo_size_ratio
        padding_units = target_units * (style.logo_padding / 100.0)
        plate = prepare_logo(
            style.logo_path,
            int(target_units * 40),
            int(padding_units * 40),
            style.logo_backing,
            style.logo_backing_color,
        )
        buf = io.BytesIO()
        plate.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        plate_units = target_units + padding_units * 2
        px = q + size / 2 - plate_units / 2
        py = q + size / 2 - plate_units / 2
        parts.append(
            f'<image x="{px:.3f}" y="{py:.3f}" width="{plate_units:.3f}" height="{plate_units:.3f}" '
            f'href="data:image/png;base64,{b64}"/>'
        )

    body = "".join(parts)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'width="{style.scale_px}" height="{style.scale_px}">'
        f"<defs>{defs_xml}</defs>{body}</svg>"
    )
    return _apply_frame_svg(svg, total, style)


def _apply_frame_svg(inner_svg: str, total: float, style: QRStyle) -> str:
    if style.frame_style == "none":
        return inner_svg

    thickness = total * 0.03
    banner_h = total * 0.16 if style.frame_style == "banner" else 0
    new_total_w = total + thickness * 2
    new_total_h = total + thickness * 2 + banner_h

    artwork_active = (
        style.logo_mode == "integration" and style.logo_path and os.path.exists(style.logo_path)
    )

    if style.transparent_bg:
        # keep the padding transparent — only stroke a thin frame-color outline
        stroke_w = max(1.0, thickness / 3)
        inset = stroke_w / 2
        if style.frame_style == "rounded":
            frame_rect = (
                f'<rect x="{inset:.3f}" y="{inset:.3f}" width="{new_total_w - stroke_w:.3f}" '
                f'height="{new_total_h - stroke_w:.3f}" rx="{thickness * 1.4:.3f}" '
                f'fill="none" stroke="{style.frame_color}" stroke-width="{stroke_w:.3f}"/>'
            )
        else:
            frame_rect = (
                f'<rect x="{inset:.3f}" y="{inset:.3f}" width="{new_total_w - stroke_w:.3f}" '
                f'height="{new_total_h - stroke_w:.3f}" fill="none" '
                f'stroke="{style.frame_color}" stroke-width="{stroke_w:.3f}"/>'
            )
    elif artwork_active:
        # the border is also "ink": one solid color, the styled area-average
        # of the artwork — except the banner strip, which stays a plain
        # solid color so its text stays legible
        ink = style_ink_color(average_color(style.logo_path), style)
        if style.safe_mode:
            ink = enforce_dark_color(ink)
        if style.frame_style == "rounded":
            frame_rect = (
                f'<rect x="0" y="0" width="{new_total_w:.3f}" height="{new_total_h:.3f}" '
                f'rx="{thickness * 1.4:.3f}" fill="{rgb_to_hex(ink)}"/>'
            )
        else:
            frame_rect = f'<rect x="0" y="0" width="{new_total_w:.3f}" height="{new_total_h:.3f}" fill="{rgb_to_hex(ink)}"/>'
        if banner_h > 0:
            frame_rect += f'<rect x="0" y="{new_total_h - banner_h:.3f}" width="{new_total_w:.3f}" height="{banner_h:.3f}" fill="{style.frame_color}"/>'
    elif style.frame_style == "rounded":
        frame_rect = (
            f'<rect x="0" y="0" width="{new_total_w:.3f}" height="{new_total_h:.3f}" '
            f'rx="{thickness * 1.4:.3f}" fill="{style.frame_color}"/>'
        )
    else:
        frame_rect = f'<rect x="0" y="0" width="{new_total_w:.3f}" height="{new_total_h:.3f}" fill="{style.frame_color}"/>'

    text_el = ""
    if style.frame_style == "banner" and style.frame_text.strip():
        text_el = (
            f'<text x="{new_total_w / 2:.3f}" y="{total + thickness + banner_h / 2:.3f}" '
            f'font-family="Segoe UI, Arial, sans-serif" font-size="{banner_h * 0.5:.3f}" '
            f'font-weight="700" letter-spacing="{banner_h * 0.08:.3f}" '
            f'text-anchor="middle" dominant-baseline="middle" fill="{style.frame_text_color}">'
            f"{style.frame_text.upper()}</text>"
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {new_total_w:.3f} {new_total_h:.3f}" '
        f'width="{style.scale_px}" height="{int(style.scale_px * new_total_h / total)}">'
        f"{frame_rect}"
        f'<g transform="translate({thickness:.3f},{thickness:.3f})">{inner_svg}</g>'
        f"{text_el}"
        f"</svg>"
    )
