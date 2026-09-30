"""
measurement.py - Live measurement screen: realtime data, results table and workflow buttons.

Part of the ui package (split from the original monolithic ui.py).
"""

import customtkinter as ctk
import threading
import time
from Hardware.config import SIMULATION_MODE
from ui.hardware_actions import clean
from ui.theme import c as tc, card as theme_card, sp, font as theme_font

# matplotlib imported lazily in create_measurement_screen to speed up startup
plt = None
FigureCanvasTkAgg = None

class MeasurementMixin:
    """MeasurementMixin - Live measurement screen: realtime data, results table and workflow buttons."""

    def __create_measurement_screen_(self, test_id):
        """Creates a measurement screen with live plotting capabilities optimized for RPi.

        Layout structure:
        - Header: Back button, Title
        - Graph area: Matplotlib plot (main focus, expandable)
        - Data display: Real-time data table and Results table
        - Control buttons: WATER, BLANK, STD, SAMPLE, QC1, QC2, WASH
        """
        # Initialize data storage for measurements
        self.measurement_data = {
            'time': [2, 4, 2],
            'values': [0.25, 0.50, -0.25]
        }

        # Create main frame with responsive grid layout
        measure_frame = ctk.CTkFrame(self)
        measure_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Configure grid weights for proper sizing:
        # Row 0: Header (fixed height)
        # Row 1: Graph (expanded, weight=3)
        # Row 2: Data display (fixed height, weight=1)
        # Row 3: Control buttons (fixed height)
        measure_frame.grid_rowconfigure(0, weight=0)
        measure_frame.grid_rowconfigure(1, weight=3)  # Graph gets most space

    def create_measurement_screen(self, test_id):
        """Creates a measurement screen with live plotting capabilities optimized for RPi."""
        global plt, FigureCanvasTkAgg
        if plt is None:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        # Initialize data storage for measurements
        self.measurement_data = {'time': [], 'values': []}
        self.start_time = None
        self.is_measuring = False
        self.start_time = time.time()
        self.time_data = []
        self.abs_data = []
        self.vline = None
        # Cached high/low limits for result-box colouring (loaded lazily).
        self._result_limits = None
        # Flow-cell cleaning gate: None | 'running' | 'failed' (see
        # begin_post_run_clean). Reset with the screen so a rebuild never
        # inherits a stale lock.
        self._post_run_clean = None
        self._clean_manual = False
        # Which screen the in-flight clean belongs to. A clean started by the
        # PREVIOUS screen must never freeze - or unlock - THIS screen's buttons.
        self._clean_screen_token = None
        # A hardware press that lands while the LED alignment is still
        # running is remembered here and executed as soon as it finishes.
        self._pending_press_after_align = False

        # Clear existing frames
        self.clear_frames()
        # The previous screen (if any) is gone: drop its run progress clock too,
        # otherwise a Back during a TP/Kinetic run leaves a ticking clock behind
        # on the test list (and a stale anchor for the next screen).
        self._stop_run_clock()
        self._awaiting_first_reading = False
        # Throw away the plot state of whatever screen we just left. Without
        # this, opening another test after a Back still showed the aborted
        # run's curve (and its between-reading animation) on the fresh graph.
        try:
            self.workflow_manager.reset_plot_for_new_screen()
        except Exception as exc:
            print(f"[WF] Plot reset skipped: {exc}")
        # Mark the measurement screen as active so the hardware-button poller
        # keeps running (clear_frames above resets it to False).
        self._measurement_screen_active = True
        # Drain any stale limit-switch events from the previous screen
        try:
            from Hardware.serial_manager import get_manager
            get_manager().drain_all()
        except Exception:
            pass

        # LED alignment — done once, in a BACKGROUND thread so the UI
        # renders immediately. Buttons are frozen until LED align finishes.
        # In SIMULATION there is no LED to align, so the gate must be open from
        # the start: the align thread below never runs there, and nothing else
        # would ever set the flag — which used to leave EVERY workflow button
        # greyed out and dead on a desktop/simulation run.
        _awaiting_led_align = bool(not SIMULATION_MODE and self.current_test_name)
        self._led_align_done = not _awaiting_led_align
        # Seed the header status chip before the widgets exist: the align thread
        # starts below, so the operator sees "aligning" from the first frame.
        self.handle_step_status("aligning" if _awaiting_led_align else "ready")
        # clear_frames() above already bumped _screen_token: capture this
        # screen's epoch so a STALE align thread from a previous screen can
        # never enable OUR buttons early or steal OUR UART replies.
        _my_screen = self._screen_token
        if _awaiting_led_align:
            def _run_led_align(screen_token=_my_screen):
                if screen_token != self._screen_token:
                    return  # superseded before we even started
                try:
                    params = self.db_manager.load_parameters(self.current_test_name) or {}
                    wavelength = params.get('wavelength', '')
                    is_340 = (wavelength == '340nm')
                    if self._screen_token != screen_token:
                        return  # Back pressed while loading params
                    if is_340:
                        print('[WF] UV LED align (340nm) — once on test selection...')
                        from Hardware.stm32_backend import send_uv_led_align
                        send_uv_led_align()
                    else:
                        print('[WF] White LED align — once on test selection...')
                        from Hardware.stm32_backend import send_white_led_align
                        send_white_led_align()
                except Exception as e:
                    print(f'[WF] LED align skipped: {e}')
                finally:
                    # Only the CURRENT screen may unfreeze its buttons. A
                    # stale thread must die silently (its _send_and_wait
                    # already exited fast via the supersede check).
                    if self._screen_token != screen_token:
                        print('[WF] Stale LED align thread exiting quietly')
                        return
                    self._led_align_done = True
                    # Unfreeze all workflow buttons. Via the thread-safe queue:
                    # a plain after() from THIS worker thread raises "main thread
                    # is not in main loop" while Tk is not in mainloop(), and the
                    # swallowed exception left every button frozen for good - the
                    # "buttons frozen and nothing happens" report.
                    poster = getattr(self, 'ui_post', None)
                    if poster is not None:
                        poster(self._enable_workflow_buttons)
                    else:
                        self.after(0, self._enable_workflow_buttons)
                    print('[WF] LED align done — buttons enabled')

            import threading
            self.handle_step_status("aligning")
            threading.Thread(target=_run_led_align, daemon=True).start()

        # Main container frame
        measure_frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        measure_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # UI LAYOUT CONFIGURATION
        # Row 1 (Graph) and Row 2 (Data) are flexible; Row 0 and 3 are fixed.
        measure_frame.grid_rowconfigure(0, weight=0)  # Header
        measure_frame.grid_rowconfigure(1, weight=1)  # Graph area
        measure_frame.grid_rowconfigure(2, weight=0)  # Data display area (compact)
        measure_frame.grid_rowconfigure(3, weight=0)  # Control buttons (fixed height)
        measure_frame.grid_columnconfigure(0, weight=1)

        # 1. Header Section
        # The header carries the test name (no "Measurement:" prefix - the
        # screen IS the measurement, and the name is what the operator has to
        # read at a glance), the live status chip and the flow-cell temperature
        # chip.
        #
        # It is laid out with PACK, right-hand chips first. Pack hands out room
        # in packing order, so the two chips are guaranteed their full width
        # and the only thing that can ever be squeezed is the title (a short
        # test name). With the old grid the status chip grew when the run clock
        # appeared and pushed the temperature chip off the right edge of the
        # panel.
        header_frame = ctk.CTkFrame(measure_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 8))

        # Temperature chip, pinned to the panel's right edge: the same readout
        # the home screen shows - "Temperature Stabilizing" with an amber dot
        # while the ten-minute warm-up runs, then the live flow-cell reading
        # (36.9 / 37.0 / 37.1 °C) with a green dot. main_menu's one-second tick
        # keeps it current, so the two screens can never disagree.
        self.temp_chip = ctk.CTkFrame(
            header_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=10,
            border_width=1,
            border_color=tc("border"),
        )
        self.temp_chip.pack(side="right")
        self.temp_chip_dot = ctk.CTkLabel(
            self.temp_chip, text="●", width=12,
            font=theme_font(11, bold=True),
            text_color=tc("warning" if self.temperature_warning_needed() else "success"))
        self.temp_chip_dot.pack(side="left", padx=(8, 3), pady=3)
        self.temp_chip_label = ctk.CTkLabel(
            self.temp_chip, text=self.temperature_status_text(),
            font=theme_font(12, bold=True), text_color=tc("text"))
        self.temp_chip_label.pack(side="left", padx=(0, 10), pady=3)

        # Live status chip: the operator's "what is the instrument doing right
        # now?" readout (Aspirating, <test> running, Cleaning flow cell, LED
        # align in progress/complete, Ready). Deliberately NOT in the
        # Time/Values box below: that box is the live reading display - a status
        # message there would overwrite the timestamp exactly while the run is
        # streaming (and it is reset on every run start, so the message would
        # flicker).
        self.status_chip = ctk.CTkFrame(
            header_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=10,
            border_width=1,
            border_color=tc("border"),
        )
        self.status_chip.pack(side="right", padx=(0, 12))
        self.status_dot = ctk.CTkLabel(
            self.status_chip, text="●", width=12,
            font=theme_font(11, bold=True), text_color=tc("text_muted"))
        self.status_dot.pack(side="left", padx=(8, 3), pady=3)
        self.status_label = ctk.CTkLabel(
            self.status_chip, text="Ready",
            font=theme_font(12, bold=True), text_color=tc("text"))
        self.status_label.pack(side="left", padx=(0, 10), pady=3)
        # Run progress clock (TP/Kinetic only). The reading cadence there is
        # 10 s, so the Time box below can only move once every 10 s - this shows
        # the run advancing in between without touching that box. Fixed width
        # and right anchor so the digits never make the chip jitter; it stays
        # hidden until the run's first reading arrives.
        self.status_clock = ctk.CTkLabel(
            self.status_chip, text="", width=86, anchor="e",
            font=theme_font(12, bold=True), text_color=tc("text_muted"))
        self._clock_on = False
        self._clock_armed = False
        self._clock_window = 0.0
        self._clock_widget_shown = False
        # Restore whatever the screen already announced (align in progress / a
        # clean still running) instead of leaving the chip on "Starting...".
        _seeded = getattr(self, '_status_text', None)
        if _seeded:
            self._set_status(*_seeded)

        # Left group: back, the per-day sample counter badge and the test name.
        back_btn = ctk.CTkButton(header_frame, text="←", width=40, height=34,
                                font=theme_font(15, bold=True),
                                fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                                text_color=tc("btn_text"), corner_radius=10,
                                border_width=1, border_color=tc("border"),
                                command=self.back_to_test_list)
        back_btn.pack(side="left")

        # Per-day sample counter badge: shows "Sample 1", "Sample 2", ... at the
        # left of the header whenever SAMPLE is selected. The number is derived
        # from today's logged SAMPLE results, so it survives switching between
        # tests and resets automatically on a new day.
        self.sample_indicator = ctk.CTkLabel(
            header_frame,
            text="",
            font=theme_font(12, bold=True),
            text_color=tc("accent_text"),
            fg_color="transparent",
            corner_radius=10,
            padx=10,
            pady=3,
        )
        self.sample_indicator.pack(side="left", padx=(12, 0))

        title = ctk.CTkLabel(header_frame, text=str(self.current_test_name or ""),
                            font=theme_font(18, bold=True),
                            text_color=tc("text"))
        title.pack(side="left", padx=(12, 0))

        # Kept on the app: the theme repaint and the tests use it.
        self.measurement_title = title

        # Add temperature display
        # if not hasattr(self, 'temp_label'):
        # self.temp_label = ctk.CTkLabel(
        #     header_frame,
        #     text="TEMP: --.- °C",
        #     font=ctk.CTkFont(size=14, weight="bold")
        # )
        # self.temp_label.grid(row=0, column=1, padx=20, sticky="e")

        # Temperature Display
        # self.temp_label = ctk.CTkLabel(header_frame, text="Temp: --.- °C", font=ctk.CTkFont(size=14))
        # self.temp_label.grid(row=0, column=3, padx=10)
        # self.update_temperature_ui()

        # 2. Graph Area — show a placeholder first for instant screen load,
        # then create the matplotlib canvas after the screen is rendered.
        graph_frame = ctk.CTkFrame(measure_frame, **theme_card(radius=14))
        graph_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 4))
        self._graph_frame = graph_frame

        # Placeholder label — visible immediately while matplotlib loads
        self._graph_placeholder = ctk.CTkLabel(
            graph_frame,
            text="Loading graph...",
            font=theme_font(14, bold=True),
            text_color=tc("text_muted")
        )
        self._graph_placeholder.pack(expand=True)

        self._graph_ready = False
        # Schedule canvas build after the screen has rendered (300ms for layout
        # to settle). A run started sooner builds it on demand — see
        # _ensure_graph_canvas. The screen token is captured HERE: if the user
        # navigates away (or the theme rebuilds the screen) before the timer
        # fires, the deferred call must not touch the destroyed frame.
        self._graph_after_id = self.after(
            300, lambda tok=self._screen_token: self._ensure_graph_canvas(tok))
        # 3. Data Display Area
        # Compact on purpose: every pixel this band gives back goes to the graph
        # above it, which is what the operator actually reads during a run. The
        # values stay comfortably readable (18 px readings, 20 px result) - only
        # the padding and the header row got thin.
        data_display_frame = ctk.CTkFrame(measure_frame, fg_color="transparent")
        data_display_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=2)
        data_display_frame.grid_columnconfigure(0, weight=1)
        data_display_frame.grid_columnconfigure(1, weight=1)
        data_display_frame.grid_rowconfigure(0, weight=1)

        self.realtime_data_frame = ctk.CTkFrame(data_display_frame)
        self.realtime_data_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.initialize_realtime_data_table()

        self.results_frame = ctk.CTkFrame(data_display_frame)
        self.results_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.initialize_results_table()

        self.update_realtime_data(0, 0.0)
        self.update_results_display("-", "-", "-")


        # 4. Control Buttons Section (The Seven Buttons)
        button_frame = ctk.CTkFrame(measure_frame, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 6))

        buttons = ["WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2", "WASH"]
        self.control_buttons = {}

        for i in range(len(buttons)):
            button_frame.grid_columnconfigure(i, weight=1)

        for i, text in enumerate(buttons):
            btn = ctk.CTkButton(
                button_frame,
                text=text,
                width=60,
                height=32,
                fg_color=tc("btn_neutral"),
                hover_color=tc("btn_neutral_hover"),
                corner_radius=10,
                border_width=1,
                border_color=tc("border"),
                text_color=tc("btn_text"),
                font=theme_font(10, bold=True),
                # Clicking a button only SELECTS it (rules 1-3); the physical
                # hardware button (or Enter/Space in simulation) executes it.
                command=lambda t=text: self.handle_button_click(t)
            )
            btn.grid(row=0, column=i, padx=3, pady=3, sticky="ew")
            self.control_buttons[text] = btn

        self.determine_workflow_sequence()

        # Freeze all buttons until LED align completes (hardware only — in
        # simulation the buttons must be usable right away).
        if _awaiting_led_align:
            self._disable_workflow_buttons()

        self.highlight_next_workflow_button()

        # Start polling the physical hardware button (rules 1-3).
        # Enter/Space also acts as the hardware button (temp fallback for desktop testing)
        self._sim_button_pressed = False
        self._hw_button_prev = False
        try:
            self.bind("<Return>", self._simulate_hardware_press)
            self.bind("<space>", self._simulate_hardware_press)
        except Exception as e:
            print(f"Could not bind hardware key: {e}")
        # Tk only delivers keyboard events to the focused window, so a laptop
        # (no physical button) could see the stand-in Space/Enter keys do
        # nothing when the window did not own keyboard focus. Claim it as the
        # measurement screen opens; harmless on the Pi where a real keyboard is
        # not normally attached.
        try:
            self.focus_force()
        except Exception as e:
            print(f"Could not focus the measurement window: {e}")
        self._hw_poll_after_id = self.after(100, self.check_hardware_button)

        self.frames['measurement'] = measure_frame
        return measure_frame

    def _ensure_graph_canvas(self, screen_token=None):
        """Create the measurement screen's matplotlib canvas. Idempotent.

        Normally called 300 ms after the screen opens so the screen paints
        instantly. It is also called ON DEMAND when a workflow starts before
        that timer fired: pressing the hardware button (or spacebar in
        simulation) within those 300 ms used to run initialize_plot against a
        None axes and kill the run with "'NoneType' object has no attribute
        'clear'".
        """
        if getattr(self, '_graph_ready', False):
            return
        token = self._screen_token if screen_token is None else screen_token
        if token != self._screen_token:
            return  # user pressed Back before the canvas was built
        graph_frame = getattr(self, '_graph_frame', None)
        if graph_frame is None or getattr(self, '_graph_placeholder', None) is None:
            return
        # The frame may already be gone (screen rebuilt / theme switched while
        # the timer was pending): never call Tk on a destroyed widget.
        try:
            if not (graph_frame.winfo_exists() and self._graph_placeholder.winfo_exists()):
                return
        except Exception:
            return
        # This call owns the build now — drop the pending timer.
        pending = getattr(self, '_graph_after_id', None)
        if pending:
            try:
                self.after_cancel(pending)
            except Exception:
                pass
            self._graph_after_id = None
        try:
            self._graph_placeholder.destroy()
        except Exception:
            pass
        # Flush pending geometry so the frame reports its REAL size. Without
        # this, a canvas built on the 300 ms timer measured the not-yet-laid-out
        # frame (1x1, clamped to a small figure) - why the TP/Kinetic graph
        # stayed a shrunken version until the first run redrew it.
        gw, gh = self._measure_graph_frame()
        self.fig = plt.Figure(figsize=(gw/100, gh/100), dpi=100,
                              facecolor=tc("graph_bg"))
        self.ax = self.fig.add_subplot(111)

        self.ax.set_title("Absorbance vs Time", color=tc("graph_title"),
                          fontsize=15, fontweight='bold')
        self.ax.set_xlabel("Time (s)", color=tc("graph_text"),
                           fontsize=12.5, fontweight='bold')
        self.ax.set_ylabel("Absorbance", color=tc("graph_text"),
                           fontsize=12.5, fontweight='bold')
        # The workflow owns the plot look (it also themes every per-run plot).
        try:
            self.workflow_manager.style_axes(self.ax)
        except Exception:
            self.ax.tick_params(axis='both', which='major', labelsize=8)
        self.ax.grid(True, linestyle='--', alpha=0.6, color=tc("graph_grid"))

        self.line, = self.ax.plot([], [], linewidth=2.2, color=tc("graph_line"),
                                  marker='o', markersize=4)
        self.measurement_final_point, = self.ax.plot(
            [], [], linestyle='None', marker='o', label='Current', markersize=8,
            markerfacecolor='none', markeredgecolor=tc("graph_marker"),
            markeredgewidth=2)

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # Fixed axes rectangle instead of tight_layout(): the graph must not
        # move when a later resize pass re-runs the layout (see
        # workflow/plotting.py:AXES_RECT).
        try:
            from workflow.plotting import apply_stable_layout

            apply_stable_layout(self.fig)
        except Exception as exc:
            print(f"[UI] could not fix the graph layout: {exc}")
        self.canvas.draw_idle()
        self.workflow_manager.set_measurement_plot_components(
            self.fig,
            self.canvas,
            self.ax,
            self.line,
            self.measurement_final_point
        )
        self._graph_ready = True
        # Keep the figure glued to its frame. The canvas is built on a timer,
        # so on a slow machine (or when the screen opens while the window is
        # still settling) it can be created from a placeholder-sized frame and
        # then never resize: the plot sat small in the corner until the first
        # run redrew it. Refit now and on every later frame resize.
        try:
            graph_frame.bind("<Configure>", self._on_graph_frame_configure)
        except Exception:
            pass
        # Settle burst: a single refit can measure the frame before Tk finished
        # laying the screen out. `_sync_graph_size` is idempotent and early-exits
        # when the figure already matches, so these extra passes are free.
        for delay in (0, 60, 200, 500, 1000):
            try:
                self.after(delay, self._sync_graph_size)
            except Exception:
                break
        print("[UI] measurement graph canvas ready")

    def _on_graph_frame_configure(self, _event=None):
        """Debounced refit: the graph frame changed size."""
        if not getattr(self, '_graph_ready', False):
            return
        pending = getattr(self, '_graph_resize_after_id', None)
        if pending:
            try:
                self.after_cancel(pending)
            except Exception:
                pass
        try:
            self._graph_resize_after_id = self.after(120, self._sync_graph_size)
        except Exception:
            pass

    def _measure_graph_frame(self):
        """Current size of the graph frame with pending geometry flushed.

        ``update_idletasks`` is what makes this reliable: a widget that has
        never been mapped reports 1x1 until Tk runs its geometry pass, and a
        figure built from that never grows back to full size on its own.
        """
        frame = getattr(self, '_graph_frame', None)
        if frame is None:
            return 400, 200
        try:
            frame.update_idletasks()
            w = int(frame.winfo_width())
            h = int(frame.winfo_height())
        except Exception:
            return 400, 200
        return max(400, w), max(200, h)

    def _sync_graph_size(self):
        """Make the figure match the graph frame exactly. Idempotent/cheap.

        Retries (bounded) while the frame still reports a pre-layout size: the
        canvas is built on a timer, so on the first passes the frame can be
        smaller than it will be a moment later and the figure would stay small.
        """
        if not getattr(self, '_graph_ready', False):
            return
        fig = getattr(self, 'fig', None)
        frame = getattr(self, '_graph_frame', None)
        if fig is None or frame is None:
            return
        try:
            if not frame.winfo_exists():
                return
        except Exception:
            return
        w, h = self._measure_graph_frame()
        # Frame smaller than any real layout = Tk has not laid the screen out
        # yet; try again shortly instead of freezing the small figure in.
        if (w <= 401 or h <= 201) and getattr(self, '_graph_size_retries', 0) < 10:
            self._graph_size_retries = getattr(self, '_graph_size_retries', 0) + 1
            try:
                self.after(120, self._sync_graph_size)
            except Exception:
                pass
            return
        self._graph_size_retries = 0
        try:
            dpi = fig.get_dpi() or 100
            cur_w, cur_h = (int(v) for v in (fig.get_size_inches() * dpi))
        except Exception:
            return
        if abs(cur_w - w) < 6 and abs(cur_h - h) < 6:
            return
        try:
            from workflow.plotting import apply_stable_layout

            fig.set_size_inches(w / dpi, h / dpi)
            # No tight_layout() here: it re-measures the tick labels, so the
            # axes moved whenever this fired mid-run and the plot looked like
            # it had jumped sideways. The rectangle is fixed (AXES_RECT), so a
            # resize only scales the plot - it never moves it.
            apply_stable_layout(fig)
            if getattr(self, 'canvas', None) is not None:
                self.canvas.draw_idle()
            print(f"[UI] graph resized to {w}x{h}")
        except Exception as exc:
            print(f"[UI] graph resize skipped: {exc}")

    def restyle_for_theme(self):
        """Repaint the measurement screen in the active theme, without rebuilding.

        Used when the theme changes while this screen is on show (the toggle
        lives on the main menu, so this is the safety net that keeps a live
        graph from staying in the old palette).
        """
        try:
            if getattr(self, 'fig', None) is not None:
                self.fig.set_facecolor(tc("graph_bg"))
            ax = getattr(self, 'ax', None)
            if ax is not None:
                self.workflow_manager.style_axes(ax)
                ax.set_title(ax.get_title(), color=tc("graph_title"),
                             fontsize=15, fontweight='bold')
                # The graph carries no legend box; make sure a theme repaint
                # cannot leave one behind.
                self.workflow_manager.remove_legend(ax)
                if getattr(self, 'canvas', None) is not None:
                    self.canvas.draw_idle()
        except Exception as exc:
            print(f"[THEME] graph restyle skipped: {exc}")
        try:
            graph_frame = getattr(self, '_graph_frame', None)
            if graph_frame is not None:
                graph_frame.configure(fg_color=tc("surface"), border_color=tc("border"))
        except Exception:
            pass
        try:
            self.update_button_states(None, is_running=False)
        except Exception as exc:
            print(f"[THEME] button restyle skipped: {exc}")
        try:
            label = getattr(self, 'result_value_label', None)
            if label is not None:
                self.update_result_box_color(label.cget("text"))
        except Exception:
            pass
        try:
            chip = getattr(self, 'status_chip', None)
            if chip is not None:
                chip.configure(border_color=tc("border"))
                seeded = getattr(self, '_status_text', None)
                if seeded:
                    self._set_status(*seeded)
        except Exception as exc:
            print(f"[THEME] status chip restyle skipped: {exc}")
        try:
            temp_chip = getattr(self, 'temp_chip', None)
            if temp_chip is not None:
                temp_chip.configure(fg_color=tc("surface_sunken"),
                                    border_color=tc("border"))
                label = getattr(self, 'temp_chip_label', None)
                if label is not None:
                    label.configure(text=self.temperature_status_text(),
                                    text_color=tc("text"))
                dot = getattr(self, 'temp_chip_dot', None)
                if dot is not None:
                    dot.configure(text_color=tc("warning"
                                                if self.temperature_warning_needed()
                                                else "success"))
        except Exception as exc:
            print(f"[THEME] temperature chip restyle skipped: {exc}")

    def _next_standard(self, button_type):
        """Return the next button in the standard order after the given one.

        Standard button order (rule 8): [Water, Blank, Standard, Sample].
        After SAMPLE the recommendation stays SAMPLE (continuous sampling).
        """
        if button_type == "SAMPLE" or button_type not in self.standard_button_order:
            return "SAMPLE"
        pos = self.standard_button_order.index(button_type)
        if pos >= len(self.standard_button_order) - 1:
            return "SAMPLE"
        return self.standard_button_order[pos + 1]

    def _recommend_button(self, button_type):
        """Highlight exactly ONE button (rule 3) as the system recommendation."""
        self.recommended_button = button_type
        self.selected_button = button_type
        self.last_recommended_button = button_type
        self._apply_highlight(button_type)
        self._update_sample_indicator(button_type)
        print(f"[RECOMMEND] Next step: {button_type} (press hardware button to run)")

    # Status chip tones -> (dot colour, text colour) palette keys.
    _STATUS_TONES = {
        "idle":    ("text_muted", "text"),
        "info":    ("info", "text"),
        "running": ("run_active", "text"),
        "busy":    ("warning", "text"),
        "ok":      ("success", "text"),
        "error":   ("danger", "text"),
    }

    # Panel wording: short, non-technical and identical everywhere. The header
    # already shows which test is loaded, so the chip never repeats the test
    # name - it only says what the instrument is doing right now.
    _BUTTON_TYPES = {
        "WATER": "water", "BLANK": "blank", "STD": "std",
        "SAMPLE": "sample", "QC1": "qc1", "QC2": "qc2", "WASH": "wash",
    }
    _STEP_WORDS = {
        "water": "water", "blank": "blank", "std": "standard",
        "standard": "standard", "sample": "sample",
        "qc1": "QC 1", "qc2": "QC 2", "wash": "flow cell",
    }
    _STATE_WORDS = {
        "ready": "Ready",
        # No trailing "..." on the align line: on the panel the status chip is
        # read at a glance, and the dots (plus the chip widening by two glyphs)
        # only made it look truncated. "Incubating" is shown as "Aspirating" -
        # the operator asked for one word for the whole pre-reading wait.
        "aligning": "LED align in progress",
        "aligned": "LED align complete",
        "incubating": "Aspirating",
        "aspirating": "Aspirating",
        "measuring": "Measuring",
        "washing": "Washing",
        "wash_failed": "Wash failed",
    }
    _EVENT_TONES = {
        "aspirating": "busy", "incubating": "busy", "washing": "busy",
        "measuring": "running", "aligning": "info", "aligned": "ok",
        "wash_failed": "error", "ready": "idle",
    }

    def status_wording(self, event, type_of=None):
        """Return the header wording for a workflow event."""
        if event in ("aspirating", "measuring"):
            word = self._STEP_WORDS.get(str(type_of or "").lower(), "")
            return f"{self._STATE_WORDS[event]} {word}".strip()
        return self._STATE_WORDS.get(event, str(event))

    def handle_step_status(self, event, type_of=None, tone=None):
        """Worded status for a workflow step (the UI owns the wording)."""
        if tone is None:
            tone = self._EVENT_TONES.get(event, "idle")
        self._status_event = event
        self._set_status(self.status_wording(event, type_of), tone)

    # Run progress clock (TP/Kinetic only). It starts the moment the operator
    # fires the test, because that is the wait they are sitting through, and it
    # runs until the run ends. The Time box below stays the READING's own second
    # (the graph's x-axis), so the two are different quantities by design: the
    # difference is the pre-roll (aspirate + incubation before the first
    # reading), which the chip names while it happens. The pre-roll is measured
    # from the first reading and added to the total, so "/ total" is the real
    # end-to-end length of the test and the clock lands exactly on the end of
    # the run instead of overrunning a nominal window.
    # EP hides it: a reading arrives every second there, so the Time box already
    # ticks and a second counter would be duplication.
    CLOCK_TICK_MS = 200

    @staticmethod
    def _clock_mmss(seconds):
        try:
            total = max(0, int(seconds))
        except (TypeError, ValueError):
            total = 0
        return f"{total // 60:02d}:{total % 60:02d}"

    def _start_run_clock(self, method_type=None, window_seconds=None):
        """Arm the header clock (TP/Kinetic runs with a known window only).

        Arming does NOT start it. It starts when the board confirms it has
        accepted the run (handle_acquisition_started) - the same instant the
        firmware starts its own countdown - so the two clocks never disagree.
        """
        self._stop_run_clock()
        method = str(method_type or "").strip().upper()
        if method not in ("TP", "KINETIC", "KINETICS"):
            return
        try:
            window = float(window_seconds or 0)
        except (TypeError, ValueError):
            window = 0.0
        if window <= 0:
            return
        self._clock_window = window
        self._clock_method = method
        self._clock_armed = True

    def handle_acquisition_started(self, window_seconds=None, method_type=None):
        """The board accepted the run: start the clock on the firmware's schedule.

        It starts at 00:00 and counts the same seconds the firmware counts, so
        the run's first TP/Kinetic reading lands when the clock reads its own
        second (10 s, 20 s, ...). The pre-roll - aspirating, aligning - is
        deliberately not counted; the chip names those steps while they happen.
        """
        if not getattr(self, "_clock_armed", False):
            return
        if window_seconds:
            try:
                self._clock_window = float(window_seconds)
            except (TypeError, ValueError):
                pass
        method = str(method_type or getattr(self, "_clock_method", "")
                     or "").strip().upper()
        if method and method not in ("TP", "KINETIC", "KINETICS"):
            return
        self._clock_armed = False
        self._clock_started_at = time.time()
        self._clock_on = True
        self._show_run_clock(
            f"00:00 / {self._clock_mmss(getattr(self, '_clock_window', 0))}")
        try:
            self.after(self.CLOCK_TICK_MS, self._clock_tick)
        except Exception:
            self._clock_on = False

    def _stop_run_clock(self):
        """Hide the clock: run finished, aborted, or a method without a window."""
        self._clock_on = False
        self._clock_armed = False
        self._clock_started_at = None
        self._clock_widget_shown = False
        try:
            clock = getattr(self, "status_clock", None)
            if clock is not None:
                clock.configure(text="")
                clock.pack_forget()
        except Exception:
            pass

    def _show_run_clock(self, text):
        try:
            clock = self.status_clock
            clock.configure(text=text)
            if not getattr(self, "_clock_widget_shown", False):
                clock.pack(side="left", padx=(0, 10), pady=4)
                self._clock_widget_shown = True
        except Exception:
            self._clock_on = False

    def _clock_start_fallback(self):
        """Start the clock if the board's confirmation never made it back.

        The run is demonstrably under way once a reading has arrived, so the
        first reading is the next best anchor - slightly late, but the operator
        still gets a running clock instead of a silent gap.
        """
        if (getattr(self, "_clock_armed", False)
                and not getattr(self, "_clock_on", False)):
            print("[CLOCK] board start confirmation missed - anchoring on the first reading")
            self.handle_acquisition_started()

    def _clock_tick(self):
        if not getattr(self, "_clock_on", False):
            return
        if not (getattr(self, "is_measuring", False)
                or getattr(self, "_measurement_running", False)):
            self._stop_run_clock()
            return
        started = getattr(self, "_clock_started_at", None)
        if started is not None:
            elapsed = max(0.0, time.time() - started)
            self._show_run_clock(
                f"{self._clock_mmss(elapsed)} / "
                f"{self._clock_mmss(getattr(self, '_clock_window', 0))}")
        try:
            self.after(self.CLOCK_TICK_MS, self._clock_tick)
        except Exception:
            self._clock_on = False

    def _set_status(self, text, tone="idle"):
        """Write one line into the header status chip.

        Safe from any thread: the chip is Tk state, so a call arriving from the
        measurement/clean worker is re-posted onto the main thread. The last
        message is remembered so a theme rebuild (which recreates the widget)
        restores it instead of leaving the chip blank.
        """
        self._status_text = (text, tone)
        if threading.current_thread() is not threading.main_thread():
            poster = getattr(self, 'ui_post', None)
            if poster is not None:
                poster(self._set_status, text, tone)
            return
        chip = getattr(self, 'status_chip', None)
        label = getattr(self, 'status_label', None)
        dot = getattr(self, 'status_dot', None)
        if chip is None or label is None or dot is None:
            return
        dot_key, text_key = self._STATUS_TONES.get(tone, self._STATUS_TONES["idle"])
        try:
            label.configure(text=text, text_color=tc(text_key))
            dot.configure(text_color=tc(dot_key))
            if tone == "error":
                chip.configure(fg_color=tc("danger_soft"))
            elif tone == "busy":
                chip.configure(fg_color=tc("warning_soft"))
            elif tone == "ok":
                chip.configure(fg_color=tc("success_soft"))
            else:
                chip.configure(fg_color=tc("surface_sunken"))
        except Exception:
            pass

    def _update_sample_indicator(self, button_type):
        """Show the per-day sample badge in the header when SAMPLE is selected.

        The number is 1 + today's logged SAMPLE results for this test, so the
        badge always announces the number the next sample run will be stored
        under (Sample 1, Sample 2, ...). It resets to Sample 1 on a new day.
        """
        try:
            indicator = getattr(self, 'sample_indicator', None)
            if indicator is None:
                return
            if button_type == "SAMPLE" and self.current_test_name:
                next_num = self.db_manager.count_samples_today(self.current_test_name) + 1
                indicator.configure(text=f"Sample {next_num}",
                                    fg_color=tc("accent_soft"),
                                    text_color=tc("accent_text"))
            else:
                indicator.configure(text="", fg_color="transparent")
        except Exception as e:
            print(f"Error updating sample indicator: {e}")

    def _apply_highlight(self, button_type):
        """Visually highlight a single button; all others stay normal & clickable."""
        if not hasattr(self, 'control_buttons'):
            return
        # Don't highlight while buttons are frozen (LED align in progress)
        if not getattr(self, '_led_align_done', True):
            return
        for name, btn in self.control_buttons.items():
            try:
                if name == button_type:
                    btn.configure(
                        fg_color=tc("highlight"),
                        hover_color=tc("highlight_hover"),
                        text_color=tc("on_highlight"),
                        border_width=2,
                        border_color=tc("highlight_hover"),
                        state="normal",
                        text=name
                    )
                else:
                    if name == "BLANK" and getattr(self, '_blank_frozen', True):
                        # Test has no blank step selected - keep BLANK frozen
                        # even though it is not the highlighted button.
                        continue
                    btn.configure(
                        fg_color=tc("btn_neutral"),
                        hover_color=tc("btn_neutral_hover"),
                        text_color=tc("btn_text"),
                        border_width=1,
                        border_color=tc("border"),
                        state="normal",
                        text=name
                    )
            except Exception:
                # Buttons may be destroyed if a threaded run completes after
                # the user navigated away - never let that crash the callback.
                pass
        # Highlighting must never unlock the row while the cell is cleaning.
        self._enforce_post_run_clean_gate()

    def _apply_blank_freeze(self):
        """Grey out + disable the BLANK button when the test has no blank step.

        Blank is selected per test in test parameters (tickbox -> R.Blank /
        S.Blank). When nothing is selected the BLANK button must stay frozen
        for the whole test and must never be recommended.
        """
        if not hasattr(self, 'control_buttons'):
            return
        btn = self.control_buttons.get("BLANK")
        if btn is None:
            return
        if getattr(self, '_blank_frozen', True):
            try:
                btn.configure(state="disabled", fg_color=tc("btn_disabled"),
                              hover_color=tc("btn_disabled"), text_color=tc("text_faint"),
                              border_width=0, text="BLANK")
            except Exception:
                pass

    def _disable_workflow_buttons(self):
        """Freeze all workflow buttons (WATER, BLANK, STD, SAMPLE, etc.)."""
        if not hasattr(self, 'control_buttons'):
            return
        for name, btn in self.control_buttons.items():
            try:
                btn.configure(state="disabled", fg_color=tc("btn_disabled"),
                              text_color=tc("text_faint"))
            except Exception:
                pass

    def _enable_workflow_buttons(self):
        """Unfreeze all workflow buttons after LED align completes."""
        if not hasattr(self, 'control_buttons'):
            return
        for name, btn in self.control_buttons.items():
            try:
                if name == "BLANK" and getattr(self, '_blank_frozen', True):
                    continue  # frozen below after the loop
                btn.configure(state="normal", fg_color=tc("btn_neutral"),
                              text_color=tc("btn_text"))
            except Exception:
                pass
        # Re-apply the highlight to the recommended button
        self.highlight_next_workflow_button()
        # Keep the BLANK button frozen for tests that have no blank step.
        self._apply_blank_freeze()
        # Last word here too: this runs from a background thread, so it must
        # never be the thing that unlocks the row while a clean is in flight.
        self._enforce_post_run_clean_gate()
        # A hardware press that arrived during alignment runs now.
        if getattr(self, '_pending_press_after_align', False):
            self._pending_press_after_align = False
            print("[HW-BUTTON] Running the press queued during LED align")
            self.after(0, self._execute_selected_button)
        # Align finished: say so, then settle back to Ready so the chip never
        # keeps a stale "in progress" line while the operator is choosing a step.
        self.handle_step_status("aligned")
        try:
            self.after(4000, lambda: self._set_status("Ready")
                       if getattr(self, '_led_align_done', False)
                       and not getattr(self, 'is_measuring', False)
                       and getattr(self, '_post_run_clean', None) is None else None)
        except Exception:
            pass

    def handle_sequence_progression(self, button_type, method_type, blank_value):
        """Advance the recommendation after a button completes successfully.

        Implements the documented flow rules:
          - EP S.Blank  : WATER -> BLANK -> SAMPLE -> BLANK -> ... (continuous)
          - Normal run  : advance along the planned sequence
          - SAMPLE      : keep recommending SAMPLE (continuous sampling, rule 6)
          - Manual override / disruption: next button in the standard order
            after the executed one (rule 8: WATER->BLANK->STD->SAMPLE)
          - QC1 -> QC2 -> resume original sequence (rule 9A)
          - WASH / Dilution -> direct resume (rule 9B)
        """
        try:
            # --- Non-sequence buttons (rules 9A / 9B) -----------------------
            if button_type in ("QC1", "QC2"):
                self.handle_qc_progression(button_type)
                return
            if button_type in ("WASH", "DILUTION"):
                # WASH repeats (WASH -> WASH ...); DILUTION resumes the plan.
                self.handle_maintenance_progression(button_type)
                return

            # --- EP S.Blank continuous alternation (rule 5B) -----------------
            if self.is_s_blank_mode:
                if button_type == "WATER":
                    self._recommend_button("BLANK")
                elif button_type == "BLANK":
                    self._recommend_button("SAMPLE")
                elif button_type == "SAMPLE":
                    self._recommend_button("BLANK")
                return

            # --- Continuous sampling + first-run bookkeeping (rules 6, impl. notes) -
            if button_type == "SAMPLE":
                if not getattr(self, '_first_run_marked', False):
                    self._first_run_marked = True
                    self.db_manager.update_already_run(self.current_test_name, 1)
                    print("[SEQUENCE] First run complete - marked already_run=1")
                self.recovery_mode = False
                self._recommend_button("SAMPLE")
                return

            # --- Determine next recommendation -------------------------------
            # Normal progression: if the executed button is in the planned
            # sequence (and not its last step), advance along the plan.
            # Otherwise (end of plan, or manual override) follow the standard
            # button order: WATER->BLANK->STD->SAMPLE->SAMPLE (rules 6 & 8).
            was_recommended = (button_type == getattr(self, 'recommended_button', None))

            next_button = None
            if was_recommended and button_type in self.workflow_sequence:
                pos_in_plan = self.workflow_sequence.index(button_type)
                if pos_in_plan + 1 < len(self.workflow_sequence):
                    # Advance along the planned sequence
                    next_button = self.workflow_sequence[pos_in_plan + 1]
                    self.current_workflow_index = pos_in_plan + 1
                else:
                    # Executed the last planned step -> continuous sample
                    next_button = "SAMPLE"
                    self.current_workflow_index = len(self.workflow_sequence) - 1
            else:
                # Manual override / disruption (rule 8): next in standard order.
                # Once disrupted, the pipeline continues along the standard order
                # (e.g. BLANK->STD->SAMPLE->SAMPLE) exactly as the scenarios describe.
                next_button = self._next_standard(button_type)
                self.recovery_mode = True
                if button_type in self.standard_button_order:
                    self.current_workflow_index = self.standard_button_order.index(button_type)

            if next_button:
                self._recommend_button(next_button)
        except Exception as e:
            print(f"Error in handle_sequence_progression: {e}")

    def update_color_display(self, color_type, rgb_values):
        """
        Update the color display boxes with RGB values
        Args:
            color_type: Either "standard" or "sample"
            rgb_values: List of [R, G, B] values, each from 0-255
        """
        print(f"update_color_display called for {color_type} with values: {rgb_values}")

        if rgb_values is None or not isinstance(rgb_values, list) or len(rgb_values) != 3:
            # Invalid RGB values, don't update
            print(f"WARNING: Invalid RGB values for {color_type}: {rgb_values}")
            return

        # Ensure values are integers in 0-255 range
        rgb_values = [max(0, min(255, int(val))) for val in rgb_values]

        # Create hex color string from RGB
        hex_color = "#{:02x}{:02x}{:02x}".format(rgb_values[0], rgb_values[1], rgb_values[2])
        print(f"Setting {color_type} color to {hex_color}, RGB: {rgb_values}")

        if color_type == "standard":
            self.standard_rgb = rgb_values
            self.standard_color_box.configure(fg_color=hex_color)
            print(f"Standard color box updated with {hex_color}")
        elif color_type == "sample":
            self.sample_rgb = rgb_values
            self.sample_color_box.configure(fg_color=hex_color)
            print(f"Sample color box updated with {hex_color}")
        else:
            print(f"WARNING: Unknown color_type: {color_type}")

    def initialize_realtime_data_table(self):
        """Initialize the real-time data table structure optimized for RPi."""
        # Configure grid to ensure proper sizing.
        #
        # The two rows carry a MINIMUM height as well as a weight: this band is
        # the only thing between the graph and the action row, so its height has
        # to be the same whether it holds the header+reading table or (for an
        # out-of-range result) a single one-line notice. Without the minimum the
        # band shrank, the graph above it - which is the row with the stretch -
        # silently grew, and the plot appeared to jump mid-run.
        self.realtime_data_frame.grid_rowconfigure(0, weight=1, minsize=sp(22))
        self.realtime_data_frame.grid_rowconfigure(1, weight=1, minsize=sp(30))
        self.realtime_data_frame.grid_columnconfigure(0, weight=1)
        self.realtime_data_frame.grid_columnconfigure(1, weight=1)

        list_value = [1,2,3,4,5]
        # drop_values = ctk.CTkComboBox(self.realtime_data_frame,values=list_value)

        # Create table headers with borders - more compact
        headers = ["Time (s)", "Absorbance"]
        for col_index, header in enumerate(headers):
            cell_frame = ctk.CTkFrame(
                self.realtime_data_frame,
                fg_color=tc("btn_neutral"),
                corner_radius=8,
            )
            cell_frame.grid(row=0, column=col_index, padx=2, pady=(2, 1), sticky="nsew")
            # An explicit height, because a CTkLabel otherwise asks for 28 px
            # whatever its font: that floor, not the text, was what kept this
            # band (and so the graph) fat.
            header_label = ctk.CTkLabel(
                cell_frame,
                text=header,
                height=sp(18),
                font=theme_font(10, bold=True),
                text_color=tc("text_muted"),
            )
            header_label.pack(expand=True, fill="both", padx=3, pady=2)

        # Create value cells (empty for now) - more compact
        self.time_value_frame = ctk.CTkFrame(
            self.realtime_data_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=8,
            border_width=1,
            border_color=tc("border"),
        )
        self.time_value_frame.grid(row=1, column=0, padx=2, pady=(1, 2), sticky="nsew")
        # Reading values are read from arm's length: 15 px is still clearly
        # legible on the 7" panel while leaving the graph the space it needs.
        self.time_value_label = ctk.CTkLabel(
            self.time_value_frame,
            text="0.00",
            height=sp(24),
            font=theme_font(15, bold=True),
            text_color=tc("text"),
        )
        self.time_value_label.pack(expand=True, fill="both", padx=3, pady=2)

        self.realtime_value_frame = ctk.CTkFrame(
            self.realtime_data_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=8,
            border_width=1,
            border_color=tc("border"),
        )
        self.realtime_value_frame.grid(row=1, column=1, padx=2, pady=(1, 2), sticky="nsew")
        self.realtime_value_label = ctk.CTkLabel(
            self.realtime_value_frame,
            text="0.0000",
            height=sp(24),
            font=theme_font(15, bold=True),
            text_color=tc("text"),
        )
        self.realtime_value_label.pack(expand=True, fill="both", padx=3, pady=2)

    def update_result_box_color(self, result_value):
        """Colour the Result cell: green when inside the test's high/low limits."""
        try:
            value = float(result_value)
        except (TypeError, ValueError):
            # Default color
            self.result_value_frame.configure(fg_color=tc("surface_sunken"))
            self.result_value_label.configure(text_color=tc("text"))
            return

        # Prefer the test's configured range (cached per measurement screen).
        # An empty tuple means "no limits configured - already checked".
        limits = self._result_limits
        if limits is None:
            try:
                p = self.db_manager.load_parameters(self.current_test_name) or {}
                lo, hi = p.get('low_limit'), p.get('high_limit')
                if lo is not None and hi is not None:
                    lo, hi = float(lo), float(hi)
                    limits = (lo, hi) if hi > lo else ()
                else:
                    limits = ()
            except Exception:
                limits = ()
            self._result_limits = limits

        if not limits:
            # No high/low configured - there is nothing to compare against, so
            # keep the neutral default. Green/red only ever mean "inside/outside
            # the test's High/Low range" (never "no limits set").
            self.result_value_frame.configure(fg_color=tc("surface_sunken"))
            self.result_value_label.configure(text_color=tc("text"))
            return

        lo, hi = limits
        in_range = lo <= value <= hi
        if in_range:
            self.result_value_frame.configure(fg_color=tc("success"))
            self.result_value_label.configure(text_color=tc("on_success"))
        else:
            self.result_value_frame.configure(fg_color=tc("danger"))
            self.result_value_label.configure(text_color=tc("on_danger"))

    def initialize_results_table(self):
        """Initialize the results table structure optimized for RPi.

        Columns: Type | Result | Unit. Result shows the meaningful value for
        the run: raw water reference, average blank absorbance, user-input std
        concentration, calculated sample concentration.

        The table is rebuilt from scratch on every call: it is re-invoked when
        the dilution panel is dismissed (restore / reset dilution mode), so any
        leftover cells - the dilution factor buttons or an old out-of-range
        notice - are cleared first. Without this each rebuild stacked a
        duplicate set of labels into the same grid cells, leaving ghost text
        behind the live values.
        """
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        # Configure grid to ensure proper sizing. The row minimums are what keep
        # the band (and therefore the graph above it) exactly the same height
        # when this table is temporarily replaced by the out-of-range notice or
        # by the dilution factor picker - see initialize_realtime_data_table.
        self.results_frame.grid_rowconfigure(0, weight=1, minsize=sp(22))
        self.results_frame.grid_rowconfigure(1, weight=1, minsize=sp(30))
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_columnconfigure(1, weight=1)
        self.results_frame.grid_columnconfigure(2, weight=1)

        # Create table headers with borders - more compact
        headers = ["Type", "Result", "Unit"]
        # (headers keep the smaller size: the VALUES are the readable part)
        for col_index, header in enumerate(headers):
            cell_frame = ctk.CTkFrame(
                self.results_frame,
                fg_color=tc("btn_neutral"),
                corner_radius=8,
            )
            cell_frame.grid(row=0, column=col_index, padx=2, pady=(2, 1), sticky="nsew")
            header_label = ctk.CTkLabel(
                cell_frame,
                text=header,
                height=sp(18),
                font=theme_font(10, bold=True),
                text_color=tc("text_muted"),
            )
            header_label.pack(expand=True, fill="both", padx=3, pady=2)

        # Create value cells (empty for now) - more compact
        self.type_value_frame = ctk.CTkFrame(
            self.results_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=8,
            border_width=1,
            border_color=tc("border"),
        )
        self.type_value_frame.grid(row=1, column=0, padx=2, pady=(1, 2), sticky="nsew")
        self.type_value_label = ctk.CTkLabel(
            self.type_value_frame,
            text="-",
            height=sp(22),
            font=theme_font(12, bold=True),
            text_color=tc("text"),
        )
        self.type_value_label.pack(expand=True, fill="both", padx=3, pady=2)

        self.result_value_frame = ctk.CTkFrame(
            self.results_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=8,
            border_width=1,
            border_color=tc("border"),
        )
        self.result_value_frame.grid(row=1, column=1, padx=2, pady=(1, 2), sticky="nsew")
        self.result_value_label = ctk.CTkLabel(
            self.result_value_frame,
            text="-",
            # The single number the operator came for: still the largest text on
            # the screen, but trimmed step by step (26 -> 20 -> 18 -> 17 px, on
            # the operator's request for "slightly smaller, still readable") so
            # the band below the graph keeps giving height back to the plot.
            height=sp(26),
            font=theme_font(17, bold=True),
            text_color=tc("text"),
        )
        self.result_value_label.pack(expand=True, fill="both", padx=3, pady=2)

        self.unit_value_frame = ctk.CTkFrame(
            self.results_frame,
            fg_color=tc("surface_sunken"),
            corner_radius=8,
            border_width=1,
            border_color=tc("border"),
        )
        self.unit_value_frame.grid(row=1, column=2, padx=2, pady=(1, 2), sticky="nsew")
        self.unit_value_label = ctk.CTkLabel(
            self.unit_value_frame,
            text="-",
            height=sp(22),
            font=theme_font(12, bold=True),
            text_color=tc("text"),
        )
        self.unit_value_label.pack(expand=True, fill="both", padx=3, pady=2)

    def update_realtime_data(self, t, value):
        """Update real-time data table, graph line, and axes dynamically."""

        # ✅ Update table values
        self.time_value_label.configure(text=f"{t:.2f}")
        self.realtime_value_label.configure(text=f"{value:.4f}")

        # ✅ Reset call (t=0, val=0) — just update labels, don't add to data
        if value == 0 and t == 0:
            print("Real-time display reset")
            # Drop any stale points from a previous run so the next run's line
            # never shows leftover data.
            self.time_data = []
            self.abs_data = []
            return

        # First real reading of this run: the board's incubation wait is over,
        # so the panel moves on from "Incubating". The progress clock anchors on
        # this reading's own second - which is what keeps it identical to the
        # graph's x-axis instead of running ahead by the pre-roll.
        if getattr(self, '_awaiting_first_reading', False):
            self._awaiting_first_reading = False
            if getattr(self, '_status_event', None) == 'incubating':
                self.handle_step_status('measuring',
                                        getattr(self, '_run_type_of', None))
        self._clock_start_fallback()

        # ✅ Store data (use the sequential second `t`, not wall-clock time)
        self.time_data.append(t)
        self.abs_data.append(value)

        # NOTE: Plot redraw is handled by workflow.update_plot() which runs
        # right after this call. No canvas.draw() here to avoid double redraw
        # and UI lag.

        print(f"Updated real-time data with: Time (s): {t:.2f}, Value: {value:.4f}")

    def update_results_display(self, test_type, result, unit):
        """Update the results table values with sample counter support.

        Columns: Type | Result | Unit. Result shows the meaningful value for
        the run: raw water reference, average blank absorbance, user-input std
        concentration, calculated sample concentration.
        """
        # Handle empty result and unit
        result_display = result if result else "-"
        unit_display = unit if unit else "-"

        # DB-driven per-day sample numbering: the just-completed run is already
        # logged (handle_measurement_result saves before calling this), so its
        # number equals today's SAMPLE count for this test. Survives switching
        # between tests and resets to Sample 1 on a new day.
        if test_type == "Sample":
            test_type = f"Sample {self.db_manager.count_samples_today(self.current_test_name)}"

        # Store the last values
        self.last_result_values = {
            'type': test_type,
            'result': result_display,
            'unit': unit_display
        }

        # Update the display
        self.type_value_label.configure(text=test_type)
        self.result_value_label.configure(text=result_display)
        # Limit-based colouring only makes sense for concentrations
        # (Std/Sample/QC). Water (raw reference) and Blank (absorbance) are not
        # concentrations, so keep those neutral.
        if test_type.startswith(("Std", "Sample", "QC")):
            self.update_result_box_color(result_display)
        else:
            self.result_value_frame.configure(fg_color=tc("surface_sunken"))
            self.result_value_label.configure(text_color=tc("text"))
        self.unit_value_label.configure(text=unit_display)
        print(f"Updating results display with: Type: {test_type}, Result: {result_display}, Unit: {unit_display}")

    def handle_button_click(self, button_type):
        """Manual override: clicking a button SELECTS it (rules 1-3).

        Clicking does NOT run the test - it moves the orange highlight to the
        clicked button. The physical hardware button executes the highlighted
        selection (rule 2/3). Clicking the already-highlighted button keeps it.
        """
        try:
            if getattr(self, 'is_measuring', False):
                print("[SELECT] Measurement in progress - selection ignored")
                return
            if button_type == "BLANK" and getattr(self, '_blank_frozen', True):
                print("[SELECT] BLANK disabled for this test (no blank selected)")
                self.show_notification("Blank is not enabled for this test", error=True)
                return
            self.selected_button = button_type
            self._apply_highlight(button_type)
            self._update_sample_indicator(button_type)
            print(f"[SELECT] {button_type} selected (press hardware button to run)")
        except Exception as e:
            print(f"Error handling button click: {e}")

    def update_button_selection(self, selected_button):
        """Keep as alias for manual selection (used by callers)."""
        self.handle_button_click(selected_button)

    def determine_workflow_sequence(self):
        """Determine the recommended workflow sequence from test parameters & run status.

        The Blank choice in test parameters decides everything (same rules for
        every method - EP, TP and Kinetic):
          R.Blank selected:
             Standard  : first run  WATER -> BLANK -> STD -> SAMPLE
                         later runs WATER -> SAMPLE
             Factor    : first run  WATER -> BLANK -> SAMPLE
                         later runs WATER -> SAMPLE
          S.Blank selected:
             continuous WATER -> BLANK -> SAMPLE -> BLANK -> SAMPLE ...
          Blank NOT selected:
             the BLANK button is frozen for the whole test
             Standard  : first run  WATER -> STD -> SAMPLE
                         later runs WATER -> SAMPLE
             Factor    : WATER -> SAMPLE (always)
        """
        try:
            if not self.current_test_name:
                raise ValueError("No test currently selected")

            params = self.db_manager.load_parameters(self.current_test_name)
            if not params:
                raise ValueError(f"Could not load parameters for {self.current_test_name}")

            already_run = params.get('already_run', 0)
            method_type = str(params.get('method', '')).strip().upper()
            blank_mode = params.get('blank', '')
            if isinstance(blank_mode, (int, float)):
                blank_mode = str(int(blank_mode))
            else:
                blank_mode = str(blank_mode or '')
            use_factor = 1 if params.get('use_factor', 0) else 0
            use_std = not use_factor

            is_s_blank = blank_mode == "S.Blank"
            is_r_blank = blank_mode == "R.Blank"
            # Blank enabled? (R.Blank / S.Blank selected in test parameters).
            # When it is NOT selected the BLANK button stays frozen for the
            # whole test and no sequence step ever recommends it.
            self._blank_frozen = not (is_s_blank or is_r_blank)

            print(f"[SEQUENCE] Method: {method_type}, Blank: {blank_mode!r}, "
                  f"Factor: {use_factor}, Already run: {already_run}, "
                  f"Blank frozen: {self._blank_frozen}")

            # Initialize sequence tracking variables
            self.workflow_sequence = []
            self.original_sequence = []
            self.current_workflow_index = 0
            self.is_s_blank_mode = is_s_blank
            self.is_r_blank_mode = is_r_blank
            self.last_recommended_button = None
            self.selected_button = None
            self.qc_sequence_active = False
            self.return_to_button = None
            # Manual-override recovery order (rule 8) skips BLANK when it is
            # frozen, so a disruption can never recommend a frozen step.
            if self._blank_frozen:
                self.standard_button_order = ["WATER", "STD", "SAMPLE"]
            else:
                self.standard_button_order = ["WATER", "BLANK", "STD", "SAMPLE"]

            if is_s_blank:
                # Rule 5B: continuous alternating WATER->BLANK->SAMPLE->BLANK...
                self.workflow_sequence = ["WATER", "BLANK", "SAMPLE"]
            elif is_r_blank:
                # Rule 5A: R.Blank (any method)
                if use_std:
                    self.workflow_sequence = ["WATER", "BLANK", "STD", "SAMPLE"] if already_run == 0 else ["WATER", "SAMPLE"]
                else:
                    self.workflow_sequence = ["WATER", "BLANK", "SAMPLE"] if already_run == 0 else ["WATER", "SAMPLE"]
            else:
                # Blank not selected - blank never appears in the sequence.
                if use_std:
                    self.workflow_sequence = ["WATER", "STD", "SAMPLE"] if already_run == 0 else ["WATER", "SAMPLE"]
                else:
                    self.workflow_sequence = ["WATER", "SAMPLE"]

            self.original_sequence = self.workflow_sequence.copy()
            print(f"[SEQUENCE] Planned: {self.workflow_sequence}")

            # Rule 1-3: immediately highlight the first recommended step so the
            # system always recommends exactly one button on screen entry.
            if self.workflow_sequence:
                self._recommend_button(self.workflow_sequence[0])

        except Exception as e:
            error_message = f"Error determining workflow sequence: {str(e)}"
            print(error_message)
            self.create_popup(error_message)

    def highlight_next_workflow_button(self):
        """Highlight exactly ONE button: the system recommendation (rules 1-3).

        All buttons remain enabled and clickable (rule 7) - the orange one is
        simply the recommended + selected step that the hardware button runs.
        """
        try:
            if not hasattr(self, 'workflow_sequence') or not self.workflow_sequence:
                print("No workflow sequence defined, cannot highlight next button")
                return

            # If the user manually selected a button, keep that selection visible
            if getattr(self, 'selected_button', None):
                self._apply_highlight(self.selected_button)
                return

            # Otherwise highlight the current planned step
            idx = getattr(self, 'current_workflow_index', 0)
            if 0 <= idx < len(self.workflow_sequence):
                self._recommend_button(self.workflow_sequence[idx])
            else:
                self._recommend_button("SAMPLE")
        except Exception as e:
            print(f"Error highlighting next workflow button: {str(e)}")

    def check_hardware_button(self):
        """Poll for hardware button press (UART passive listener) or keyboard (Space/Enter).

        The firmware's Limit_sw_pressed thread sends "LIMIT SWITCH PRESS SUCCESSFUL"
        over UART when the physical button is pressed AND systemState == IDLE.
        We listen passively — zero extra UART commands sent.

        CRITICAL: During a measurement (take_readings reading sensor data),
        we MUST NOT read from serial — that would steal sensor bytes.
        is_measuring flag gates the UART read.
        """
        try:
            if not getattr(self, '_measurement_screen_active', False):
                self._hw_poll_after_id = None
                return
            triggered = False
            # 1. Check keyboard trigger (Space/Enter) — simulation or desktop
            if getattr(self, '_sim_button_pressed', False):
                self._sim_button_pressed = False
                triggered = True
            # 2. Check firmware limit switch message (hardware mode)
            #    ONLY when NOT measuring — reading serial during measurement
            #    would steal sensor data from take_readings()
            if not triggered and not SIMULATION_MODE:
                is_running = getattr(self, 'is_measuring', False) or \
                             getattr(self, '_measurement_running', False)
                if not is_running:
                    try:
                        from Hardware.stm32_backend import check_limit_switch
                        if check_limit_switch():
                            triggered = True
                    except ImportError:
                        pass
                # else: measurement in progress — serial read SKIPPED (safe)
            if triggered:
                print("[HW-BUTTON] Button triggered — executing step")
                self._execute_selected_button()
            # 50 ms instead of 100 ms: this is a pure queue drain (no serial
            # read), so it costs nothing and halves the worst-case lag between
            # the physical button and the command going out.
            self._hw_poll_after_id = self.after(50, self.check_hardware_button)
        except Exception as e:
            print(f"check_hardware_button error: {e}")
            self._hw_poll_after_id = self.after(200, self.check_hardware_button)

    def _simulate_hardware_press(self, event=None):
        """Simulation-mode stand-in for the physical hardware button."""
        self._sim_button_pressed = True
        return "break"

    def _execute_selected_button(self):
        """Run the currently highlighted (selected) workflow step (rule 3)."""
        if not getattr(self, '_led_align_done', True):
            # The press landed while the LED alignment was still in flight
            # (a fraction of a second after entering the screen). Queue it
            # instead of dropping it: the operator should not have to press
            # the hardware button twice.
            self._pending_press_after_align = True
            print("[HW-BUTTON] LED align in progress - press queued")
            return
        if getattr(self, 'is_measuring', False):
            print("[HW-BUTTON] Measurement in progress - ignored")
            return
        if getattr(self, '_post_run_clean', None) == 'running':
            # The row is frozen while the cell is being flushed; a physical
            # press must not slip a run in behind the clean (its aspirate would
            # be refused by the busy UART). The ONLY usable step in this state
            # is the WASH retry, which the 'failed' gate maps in below.
            print("[HW-BUTTON] Flow cell clean in progress - press ignored")
            self.handle_step_status("washing", tone="busy")
            return
        if getattr(self, '_measurement_running', False):
            # A worker thread still owns the UART (previous run winding down
            # after Back/abort). Starting another run now would interleave two
            # UART sessions and corrupt both — ignore until it exits (fast:
            # abort-aware waits quit within ~0.5 s).
            print("[HW-BUTTON] Previous run still exiting - ignored")
            return
        button_type = getattr(self, 'selected_button', None) or getattr(self, 'recommended_button', None)
        if not button_type:
            self.highlight_next_workflow_button()
            return
        print(f"[HW-BUTTON] Executing highlighted step: {button_type}")
        self.handle_measurement_button(button_type)

    def _store_measurement_context(self, button_type):
        """Store context needed by handle_measurement_result callback."""
        params = self.db_manager.load_parameters(self.current_test_name)
        self._ctx_seq = getattr(self, '_ctx_seq', 0) + 1
        self._ctx = {
            'button_type': button_type,
            'params': params,
            'method_type': params.get('method', '') if params else '',
            'blank_value': params.get('blank', '') if params else '',
            # Epochs so a STALE run finishing late can be told apart from
            # the current one: screen_token changes on every navigation,
            # seq changes on every button press.
            'screen_token': getattr(self, '_screen_token', 0),
            'seq': self._ctx_seq,
        }

    def handle_measurement_result(self, type_of, success, msg):
        """Called from background thread via after() when measurement completes."""
        ctx = getattr(self, '_ctx', None) or {}
        button_type = ctx.get('button_type', type_of)
        params = ctx.get('params', {})
        method_type = ctx.get('method_type', '')
        blank_value = ctx.get('blank_value', '')

        # STALE-RUN GUARD: if the user pressed Back (screen_token changed)
        # or started a newer run (seq changed) while this run was in flight,
        # its results belong to a dead screen. Discard silently — no DB
        # writes under the wrong test, no widget updates on the new screen,
        # no popups. The newer run (if any) owns is_measuring, so leave it.
        _cur_seq = getattr(self, '_ctx_seq', 0)
        _cur_screen = getattr(self, '_screen_token', 0)
        if (ctx.get('screen_token', _cur_screen) != _cur_screen
                or ctx.get('seq', _cur_seq) != _cur_seq):
            print("[WF] Stale measurement result discarded (screen/run changed)")
            return

        # Reset the run-lock FIRST so a failure later in this callback (e.g. the
        # user navigated away while the run was in flight) can never leave the
        # hardware button permanently blocked.
        self.is_measuring = False
        self._stop_run_clock()
        try:
            self.update_button_states(None, is_running=False)
        except Exception:
            pass

        # ---- Dilution (SAMPLE only) -------------------------------------
        # The workflow refused to store an out-of-range sample. Show the
        # dilution-factor buttons in the results area and keep SAMPLE selected
        # so the (diluted) sample can be re-run; nothing else advances.
        if (success and button_type == "SAMPLE" and isinstance(msg, dict)
                and msg.get('dilution_needed')):
            value = msg.get('result')
            try:
                detail = f"{float(value):.3f}"
            except (TypeError, ValueError):
                detail = "-"
            print(f"[DIL] Sample result {detail} out of range - asking for a dilution factor")
            self._last_out_of_range_value = detail
            try:
                self.show_dilution_interface()
            except Exception as e:
                print(f"[DIL] could not show the dilution interface: {e}")
            self._dilution_pending = True
            # Keep SAMPLE as the recommended/selected step for the re-run.
            self.selected_button = "SAMPLE"
            self._recommend_button("SAMPLE")
            self.show_notification(f"Result out of range ({detail}) - select a dilution factor",
                                   error=True)
            return

        if success:
            if button_type in ["WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2"]:
                unit = params.get('unit', '') if params else ''
                # Store BOTH values per result row: the meaningful result (water
                # raw reference, user-input std concentration, calculated sample
                # concentration, QC concentration) and the run's average
                # absorbance (blank/std/sample). The RESULT screen displays
                # separate Abs and Result columns from these.
                abs_val = None
                save_val = None
                if isinstance(msg, dict):
                    abs_val = msg.get('abs')
                    save_val = msg.get('result')
                elif msg is not None:
                    try:
                        save_val = float(msg)
                    except (ValueError, TypeError):
                        save_val = None
                self.db_manager.save_test_result(
                    self.current_test_name, button_type, save_val, unit, abs_val)

            # ---- Diluted re-run finished: restore the table, leave dilution mode --
            diluted_by = msg.get('diluted_by') if isinstance(msg, dict) else None
            if button_type == "SAMPLE" and diluted_by:
                try:
                    self.restore_results_table_after_dilution()
                except Exception as e:
                    print(f"[DIL] could not restore the results table: {e}")
                self.reset_dilution_mode()
                self._dilution_pending = False
                try:
                    self.show_notification(f"Dilution factor {float(diluted_by):g} applied")
                except Exception:
                    pass

            if button_type in ["WATER", "BLANK", "STD", "SAMPLE"]:
                self.handle_sequence_progression(button_type, method_type, blank_value)

                # "Sample" (not "Sample Concentration") so update_results_display's
                # counter labels consecutive runs Sample, Sample(2), Sample(3)...
                # exactly like an industry analyzer's run list.
                display_type = {
                    "WATER": "Water",
                    "BLANK": "Blank",
                    "STD": "Std",
                    "SAMPLE": "Sample",
                }.get(button_type, button_type)
                unit = params.get('unit', '-') if params else '-'
                if isinstance(msg, dict):
                    # Result column: concentration for std/sample, raw water
                    # reference for water, average absorbance for blank.
                    result_str = f"{msg['result']:.3f}" if msg.get('result') is not None else (
                        f"{msg['abs']:.3f}" if msg.get('abs') is not None else "-")
                else:
                    result_str = f"{msg:.3f}" if msg is not None else "-"
                self.update_results_display(display_type, result_str, unit)

            elif button_type in ["QC1", "QC2"]:
                # Show the QC concentration in the same result box as the other
                # runs (blank/std/sample) before moving on to QC2/resume.
                unit = params.get('unit', '-') if params else '-'
                if isinstance(msg, dict) and msg.get('result') is not None:
                    try:
                        self.update_results_display(button_type, f"{float(msg['result']):.3f}", unit)
                    except (TypeError, ValueError):
                        pass
                self.handle_qc_progression(button_type)
            elif button_type in ["WASH"]:
                self.handle_maintenance_progression(button_type)

            self.highlight_next_workflow_button()
        else:
            self.highlight_next_workflow_button()
            self.show_info_dialog(title='error', message=msg)

    def handle_measurement_button(self, button_type):
        """Handle measurement button click with updated workflow logic and color display"""
        try:
            if not hasattr(self, 'workflow_manager'):
                raise AttributeError("WorkflowManager not properly initialized")
            if not self.current_test_name:
                raise ValueError("No test currently selected")

            # HARD GATE: while the flow cell is being cleaned (or a previous
            # run is still winding down) the UART belongs to that job. Starting
            # a measurement now would interleave two exchanges on the same
            # serial port and both would end up with garbled replies. The
            # buttons are frozen for the same reason - this is the backstop
            # for any path that reaches the workflow without going through
            # them (hardware press, scripted call, double-click race).
            if getattr(self, '_post_run_clean', None) == 'running':
                print("[GATE] Flow cell still cleaning - run refused")
                self.show_notification("Washing - please wait", error=True)
                return
            if getattr(self, '_measurement_running', False):
                print("[GATE] Previous run still owning the UART - run refused")
                self.show_notification("Please wait - previous step is finishing",
                                       error=True)
                return

            params = self.db_manager.load_parameters(self.current_test_name)
            already_run = params.get('already_run', 0)
            method_type = params.get('method', '')
            blank_value = params.get('blank', '')

            print(f"Executing {button_type} workflow...")

            # Panel wording + run progress clock. WASH is a maintenance step, so
            # it is announced as "Washing" and never gets a measurement clock.
            _type_of = self._BUTTON_TYPES.get(button_type, button_type.lower())
            if button_type == "WASH":
                self.handle_step_status("washing")
            else:
                self.handle_step_status("measuring", _type_of)
                # Window from the shared timing rule (water 5 s, EP blank 5 s,
                # otherwise delay + measuring) - the SAME number the graph uses,
                # so the clock and the x-axis can never disagree.
                try:
                    _run_window = self.workflow_manager.get_run_timing(
                        method_type, params, _type_of)[0]
                except Exception:
                    _run_window = None
                self._start_run_clock(method_type, _run_window)
            self._run_type_of = _type_of
            self._awaiting_first_reading = True
            self.is_measuring = True

            if button_type in ["WATER", "BLANK", "STD", "SAMPLE"]:
                self.update_realtime_data(0.0, 0.0)

            self.update_button_states(button_type, is_running=True)
            self.workflow_manager.set_current_test(self.current_test_name)

            success = False
            result = None

            if button_type == "WATER":
                success, result = self.workflow_manager.water_workflow()
            elif button_type == "BLANK":
                success, result = self.workflow_manager.blank_workflow()
            elif button_type == "STD":
                success, result = self.workflow_manager.standard_workflow()
            elif button_type == "SAMPLE":
                success, result = self.workflow_manager.sample_workflow()
            elif button_type in ("QC1", "QC2"):
                qc_number = 1 if button_type == "QC1" else 2
                qc_params = self.db_manager.load_qc_values(self.current_test_name)
                if not qc_params:
                    self.show_notification("QC parameters not set for this test", error=True)
                    self.is_measuring = False
                    self._stop_run_clock()
                    self.update_button_states(None, is_running=False)
                    self.highlight_next_workflow_button()
                    return
                # QC runs like a sample (same timing/calibration) but is never
                # diluted; it is threaded like the other workflows and reports
                # back through handle_measurement_result just like SAMPLE.
                success, result = self.workflow_manager.qc_workflow(qc_number)
            elif button_type == "WASH":
                # Threaded like the auto-clean: clean() blocks for ~4 s waiting
                # for "FLOW CELL CLEAN COMPLETE", and doing that on the UI
                # thread froze the whole window (buttons, clock, redraws).
                self._start_clean_thread(manual=True)
                return

            # For threaded workflows (WATER/BLANK/STD/SAMPLE/QC), post-processing
            # happens in the handle_measurement_result callback. For sync ones,
            # do it here.
            if button_type in ["WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2"]:
                if not success:
                    # The workflow failed synchronously (before starting a thread),
                    # so no completion callback will ever fire - reset state now
                    # instead of leaving the hardware button locked.
                    self.is_measuring = False
                    self.update_button_states(None, is_running=False)
                    self.highlight_next_workflow_button()
                    self.show_info_dialog(title='error', message=result)
                    return
                self._store_measurement_context(button_type)
                return

            self.update_button_states(None, is_running=False)
            self.is_measuring = False

            if success:
                if button_type in ["WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2"]:
                    unit = params.get('unit', '')
                    if result is not None:
                        try:
                            result_float = float(result)
                            self.db_manager.save_test_result(
                                self.current_test_name,
                                button_type,
                                result_float,
                                unit
                            )
                        except (ValueError, TypeError):
                            pass

                if button_type in ["WATER", "BLANK", "STD", "SAMPLE"]:
                    self.handle_sequence_progression(button_type, method_type, blank_value)
                elif button_type in ["QC1", "QC2"]:
                    self.handle_qc_progression(button_type)
                elif button_type in ["WASH"]:
                    self.handle_maintenance_progression(button_type)

                self.highlight_next_workflow_button()
            else:
                self.highlight_next_workflow_button()
                self.show_info_dialog(title='error', message=result)

        except Exception as e:
            self.update_button_states(None, is_running=False)
            self.is_measuring = False
            self.highlight_next_workflow_button()
            error_message = f"Error executing {button_type} workflow: {e}"
            print(error_message)
            self.create_popup(error_message)

    def update_workflow_buttons(self):
        """Update the workflow buttons based on the current workflow sequence"""
        try:
            # Make sure we have a workflow sequence
            if not hasattr(self, 'workflow_sequence') or not self.workflow_sequence:
                print("No workflow sequence defined, cannot update buttons")
                return

            # Now highlight the next button in the sequence
            self.highlight_next_workflow_button()

        except Exception as e:
            error_message = f"Error updating workflow buttons: {str(e)}"
            print(error_message)

    def update_button_states(self, active_button=None, is_running=False):
        """Update button states with better color combinations"""
        # Button state colors come from the active theme, so the whole control
        # row repaints with the rest of the app when the theme is switched.
        BUTTON_STATES = self.button_states()
        print(f"Updating states, active button: {active_button}, is running: {is_running}")
        if is_running:
            # During a test run, disable all buttons
            for button_name, button in self.control_buttons.items():
                if button_name == active_button:
                    # Active button configuration
                    button.configure(
                        fg_color=BUTTON_STATES["active"]["fg_color"],
                        hover_color=BUTTON_STATES["active"]["hover_color"],
                        text_color=BUTTON_STATES["active"]["text_color"],
                        border_width=2,
                        border_color=BUTTON_STATES["active"]["border_color"],
                        state="disabled",
                        text=f"{button_name} (Running...)"
                    )
                else:
                    # Inactive button configuration during a run
                    button.configure(
                        fg_color=BUTTON_STATES["inactive"]["fg_color"],
                        hover_color=BUTTON_STATES["inactive"]["hover_color"],
                        text_color=BUTTON_STATES["inactive"]["text_color"],
                        border_width=1,
                        border_color=BUTTON_STATES["inactive"]["border_color"],
                        state="disabled",
                        text=button_name
                    )
        else:
            # Reset all buttons to normal state - we'll highlight the recommended one separately
            for button_name, button in self.control_buttons.items():
                button.configure(
                    fg_color=BUTTON_STATES["normal"]["fg_color"],
                    hover_color=BUTTON_STATES["normal"]["hover_color"],
                    text_color=BUTTON_STATES["normal"]["text_color"],
                    border_width=0,
                    state="normal",
                    text=button_name
                )

            # After resetting all buttons, highlight the next one using highlight_next_workflow_button
            if hasattr(self, 'workflow_sequence') and hasattr(self, 'current_workflow_index'):
                self.highlight_next_workflow_button()

            # Keep the BLANK button frozen for tests that have no blank step.
            self._apply_blank_freeze()

        # Last word: a clean in flight (or a failed one) owns the button row.
        self._enforce_post_run_clean_gate()

    def handle_qc_progression(self, button_type):
        """Handle progression after QC buttons (rule 9A).

        QC1 -> recommend QC2 (complete the QC pair).
        QC2 -> resume the original planned sequence from where it was interrupted.
        """
        try:
            if button_type == "QC1":
                # Store the step we must return to after the QC pair is done.
                # If a manual WASH happened in between, the current
                # recommendation IS "WASH" (rule 9B: cleaning repeats) - resuming
                # that would hand the operator back to the wash instead of the
                # step they were actually on, so fall back to what the wash
                # displaced.
                resume = getattr(self, 'recommended_button', None)
                if resume in (None, "WASH"):
                    resume = (getattr(self, '_pre_wash_recommendation', None)
                              or resume)
                self.return_to_button = resume
                self.qc_sequence_active = True
                self._recommend_button("QC2")
            elif button_type == "QC2":
                self.qc_sequence_active = False
                return_button = getattr(self, 'return_to_button', None)
                self.return_to_button = None
                if return_button:
                    # Resume original recommendation (rule 9A)
                    self._recommend_button(return_button)
                else:
                    self.highlight_next_workflow_button()
        except Exception as e:
            print(f"Error in handle_qc_progression: {e}")

    def handle_maintenance_progression(self, button_type="WASH"):
        """Handle progression after maintenance buttons (WASH / Dilution) - rule 9B.

        WASH keeps recommending WASH: cleaning is repeatable, so the operator
        can wash as many times as needed. The loop is left by selecting another
        button (e.g. SAMPLE), which then becomes the recommendation and follows
        its own rule (SAMPLE -> SAMPLE -> ...).

        DILUTION keeps the old "direct resume": the recommendation returns to
        exactly what it was before the interruption. If a QC pair is in progress
        (e.g. QC1 -> Wash -> QC2), the pending QC step is recommended instead
        (rule 9A multi-disruption).
        """
        try:
            if str(button_type).upper() == "WASH":
                # Remember what the wash displaced: the operator goes back to
                # that step as soon as they choose it again, and a QC pair
                # started after the wash still resumes it (rules 9A + 9B).
                current = getattr(self, 'recommended_button', None)
                if current and current != "WASH":
                    self._pre_wash_recommendation = current
                self._recommend_button("WASH")
                return
            if getattr(self, 'qc_sequence_active', False):
                # QC pair was interrupted by maintenance - resume the QC pair
                self._recommend_button("QC2")
                return
            target = getattr(self, 'recommended_button', None)
            if target:
                self._recommend_button(target)
            else:
                self.highlight_next_workflow_button()
        except Exception as e:
            print(f"Error in handle_maintenance_progression: {e}")
            self.highlight_next_workflow_button()

    def button_states(self):
        """Control-button color scheme for the active theme."""
        return {
            "active": {
                "fg_color": tc("run_active"),
                "hover_color": tc("run_active_hover"),
                "text_color": tc("on_run_active"),
                "border_color": tc("run_active_hover"),
            },
            "recommended": {
                "fg_color": tc("warning"),
                "hover_color": tc("warning_hover"),
                "text_color": tc("warning_text"),
                "border_color": tc("warning_hover"),
            },
            "inactive": {
                # Frozen while a run is in flight. The fill stays receded but
                # the LABEL stays readable - a faint grey label on a dark
                # button was impossible to read, and the operator still needs
                # to see which step is which while waiting.
                "fg_color": tc("btn_disabled"),
                "hover_color": tc("btn_disabled"),
                "text_color": tc("btn_disabled_text"),
                "border_color": tc("border"),
            },
            "normal": {
                "fg_color": tc("btn_neutral"),
                "hover_color": tc("btn_neutral_hover"),
                "text_color": tc("btn_text"),
                "border_color": None,
            },
        }

    # ------------------------------------------------------------------
    # Flow-cell cleaning gate
    # ------------------------------------------------------------------
    # After EVERY finished run the cell is flushed, and the operator may not
    # start the next step until the board has confirmed it. ``_post_run_clean``
    # is the UI side of that gate:
    #   None      - idle, buttons behave normally
    #   'running' - clean in flight, every button frozen
    #   'failed'  - the board did not confirm; only WASH is usable (retry)
    # It is enforced from update_button_states()/_apply_highlight() so no
    # later callback (result painting, recommendation, restyle) can quietly
    # unlock the row mid-clean.
    def begin_post_run_clean(self):
        """Called from the run thread the moment a run finishes.

        This is the ONLY thing the operator sees between "result shown" and
        "next step allowed": every control button is frozen until the board has
        confirmed the flush, so no test can be started on a dirty (or busy)
        flow cell. The clean is an internal step - it is deliberately NOT shown
        as a WASH step in the recommendation, because it is not part of the
        operator's sequence (WATER -> BLANK -> STD -> SAMPLE).
        """
        # A clean is NOT a measurement: the run it follows has ended, and the
        # freeze that keeps the operator out comes from the clean gate below.
        # Leaving is_measuring set here made handle_post_run_clean() believe a
        # newer run owned the screen and drop its own result.
        self.is_measuring = False
        self._stop_run_clock()
        self._post_run_clean = 'running'
        self._clean_screen_token = getattr(self, '_screen_token', None)
        # No toast here: the post-run flush is an internal step, and announcing
        # "cleaning flow cell" on every run was noise. The status box beside the
        # header shows it while it happens, and the failure case still raises a
        # notification (that one needs the operator's attention).
        # Freeze the row without re-purposing the WASH button: WASH is a manual
        # maintenance step, not the running step, and painting it as
        # "WASH (Cleaning...)" made it look like the workflow had jumped to it.
        self.handle_step_status("washing")
        self._enforce_post_run_clean_gate()

    def handle_post_run_clean(self, success, error=''):
        """The board answered the CLEAN command (or it failed/timed out)."""
        manual = getattr(self, '_clean_manual', False)
        self._clean_manual = False
        # Ownership: a clean that belonged to a screen the operator already left
        # must not touch the gate of the screen that replaced it. Otherwise its
        # (usually failed) outcome painted "clean failed" onto the NEW test and
        # froze a row that had nothing to do with it.
        owner = getattr(self, '_clean_screen_token', None)
        if owner is not None and owner != getattr(self, '_screen_token', None):
            print("[CLEAN] clean belonged to a previous screen - result ignored")
            return
        # A newer run (started after this clean was requested) owns the screen
        # now: clearing the gate or unlocking the row would clobber its state.
        if (getattr(self, 'is_measuring', False)
                or getattr(self, '_measurement_running', False)):
            print("[CLEAN] a newer run owns the screen - clean result ignored")
            return
        self._post_run_clean = None if success else 'failed'
        try:
            if success:
                # No "Flow cell cleaned" toast - the status box says "Ready"
                # again and the row unlocks, which is the same information
                # without a pop-up on every single run.
                self.handle_step_status("ready")
            else:
                self.handle_step_status("wash_failed")
                self.show_notification(
                    f"Wash failed ({error}) - press WASH to retry", error=True)
        except Exception:
            pass
        try:
            self.is_measuring = False
            if not getattr(self, '_led_align_done', True):
                # This screen was opened while the clean was still in flight, so
                # its LED alignment still owns the button row. Unfreezing here
                # would hand the operator a live button before align finished;
                # _enable_workflow_buttons() unlocks when the align reports in.
                print("[CLEAN] clean finished during LED align - row stays frozen")
                return
            self.update_button_states(None, is_running=False)
            if success:
                resume = getattr(self, '_pre_clean_retry_step', None)
                self._pre_clean_retry_step = None
                if resume:
                    # This clean was the operator recovering from a failed
                    # automatic flush. The gate had forced WASH into the
                    # selection, so restore the step they were actually on -
                    # and do NOT advance the sequence again: the run that
                    # happened before the failed flush already advanced it.
                    self.selected_button = resume
                    self._recommend_button(resume)
                else:
                    if manual:
                        # A manual WASH keeps WASH recommended (rule 9B):
                        # cleaning is repeatable. An automatic post-run clean
                        # must NOT move the recommendation - the run itself
                        # already advanced the sequence in
                        # handle_measurement_result.
                        self.handle_maintenance_progression("WASH")
                    self.highlight_next_workflow_button()
        except Exception as exc:
            print(f"[CLEAN] could not restore the buttons: {exc}")

    def _start_clean_thread(self, manual=False):
        """Run one CLEAN off the UI thread; unlock through the same gate."""
        if getattr(self, '_post_run_clean', None) == 'running':
            return
        self._clean_manual = bool(manual)
        self.begin_post_run_clean()

        def _work():
            ok, err = True, ''
            try:
                print("[CLEAN] sending CLEAN" + (" (manual WASH)" if manual else ""))
                clean()
            except Exception as exc:                # noqa: BLE001 - shown to operator
                ok, err = False, str(exc)
            # Through the thread-safe queue: a plain after() from this worker
            # raises "main thread is not in main loop" whenever Tk is not
            # inside mainloop(), and the swallowed exception left the row
            # frozen on "cleaning" forever.
            poster = getattr(self, 'ui_post', None)
            if poster is not None:
                poster(self.handle_post_run_clean, ok, err)
            else:
                try:
                    self.after(0, lambda: self.handle_post_run_clean(ok, err))
                except Exception as exc:            # noqa: BLE001 - last resort
                    print(f"[CLEAN] could not report the result: {exc}")

        threading.Thread(target=_work, daemon=True).start()

    def _enforce_post_run_clean_gate(self):
        """Freeze the control row while a clean is in flight/failed."""
        state = getattr(self, '_post_run_clean', None)
        if not state or not getattr(self, 'control_buttons', None):
            return
        frozen_text = tc("btn_disabled_text")
        for name, btn in self.control_buttons.items():
            try:
                if state == 'running':
                    # Frozen but READABLE, and labelled exactly as it was: the
                    # row must look "busy", not "switched to WASH".
                    btn.configure(state="disabled", border_width=1,
                                  border_color=tc("border"),
                                  fg_color=tc("btn_disabled"),
                                  hover_color=tc("btn_disabled"),
                                  text_color=frozen_text, text=name)
                elif state == 'failed' and name == "WASH":
                    # Freezing is what stops another test running; the single
                    # exception is WASH itself, so the operator has a way back
                    # instead of a locked instrument.
                    btn.configure(state="normal", fg_color=tc("warning"),
                                  hover_color=tc("warning_hover"),
                                  text_color=tc("warning_text"),
                                  border_width=2, border_color=tc("warning_hover"),
                                  text="WASH (Retry clean)")
                elif state == 'failed':
                    btn.configure(state="disabled", border_width=1,
                                  border_color=tc("border"),
                                  fg_color=tc("btn_disabled"),
                                  hover_color=tc("btn_disabled"),
                                  text_color=frozen_text, text=name)
            except Exception:
                pass
        # The retry button must also be the step the hardware button executes.
        # Without this the row showed "WASH (Retry clean)" while the stored
        # selection was still the planned step, so pressing the button ran a
        # SAMPLE/STD right after a failed clean - and with the abandoned clean
        # still holding the UART that aspirate came back as
        # "ASPIRATE BUSY - UART stayed locked" (see loghard.txt).
        if state == 'failed':
            current = (getattr(self, 'selected_button', None)
                       or getattr(self, 'recommended_button', None))
            if current and current != "WASH":
                # Remember where the operator was so a successful retry hands
                # them back their planned step instead of parking on WASH.
                self._pre_clean_retry_step = current
            self.selected_button = "WASH"
            self.recommended_button = "WASH"
            self.last_recommended_button = "WASH"

    def reset_button_states(self):
        """Reset all buttons to their original state"""
        normal = self.button_states()["normal"]
        for button_name, button in self.control_buttons.items():
            button.configure(
                fg_color=normal["fg_color"],
                hover_color=normal["hover_color"],
                text_color=normal["text_color"],
                border_width=0,
                state="normal",
                text=button_name
            )

    def show_action_popup(self, action_type):
        """Show Run/Cancel popup for any action"""
        popup = ctk.CTkToplevel(self)
        popup.title(f"{action_type} Action")
        # Center popup
        width = 600
        height = 150
        x = self.winfo_x() + (self.winfo_width() - width) // 2
        y = self.winfo_y() + (self.winfo_height() - height) // 2
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.update()
        popup.grab_set()
        # Add buttons
        button_frame = ctk.CTkFrame(popup)
        button_frame.pack(expand=True)
        run_btn = ctk.CTkButton(
            button_frame,
            text="Run",
            command=lambda: self.execute_action_workflow(action_type, popup)
        )
        run_btn.pack(side="left", padx=10)
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=popup.destroy
        )
        cancel_btn.pack(side="left", padx=10)
