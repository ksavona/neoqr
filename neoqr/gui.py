"""NeoQR GUI — Blade Runner themed QR code forge."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from . import data_builders as db
from . import exporter as ex
from .artistic import OVERLAY_MODES
from .palette import generate_palettes, random_neon_hex
from .scan_safety import scan_check
from .style import PRESETS, QRStyle

ctk.set_appearance_mode("dark")

BG_ROOT = "#07070c"
BG_PANEL = "#101018"
BG_CARD = "#15151f"
BORDER = "#262638"
NEON_CYAN = "#00fff2"
NEON_MAGENTA = "#ff2079"
NEON_AMBER = "#ffc857"
TEXT_LIGHT = "#e8e8f0"
TEXT_DIM = "#8a8aa0"
DANGER = "#ff4d4d"
OK_GREEN = "#37ff8b"

FONT_TITLE = ("Consolas", 22, "bold")
FONT_HEAD = ("Consolas", 13, "bold")
FONT_BODY = ("Consolas", 12)
FONT_SMALL = ("Consolas", 10)

MODULE_SHAPES = ["square", "dots", "plus", "rounded", "extra-rounded", "classy", "classy-rounded"]
EYE_SHAPES = ["square", "rounded", "circle", "leaf"]
FRAME_STYLES = ["none", "simple", "rounded", "banner"]
ERROR_LEVELS = ["L", "M", "Q", "H"]


def section(parent, title):
    frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER)
    frame.pack(fill="x", padx=10, pady=(0, 10))
    lbl = ctk.CTkLabel(frame, text=title, font=FONT_HEAD, text_color=NEON_CYAN, anchor="w")
    lbl.pack(fill="x", padx=12, pady=(10, 4))
    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.pack(fill="x", padx=12, pady=(0, 12))
    return body


def color_swatch(parent, initial_hex, on_change, label=""):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=3)
    if label:
        ctk.CTkLabel(row, text=label, font=FONT_BODY, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
    swatch_btn = ctk.CTkButton(
        row, text="", width=40, height=24, fg_color=initial_hex, hover_color=initial_hex,
        border_width=1, border_color=BORDER, corner_radius=6,
    )
    entry_var = tk.StringVar(value=initial_hex)
    entry = ctk.CTkEntry(row, textvariable=entry_var, width=90, font=FONT_SMALL)
    entry.pack(side="right", padx=(6, 0))
    swatch_btn.pack(side="right")

    def pick():
        rgb, hexv = colorchooser.askcolor(color=entry_var.get() or "#000000")
        if hexv:
            entry_var.set(hexv.upper())
            swatch_btn.configure(fg_color=hexv, hover_color=hexv)
            on_change(hexv.upper())

    def on_type(*_):
        v = entry_var.get()
        if len(v) in (4, 7) and v.startswith("#"):
            try:
                swatch_btn.configure(fg_color=v, hover_color=v)
                on_change(v.upper())
            except Exception:
                pass

    swatch_btn.configure(command=pick)
    entry_var.trace_add("write", on_type)
    return entry_var, swatch_btn


class NeoQRApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NEOQR // Replicant Code Forge")
        self.geometry("1420x900")
        self.minsize(980, 600)
        self.configure(fg_color=BG_ROOT)

        self.style = PRESETS["Blade Runner Neon"].clone()
        self.style.scale_px = 900
        self.data_type = tk.StringVar(value="URL")
        self._refresh_job = None
        self.preview_ctkimage = None

        self._build_layout()
        self._schedule_refresh()

    # ---------------------------------------------------------- layout ----
    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color=BG_PANEL, height=64, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="N E O Q R", font=("Consolas", 26, "bold"), text_color=NEON_CYAN
        ).pack(side="left", padx=20)
        ctk.CTkLabel(
            header, text="// REPLICANT CODE FORGE — DESIGN YOUR OWN QR", font=FONT_SMALL, text_color=NEON_MAGENTA
        ).pack(side="left", padx=4)

        body_outer = ctk.CTkFrame(self, fg_color=BG_ROOT)
        body_outer.pack(fill="both", expand=True)

        # a horizontal-scroll fallback: on very narrow windows the 3-column
        # layout can't shrink further, so let it scroll instead of clipping
        body_canvas = tk.Canvas(body_outer, bg=BG_ROOT, highlightthickness=0, bd=0)
        h_scroll = ctk.CTkScrollbar(body_outer, orientation="horizontal", command=body_canvas.xview)
        body_canvas.configure(xscrollcommand=h_scroll.set)
        body_canvas.pack(side="top", fill="both", expand=True)
        h_scroll.pack(side="bottom", fill="x")

        body = ctk.CTkFrame(body_canvas, fg_color=BG_ROOT)
        body_window = body_canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_scrollregion(_event=None):
            body_canvas.configure(scrollregion=body_canvas.bbox("all"))

        def _sync_size(event):
            body_canvas.itemconfig(
                body_window,
                width=max(event.width, body.winfo_reqwidth()),
                height=max(event.height, body.winfo_reqheight()),
            )

        body.bind("<Configure>", _sync_scrollregion)
        body_canvas.bind("<Configure>", _sync_size)

        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=0)
        body.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(body, fg_color=BG_ROOT, width=340, label_text="")
        self.left_panel.grid(row=0, column=0, sticky="nswe", padx=(10, 0), pady=10)

        center = ctk.CTkScrollableFrame(body, fg_color=BG_ROOT, label_text="")
        center.grid(row=0, column=1, sticky="nswe", pady=10)
        self._build_preview(center)

        self.right_panel = ctk.CTkScrollableFrame(body, fg_color=BG_ROOT, width=360, label_text="")
        self.right_panel.grid(row=0, column=2, sticky="nswe", padx=(0, 10), pady=10)

        self._build_data_panel(self.left_panel)
        self._build_style_panel(self.right_panel)

    # ------------------------------------------------------ preview area --
    def _build_preview(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=10, pady=0)

        self.preview_label = ctk.CTkLabel(card, text="", fg_color="transparent")
        self.preview_label.pack(expand=True, pady=(20, 6))

        self.status_label = ctk.CTkLabel(card, text="", font=FONT_SMALL, text_color=OK_GREEN)
        self.status_label.pack(pady=(0, 6))

        info_row = ctk.CTkFrame(card, fg_color="transparent")
        info_row.pack(pady=(0, 14))
        self.info_label = ctk.CTkLabel(info_row, text="", font=FONT_SMALL, text_color=TEXT_DIM)
        self.info_label.pack()

        export_row = ctk.CTkFrame(card, fg_color="transparent")
        export_row.pack(pady=(0, 20))
        ctk.CTkButton(
            export_row, text="⬇ EXPORT PNG", font=FONT_HEAD, fg_color=NEON_CYAN, text_color="#001014",
            hover_color="#5cf5ec", corner_radius=8, width=160, command=self.export_png,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            export_row, text="⬇ EXPORT SVG", font=FONT_HEAD, fg_color=NEON_MAGENTA, text_color="#1a0010",
            hover_color="#ff5fa3", corner_radius=8, width=160, command=self.export_svg,
        ).pack(side="left", padx=8)

        res_row = ctk.CTkFrame(card, fg_color="transparent")
        res_row.pack(pady=(0, 20))
        ctk.CTkLabel(res_row, text="Resolution:", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left", padx=(0, 6))
        self.res_var = tk.StringVar(value="1024 px")
        res_menu = ctk.CTkOptionMenu(
            res_row, values=["512 px", "1024 px", "2048 px", "4096 px"], variable=self.res_var,
            width=110, command=lambda *_: self._on_style_change(),
        )
        res_menu.pack(side="left")

    # -------------------------------------------------------- data panel --
    def _build_data_panel(self, parent):
        ctk.CTkLabel(parent, text="DATA", font=FONT_TITLE, text_color=NEON_MAGENTA).pack(
            anchor="w", padx=10, pady=(4, 10)
        )

        type_grid = ctk.CTkFrame(parent, fg_color="transparent")
        type_grid.pack(fill="x", padx=10, pady=(0, 12))
        type_grid.grid_columnconfigure((0, 1), weight=1)
        self.type_buttons: dict[str, ctk.CTkButton] = {}
        keys = list(db.DATA_TYPES.keys())
        for i, key in enumerate(keys):
            btn = ctk.CTkButton(
                type_grid, text=key, font=FONT_SMALL, height=32, corner_radius=8,
                fg_color=BG_PANEL, border_width=1, border_color=BORDER, text_color=TEXT_LIGHT,
                command=lambda k=key: self._select_data_type(k),
            )
            btn.grid(row=i // 2, column=i % 2, sticky="we", padx=3, pady=3)
            self.type_buttons[key] = btn

        self.data_body = ctk.CTkFrame(parent, fg_color="transparent")
        self.data_body.pack(fill="x")

        self.field_vars: dict[str, tk.Variable] = {}
        self._select_data_type(self.data_type.get())

    def _select_data_type(self, key):
        self.data_type.set(key)
        for k, btn in self.type_buttons.items():
            if k == key:
                btn.configure(fg_color=NEON_MAGENTA, text_color="#1a0010", border_color=NEON_MAGENTA)
            else:
                btn.configure(fg_color=BG_PANEL, text_color=TEXT_LIGHT, border_color=BORDER)
        self._switch_data_type()

    def _clear_data_body(self):
        for w in self.data_body.winfo_children():
            w.destroy()
        self.field_vars.clear()

    def _add_entry(self, key, label, default="", multiline=False):
        row = ctk.CTkFrame(self.data_body, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(row, text=label, font=FONT_SMALL, text_color=TEXT_DIM, anchor="w").pack(fill="x")
        var = tk.StringVar(value=default)
        if multiline:
            box = ctk.CTkTextbox(row, height=64, font=FONT_BODY, fg_color=BG_PANEL, border_width=1, border_color=BORDER)
            box.pack(fill="x", pady=(2, 0))
            box.insert("1.0", default)
            box.bind("<KeyRelease>", lambda e: self._schedule_refresh())
            self.field_vars[key] = box
        else:
            entry = ctk.CTkEntry(row, textvariable=var, font=FONT_BODY, fg_color=BG_PANEL, border_width=1, border_color=BORDER)
            entry.pack(fill="x", pady=(2, 0))
            var.trace_add("write", lambda *_: self._schedule_refresh())
            self.field_vars[key] = var
        return var

    def _field_value(self, key):
        w = self.field_vars.get(key)
        if isinstance(w, tk.Variable):
            return w.get()
        if w is not None:
            return w.get("1.0", "end-1c")
        return ""

    def _switch_data_type(self):
        self._clear_data_body()
        t = self.data_type.get()
        if t == "URL":
            self._add_entry("url", "Website URL", "https://")
        elif t == "Text":
            self._add_entry("text", "Message", "", multiline=True)
        elif t == "Wi-Fi":
            self._add_entry("ssid", "Network name (SSID)")
            self._add_entry("password", "Password")
            row = ctk.CTkFrame(self.data_body, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text="Security", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
            sec_var = tk.StringVar(value="WPA")
            ctk.CTkOptionMenu(row, values=["WPA", "WEP", "NONE"], variable=sec_var, width=100,
                               command=lambda *_: self._schedule_refresh()).pack(side="right")
            self.field_vars["security"] = sec_var
            hidden_var = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(self.data_body, text="Hidden network", variable=hidden_var,
                             font=FONT_SMALL, command=self._schedule_refresh).pack(anchor="w", padx=10, pady=4)
            self.field_vars["hidden"] = hidden_var
        elif t == "Contact":
            self._add_entry("name", "Full name")
            self._add_entry("org", "Organization")
            self._add_entry("title", "Job title")
            self._add_entry("phone", "Phone")
            self._add_entry("email", "Email")
            self._add_entry("website", "Website")
        elif t == "Email":
            self._add_entry("address", "To address")
            self._add_entry("subject", "Subject")
            self._add_entry("body", "Body", multiline=True)
        elif t == "SMS":
            self._add_entry("phone", "Phone number")
            self._add_entry("message", "Message", multiline=True)
        elif t == "Phone":
            self._add_entry("number", "Phone number")
        elif t == "Location":
            self._add_entry("lat", "Latitude")
            self._add_entry("lon", "Longitude")
        self._schedule_refresh()

    def _current_payload(self) -> str:
        t = self.data_type.get()
        try:
            if t == "URL":
                return db.build_url(self._field_value("url"))
            if t == "Text":
                return db.build_text(self._field_value("text"))
            if t == "Wi-Fi":
                return db.build_wifi(
                    self._field_value("ssid"), self._field_value("password"),
                    self.field_vars["security"].get(), self.field_vars["hidden"].get(),
                )
            if t == "Contact":
                return db.build_vcard(
                    self._field_value("name"), self._field_value("org"), self._field_value("title"),
                    self._field_value("phone"), self._field_value("email"), self._field_value("website"),
                )
            if t == "Email":
                return db.build_email(self._field_value("address"), self._field_value("subject"), self._field_value("body"))
            if t == "SMS":
                return db.build_sms(self._field_value("phone"), self._field_value("message"))
            if t == "Phone":
                return db.build_phone(self._field_value("number"))
            if t == "Location":
                return db.build_geo(self._field_value("lat"), self._field_value("lon"))
        except Exception:
            return ""
        return ""

    # ------------------------------------------------------- style panel --
    def _build_style_panel(self, parent):
        ctk.CTkLabel(parent, text="DESIGN", font=FONT_TITLE, text_color=NEON_CYAN).pack(anchor="w", padx=10, pady=(4, 10))

        # presets
        sec = section(parent, "PRESETS")
        preset_var = tk.StringVar(value="Blade Runner Neon")
        ctk.CTkOptionMenu(sec, values=list(PRESETS.keys()), variable=preset_var,
                           command=self._apply_preset).pack(fill="x")

        # module shape
        sec = section(parent, "MODULE SHAPE")
        self.module_var = tk.StringVar(value=self.style.module_shape)
        ctk.CTkOptionMenu(sec, values=MODULE_SHAPES, variable=self.module_var,
                           command=lambda v: self._set_style(module_shape=v)).pack(fill="x")

        # eyes
        sec = section(parent, "EYES (FINDER PATTERNS)")
        row1 = ctk.CTkFrame(sec, fg_color="transparent"); row1.pack(fill="x", pady=3)
        ctk.CTkLabel(row1, text="Frame", font=FONT_SMALL, text_color=TEXT_DIM, width=60, anchor="w").pack(side="left")
        self.eye_frame_var = tk.StringVar(value=self.style.eye_frame_shape)
        ctk.CTkOptionMenu(row1, values=EYE_SHAPES, variable=self.eye_frame_var,
                           command=lambda v: self._set_style(eye_frame_shape=v), width=140).pack(side="right")
        row2 = ctk.CTkFrame(sec, fg_color="transparent"); row2.pack(fill="x", pady=3)
        ctk.CTkLabel(row2, text="Ball", font=FONT_SMALL, text_color=TEXT_DIM, width=60, anchor="w").pack(side="left")
        self.eye_ball_var = tk.StringVar(value=self.style.eye_ball_shape)
        ctk.CTkOptionMenu(row2, values=EYE_SHAPES, variable=self.eye_ball_var,
                           command=lambda v: self._set_style(eye_ball_shape=v), width=140).pack(side="right")

        # colors
        sec = section(parent, "COLOR")
        fg_type_row = ctk.CTkFrame(sec, fg_color="transparent"); fg_type_row.pack(fill="x", pady=3)
        ctk.CTkLabel(fg_type_row, text="Gradient", font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        self.fg_type_var = tk.StringVar(value=self.style.fg_type)
        ctk.CTkOptionMenu(fg_type_row, values=["solid", "linear", "radial"], variable=self.fg_type_var,
                           command=lambda v: self._set_style(fg_type=v), width=140).pack(side="right")
        self.fg_color_var, self.fg_color_swatch = color_swatch(sec, self.style.fg_color, lambda v: self._set_style(fg_color=v), "Foreground")
        color_swatch(sec, self.style.fg_color2, lambda v: self._set_style(fg_color2=v), "Foreground 2")
        self.bg_color_var, self.bg_color_swatch = color_swatch(sec, self.style.bg_color, lambda v: self._set_style(bg_color=v), "Background")
        self.transparent_var = tk.BooleanVar(value=self.style.transparent_bg)
        ctk.CTkCheckBox(sec, text="Transparent background", variable=self.transparent_var, font=FONT_SMALL,
                         command=lambda: self._set_style(transparent_bg=self.transparent_var.get())).pack(anchor="w", pady=(6, 0))
        self.safe_var = tk.BooleanVar(value=self.style.safe_mode)
        ctk.CTkCheckBox(sec, text="Safe Mode (guarantee scannability)", variable=self.safe_var, font=FONT_SMALL,
                         command=lambda: self._set_style(safe_mode=self.safe_var.get())).pack(anchor="w", pady=(4, 0))

        # auto palette
        sec = section(parent, "AUTO COLOR PALETTES")
        self.base_hex_var, base_swatch = color_swatch(sec, self.style.fg_color, lambda v: None, "Base hue")
        btn_row = ctk.CTkFrame(sec, fg_color="transparent"); btn_row.pack(fill="x", pady=(6, 6))
        ctk.CTkButton(btn_row, text="🎲 Random", width=90, command=self._randomize_base, fg_color=BG_PANEL,
                      border_width=1, border_color=BORDER, text_color=TEXT_LIGHT).pack(side="left")
        ctk.CTkButton(btn_row, text="Generate Palettes ▸", command=self._gen_palettes, fg_color=NEON_CYAN,
                      text_color="#001014", hover_color="#5cf5ec").pack(side="right")
        self.palette_row = ctk.CTkFrame(sec, fg_color="transparent")
        self.palette_row.pack(fill="x", pady=(4, 0))

        # logo
        sec = section(parent, "LOGO IMAGE")
        self.logo_path_var = tk.StringVar(value="")
        row = ctk.CTkFrame(sec, fg_color="transparent"); row.pack(fill="x")
        ctk.CTkButton(row, text="📁 Choose image…", command=self._choose_logo, fg_color=BG_PANEL,
                      border_width=1, border_color=BORDER, text_color=TEXT_LIGHT).pack(side="left")
        ctk.CTkButton(row, text="✕", width=30, command=self._clear_logo, fg_color=BG_PANEL,
                      border_width=1, border_color=BORDER, text_color=DANGER).pack(side="right")
        self.logo_name_label = ctk.CTkLabel(sec, text="No logo selected", font=FONT_SMALL, text_color=TEXT_DIM)
        self.logo_name_label.pack(anchor="w", pady=(4, 6))

        mode_row = ctk.CTkFrame(sec, fg_color="transparent"); mode_row.pack(fill="x", pady=(2, 8))
        self.logo_mode_var = tk.StringVar(value=self.style.logo_mode)
        ctk.CTkRadioButton(
            mode_row, text="① Logo in middle", value="middle", variable=self.logo_mode_var,
            font=FONT_SMALL, command=self._on_logo_mode_change,
        ).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(
            mode_row, text="② Logo integration (artwork woven into the QR)", value="integration",
            variable=self.logo_mode_var, font=FONT_SMALL, command=self._on_logo_mode_change,
        ).pack(anchor="w", pady=2)

        self.logo_middle_frame = ctk.CTkFrame(sec, fg_color="transparent")
        size_row = ctk.CTkFrame(self.logo_middle_frame, fg_color="transparent"); size_row.pack(fill="x")
        ctk.CTkLabel(size_row, text="Logo size", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.logo_size_slider = ctk.CTkSlider(self.logo_middle_frame, from_=0.10, to=0.35, command=lambda v: self._set_style(logo_size_ratio=float(v)))
        self.logo_size_slider.set(self.style.logo_size_ratio)
        self.logo_size_slider.pack(fill="x", pady=(2, 8))

        backing_row = ctk.CTkFrame(self.logo_middle_frame, fg_color="transparent"); backing_row.pack(fill="x", pady=3)
        ctk.CTkLabel(backing_row, text="Backing plate", font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        self.logo_backing_var = tk.StringVar(value=self.style.logo_backing)
        ctk.CTkOptionMenu(backing_row, values=["none", "rounded", "circle", "square"], variable=self.logo_backing_var,
                           command=lambda v: self._set_style(logo_backing=v), width=140).pack(side="right")
        color_swatch(self.logo_middle_frame, self.style.logo_backing_color, lambda v: self._set_style(logo_backing_color=v), "Plate color")

        thickness_row = ctk.CTkFrame(self.logo_middle_frame, fg_color="transparent"); thickness_row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(thickness_row, text="Plate thickness", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.logo_padding_slider = ctk.CTkSlider(
            self.logo_middle_frame, from_=0, to=40,
            command=lambda v: self._set_style(logo_padding=float(v)),
        )
        self.logo_padding_slider.set(self.style.logo_padding)
        self.logo_padding_slider.pack(fill="x", pady=(2, 8))

        self.logo_integration_frame = ctk.CTkFrame(sec, fg_color="transparent")
        shape_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); shape_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(shape_row, text="Dot shape", font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        self.dot_shape_var = tk.StringVar(value=self.style.dot_shape)
        ctk.CTkOptionMenu(shape_row, values=["circle", "square", "star", "plus"], variable=self.dot_shape_var,
                           command=lambda v: self._set_style(dot_shape=v), width=140).pack(side="right")
        strength_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); strength_row.pack(fill="x")
        ctk.CTkLabel(strength_row, text="Threshold %", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.threshold_slider = ctk.CTkSlider(
            self.logo_integration_frame, from_=0, to=100,
            command=lambda v: self._set_style(threshold_percent=float(v)),
        )
        self.threshold_slider.set(self.style.threshold_percent)
        self.threshold_slider.pack(fill="x", pady=(2, 6))

        darken_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); darken_row.pack(fill="x")
        ctk.CTkLabel(darken_row, text="Darker %", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.darken_slider = ctk.CTkSlider(
            self.logo_integration_frame, from_=0, to=100,
            command=lambda v: self._set_style(darken_percent=float(v)),
        )
        self.darken_slider.set(self.style.darken_percent)
        self.darken_slider.pack(fill="x", pady=(2, 6))

        lighten_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); lighten_row.pack(fill="x")
        ctk.CTkLabel(lighten_row, text="Lighter %", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.lighten_slider = ctk.CTkSlider(
            self.logo_integration_frame, from_=0, to=100,
            command=lambda v: self._set_style(lighten_percent=float(v)),
        )
        self.lighten_slider.set(self.style.lighten_percent)
        self.lighten_slider.pack(fill="x", pady=(2, 6))

        hue_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); hue_row.pack(fill="x")
        ctk.CTkLabel(hue_row, text="Hue shift", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.hue_slider = ctk.CTkSlider(
            self.logo_integration_frame, from_=0, to=360,
            command=lambda v: self._set_style(hue_shift=float(v)),
        )
        self.hue_slider.set(self.style.hue_shift)
        self.hue_slider.pack(fill="x", pady=(2, 6))

        sat_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); sat_row.pack(fill="x")
        ctk.CTkLabel(sat_row, text="Saturation", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        ctk.CTkButton(
            sat_row, text="Reset", width=50, height=20, font=FONT_SMALL, fg_color=BG_PANEL,
            border_width=1, border_color=BORDER, text_color=TEXT_LIGHT, command=self._reset_saturation,
        ).pack(side="right")
        self.saturation_slider = ctk.CTkSlider(
            self.logo_integration_frame, from_=-100, to=100,
            command=lambda v: self._set_style(saturation_shift=float(v)),
        )
        self.saturation_slider.set(self.style.saturation_shift)
        self.saturation_slider.pack(fill="x", pady=(2, 6))

        overlay_row = ctk.CTkFrame(self.logo_integration_frame, fg_color="transparent"); overlay_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(overlay_row, text="Overlay mode", font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        self.overlay_mode_var = tk.StringVar(value=self.style.overlay_mode)
        ctk.CTkOptionMenu(
            overlay_row, values=OVERLAY_MODES, variable=self.overlay_mode_var,
            command=lambda v: self._set_style(overlay_mode=v), width=140,
        ).pack(side="right")

        ctk.CTkLabel(
            self.logo_integration_frame,
            text="Shows the full artwork with no white anywhere — behind the\nmodules, the eyes and the border. Each ink shape samples the\nreal pixels under it: light gets darker by 'Darken %', already-\ndark gets lighter by 'Lighten %'. Hue/Saturation and Overlay\nrecolor the sample first. Safe Mode keeps it scannable.",
            font=FONT_SMALL, text_color=TEXT_DIM, justify="left",
        ).pack(anchor="w")

        self._update_logo_mode_visibility()



        # frame
        sec = section(parent, "FRAME / BORDER")
        frame_row = ctk.CTkFrame(sec, fg_color="transparent"); frame_row.pack(fill="x", pady=3)
        ctk.CTkLabel(frame_row, text="Style", font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        self.frame_style_var = tk.StringVar(value=self.style.frame_style)
        ctk.CTkOptionMenu(frame_row, values=FRAME_STYLES, variable=self.frame_style_var,
                           command=lambda v: self._set_style(frame_style=v), width=140).pack(side="right")
        self.frame_color_var, self.frame_color_swatch = color_swatch(sec, self.style.frame_color, lambda v: self._set_style(frame_color=v), "Frame color")
        self.frame_text_var = self._style_text_entry(sec, "Banner text", self.style.frame_text, "frame_text")
        color_swatch(sec, self.style.frame_text_color, lambda v: self._set_style(frame_text_color=v), "Text color")

        # structure
        sec = section(parent, "STRUCTURE")
        ec_row = ctk.CTkFrame(sec, fg_color="transparent"); ec_row.pack(fill="x", pady=3)
        ctk.CTkLabel(ec_row, text="Error correction", font=FONT_SMALL, text_color=TEXT_DIM, width=110, anchor="w").pack(side="left")
        self.ec_var = tk.StringVar(value=self.style.error_correction)
        ctk.CTkOptionMenu(ec_row, values=ERROR_LEVELS, variable=self.ec_var,
                           command=lambda v: self._set_style(error_correction=v), width=100).pack(side="right")
        qz_row = ctk.CTkFrame(sec, fg_color="transparent"); qz_row.pack(fill="x", pady=3)
        ctk.CTkLabel(qz_row, text="Quiet zone", font=FONT_SMALL, text_color=TEXT_DIM).pack(side="left")
        self.qz_slider = ctk.CTkSlider(sec, from_=1, to=8, number_of_steps=7, command=lambda v: self._set_style(quiet_zone=int(v)))
        self.qz_slider.set(self.style.quiet_zone)
        self.qz_slider.pack(fill="x", pady=(2, 0))

    def _style_text_entry(self, parent, label, default, key):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, font=FONT_SMALL, text_color=TEXT_DIM, width=90, anchor="w").pack(side="left")
        var = tk.StringVar(value=default)
        entry = ctk.CTkEntry(row, textvariable=var, font=FONT_SMALL, width=150)
        entry.pack(side="right")
        var.trace_add("write", lambda *_: self._set_style(**{key: var.get()}))
        return var

    # ------------------------------------------------------------ actions -
    def _apply_preset(self, name):
        preset = PRESETS[name].clone()
        preset.scale_px = self.style.scale_px
        preset.logo_path = self.style.logo_path
        self.style = preset
        self._sync_widgets_from_style()
        self._schedule_refresh()

    def _sync_widgets_from_style(self):
        self.module_var.set(self.style.module_shape)
        self.eye_frame_var.set(self.style.eye_frame_shape)
        self.eye_ball_var.set(self.style.eye_ball_shape)
        self.fg_type_var.set(self.style.fg_type)
        self.transparent_var.set(self.style.transparent_bg)
        self.safe_var.set(self.style.safe_mode)
        self.logo_backing_var.set(self.style.logo_backing)
        self.logo_mode_var.set(self.style.logo_mode)
        self.frame_style_var.set(self.style.frame_style)
        self.frame_text_var.set(self.style.frame_text)
        self.ec_var.set(self.style.error_correction)
        self.qz_slider.set(self.style.quiet_zone)
        self.logo_size_slider.set(self.style.logo_size_ratio)
        self.logo_padding_slider.set(self.style.logo_padding)
        self.threshold_slider.set(self.style.threshold_percent)
        self.darken_slider.set(self.style.darken_percent)
        self.lighten_slider.set(self.style.lighten_percent)
        self.hue_slider.set(self.style.hue_shift)
        self.saturation_slider.set(self.style.saturation_shift)
        self.overlay_mode_var.set(self.style.overlay_mode)
        self.dot_shape_var.set(self.style.dot_shape)
        self._update_logo_mode_visibility()

    def _set_style(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self.style, k, v)
        self._schedule_refresh()

    def _reset_saturation(self):
        self.style.saturation_shift = 0.0
        self.saturation_slider.set(0.0)
        self._schedule_refresh()

    def _randomize_base(self):
        hexv = random_neon_hex()
        self.base_hex_var.set(hexv)

    def _gen_palettes(self):
        for w in self.palette_row.winfo_children():
            w.destroy()
        base = self.base_hex_var.get()
        try:
            palettes = generate_palettes(base)
        except Exception:
            return
        for p in palettes:
            btn = ctk.CTkButton(
                self.palette_row, text=p.name, font=FONT_SMALL, height=26,
                fg_color=p.foreground, text_color=p.background, hover_color=p.accent,
                command=lambda p=p: self._apply_palette(p),
            )
            btn.pack(fill="x", pady=2)

    def _apply_palette(self, palette):
        self.style.fg_color = palette.foreground
        self.style.bg_color = palette.background
        self.style.frame_color = palette.accent
        self.style.eye_frame_color = ""
        self.style.eye_ball_color = ""
        self.fg_color_var.set(palette.foreground)
        self.fg_color_swatch.configure(fg_color=palette.foreground, hover_color=palette.foreground)
        self.bg_color_var.set(palette.background)
        self.bg_color_swatch.configure(fg_color=palette.background, hover_color=palette.background)
        self.frame_color_var.set(palette.accent)
        self.frame_color_swatch.configure(fg_color=palette.accent, hover_color=palette.accent)
        self._schedule_refresh()

    def _choose_logo(self):
        path = filedialog.askopenfilename(
            title="Select logo image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All files", "*.*")],
        )
        if path:
            self.style.logo_path = path
            self.logo_name_label.configure(text=os.path.basename(path), text_color=NEON_CYAN)
            self._schedule_refresh()

    def _clear_logo(self):
        self.style.logo_path = ""
        self.logo_name_label.configure(text="No logo selected", text_color=TEXT_DIM)
        self._schedule_refresh()

    def _on_logo_mode_change(self):
        self.style.logo_mode = self.logo_mode_var.get()
        self._update_logo_mode_visibility()
        self._schedule_refresh()

    def _update_logo_mode_visibility(self):
        if self.logo_mode_var.get() == "middle":
            self.logo_integration_frame.pack_forget()
            self.logo_middle_frame.pack(fill="x")
        else:
            self.logo_middle_frame.pack_forget()
            self.logo_integration_frame.pack(fill="x")

    # ---------------------------------------------------------- rendering -
    def _on_style_change(self, *_):
        self._schedule_refresh()

    def _schedule_refresh(self, *_):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(200, self._do_refresh)

    def _do_refresh(self):
        self._refresh_job = None
        payload = self._current_payload()
        if not payload:
            self.preview_label.configure(image=None, text="Enter data to preview…")
            self.status_label.configure(text="")
            self.info_label.configure(text="")
            return
        preview_style = self.style.clone()
        preview_style.scale_px = 480
        try:
            img = ex.generate_png(payload, preview_style)
        except Exception as exc:
            self.status_label.configure(text=f"⚠ {exc}", text_color=DANGER)
            return

        checker = self._checkerboard(img.size)
        composed = Image.alpha_composite(checker, img)
        ctk_img = ctk.CTkImage(light_image=composed, dark_image=composed, size=(420, composed.height * 420 // composed.width))
        self.preview_label.configure(image=ctk_img, text="")
        self.preview_ctkimage = ctk_img

        safe, ratio = scan_check(self.style)
        if safe or self.style.safe_mode:
            self.status_label.configure(text=f"● SCAN-SAFE  (contrast {ratio:.1f}:1)", text_color=OK_GREEN)
        else:
            self.status_label.configure(text=f"⚠ LOW CONTRAST — may not scan  ({ratio:.1f}:1)", text_color=DANGER)

        _, version = ex.generate_matrix(payload, self.style)
        self.info_label.configure(text=f"Version {version} · {len(payload)} chars · EC {self.style.error_correction}")

    @staticmethod
    def _checkerboard(size, cell=12):
        from PIL import ImageDraw

        w, h = size
        img = Image.new("RGBA", size, (30, 30, 40, 255))
        draw = ImageDraw.Draw(img)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if (x // cell + y // cell) % 2 == 0:
                    draw.rectangle((x, y, x + cell, y + cell), fill=(40, 40, 52, 255))
        return img

    # ------------------------------------------------------------- export -
    def _export_style(self):
        s = self.style.clone()
        s.scale_px = int(self.res_var.get().split(" ")[0])
        return s

    def export_png(self):
        payload = self._current_payload()
        if not payload:
            messagebox.showwarning("NeoQR", "Enter some data first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            ex.save_png(payload, self._export_style(), path)
            messagebox.showinfo("NeoQR", f"Exported PNG:\n{path}")
        except Exception as exc:
            messagebox.showerror("NeoQR", str(exc))

    def export_svg(self):
        payload = self._current_payload()
        if not payload:
            messagebox.showwarning("NeoQR", "Enter some data first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG vector", "*.svg")])
        if not path:
            return
        try:
            ex.save_svg(payload, self._export_style(), path)
            messagebox.showinfo("NeoQR", f"Exported SVG:\n{path}")
        except Exception as exc:
            messagebox.showerror("NeoQR", str(exc))


def main():
    app = NeoQRApp()
    app.mainloop()


if __name__ == "__main__":
    main()
