"""High level API: turn a payload string + QRStyle into exported files."""
from __future__ import annotations

from PIL import Image

from .matrix import build_matrix
from .render_png import render_png
from .render_svg import render_svg
from .scan_safety import make_scannable
from .style import QRStyle


def generate_matrix(payload: str, style: QRStyle):
    style = make_scannable(style)
    error_level = "H" if style.logo_path else style.error_correction
    matrix, version = build_matrix(payload, error_correction=error_level)
    return matrix, version


def generate_png(payload: str, style: QRStyle) -> Image.Image:
    style = make_scannable(style)
    matrix, _ = build_matrix(
        payload, error_correction="H" if style.logo_path else style.error_correction
    )
    return render_png(matrix, style)


def generate_svg(payload: str, style: QRStyle) -> str:
    style = make_scannable(style)
    matrix, _ = build_matrix(
        payload, error_correction="H" if style.logo_path else style.error_correction
    )
    return render_svg(matrix, style)


def save_png(payload: str, style: QRStyle, path: str) -> None:
    img = generate_png(payload, style)
    img.save(path, format="PNG")


def save_svg(payload: str, style: QRStyle, path: str) -> None:
    svg = generate_svg(payload, style)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
