"""Logo pre-processing: resize + optional backing plate for contrast."""
from __future__ import annotations

from PIL import Image, ImageDraw

from .palette import hex_to_rgb


def prepare_logo(logo_path: str, target_px: int, padding: int, backing: str, backing_color: str) -> Image.Image:
    """Return an RGBA image of size (target_px + 2*padding) with the logo centered
    on an optional solid backing plate for readability against the QR pattern."""
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((target_px, target_px), Image.LANCZOS)

    plate_size = target_px + padding * 2
    plate = Image.new("RGBA", (plate_size, plate_size), (0, 0, 0, 0))

    if backing != "none":
        color = (*hex_to_rgb(backing_color), 255)
        draw = ImageDraw.Draw(plate)
        if backing == "circle":
            draw.ellipse((0, 0, plate_size, plate_size), fill=color)
        elif backing == "square":
            draw.rectangle((0, 0, plate_size, plate_size), fill=color)
        else:  # rounded
            draw.rounded_rectangle((0, 0, plate_size, plate_size), radius=plate_size * 0.22, fill=color)

    offset = ((plate_size - logo.width) // 2, (plate_size - logo.height) // 2)
    plate.alpha_composite(logo, offset)
    return plate
