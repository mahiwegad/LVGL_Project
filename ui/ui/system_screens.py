"""
system_screens.py - SYSTEM (diagnostics), MAINTENANCE (pump/fluid), POWER and
ABOUT screens.

These four screens complete the home menu. They all share the same shell -
back button, title, one-line explanation and the live temperature chip - so the
operator never has to relearn a screen, and they are all laid out for the
instrument's 1280x720 panel (see ui/theme.py for the layout scale).

POWER is the app's way out: the instrument window has no title bar and no
window buttons, so shutting down, rebooting, suspending - or just closing the
app - all live here, each behind a confirmation dialog.

In SIMULATION_MODE none of the power commands are executed (that would shut
down the development machine); the exact command that WOULD run is printed and
shown in a notification, so the action can still be verified end to end.
"""

import os
import platform
import subprocess
import sys
import threading

import customtkinter as ctk

from Hardware.config import SIMULATION_MODE
from ui.hardware_actions import reverse, flow_water
from ui.theme import (
    c as tc,
    card as theme_card,
    is_dark,
    sp,
    font as theme_font,
    ui_scale,
)

APP_NAME = "Biospectrometer Analyzer"
APP_VERSION = "2.0"
BUILD_NAME = "main2026"

# Who made the instrument. The ABOUT screen is the operator's only place to
# find the manufacturer, so the company and its public address lead the page
# and the software details follow underneath them.
COMPANY_NAME = "Biospectronics Pvt. Ltd."
COMPANY_URL = "https://www.biospectronics.in/"
COMPANY_TAGLINE = "Manufacturer of the Biospectrometer Analyzer"

# What each POWER entry does, per platform. Lists are passed straight to
# subprocess (never through a shell), so there is no quoting/escaping surface.
POWER_ACTIONS = {
    "shutdown": {
        "title": "Shut down",
        "hint": "Power the instrument off completely.",
        "detail": "The instrument will power off. Switch it on again to use it.",
        "windows": [["shutdown", "/s", "/t", "0"]],
        "linux": [
            ["systemctl", "poweroff"],
            ["shutdown", "-h", "now"],
            ["sudo", "-n", "systemctl", "poweroff"],
        ],
    },
    "reboot": {
        "title": "Reboot",
        "hint": "Restart the instrument software and hardware.",
        "detail": "The instrument will restart. The software starts again automatically.",
        "windows": [["shutdown", "/r", "/t", "0"]],
        "linux": [
            ["systemctl", "reboot"],
            ["shutdown", "-r", "now"],
            ["sudo", "-n", "systemctl", "reboot"],
        ],
    },
    "sleep": {
        "title": "Standby / Sleep",
        "hint": "Suspend the instrument; touch the screen to wake it.",
        "detail": "The instrument goes to sleep. Touch the screen or press the power key to wake it.",
        "windows": [["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]],
        "linux": [
            ["systemctl", "suspend"],
            ["loginctl", "suspend"],
            ["sudo", "-n", "systemctl", "suspend"],
        ],
    },
}


class SystemScreensMixin:
    """SystemScreensMixin - SYSTEM / MAINTENANCE / POWER / ABOUT."""

    # ------------------------------------------------------------------
    # Shared shell
    # ------------------------------------------------------------------
    def _utility_screen(self, title, subtitle, frame_key):
        """A titled screen with a back button and the temperature chip."""
        self.clear_frames()
        frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=sp(18), pady=(sp(14), sp(6)))
        header.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            header, text="←", width=sp(52), height=sp(46),
            font=theme_font(18, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(10),
            border_width=1, border_color=tc("border"),
            command=self.show_main_menu,
        ).grid(row=0, column=0, sticky="w")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", padx=sp(14))
        ctk.CTkLabel(title_box, text=title, font=theme_font(23, bold=True),
                     text_color=tc("text")).pack(anchor="w")
        ctk.CTkLabel(title_box, text=subtitle, font=theme_font(12),
                     text_color=tc("text_muted")).pack(anchor="w")

        self._temperature_chip(header).grid(row=0, column=3, sticky="e")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=sp(18), pady=(0, sp(18)))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.frames[frame_key] = frame
        return frame, body

    def _temperature_chip(self, parent):
        """The pill showing 'Temperature Stabilizing' / 'Temperature : 37.0 °C'."""
        chip = ctk.CTkFrame(parent, fg_color=tc("surface_sunken"), corner_radius=sp(10),
                            border_width=1, border_color=tc("border"))
        model = getattr(self, 'temp_warmup', None)
        settled = bool(model is not None and model.is_done)
        self.temp_chip_dot = ctk.CTkLabel(
            chip, text="●", font=theme_font(13, bold=True),
            text_color=tc("success" if settled else "warning"))
        self.temp_chip_dot.pack(side="left", padx=(sp(10), sp(4)), pady=sp(6))
        self.temp_chip_label = ctk.CTkLabel(
            chip,
            text=self.temperature_status_text() if model is not None else "Temperature",
            font=theme_font(13, bold=True), text_color=tc("text"))
        self.temp_chip_label.pack(side="left", padx=(0, sp(12)), pady=sp(6))
        return chip

    def _card(self, parent, row=0, column=0, columnspan=1, sticky="nsew",
              padx=0, pady=0, radius=16):
        card = ctk.CTkFrame(parent, **theme_card(radius=sp(radius)))
        card.grid(row=row, column=column, columnspan=columnspan, sticky=sticky,
                  padx=sp(padx), pady=sp(pady))
        return card

    # ------------------------------------------------------------------
    # SYSTEM - diagnostics
    # ------------------------------------------------------------------
    def show_system_screen(self):
        """Instrument status: firmware, connection, software and the panel."""
        self._screen_rebuild = self.show_system_screen
        frame, body = self._utility_screen(
            "SYSTEM", "Firmware, connection and software status", "system")

        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1, uniform="sys")
        body.grid_columnconfigure(1, weight=1, uniform="sys")

        left = self._card(body, row=0, column=0, padx=(0, 6), pady=0)
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Connection", font=theme_font(15, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, sticky="w",
                                                 padx=sp(16), pady=(sp(14), sp(8)))
        self.system_status_label = ctk.CTkLabel(
            left,
            text="Simulation mode" if SIMULATION_MODE else "Firmware: not checked",
            font=theme_font(14), text_color=tc("text_muted"), justify="left",
            wraplength=sp(430))
        self.system_status_label.grid(row=1, column=0, sticky="w", padx=sp(16))

        self.system_check_btn = ctk.CTkButton(
            left, text="Check connection", height=sp(52),
            font=theme_font(15, bold=True),
            fg_color=tc("accent"), hover_color=tc("accent_hover"),
            text_color=tc("text_on_accent"), corner_radius=sp(12),
            command=self.check_system_connection)
        self.system_check_btn.grid(row=2, column=0, sticky="ew", padx=sp(16),
                                   pady=(sp(14), sp(16)))

        right = self._card(body, row=0, column=1, padx=(6, 0), pady=0)
        right.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(right, text="Software", font=theme_font(15, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, columnspan=2,
                                                 sticky="w", padx=sp(16),
                                                 pady=(sp(14), sp(8)))
        rows = [
            ("Application", f"{APP_NAME} {APP_VERSION}"),
            ("Build", BUILD_NAME),
            ("Python", platform.python_version()),
            ("Hardware mode", "Simulation" if SIMULATION_MODE else "Instrument"),
        ]
        for index, (key, value) in enumerate(rows, start=1):
            ctk.CTkLabel(right, text=key, font=theme_font(13),
                         text_color=tc("text_muted")).grid(
                row=index, column=0, sticky="w", padx=(sp(16), sp(10)), pady=sp(3))
            ctk.CTkLabel(right, text=value, font=theme_font(13, bold=True),
                         text_color=tc("text")).grid(
                row=index, column=1, sticky="w", padx=(0, sp(16)), pady=sp(3))

        ctk.CTkLabel(right, text="Appearance", font=theme_font(15, bold=True),
                     text_color=tc("text")).grid(row=len(rows) + 1, column=0,
                                                 columnspan=2, sticky="w",
                                                 padx=sp(16), pady=(sp(16), sp(8)))
        self.theme_switch = ctk.CTkSegmentedButton(
            right, values=["☀  Light", "☾  Dark"], command=self._on_theme_toggle,
            fg_color=tc("btn_neutral"), selected_color=tc("accent"),
            selected_hover_color=tc("accent_hover"), unselected_color=tc("btn_neutral"),
            unselected_hover_color=tc("btn_neutral_hover"), text_color=tc("text"),
            font=theme_font(12, bold=True), corner_radius=sp(10), height=sp(34))
        self.theme_switch.set("☾  Dark" if is_dark() else "☀  Light")
        self.theme_switch.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w",
                               padx=sp(16), pady=(0, sp(16)))

        self.polish_screen(frame)
        return frame

    def check_system_connection(self):
        """Ask the board for its status without blocking the UI."""
        if SIMULATION_MODE:
            self.system_status_label.configure(
                text="Simulation mode - no board is connected.\nSet "
                     "SIMULATION_MODE = False in Hardware/config.py to talk to the STM32.",
                text_color=tc("text_muted"))
            self.show_notification("Simulation mode: board not queried")
            return

        self.system_check_btn.configure(state="disabled", text="Checking...")

        def _worker():
            try:
                from Hardware.stm32_backend import firmware_status, send_ping
                alive = send_ping(attempts=1, timeout=1.5)
                state, raw = firmware_status(timeout=1.5)
                if not alive:
                    text = "No answer from the STM32 board."
                else:
                    words = {0: "idle", 1: "measuring", 2: "cleaning", 3: "aligning"}
                    text = f"Board answering. State: {words.get(state, raw or 'unknown')}."
            except Exception as exc:                     # noqa: BLE001 - reported
                text = f"Check failed: {exc}"
            self.ui_post(self._system_check_done, text)

        threading.Thread(target=_worker, daemon=True).start()

    def _system_check_done(self, text):
        try:
            self.system_status_label.configure(
                text=text,
                text_color=tc("text") if "answering" in text else tc("danger"))
            self.system_check_btn.configure(state="normal", text="Check connection")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # MAINTENANCE - pump / fluid controls (moved off the old SYSTEM screen)
    # ------------------------------------------------------------------
    def show_maintenance_screen(self):
        """Pump and fluid controls: reverse, flow, fill DI, clean the flow cell."""
        self._screen_rebuild = self.show_maintenance_screen
        frame, body = self._utility_screen(
            "MAINTENANCE", "Pump and fluid controls", "maintenance")

        card = self._card(body, row=0, column=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(2, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(card, text="Pump / Fluid Controls",
                     font=theme_font(16, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, columnspan=3,
                                                 sticky="w", padx=sp(18),
                                                 pady=(sp(16), sp(2)))
        ctk.CTkLabel(card,
                     text="Prime and rinse the tubing. Run these with the sample "
                          "probe in DI water or cleaning solution.",
                     font=theme_font(12), text_color=tc("text_muted"),
                     wraplength=sp(600), justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", padx=sp(18), pady=(0, sp(10)))

        entries = (
            ("Reverse", "Run the pump backwards.", reverse, tc("btn_neutral"),
             tc("btn_neutral_hover"), tc("btn_text")),
            ("Flow water", "Flow water through the flow cell.", flow_water,
             tc("btn_neutral"), tc("btn_neutral_hover"), tc("btn_text")),
            ("Fill DI", "Fill the line with DI water.", flow_water,
             tc("btn_neutral"), tc("btn_neutral_hover"), tc("btn_text")),
        )
        for index, (text, hint, command, fg, hover, text_color) in enumerate(entries):
            box = ctk.CTkFrame(card, fg_color="transparent")
            box.grid(row=2, column=index, sticky="nsew", padx=sp(10), pady=sp(10))
            btn = ctk.CTkButton(
                box, text=text, height=sp(66), font=theme_font(15, bold=True),
                fg_color=fg, hover_color=hover, text_color=text_color,
                corner_radius=sp(14), border_width=1, border_color=tc("border"),
                command=command)
            btn.pack(fill="x")
            ctk.CTkLabel(box, text=hint, font=theme_font(11),
                         text_color=tc("text_muted"), wraplength=sp(260),
                         justify="left").pack(anchor="w", pady=(sp(6), 0))

        clean_btn = ctk.CTkButton(
            card, text="Clean flow cell", height=sp(64), font=theme_font(16, bold=True),
            fg_color=tc("accent"), hover_color=tc("accent_hover"),
            text_color=tc("text_on_accent"), corner_radius=sp(14),
            command=self._maintenance_clean)
        clean_btn.grid(row=3, column=0, columnspan=3, sticky="ew",
                       padx=sp(10), pady=(sp(4), sp(16)))

        self.polish_screen(frame)
        return frame

    def _maintenance_clean(self):
        """Run the flow-cell clean from MAINTENANCE (never blocks the UI)."""
        self.show_notification("Cleaning the flow cell...")

        def _worker():
            try:
                ok = clean()
            except Exception as exc:                     # noqa: BLE001 - reported
                print(f"[MAINT] clean failed: {exc}")
                ok = False
            self.ui_post(
                self.show_notification,
                "Flow cell cleaned" if ok else "Clean failed - check the flow cell",
                error=not ok)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # POWER - shut down / reboot / standby / close the app
    # ------------------------------------------------------------------
    def show_power_screen(self):
        """The instrument's exit screen: the window has no title bar."""
        self._screen_rebuild = self.show_power_screen
        frame, body = self._utility_screen(
            "POWER", "Shut down, reboot or suspend the instrument", "power")

        card = self._card(body, row=0, column=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(2, weight=1)
        card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(card, text="Power", font=theme_font(16, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, columnspan=3,
                                                 sticky="w", padx=sp(18),
                                                 pady=(sp(16), sp(8)))
        for index, kind in enumerate(("shutdown", "reboot", "sleep")):
            spec = POWER_ACTIONS[kind]
            box = ctk.CTkFrame(card, fg_color="transparent")
            box.grid(row=1, column=index, sticky="nsew", padx=sp(12), pady=sp(12))
            shade = {"shutdown": "danger", "reboot": "warning",
                     "sleep": "accent"}.get(kind, "accent")
            btn = ctk.CTkButton(
                box, text=spec["title"], height=sp(84),
                font=theme_font(17, bold=True),
                fg_color=tc(shade), hover_color=tc(shade + "_hover") if shade != "accent"
                else tc("accent_hover"),
                text_color=tc("text_on_accent"), corner_radius=sp(16),
                command=lambda k=kind: self.request_power_action(k))
            btn.pack(fill="x")
            ctk.CTkLabel(box, text=spec["hint"], font=theme_font(12),
                         text_color=tc("text_muted"), wraplength=sp(300),
                         justify="left").pack(anchor="w", pady=(sp(8), 0))

        ctk.CTkLabel(card,
                     text="Close application only (leaves the instrument powered on) "
                          "is available below.",
                     font=theme_font(12), text_color=tc("text_muted")).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=sp(18), pady=(sp(4), sp(2)))
        ctk.CTkButton(
            card, text="Close application", height=sp(52),
            font=theme_font(15, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(12),
            border_width=1, border_color=tc("border"),
            command=self.request_close_application).grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=sp(18),
            pady=(sp(2), sp(16)))

        self.polish_screen(frame)
        return frame

    def power_command_preview(self, kind):
        """The exact command line POWER would run on this machine (for tests)."""
        spec = POWER_ACTIONS.get(kind)
        if not spec:
            return None
        key = "windows" if os.name == "nt" else "linux"
        return spec[key][0]

    def request_power_action(self, kind):
        """Confirm, then run one POWER action."""
        spec = POWER_ACTIONS.get(kind)
        if spec is None:
            return
        argv = self.power_command_preview(kind)
        command_text = " ".join(argv) if argv else "n/a"
        self.show_confirm_dialog(
            spec["title"],
            f"{spec['detail']}\n\nMachine: {platform.node() or 'this instrument'}\n"
            f"Command: {command_text}",
            on_confirm=lambda k=kind: self.run_power_action(k))

    def request_close_application(self):
        """Close the app but leave the instrument running."""
        self.show_confirm_dialog(
            "Close application",
            "Close the analyzer software?\n\nThe instrument stays powered on; "
            "start the software again to continue measuring.",
            on_confirm=self.on_closing)

    def run_power_action(self, kind):
        """Execute a POWER action, falling back through the platform's options.

        Simulation mode never executes anything: shutting down the development
        machine because a button was pressed would be a nasty surprise, so the
        command is logged instead (and the UI reports it).
        """
        spec = POWER_ACTIONS.get(kind)
        if spec is None:
            return
        key = "windows" if os.name == "nt" else "linux"
        candidates = list(spec[key])
        if SIMULATION_MODE or str(os.environ.get("BIO_NO_POWER", "")) == "1":
            print(f"[POWER] simulation: would run {candidates[0]}")
            self.show_notification(
                f"Simulation mode: would run '{' '.join(candidates[0])}'")
            return

        def _worker():
            errors = []
            for argv in candidates:
                try:
                    result = subprocess.run(argv, capture_output=True, text=True,
                                            timeout=20)
                    if result.returncode == 0:
                        print(f"[POWER] {kind} via {' '.join(argv)}")
                        return
                    errors.append(f"{' '.join(argv)} -> rc={result.returncode} "
                                  f"{(result.stderr or '').strip()[:120]}")
                except FileNotFoundError:
                    errors.append(f"{argv[0]} not found")
                except Exception as exc:                  # noqa: BLE001 - reported
                    errors.append(f"{' '.join(argv)} -> {exc}")
                print(f"[POWER] {' '.join(argv)} failed, trying the next option")
            detail = "; ".join(errors) if errors else "no command available"
            print(f"[POWER] {kind} failed: {detail}")
            self.ui_post(self.show_notification,
                         f"Could not {kind} the instrument", error=True)

        self.show_notification(f"{spec['title']} requested...")
        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Confirmation dialog (the app's own - messagebox has no theming/touch size)
    # ------------------------------------------------------------------
    def _dialog_geometry(self, card, wrap_labels=(), max_width=None):
        """Size a dialog to the content it actually has to show.

        A fixed box plus self-wrapping text is only correct for the font it was
        measured with. On the instrument the three POWER confirmations came out
        with their message cut off at BOTH edges - the box was 680x320 whatever
        the text did. So the card is built hidden, measured, and the popup is
        opened at the size its own content asks for, clamped to the panel, with
        each body label re-wrapped to the width the dialog really got. That is
        the same recipe as the warm-up warning, which reads correctly on the
        same panel.
        """
        def _measure():
            try:
                card.update_idletasks()
                return (int(card.winfo_reqwidth()) + sp(16),
                        int(card.winfo_reqheight()) + sp(16))
            except Exception:
                return sp(620), sp(300)

        try:
            panel_w = int(self.winfo_width()) or 1280
            panel_h = int(self.winfo_height()) or 720
            panel_x, panel_y = self.winfo_rootx(), self.winfo_rooty()
        except Exception:
            panel_w, panel_h, panel_x, panel_y = 1280, 720, 0, 0

        limit_w = panel_w - sp(24)
        if max_width:
            limit_w = min(limit_w, int(max_width))
        need_w, need_h = _measure()
        width = max(sp(480), min(need_w, limit_w))
        # Wrap the text to the width the dialog actually received, so a wider
        # font on the Pi WRAPS the message instead of running out of the box.
        for label in wrap_labels:
            try:
                label.configure(wraplength=max(sp(240), width - sp(64)))
            except Exception:
                pass
        need_w, need_h = _measure()
        height = max(sp(220), min(need_h, panel_h - sp(24)))
        px = panel_x + max(0, (panel_w - width) // 2)
        py = panel_y + max(0, (panel_h - height) // 2)
        # Nothing may open off the visible screen: a window that was handed over
        # minimised reports its origin as (-32000, -32000).
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            px = max(0, min(px, max(0, screen_w - width)))
            py = max(0, min(py, max(0, screen_h - height)))
        except Exception:
            px, py = max(0, px), max(0, py)
        return width, height, px, py

    def show_confirm_dialog(self, title, message, on_confirm=None):
        """A touch-sized Yes/No dialog, sized to the text it has to show.

        Returns the popup. See _dialog_geometry for why the size is measured
        rather than fixed.
        """
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        try:
            popup.withdraw()
        except Exception:
            pass
        try:
            popup.configure(fg_color=tc("window_bg"))
        except Exception:
            pass

        card = ctk.CTkFrame(popup, **theme_card(radius=16))
        card.pack(fill="both", expand=True, padx=sp(8), pady=sp(8))
        card.grid_columnconfigure(0, weight=1)
        title_label = ctk.CTkLabel(card, text=title, font=theme_font(21, bold=True),
                                   text_color=tc("text"), justify="left",
                                   anchor="w")
        title_label.grid(row=0, column=0, sticky="ew", padx=sp(20),
                         pady=(sp(16), sp(4)))
        # The message wraps: its wrap width is matched to the dialog's final
        # width below, once that is known.
        body_label = ctk.CTkLabel(card, text=message, font=theme_font(13),
                                  text_color=tc("text_muted"), justify="left",
                                  anchor="w", wraplength=sp(600))
        body_label.grid(row=1, column=0, sticky="ew", padx=sp(20))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=sp(20),
                     pady=(sp(14), sp(16)))

        def _close():
            try:
                popup.grab_release()
            except Exception:
                pass
            try:
                popup.destroy()
            except Exception:
                pass

        def _yes():
            _close()
            if callable(on_confirm):
                on_confirm()

        ctk.CTkButton(buttons, text="No", width=sp(150), height=sp(56),
                      font=theme_font(17, bold=True), fg_color=tc("btn_neutral"),
                      hover_color=tc("btn_neutral_hover"), text_color=tc("btn_text"),
                      corner_radius=sp(12), command=_close).pack(side="left")
        ctk.CTkButton(buttons, text="Yes", width=sp(150), height=sp(56),
                      font=theme_font(17, bold=True), fg_color=tc("accent"),
                      hover_color=tc("accent_hover"),
                      text_color=tc("text_on_accent"), corner_radius=sp(12),
                      command=_yes).pack(side="right")

        # Open at the size the text needs (760 px is as wide as a message is
        # allowed to get: past that the eye loses the line).
        width, height, px, py = self._dialog_geometry(
            card, (title_label, body_label), max_width=sp(760))
        try:
            popup.geometry(f"{width}x{height}+{px}+{py}")
            popup.deiconify()
            popup.lift()
        except Exception:
            pass
        try:
            popup.bind("<Escape>", lambda _e: _close())
            popup.grab_set()
            popup.focus_set()
        except Exception:
            pass
        self.polish_screen(popup)
        return popup

    # ------------------------------------------------------------------
    # ABOUT
    # ------------------------------------------------------------------
    def show_about_screen(self):
        """Who built the instrument: company, website, then the software build."""
        self._screen_rebuild = self.show_about_screen
        frame, body = self._utility_screen(
            "ABOUT", "Manufacturer and software information", "about")

        card = self._card(body, row=0, column=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(card, text=COMPANY_NAME, font=theme_font(24, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, sticky="w",
                                                 padx=sp(22), pady=(sp(18), 0))
        ctk.CTkLabel(card, text=COMPANY_TAGLINE, font=theme_font(14),
                     text_color=tc("text_muted")).grid(
            row=1, column=0, sticky="w", padx=sp(22), pady=(sp(2), 0))

        # The company's public address gets its own tinted strip: it is the one
        # line an operator reads out loud to a service engineer.
        site = ctk.CTkFrame(card, fg_color=tc("accent_soft"), corner_radius=sp(12))
        site.grid(row=2, column=0, sticky="ew", padx=sp(22), pady=(sp(14), 0))
        site.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(site, text="Website", font=theme_font(13),
                     text_color=tc("text_muted")).grid(
            row=0, column=0, sticky="w", padx=(sp(16), sp(14)), pady=sp(12))
        ctk.CTkLabel(site, text=COMPANY_URL, font=theme_font(18, bold=True),
                     text_color=tc("accent_text")).grid(
            row=0, column=1, sticky="w", padx=(0, sp(16)), pady=sp(12))

        # Two columns keep the whole page readable without scrolling.
        columns = ctk.CTkFrame(card, fg_color="transparent")
        columns.grid(row=3, column=0, sticky="ew", padx=sp(22), pady=(sp(16), 0))
        for col in range(2):
            columns.grid_columnconfigure(col, weight=1, uniform="about")

        try:
            panel = (f"{self.winfo_screenwidth()} x {self.winfo_screenheight()} px"
                     f"   (layout scale {ui_scale():.2f})")
        except Exception:
            panel = "unknown"
        try:
            db_name = os.path.basename(str(self.db_manager.db_name))
        except Exception:
            db_name = "jsrt_parameters.db"

        self._about_rows(columns, 0, "Software", [
            ("Product", APP_NAME),
            ("Version", f"{APP_VERSION}   ·   build {BUILD_NAME}"),
            ("Panel", panel),
        ])
        self._about_rows(columns, 1, "Instrument", [
            ("Hardware", "simulation" if SIMULATION_MODE
                         else "STM32 + AS7341 sensors"),
            ("Database", db_name),
            ("Python", platform.python_version()),
        ])

        ctk.CTkLabel(card,
                     text="For service, quote the version and build above and "
                          "describe what the instrument was doing when the "
                          "problem happened.",
                     font=theme_font(12), text_color=tc("text_muted"),
                     wraplength=sp(900), justify="left").grid(
            row=4, column=0, sticky="w", padx=sp(22), pady=(sp(20), sp(18)))

        self.polish_screen(frame)
        return frame

    @staticmethod
    def _about_rows(parent, column, title, rows):
        """A titled key/value block for the ABOUT screen."""
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=0, column=column, sticky="new",
                 padx=(0, sp(16)) if column == 0 else (sp(16), 0))
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(box, text=title, font=theme_font(15, bold=True),
                     text_color=tc("text")).grid(row=0, column=0, columnspan=2,
                                                 sticky="w", pady=(0, sp(6)))
        for index, (key, value) in enumerate(rows, start=1):
            ctk.CTkLabel(box, text=key, font=theme_font(13),
                         text_color=tc("text_muted")).grid(
                row=index, column=0, sticky="w", padx=(0, sp(14)), pady=sp(4))
            ctk.CTkLabel(box, text=str(value), font=theme_font(13, bold=True),
                         text_color=tc("text"), wraplength=sp(520),
                         justify="left").grid(row=index, column=1, sticky="w",
                                              pady=sp(4))
        return box
