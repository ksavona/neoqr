"""Shared geometry helpers for neighbor-aware corner rounding (used by both
the PNG and SVG renderers so the two export formats stay visually identical)."""
from __future__ import annotations


def get_neighbors(matrix, r, c):
    size = len(matrix)

    def dark(rr, cc):
        if rr < 0 or cc < 0 or rr >= size or cc >= size:
            return False
        return bool(matrix[rr][cc])

    return {"N": dark(r - 1, c), "S": dark(r + 1, c), "E": dark(r, c + 1), "W": dark(r, c - 1)}


def rounding_for_module(shape: str, r: int, c: int, n: dict):
    """Return (top_left, top_right, bottom_right, bottom_left, radius_ratio)."""
    if shape == "square":
        return (False, False, False, False, 0.0)
    if shape == "dots":
        return (True, True, True, True, 1.0)
    if shape in ("rounded", "extra-rounded"):
        ratio = 1.0 if shape == "extra-rounded" else 0.55
        tl = not n["N"] and not n["W"]
        tr = not n["N"] and not n["E"]
        br = not n["S"] and not n["E"]
        bl = not n["S"] and not n["W"]
        return (tl, tr, br, bl, ratio)
    if shape in ("classy", "classy-rounded"):
        ratio = 0.9 if shape == "classy" else 0.5
        if (r + c) % 2 == 0:
            tl = not n["N"] and not n["W"]
            br = not n["S"] and not n["E"]
            return (tl, False, br, False, ratio)
        tr = not n["N"] and not n["E"]
        bl = not n["S"] and not n["W"]
        return (False, tr, False, bl, ratio)
    return (False, False, False, False, 0.0)


EYE_SHAPES = ["square", "rounded", "circle", "leaf"]
MODULE_SHAPES = ["square", "dots", "plus", "rounded", "extra-rounded", "classy", "classy-rounded"]
