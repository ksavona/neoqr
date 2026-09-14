"""Raster (PNG/JPEG) renderer built directly from the QR bit-matrix so that
every visual style option renders identically here and in render_svg.py."""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import matrix as matrix_mod
from .artistic import (
    SHAPE_AREA_FACTORS,
    build_artwork_grid,
    build_cover_image,
    build_cover_image_rect,
    module_diameter_ratio,
    plus_points,
    star_points,
    style_ink_array,
    to_float_array,
    to_pil,
)
from .geometry import get_neighbors, rounding_for_module
from .logo import prepare_logo
from .palette import hex_to_rgb
from .style import QRStyle

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\consolab.ttf",
]


def _load_font(px_size: int):
    px_size = max(8, px_size)
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, px_size)
            except OSError:
                continue
    return ImageFont.load_default()


def _lerp(c1, c2, t: float):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def make_gradient_fn(style: QRStyle):
    c1 = hex_to_rgb(style.fg_color)
    if style.fg_type == "solid":
        return lambda x, y: c1
    c2 = hex_to_rgb(style.fg_color2)
    if style.fg_type == "radial":
        def fn(x, y):
            d = math.hypot(x - 0.5, y - 0.5) / 0.7071
            return _lerp(c1, c2, max(0.0, min(1.0, d)))

        return fn

    angle = math.radians(style.gradient_angle)
    ax, ay = math.cos(angle), math.sin(angle)

    def fn(x, y):
        px, py = x - 0.5, y - 0.5
        t = (px * ax + py * ay) / 0.7071 * 0.5 + 0.5
        return _lerp(c1, c2, max(0.0, min(1.0, t)))

    return fn


def draw_shape_box(draw: "ImageDraw.ImageDraw", box, shape: str, fill):
    x0, y0, x1, y1 = box
    w = x1 - x0
    if shape == "circle":
        draw.ellipse(box, fill=fill)
    elif shape == "rounded":
        draw.rounded_rectangle(box, radius=min(w * 0.28, w / 2 - 0.5), fill=fill)
    elif shape == "leaf":
        draw.rounded_rectangle(
            box, radius=min(w * 0.5, w / 2 - 0.5), fill=fill, corners=(True, False, True, False)
        )
    else:  # square
        draw.rectangle(box, fill=fill)


def _shape_mask_draw(draw: "ImageDraw.ImageDraw", shape: str, cx: float, cy: float, r: float):
    if shape == "square":
        draw.rectangle((cx - r, cy - r, cx + r, cy + r), fill=255)
    elif shape == "star":
        draw.polygon(star_points(cx, cy, r), fill=255)
    elif shape == "plus":
        draw.polygon(plus_points(cx, cy, r), fill=255)
    else:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)


def lighten_box(canvas: Image.Image, box, blend: float):
    """Nudge real pixels back toward white by `blend` (0..1)."""
    if blend <= 0:
        return
    x0, y0, x1, y1 = (int(v) for v in box)
    region = canvas.crop((x0, y0, x1, y1))
    rb, gb, bb, ab = region.split()
    lighten = lambda band: band.point(lambda p: int(p * (1 - blend) + 255 * blend))  # noqa: E731
    canvas.paste(Image.merge("RGBA", (lighten(rb), lighten(gb), lighten(bb), ab)), (x0, y0))


def _cell_mean(canvas: Image.Image, box) -> float:
    x0, y0, x1, y1 = (int(v) for v in box)
    hist = canvas.crop((x0, y0, x1, y1)).convert("L").histogram()
    total = sum(hist)
    if not total:
        return 0.0
    return (sum(i * h for i, h in enumerate(hist)) / total) / 255.0


def enforce_dark(canvas: Image.Image, box, max_lum: float = 0.12):
    """Safe Mode guarantee: an on-module/ink cell must end up reliably dark on
    average, whatever the user's sliders produced — scale it down if not."""
    mean = _cell_mean(canvas, box)
    if mean <= max_lum or mean <= 0:
        return
    factor = max_lum / mean
    x0, y0, x1, y1 = (int(v) for v in box)
    region = canvas.crop((x0, y0, x1, y1))
    rb, gb, bb, ab = region.split()
    scale = lambda p: int(p * factor)  # noqa: E731
    canvas.paste(Image.merge("RGBA", (rb.point(scale), gb.point(scale), bb.point(scale), ab)), (x0, y0))


def enforce_light(canvas: Image.Image, box, min_lum: float = 0.88):
    """Safe Mode guarantee: an off-module/gap cell must end up reliably light
    on average — nudge it toward white further if not."""
    mean = _cell_mean(canvas, box)
    if mean >= min_lum or mean >= 1.0:
        return
    blend = min(1.0, (min_lum - mean) / (1.0 - mean))
    lighten_box(canvas, box, blend)


def _masked_mean(canvas: Image.Image, mask_img: Image.Image, box, want_ink: bool):
    x0, y0, x1, y1 = (int(v) for v in box)
    m = np.asarray(mask_img.crop((x0, y0, x1, y1)))
    sel = (m > 127) if want_ink else (m <= 127)
    if not sel.any():
        return None, None, None
    region = canvas.crop((x0, y0, x1, y1))
    arr = np.asarray(region.convert("RGB"), dtype=np.float32) / 255.0
    return arr, sel, region


_LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def enforce_dark_masked(canvas: Image.Image, mask_img: Image.Image, box, max_lum: float = 0.12):
    """Same guarantee as enforce_dark, but only over the masked ("ink")
    pixels within `box` — used for eye rings/ball, which share a box with
    their (light) hole."""
    arr, sel, region = _masked_mean(canvas, mask_img, box, want_ink=True)
    if arr is None:
        return
    mean = float((arr[sel] @ _LUMA_WEIGHTS).mean())
    if mean <= max_lum or mean <= 0:
        return
    out = arr.copy()
    out[sel] *= max_lum / mean
    x0, y0 = int(box[0]), int(box[1])
    result = to_pil(out).convert("RGBA")
    result.putalpha(region.split()[3])
    canvas.paste(result, (x0, y0))


def enforce_light_masked(canvas: Image.Image, mask_img: Image.Image, box, min_lum: float = 0.88):
    """Same guarantee as enforce_light, but only over the masked ("gap")
    pixels within `box` — used for the eye's inner hole ring."""
    arr, sel, region = _masked_mean(canvas, mask_img, box, want_ink=False)
    if arr is None:
        return
    mean = float((arr[sel] @ _LUMA_WEIGHTS).mean())
    if mean >= min_lum:
        return
    blend = min(1.0, (min_lum - mean) / (1.0 - mean)) if mean < 1.0 else 0.0
    out = arr.copy()
    out[sel] = out[sel] * (1 - blend) + blend
    x0, y0 = int(box[0]), int(box[1])
    result = to_pil(out).convert("RGBA")
    result.putalpha(region.split()[3])
    canvas.paste(result, (x0, y0))


def render_png(qr_matrix, style: QRStyle) -> Image.Image:
    size = len(qr_matrix)
    total_modules = size + style.quiet_zone * 2
    scale = max(4, style.scale_px // total_modules)
    canvas_px = scale * total_modules
    q = style.quiet_zone

    zones = matrix_mod.compute_eye_zones(size)
    eye_mask = zones.eye_mask

    artwork_active = (
        style.logo_mode == "integration" and style.logo_path and os.path.exists(style.logo_path)
    )

    if artwork_active:
        canvas = _render_artwork_body(qr_matrix, eye_mask, style, size, scale, canvas_px, q)
    else:
        canvas = _render_normal_body(qr_matrix, eye_mask, style, size, scale, canvas_px, q)

    # --- logo (middle mode only — integration mode already weaves the logo in) ---
    if style.logo_path and os.path.exists(style.logo_path) and style.logo_mode == "middle":
        target_px = int(canvas_px * style.logo_size_ratio)
        padding = max(2, int(target_px * style.logo_padding / 100.0))
        plate = prepare_logo(style.logo_path, target_px, padding, style.logo_backing, style.logo_backing_color)
        offset = ((canvas_px - plate.width) // 2, (canvas_px - plate.height) // 2)
        canvas.alpha_composite(plate, offset)

    canvas = _apply_frame(canvas, style)
    return canvas


def _render_normal_body(qr_matrix, eye_mask, style: QRStyle, size, scale, canvas_px, q) -> Image.Image:
    canvas = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if not style.transparent_bg:
        draw.rectangle((0, 0, canvas_px, canvas_px), fill=(*hex_to_rgb(style.bg_color), 255))

    gradient_fn = make_gradient_fn(style)

    for r in range(size):
        for c in range(size):
            if eye_mask[r][c] or not qr_matrix[r][c]:
                continue
            x0, y0 = (q + c) * scale, (q + r) * scale
            box = (x0, y0, x0 + scale, y0 + scale)
            color = gradient_fn((c + 0.5) / size, (r + 0.5) / size)

            if style.module_shape == "dots":
                pad = scale * 0.06
                draw.ellipse((x0 + pad, y0 + pad, x0 + scale - pad, y0 + scale - pad), fill=color)
                continue

            if style.module_shape == "plus":
                cx, cy = x0 + scale / 2, y0 + scale / 2
                draw.polygon(plus_points(cx, cy, scale * 0.48), fill=color)
                continue

            n = get_neighbors(qr_matrix, r, c)
            tl, tr, br, bl, ratio = rounding_for_module(style.module_shape, r, c, n)
            if ratio <= 0:
                draw.rectangle(box, fill=color)
            else:
                radius = min(ratio * scale / 2, scale / 2 - 0.5)
                draw.rounded_rectangle(box, radius=max(radius, 0.1), fill=color, corners=(tl, tr, br, bl))

    hole_fill = (0, 0, 0, 0) if style.transparent_bg else (*hex_to_rgb(style.bg_color), 255)
    for orow, ocol in matrix_mod.eye_origins(size):
        cx, cy = (ocol + 3.5) / size, (orow + 3.5) / size
        frame_color = (*hex_to_rgb(style.eye_frame_color), 255) if style.eye_frame_color else (*gradient_fn(cx, cy), 255)
        ball_color = (*hex_to_rgb(style.eye_ball_color), 255) if style.eye_ball_color else (*gradient_fn(cx, cy), 255)

        ox0, oy0 = (q + ocol) * scale, (q + orow) * scale
        outer_box = (ox0, oy0, ox0 + 7 * scale, oy0 + 7 * scale)
        inner_box = (ox0 + scale, oy0 + scale, ox0 + 6 * scale, oy0 + 6 * scale)
        ball_box = (ox0 + 2 * scale, oy0 + 2 * scale, ox0 + 5 * scale, oy0 + 5 * scale)

        draw_shape_box(draw, outer_box, style.eye_frame_shape, frame_color)
        draw_shape_box(draw, inner_box, style.eye_frame_shape, hole_fill)
        draw_shape_box(draw, ball_box, style.eye_ball_shape, ball_color)

    return canvas


def _render_artwork_body(qr_matrix, eye_mask, style: QRStyle, size, scale, canvas_px, q) -> Image.Image:
    """Logo Integration mode: the artwork covers the WHOLE canvas (no white
    anywhere), and one shared ink/gap mask decides which pixels — data
    modules, eye rings/ball, eye hole — get the darken/lighten/hue/overlay
    treatment vs. stay as the plain real image."""
    cover = build_cover_image(style.logo_path, canvas_px)
    raw_arr = to_float_array(cover)
    ink_arr = style_ink_array(raw_arr, style)

    lum_grid, _ = build_artwork_grid(style.logo_path, size)

    mask_img = Image.new("L", (canvas_px, canvas_px), 0)
    mdraw = ImageDraw.Draw(mask_img)

    for r in range(size):
        for c in range(size):
            if eye_mask[r][c] or not qr_matrix[r][c]:
                continue
            x0, y0 = (q + c) * scale, (q + r) * scale
            diameter_ratio = module_diameter_ratio(lum_grid[r][c])
            cx, cy = x0 + scale / 2, y0 + scale / 2
            shape_r = diameter_ratio * scale / 2 * SHAPE_AREA_FACTORS.get(style.dot_shape, 1.0)
            shape_r = min(shape_r, scale / 2 * 0.97)  # never bleed into a neighboring module
            _shape_mask_draw(mdraw, style.dot_shape, cx, cy, shape_r)

    for orow, ocol in matrix_mod.eye_origins(size):
        ox0, oy0 = (q + ocol) * scale, (q + orow) * scale
        outer_box = (ox0, oy0, ox0 + 7 * scale, oy0 + 7 * scale)
        inner_box = (ox0 + scale, oy0 + scale, ox0 + 6 * scale, oy0 + 6 * scale)
        ball_box = (ox0 + 2 * scale, oy0 + 2 * scale, ox0 + 5 * scale, oy0 + 5 * scale)
        draw_shape_box(mdraw, outer_box, style.eye_frame_shape, 255)
        draw_shape_box(mdraw, inner_box, style.eye_frame_shape, 0)
        draw_shape_box(mdraw, ball_box, style.eye_ball_shape, 255)

    mask_arr = (np.asarray(mask_img, dtype=np.float32) / 255.0)[..., None]
    final_arr = raw_arr * (1.0 - mask_arr) + ink_arr * mask_arr
    canvas = to_pil(final_arr).convert("RGBA")

    if style.safe_mode:
        for r in range(size):
            for c in range(size):
                if eye_mask[r][c]:
                    continue
                x0, y0 = (q + c) * scale, (q + r) * scale
                box = (x0, y0, x0 + scale, y0 + scale)
                if qr_matrix[r][c]:
                    enforce_dark(canvas, box)
                else:
                    enforce_light(canvas, box)

        for orow, ocol in matrix_mod.eye_origins(size):
            ox0, oy0 = (q + ocol) * scale, (q + orow) * scale
            eye_box = (ox0, oy0, ox0 + 7 * scale, oy0 + 7 * scale)
            enforce_dark_masked(canvas, mask_img, eye_box, max_lum=0.28)
            enforce_light_masked(canvas, mask_img, eye_box, min_lum=0.72)

        # a QR reader needs a clean, reliably light quiet zone to even find
        # the code — keep this guarantee no matter how busy the artwork is
        q_px = q * scale
        if q_px > 0:
            enforce_light(canvas, (0, 0, canvas_px, q_px), min_lum=0.85)
            enforce_light(canvas, (0, canvas_px - q_px, canvas_px, canvas_px), min_lum=0.85)
            enforce_light(canvas, (0, 0, q_px, canvas_px), min_lum=0.85)
            enforce_light(canvas, (canvas_px - q_px, 0, canvas_px, canvas_px), min_lum=0.85)

    return canvas


def _apply_frame(qr_img: Image.Image, style: QRStyle) -> Image.Image:
    if style.frame_style == "none":
        return qr_img

    w, h = qr_img.size
    thickness = max(6, int(w * (style.frame_thickness / 1024.0) * 3))
    frame_color = (*hex_to_rgb(style.frame_color), 255)
    banner_h = int(w * 0.16) if style.frame_style == "banner" else 0

    new_w = w + thickness * 2
    new_h = h + thickness * 2 + banner_h
    canvas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if style.transparent_bg:
        # keep the padding transparent — only stroke a thin frame-color outline
        stroke_w = max(2, thickness // 3)
        inset = stroke_w / 2
        if style.frame_style == "rounded":
            draw.rounded_rectangle(
                (inset, inset, new_w - 1 - inset, new_h - 1 - inset),
                radius=thickness * 1.6, outline=frame_color, width=stroke_w,
            )
        else:
            draw.rectangle(
                (inset, inset, new_w - 1 - inset, new_h - 1 - inset), outline=frame_color, width=stroke_w
            )
    elif style.logo_mode == "integration" and style.logo_path and os.path.exists(style.logo_path):
        # the border is also "ink": sample the real (extended) artwork and
        # run it through the same darken/lighten/hue/overlay pipeline —
        # except the banner strip, which stays a plain solid color so its
        # text stays legible
        if style.frame_style == "rounded":
            frame_mask = Image.new("L", (new_w, new_h), 0)
            ImageDraw.Draw(frame_mask).rounded_rectangle(
                (0, 0, new_w - 1, new_h - 1), radius=thickness * 1.6, fill=255
            )
        else:
            frame_mask = Image.new("L", (new_w, new_h), 255)

        canvas.paste(Image.new("RGBA", (new_w, new_h), frame_color), (0, 0), frame_mask)

        if banner_h > 0:
            ink_mask = Image.new("L", (new_w, new_h), 0)
            ink_mask.paste(frame_mask.crop((0, 0, new_w, new_h - banner_h)), (0, 0))
        else:
            ink_mask = frame_mask

        border_cover = build_cover_image_rect(style.logo_path, new_w, new_h)
        border_ink = to_pil(style_ink_array(to_float_array(border_cover), style)).convert("RGBA")
        canvas.paste(border_ink, (0, 0), ink_mask)

        if style.safe_mode:
            enforce_dark(canvas, (0, 0, new_w, thickness))
            enforce_dark(canvas, (0, thickness, thickness, thickness + h))
            enforce_dark(canvas, (thickness + w, thickness, thickness * 2 + w, thickness + h))
            if banner_h == 0:
                enforce_dark(canvas, (0, thickness + h, new_w, thickness * 2 + h))
    elif style.frame_style == "rounded":
        draw.rounded_rectangle((0, 0, new_w - 1, new_h - 1), radius=thickness * 1.6, fill=frame_color)
    else:
        draw.rectangle((0, 0, new_w - 1, new_h - 1), fill=frame_color)

    canvas.alpha_composite(qr_img, (thickness, thickness))

    if style.frame_style == "banner" and style.frame_text.strip():
        font = _load_font(int(banner_h * 0.5))
        text = style.frame_text.upper()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (new_w - tw) // 2
        ty = h + thickness + (banner_h - th) // 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=(*hex_to_rgb(style.frame_text_color), 255))

    return canvas
