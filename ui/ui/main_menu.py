"""
main_menu.py - Home screen (six entries), the warm-up gate and the
water-stabilization startup flow.

Layout contract: this screen is designed for the instrument's 1280x720 panel.
Font sizes and heights are written in PANEL PIXELS (see ui/theme.py), spacing
goes through ``sp()`` so a bigger development monitor simply scales the result.

The screen has no title bar and no big heading (both were removed to give the
working area back to the operator):

  row 0  top bar          - theme switch (light/dark) on the right
  row 1  status card      - warm-up progress and the flow-cell temperature
  row 2  six menu cards   - TEST RESULT SYSTEM MAINTENANCE POWER ABOUT

Warming up: the flow cell needs ten minutes from GUI start. Everything is
reachable during that window; only TEST asks "are you sure?" first, through the
modal warning built here.
"""

import customtkinter as ctk
import threading
import time

from ui.theme import c as tc, card as theme_card, is_dark, sp, font as theme_font
from ui.temperature import TemperatureStabilization, minutes_left

class MainMenuMixin:
    """MainMenuMixin - Home screen, warm-up gate and the stabilization flow."""

    # The warm-up readout (progress bar, countdown, temperature) is refreshed
    # once a second on an app-level timer: it keeps counting while the operator
    # is on another screen, and the measurement header reads the same model.
    WARMUP_TICK_MS = 1000

    # ------------------------------------------------------------------
    # Warm-up gate
    # ------------------------------------------------------------------
    def start_temperature_warmup(self):
        """Start the ten-minute warm-up window (called once, at GUI start)."""
        if getattr(self, 'temp_warmup', None) is None:
            self.temp_warmup = TemperatureStabilization()
        self.stabilization_complete = False
        self._warmup_tick()

    def warmup_model(self):
        """The shared warm-up model (created on first use if needed)."""
        model = getattr(self, 'temp_warmup', None)
        if model is None:
            model = self.temp_warmup = TemperatureStabilization()
        return model

    def temperature_status_text(self):
        """Header text for the temperature chip (main menu AND measurement)."""
        return self.warmup_model().status_text()

    def temperature_status_tone(self):
        """Chip tone: amber while stabilizing, green once the reading is live."""
        return "ok" if self.warmup_model().is_done else "busy"

    def temperature_warning_needed(self):
        """True while the warm-up window is still running."""
        model = getattr(self, 'temp_warmup', None)
        if model is None:
            return False
        return not model.is_done

    def request_test_screen(self):
        """TEST entry point: warn during warm-up, then go to the test list."""
        if self.temperature_warning_needed():
            self.show_temperature_warning(self.show_test_screen)
        else:
            self.show_test_screen()

    def _warmup_tick(self):
        """One-second app-level warm-up tick (safe on every screen)."""
        if getattr(self, '_closing', False):
            return
        model = getattr(self, 'temp_warmup', None)
        if model is not None:
            self.stabilization_complete = model.is_done
        try:
            self._paint_warmup()
        except Exception as exc:
            print(f"[WARMUP] could not paint the status card: {exc}")
        self._paint_temperature_chip()
        try:
            self.after(self.WARMUP_TICK_MS, self._warmup_tick)
        except Exception:
            pass

    @staticmethod
    def _alive(widget):
        try:
            return widget is not None and widget.winfo_exists()
        except Exception:
            return False

    def _paint_warmup(self):
        """Draw the warm-up state onto the home screen's status card."""
        model = getattr(self, 'temp_warmup', None)
        label = getattr(self, 'temp_status_label', None)
        if model is None or not self._alive(label):
            return
        if model.is_done:
            label.configure(text="Temperature Stabilized", text_color=tc("success"))
            dot = getattr(self, 'temp_status_dot', None)
            if self._alive(dot):
                dot.configure(text_color=tc("success"))
            value = getattr(self, 'temp_value_label', None)
            if self._alive(value):
                value.configure(text=f"{model.display_temp:.1f} °C", text_color=tc("text"))
            unit = getattr(self, 'temp_unit_label', None)
            if self._alive(unit):
                unit.configure(text="flow cell ready")
            caption = getattr(self, 'progress_label', None)
            if self._alive(caption) and not getattr(self, '_hw_failed', False):
                caption.configure(text="Ready to measure - every screen is available.")
            bar = getattr(self, 'stabilization_progress', None)
            if self._alive(bar):
                # A full bar in the brand colour reads as "something happened",
                # so the finished bar turns green: the same colour as the
                # headline that says the flow cell is ready.
                try:
                    bar.configure(progress_color=tc("success"))
                except Exception:
                    pass
                bar.set(1.0)
        else:
            label.configure(text="Temperature Stabilization in progress",
                            text_color=tc("text"))
            dot = getattr(self, 'temp_status_dot', None)
            if self._alive(dot):
                dot.configure(text_color=tc("warning"))
            value = getattr(self, 'temp_value_label', None)
            if self._alive(value):
                # Real MM:SS. This used to round the minutes separately from the
                # seconds, so 90 s left displayed as "2:30" instead of "01:30".
                value.configure(text=model.countdown_text(),
                                text_color=tc("text_muted"))
            unit = getattr(self, 'temp_unit_label', None)
            if self._alive(unit):
                unit.configure(text="time remaining")
            caption = getattr(self, 'progress_label', None)
            if self._alive(caption) and not getattr(self, '_hw_failed', False):
                caption.configure(
                    text="Keep the instrument switched on - ready to measure in "
                         f"{model.minutes_left()} minute(s).")
            bar = getattr(self, 'stabilization_progress', None)
            if self._alive(bar):
                try:
                    bar.configure(progress_color=tc("accent"))
                except Exception:
                    pass
                bar.set(model.progress)

    def _paint_temperature_chip(self):
        """Mirror the temperature into the measurement screen's header chip."""
        chip = getattr(self, 'temp_chip_label', None)
        if not self._alive(chip):
            return
        model = getattr(self, 'temp_warmup', None)
        if model is None:
            return
        dot = getattr(self, 'temp_chip_dot', None)
        dot_key = "success" if model.is_done else "warning"
        try:
            chip.configure(text=model.status_text(), text_color=tc("text"))
            if self._alive(dot):
                dot.configure(text_color=tc(dot_key))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Warm-up warning dialog
    # ------------------------------------------------------------------
    def _warning_dialog_size(self, card):
        """Size the warm-up warning to its content, clamped to the panel.

        A fixed box cannot work here: the very same copy is taller in the font
        the Raspberry Pi resolves (DejaVu Sans) than on a desktop, and the old
        hard-coded 640x260 cut the headline and the Yes/No buttons in half on
        the real instrument. Measuring the built card instead means the dialog
        is always exactly as big as what it has to say.
        """
        try:
            card.update_idletasks()
            need_w = int(card.winfo_reqwidth()) + sp(16)
            need_h = int(card.winfo_reqheight()) + sp(16)
        except Exception:
            need_w, need_h = sp(640), sp(300)
        try:
            panel_w = int(self.winfo_width()) or 1280
            panel_h = int(self.winfo_height()) or 720
        except Exception:
            panel_w, panel_h = 1280, 720
        width = max(sp(560), min(need_w, panel_w - sp(24)))
        height = max(sp(250), min(need_h, panel_h - sp(24)))
        try:
            px = self.winfo_rootx() + max(0, (panel_w - width) // 2)
            py = self.winfo_rooty() + max(0, (panel_h - height) // 2)
        except Exception:
            px = py = sp(80)
        return width, height, max(0, px), max(0, py)

    def show_temperature_warning(self, on_confirm=None):
        """Modal 'warm-up still running' warning with Yes / No.

        Yes  -> dismiss and continue to the test screens.
        No   -> dismiss and stay exactly where the operator was.
        """
        # Only ever one at a time.
        existing = getattr(self, 'temp_warning_dialog', None)
        if self._alive(existing):
            existing.lift()
            return existing

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        # Built while hidden, then placed at the size its own content needs (see
        # _warning_dialog_size), so it can never open too small for its text.
        try:
            popup.withdraw()
        except Exception:
            pass
        self.temp_warning_dialog = popup

        card = ctk.CTkFrame(popup, **theme_card(radius=16))
        card.pack(fill="both", expand=True, padx=sp(8), pady=sp(8))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=sp(20), pady=(sp(16), 0))
        ctk.CTkLabel(head, text="●", font=theme_font(15, bold=True),
                     text_color=tc("warning")).pack(side="left", padx=(0, sp(8)))
        # wraplength: a wider font on the Pi wraps the headline instead of
        # letting it run out of the dialog on either side (the wrap width is
        # matched to the dialog below, once its final width is known).
        headline = ctk.CTkLabel(head, text="Temperature Stabilization is in progress.",
                                font=theme_font(18, bold=True), justify="left",
                                wraplength=sp(540),
                                text_color=tc("text"))
        headline.pack(side="left")

        model = getattr(self, 'temp_warmup', None)
        remaining = model.remaining if model is not None else 0
        ctk.CTkLabel(card, text=f"{minutes_left(remaining)} minute(s) left before the "
                                f"flow cell is at temperature.",
                     font=theme_font(13), text_color=tc("text_muted")).pack(
            anchor="w", padx=sp(28), pady=(sp(6), sp(2)))
        ctk.CTkLabel(card, text="Do you still want to continue?",
                     font=theme_font(18, bold=True), text_color=tc("text")).pack(
            anchor="w", padx=sp(20), pady=(sp(6), 0))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=sp(20), pady=(sp(14), sp(16)))

        def _close():
            try:
                popup.grab_release()
            except Exception:
                pass
            try:
                popup.destroy()
            except Exception:
                pass
            self.temp_warning_dialog = None

        def _yes():
            _close()
            if callable(on_confirm):
                on_confirm()

        no_btn = ctk.CTkButton(
            buttons, text="No", width=sp(140), height=sp(48),
            font=theme_font(16, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=12,
            command=_close)
        no_btn.pack(side="left")
        yes_btn = ctk.CTkButton(
            buttons, text="Yes", width=sp(140), height=sp(48),
            font=theme_font(16, bold=True),
            fg_color=tc("accent"), hover_color=tc("accent_hover"),
            text_color=tc("text_on_accent"), corner_radius=12,
            command=_yes)
        yes_btn.pack(side="right")
        # Kept on the app so a test (or a future "confirm without a finger"
        # path) can answer the dialog without hunting through the widget tree.
        self.temp_warning_yes_button = yes_btn
        self.temp_warning_no_button = no_btn

        width, height, px, py = self._warning_dialog_size(card)
        # Second pass: match the headline's wrap width to the dialog we just
        # sized (a narrow panel must wrap the headline, not clip it), then let
        # the card report the height that wrapping actually needs.
        try:
            wanted_wrap = max(sp(280), width - sp(80))
            if abs(int(headline.cget("wraplength")) - wanted_wrap) > 4:
                headline.configure(wraplength=wanted_wrap)
                width, height, px, py = self._warning_dialog_size(card)
        except Exception:
            pass
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
    # Water stabilization (hardware) - progress note only.
    #
    # The warm-up timer above is what gates a test. The hardware routine still
    # runs at start-up; its messages go to the small caption line so the two can
    # never fight over the status card.
    # ------------------------------------------------------------------
    def show_temperature_initialization_screen(self):
        """Show a screen while temperature is being initialized"""
        if not self.initialize_uart():
            # The window's own banner (see CoreMixin.show_notification): a
            # native messagebox is not readable at arm's length on the panel.
            self.show_notification(
                "Hardware Error: could not connect to the ESP32 Sensor Board. "
                "Tap to dismiss.", duration=0, error=True)

        self.clear_frames()
        init_frame = ctk.CTkFrame(self)
        init_frame.grid(row=0, column=0, sticky="nsew", padx=sp(20), pady=sp(20))
        # Configure grid
        init_frame.grid_columnconfigure(0, weight=1)
        init_frame.grid_rowconfigure(0, weight=1)
        # Create content frame
        content_frame = ctk.CTkFrame(init_frame)
        content_frame.grid(row=0, column=0, padx=sp(50), pady=sp(50), sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=0)
        content_frame.grid_rowconfigure(2, weight=0)
        self.show_main_menu()

    # ------------------------------------------------------------------
    # Water stabilization: the worker thread PUBLISHES, the main thread PAINTS
    # ------------------------------------------------------------------
    # Tk may only be touched from the main thread. Even ``after()`` from a
    # worker takes Tcl's interpreter lock, which can deadlock the event loop:
    # the window then never finishes its first paint and never answers the
    # quit timer. So the worker writes plain values into _stab_state and the
    # main thread's poller does every widget call.
    def start_initialization(self):
        """Starts the stabilization thread (hardware warm-up)."""
        self.stabalization_started = True
        self._hw_failed = False

        self._stab_state = {
            'status': None, 'progress': None, 'message': None,
            'result': None, 'done': False,
            'painted_status': None, 'painted_progress': None,
            'painted_message': None,
        }
        self._stab_pump_after_id = self.after(120, self.pump_stabilization)

        # Start the hardware task in a background thread
        threading.Thread(target=self.run_stabilization_thread, daemon=True).start()

    def update_stabilization_ui(self, message):
        """Worker thread -> shared state (never touches Tk off the main thread)."""
        state = getattr(self, '_stab_state', None)
        if state is not None:
            state['status'] = message

    def update_progress_bar(self, value):
        """Worker thread -> shared state (never touches Tk off the main thread)."""
        state = getattr(self, '_stab_state', None)
        if state is None:
            return
        try:
            state['progress'] = float(value)
        except (TypeError, ValueError):
            pass

    def update_progress_label(self, message):
        """Worker thread -> shared state (never touches Tk off the main thread)."""
        state = getattr(self, '_stab_state', None)
        if state is not None:
            state['message'] = message

    def pump_stabilization(self):
        """Main-thread poller: paint whatever the worker published, then reap it.

        Stops itself as soon as the main-menu frame is gone (the user navigated
        away or the app is closing) so no timer keeps firing against dead
        widgets.
        """
        state = getattr(self, '_stab_state', None)
        if state is None:
            return
        frame = (getattr(self, 'frames', None) or {}).get('main')
        try:
            if frame is None or not frame.winfo_exists():
                return
        except Exception:
            return
        try:
            # The warm-up timer owns the progress bar and the headline. The
            # hardware routine only narrates itself on the caption line.
            if state['message'] is not None and state['message'] != state['painted_message']:
                state['painted_message'] = state['message']
                if self._alive(getattr(self, 'progress_label', None)):
                    self.progress_label.configure(
                        text=f"Flow cell check: {state['message']}")
            if state['status'] is not None and state['status'] != state['painted_status']:
                state['painted_status'] = state['status']
            if state['result'] is not None:
                success, msg = state['result']
                state['result'] = None
                self._apply_stabilization_result(success, msg)
        except Exception:
            return
        if state.get('done') and state['result'] is None:
            return
        self._stab_pump_after_id = self.after(120, self.pump_stabilization)

    def enforce_system_state(self, button):
        """Keep every entry usable - the warm-up gate is a warning, not a lock.

        During the ten-minute warm-up the operator may explore any screen; only
        starting a test asks for confirmation (request_test_screen). So nothing
        is ever disabled here. The method is kept because the test list calls it
        for every row it builds.
        """
        try:
            button.configure(state="normal")
        except Exception:
            pass

    def run_stabilization_thread(self):
        """The actual worker logic (runs OFF the main thread).

        It never touches Tk: progress goes into ``_stab_state`` and the main
        thread's poller (``pump_stabilization``) paints it. Widget calls from a
        worker thread raise "main thread is not in main loop" and can deadlock
        the event loop, which used to leave the status card stuck on
        "Performing Temperature Stabilization...".
        """
        success, msg = self.workflow_manager.water_stabilization(
            status_callback=self.update_stabilization_ui,
            progress_callback=self.update_progress_bar,
            progress_message_callback=self.update_progress_label
        )
        print(f"[STAB] water stabilization returned {msg}")
        state = getattr(self, '_stab_state', None)
        if state is not None:
            state['result'] = (success, msg)
            state['done'] = True

    def _apply_stabilization_result(self, success, msg):
        """Paint the stabilization outcome (always on the main thread).

        The main-menu widgets may already be destroyed if the user navigated
        away while stabilization was still running, so never let this raise.
        """
        try:
            self._paint_stabilization_result(success, msg)
        except Exception as exc:
            print(f"[STAB] could not paint the result: {exc}")

    def _paint_stabilization_result(self, success, msg):
        """Hardware flow-cell check finished.

        The warm-up COUNTDOWN is independent of this: it is a ten-minute timer
        from GUI start, so a successful check must not shorten it and a failed
        one must not stop it. Only the failure is surfaced here (with Retry);
        the warm-up tick keeps painting the bar and the headline.
        """
        if success:
            self._hw_failed = False
            print("[STAB] flow-cell check complete")
            return
        self._hw_failed = True
        label = getattr(self, 'hw_status_label', None)
        if self._alive(label):
            label.configure(text="Flow cell check failed - please check the flow cell.",
                            text_color=tc("danger"))
            label.grid()
        if self._alive(getattr(self, 'water_stabilization_retry_btn', None)):
            return
        main_frame = (getattr(self, 'frames', None) or {}).get('main')
        if not self._alive(main_frame):
            return
        self.water_stabilization_retry_btn = ctk.CTkButton(
            main_frame,
            text="Retry flow cell check",
            command=self.retry_stabilization,
            width=sp(220), height=sp(44), corner_radius=10,
            font=theme_font(14, bold=True),
            fg_color=tc("warning"), hover_color=tc("warning_hover"),
            text_color=tc("warning_text"),
        )
        self.water_stabilization_retry_btn.grid(row=3, column=0, sticky="w",
                                                padx=sp(18), pady=(sp(6), 0))

    def handle_stabilization_failure(self):
        """Update UI to show failure and stop progress"""
        self.stabilization_progress.stop()
        self.temp_status_label.configure(
            text="Temperature Stabilization Failed! Please change the flowcell",
            text_color=tc("danger"))

    def retry_stabilization(self):
        btn = getattr(self, 'water_stabilization_retry_btn', None)
        if self._alive(btn):
            btn.destroy()
        self.water_stabilization_retry_btn = None
        label = getattr(self, 'hw_status_label', None)
        if self._alive(label):
            label.configure(text="", text_color=tc("text_muted"))
            label.grid_remove()
        self.start_initialization()

    def animate_progress_bar(self, progress_bar):
        """Animate the progress bar to show activity"""
        current_value = progress_bar.get()
        if current_value >= 1.0:
            progress_bar.set(0)
        else:
            progress_bar.set(current_value + 0.01)
        # Continue animation until we're done with initialization
        if 'init' in self.frames:
            self.after(50, lambda: self.animate_progress_bar(progress_bar))

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------
    def _on_theme_toggle(self, value):
        """Segmented control handler: switch theme and repaint this screen."""
        wants_dark = "dark" in str(value).lower()
        if wants_dark != is_dark():
            # Rebuilding the screen must not happen inside the widget's own
            # callback - defer it by one event-loop turn.
            self.after(0, self.toggle_theme)

    def _menu_card(self, parent, icon, title, subtitle, command, accent=False):
        """A large, clickable menu card (click anywhere on it)."""
        frame = ctk.CTkFrame(parent, **theme_card(radius=sp(16)))
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=sp(14), pady=sp(10))

        # The panel is tall, so the icon/title/subtitle block is centred on the
        # card (placed at 50% height) instead of hugging the top edge and
        # leaving a dead half underneath it. ``inner`` still fills the card so
        # a tap anywhere on it counts.
        block = ctk.CTkFrame(inner, fg_color="transparent")
        block.place(x=0, rely=0.5, anchor="w")

        icon_color = tc("accent") if accent else tc("accent_text")
        icon_label = ctk.CTkLabel(block, text=icon, font=theme_font(22),
                                  text_color=icon_color)
        icon_label.pack(anchor="w")
        title_label = ctk.CTkLabel(block, text=title, font=theme_font(17, bold=True),
                                   text_color=tc("text"))
        title_label.pack(anchor="w", pady=(sp(3), 0))
        # wraplength keeps a long subtitle inside its column instead of forcing
        # the whole card row wider than the 1280 px panel. The descriptions are
        # written to fit ONE line at this width: a second line used to be cut
        # off by the card's bottom edge on the 7" panel (the DejaVu font the Pi
        # uses is taller than the desktop's), so every card now keeps a single
        # short line - English wording, no abbreviations.
        subtitle_label = ctk.CTkLabel(block, text=subtitle, font=theme_font(12),
                                      text_color=tc("text_muted"), justify="left",
                                      wraplength=sp(262))
        subtitle_label.pack(anchor="w", pady=(sp(2), 0))

        arrow = ctk.CTkLabel(frame, text="→", font=theme_font(19, bold=True),
                             text_color=tc("accent"))
        arrow.place(relx=0.95, rely=0.5, anchor="e")

        # A click is completed on RELEASE, never on press.
        #
        # Navigating on press handed the rest of the same physical click to the
        # screen that had just been drawn under the cursor: the ButtonRelease
        # went to the first test row (customtkinter buttons activate on release),
        # so one click on TEST opened the test list AND that first test's
        # measurement screen with nothing selected. Acting on release keeps the
        # whole click - press and release - inside the card.
        pressed = [False]

        def _press(_event=None):
            pressed[0] = True
            _enter()

        def _release(_event=None):
            if not pressed[0]:
                return
            pressed[0] = False
            command()

        def _enter(_event=None):
            try:
                frame.configure(fg_color=tc("surface_high"), border_color=tc("accent"))
            except Exception:
                pass

        def _leave(_event=None):
            # Dragged off the card: the release must not fire the command.
            pressed[0] = False
            try:
                frame.configure(fg_color=tc("surface"), border_color=tc("border"))
            except Exception:
                pass

        for widget in (frame, inner, block, icon_label, title_label,
                       subtitle_label, arrow):
            widget.bind("<Button-1>", _press)
            widget.bind("<ButtonRelease-1>", _release)
            widget.bind("<Enter>", _enter)
            widget.bind("<Leave>", _leave)
        return frame

    def create_main_menu(self):
        main_frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)  # the card grid absorbs slack

        # ---------- Top bar: theme switch ----------
        # The old "BIOCHEMISTRY ANALYZER" heading lived here; it is gone so the
        # status card and the cards below can use the height. The light/dark
        # switch moved to the top-right corner, where it stays reachable but out
        # of the way of the working area.
        top_bar = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=sp(18), pady=(sp(8), sp(4)))
        top_bar.grid_columnconfigure(0, weight=1)

        self.theme_switch = ctk.CTkSegmentedButton(
            top_bar,
            values=["☀  Light", "☾  Dark"],
            command=self._on_theme_toggle,
            fg_color=tc("btn_neutral"),
            selected_color=tc("accent"),
            selected_hover_color=tc("accent_hover"),
            unselected_color=tc("btn_neutral"),
            unselected_hover_color=tc("btn_neutral_hover"),
            text_color=tc("text"),
            font=theme_font(12, bold=True),
            corner_radius=sp(10),
            height=sp(30),
            width=sp(146),
        )
        self.theme_switch.grid(row=0, column=1, sticky="e")
        self.theme_switch.set("☾  Dark" if is_dark() else "☀  Light")

        # ---------- Status card: warm-up progress + temperature ----------
        status_card = ctk.CTkFrame(main_frame, **theme_card(radius=sp(16)))
        status_card.grid(row=1, column=0, sticky="ew", padx=sp(18), pady=(sp(2), sp(10)))
        status_card.grid_columnconfigure(1, weight=1)
        status_card.grid_columnconfigure(2, weight=0)

        self.temp_status_dot = ctk.CTkLabel(
            status_card, text="●", font=theme_font(14, bold=True),
            text_color=tc("warning"))
        self.temp_status_dot.grid(row=0, column=0, sticky="w",
                                  padx=(sp(16), sp(8)), pady=(sp(10), 0))
        self.temp_status_label = ctk.CTkLabel(
            status_card,
            text="Temperature Stabilization in progress",
            font=theme_font(16, bold=True),
            text_color=tc("text"),
        )
        self.temp_status_label.grid(row=0, column=1, sticky="w", pady=(sp(10), 0))

        # Right-hand readout: the countdown while warming up, the live flow-cell
        # temperature afterwards.
        temp_box = ctk.CTkFrame(status_card, fg_color="transparent")
        temp_box.grid(row=0, column=2, sticky="e", padx=(sp(8), sp(16)), pady=(sp(8), 0))
        self.temp_value_label = ctk.CTkLabel(
            temp_box, text="--:--", font=theme_font(20, bold=True),
            text_color=tc("text_muted"))
        self.temp_value_label.pack(anchor="e")
        self.temp_unit_label = ctk.CTkLabel(
            temp_box, text="time remaining", font=theme_font(11),
            text_color=tc("text_muted"))
        self.temp_unit_label.pack(anchor="e")

        self.stabilization_progress = ctk.CTkProgressBar(
            status_card, height=sp(10), corner_radius=sp(6),
            progress_color=tc("accent"), fg_color=tc("surface_sunken"),
        )
        self.stabilization_progress.grid(row=1, column=0, columnspan=3,
                                         sticky="ew", padx=sp(16), pady=(sp(8), sp(2)))
        self.stabilization_progress.set(0)

        self.progress_label = ctk.CTkLabel(
            status_card, text="...", font=theme_font(12),
            text_color=tc("text_muted"))
        self.progress_label.grid(row=2, column=0, columnspan=3, sticky="w",
                                 padx=sp(16), pady=(0, sp(8)))

        # Failure line: empty in normal operation, so it starts un-mapped and
        # only claims a row of its own when there is something to say. (An
        # always-present empty row cost ~24 px of the 720 px panel, which is
        # exactly the kind of slack the card grid needs.)
        self.hw_status_label = ctk.CTkLabel(
            status_card, text="", font=theme_font(12), text_color=tc("text_muted"))
        self.hw_status_label.grid(row=3, column=0, columnspan=3, sticky="w",
                                  padx=sp(16), pady=(0, sp(8)))
        self.hw_status_label.grid_remove()

        # ---------- Six menu cards (3 x 2) ----------
        cards = ctk.CTkFrame(main_frame, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="nsew", padx=sp(12), pady=(0, sp(10)))
        for col in range(3):
            cards.grid_columnconfigure(col, weight=1, uniform="menu")
        for row in range(2):
            cards.grid_rowconfigure(row, weight=1, uniform="menu")

        # Icons are restricted to glyphs that ship with DejaVu Sans (the Pi's
        # default font) AND with the desktop fonts on Windows, so the cards
        # never degrade into tofu boxes on the real instrument.
        # One short line each (see _menu_card): on the 7" panel a second line
        # was cut by the card's edge, so the wording is deliberately brief.
        entries = (
            ("⚗", "TEST", "Create tests and start a measurement.",
             self.request_test_screen, True),
            ("▤", "RESULT", "Browse runs and open QC charts.",
             self.show_result_screen, False),
            ("⚙", "SYSTEM", "Instrument status and diagnostics.",
             self.show_system_screen, False),
            ("🔧", "MAINTENANCE", "Pump and fluid controls.",
             self.show_maintenance_screen, False),
            ("⏻", "POWER", "Shut down, reboot or sleep.",
             self.show_power_screen, False),
            ("i", "ABOUT", "Manufacturer and software build.",
             self.show_about_screen, False),
        )
        for index, (icon, title, subtitle, command, accent) in enumerate(entries):
            card = self._menu_card(cards, icon, title, subtitle, command, accent=accent)
            card.grid(row=index // 3, column=index % 3, sticky="nsew",
                      padx=sp(6), pady=sp(6))

        # Start the hardware flow-cell check in a background thread (first build
        # only). The warm-up timer itself already runs from GUI start.
        if not getattr(self, "stabalization_started", False):
            self.start_initialization()

        # Paint the current warm-up state immediately (no 1 s blank).
        self._paint_warmup()

        return main_frame
