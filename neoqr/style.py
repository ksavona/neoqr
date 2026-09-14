"""Style definition for a QR render — every visual knob lives here."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GradientStop:
    color: str  # hex
    position: float = 0.0  # 0..1


@dataclass
class QRStyle:
    # --- module body ---
    module_shape: str = "rounded"  # square, dots, rounded, extra-rounded, classy, classy-rounded

    # --- eyes (finder patterns) ---
    eye_frame_shape: str = "rounded"  # square, rounded, circle, leaf
    eye_ball_shape: str = "circle"  # square, rounded, circle, leaf
    eye_frame_color: str = ""  # empty = use foreground
    eye_ball_color: str = ""  # empty = use foreground

    # --- color ---
    fg_type: str = "solid"  # solid, linear, radial
    fg_color: str = "#00FFF2"
    fg_color2: str = "#FF2079"
    gradient_angle: float = 45.0  # degrees, for linear gradients
    bg_color: str = "#0B0B12"
    transparent_bg: bool = False

    # --- structure ---
    error_correction: str = "H"  # L, M, Q, H
    quiet_zone: int = 4  # modules of margin
    scale_px: int = 1024  # output raster resolution (square)
    safe_mode: bool = True  # auto-correct contrast so all scanners can read it

    # --- logo ---
    logo_path: str = ""
    logo_mode: str = "middle"  # middle, integration
    logo_size_ratio: float = 0.22  # of the QR's width (middle mode)
    logo_padding: float = 14.0  # backing-plate thickness, % of the logo size (middle mode)
    logo_backing: str = "rounded"  # none, rounded, circle, square (middle mode)
    logo_backing_color: str = "#0B0B12"
    threshold_percent: float = 50.0  # brightness split point (0..100) — below vs. above
    darken_percent: float = 70.0  # how much pixels above the threshold are darkened
    lighten_percent: float = 70.0  # how much pixels below the threshold are lightened
    dot_shape: str = "circle"  # circle, square, star — shape used in integration mode
    hue_shift: float = 0.0  # 0..360 degrees, integration mode (0 = no change)
    saturation_shift: float = 0.0  # -100..100 percent, integration mode (0 = no change)
    overlay_mode: str = "none"  # none, multiply, darken, lighten, screen, overlay, hue, color

    # --- frame / border ---
    frame_style: str = "none"  # none, simple, rounded, banner
    frame_color: str = "#FF2079"
    frame_text: str = "SCAN ME"
    frame_text_color: str = "#00FFF2"
    frame_thickness: int = 14  # px at scale_px reference

    def clone(self) -> "QRStyle":
        return QRStyle(**self.__dict__)


# NOTE: the QR body itself always keeps a light background / dark foreground
# (enforced by safe_mode) so every scanner can read it — the Blade Runner mood
# comes through in the foreground hue and the dark neon frame/banner instead.
# NOTE: the QR body itself always keeps a light background / dark foreground
# (enforced by safe_mode) so every scanner can read it — the Blade Runner mood
# comes through in the foreground hue and the dark neon frame/banner instead.
PRESETS: dict[str, QRStyle] = {
    "None": QRStyle(
        module_shape="square",
        eye_frame_shape="square",
        eye_ball_shape="square",
        fg_type="solid",
        fg_color="#000000",
        bg_color="#FFFFFF",
        frame_style="none",
    ),
    "Blade Runner Neon": QRStyle(
        module_shape="rounded",
        eye_frame_shape="rounded",
        eye_ball_shape="circle",
        fg_type="linear",
        fg_color="#0A6E75",
        fg_color2="#8C1355",
        gradient_angle=45,
        bg_color="#F4F6FA",
        frame_style="banner",
        frame_color="#FF2079",
        frame_text="SCAN ME",
        frame_text_color="#00FFF2",
    ),
    "Replicant Noir": QRStyle(
        module_shape="classy-rounded",
        eye_frame_shape="square",
        eye_ball_shape="square",
        fg_type="solid",
        fg_color="#111214",
        bg_color="#F2F2F0",
        frame_style="simple",
        frame_color="#111214",
    ),
    "Tyrell Gold": QRStyle(
        module_shape="extra-rounded",
        eye_frame_shape="leaf",
        eye_ball_shape="circle",
        fg_type="linear",
        fg_color="#8A5B00",
        fg_color2="#3D2600",
        gradient_angle=90,
        bg_color="#FBF3DF",
        frame_style="rounded",
        frame_color="#FFC857",
    ),
    "Off-World Cyan": QRStyle(
        module_shape="dots",
        eye_frame_shape="circle",
        eye_ball_shape="circle",
        fg_type="radial",
        fg_color="#00707A",
        fg_color2="#012B33",
        bg_color="#EAFBFF",
        frame_style="banner",
        frame_color="#020617",
        frame_text="OFF-WORLD ACCESS",
        frame_text_color="#00FFE5",
    ),
    "Kowalski Red": QRStyle(
        module_shape="classy",
        eye_frame_shape="rounded",
        eye_ball_shape="square",
        fg_type="solid",
        fg_color="#8C0000",
        bg_color="#FFF3F1",
        frame_style="banner",
        frame_color="#8C0000",
        frame_text="RUN THE BLADE",
        frame_text_color="#FFFFFF",
    ),
}
