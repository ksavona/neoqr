"""QR matrix generation and finder-pattern (eye) zone detection."""
from __future__ import annotations

from dataclasses import dataclass

import qrcode
from qrcode.constants import (
    ERROR_CORRECT_H,
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
)

ERROR_LEVELS = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}

MAX_BYTES_HINT = {"L": 2953, "M": 2331, "Q": 1663, "H": 1273}


@dataclass
class QRZones:
    size: int
    # boolean grid: True if module belongs to a finder-pattern (eye) zone
    eye_mask: list


def build_matrix(data: str, error_correction: str = "M", version=None):
    """Return (matrix, actual_version) where matrix is a list[list[bool]]."""
    qr = qrcode.QRCode(
        version=version,
        error_correction=ERROR_LEVELS.get(error_correction, ERROR_CORRECT_M),
        box_size=1,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    return matrix, qr.version


_EYE_ORIGINS_FN = lambda size: [(0, 0), (0, size - 7), (size - 7, 0)]  # noqa: E731


def compute_eye_zones(size: int) -> QRZones:
    mask = [[False] * size for _ in range(size)]
    for orow, ocol in _EYE_ORIGINS_FN(size):
        for r in range(7):
            for c in range(7):
                mask[orow + r][ocol + c] = True
    return QRZones(size=size, eye_mask=mask)


def eye_origins(size: int):
    return _EYE_ORIGINS_FN(size)
