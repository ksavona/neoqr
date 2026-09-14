"""Payload builders for the various QR data types."""
from __future__ import annotations

from urllib.parse import quote


def _esc_wifi(value: str) -> str:
    # Escape characters that are special in the WIFI: URI scheme
    for ch in ("\\", ";", ",", ":", '"'):
        value = value.replace(ch, "\\" + ch)
    return value


def _esc_vcard(value: str) -> str:
    for ch in ("\\", ";", ","):
        value = value.replace(ch, "\\" + ch)
    return value.replace("\n", "\\n")


def build_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if "://" not in url and not url.lower().startswith("mailto:") and not url.lower().startswith("tel:"):
        url = "https://" + url
    return url


def build_text(text: str) -> str:
    return text


def build_wifi(ssid: str, password: str = "", security: str = "WPA", hidden: bool = False) -> str:
    security = security.upper()
    if security == "NONE":
        return f"WIFI:T:nopass;S:{_esc_wifi(ssid)};H:{'true' if hidden else 'false'};;"
    return (
        f"WIFI:T:{security};S:{_esc_wifi(ssid)};P:{_esc_wifi(password)};"
        f"H:{'true' if hidden else 'false'};;"
    )


def build_vcard(
    name: str = "",
    org: str = "",
    title: str = "",
    phone: str = "",
    email: str = "",
    website: str = "",
    address: str = "",
    note: str = "",
) -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    if name:
        lines.append(f"FN:{_esc_vcard(name)}")
        parts = name.split(" ", 1)
        last = parts[1] if len(parts) > 1 else ""
        first = parts[0]
        lines.append(f"N:{_esc_vcard(last)};{_esc_vcard(first)};;;")
    if org:
        lines.append(f"ORG:{_esc_vcard(org)}")
    if title:
        lines.append(f"TITLE:{_esc_vcard(title)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{phone}")
    if email:
        lines.append(f"EMAIL:{email}")
    if website:
        lines.append(f"URL:{website}")
    if address:
        lines.append(f"ADR:;;{_esc_vcard(address)};;;;")
    if note:
        lines.append(f"NOTE:{_esc_vcard(note)}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def build_email(address: str, subject: str = "", body: str = "") -> str:
    q = []
    if subject:
        q.append("subject=" + quote(subject))
    if body:
        q.append("body=" + quote(body))
    query = ("?" + "&".join(q)) if q else ""
    return f"mailto:{address}{query}"


def build_sms(phone: str, message: str = "") -> str:
    if message:
        return f"SMSTO:{phone}:{message}"
    return f"SMSTO:{phone}:"


def build_phone(number: str) -> str:
    return f"tel:{number}"


def build_geo(lat: str, lon: str) -> str:
    return f"geo:{lat},{lon}"


def build_event(summary: str, start: str, end: str, location: str = "") -> str:
    # start/end expected as YYYYMMDDTHHMMSS
    lines = [
        "BEGIN:VEVENT",
        f"SUMMARY:{summary}",
        f"DTSTART:{start}",
        f"DTEND:{end}",
    ]
    if location:
        lines.append(f"LOCATION:{location}")
    lines.append("END:VEVENT")
    return "\n".join(lines)


DATA_TYPES = {
    "URL": "Website link",
    "Text": "Plain text / message",
    "Wi-Fi": "Wireless network auto-join",
    "Contact": "vCard business card",
    "Email": "Pre-filled email",
    "SMS": "Pre-filled text message",
    "Phone": "Dial a number",
    "Location": "GPS coordinates",
}
