"""
core.py - App lifecycle, hardware/UART setup, screen navigation and shared dialogs.

Part of the ui package (split from the original monolithic ui.py).
"""

import customtkinter as ctk
import tkinter
from tkinter import messagebox
import queue
import threading
import time
from Hardware.config import SIMULATION_MODE
from ui.hardware_actions import reverse, flow_water
from ui.theme import (
    colors as theme_colors,
    c as tc,
    card as theme_card,
    polish_tree as theme_polish_tree,
    sp as theme_sp,
    theme as theme_manager,
    apply_appearance as theme_apply_appearance,
    DESIGN_W as WINDOW_DESIGN_W,
    DESIGN_H as WINDOW_DESIGN_H,
    ui_scale_for as window_scale_for,
    set_ui_scale as window_set_ui_scale,
)
from ui.temperature import TemperatureStabilization
from backend import DatabaseManager
from workflow import WorkflowManager

def window_plan(screen_width, screen_height, env=None):
    """Decide the window's size and chrome from the environment.

    Pure (no Tk), so the policy is testable without opening a window. Returns
    ``(width, height, fullscreen, borderless)``:

    * ``BIO_SCREEN=WxH``            - rehearse that exact panel size (dev,
      previews, harnesses). ``BIO_BORDERLESS=1`` draws it without decorations,
      which is what the instrument looks like.
    * launched (``BIO_LAUNCHED=1``) - the real instrument: borderless fullscreen
      on the whole panel, no title bar and no window buttons.
    * imported instead of launched  - a decorated window the size of the panel,
      so tests and scripts never take over the desktop.
    """
    import os as _os
    env = _os.environ if env is None else env
    target = CoreMixin._parse_emulated_screen(env.get("BIO_SCREEN", ""))
    borderless = str(env.get("BIO_BORDERLESS", "")).strip() == "1"
    launched = str(env.get("BIO_LAUNCHED", "")).strip() == "1"
    screen_w = max(320, int(screen_width or WINDOW_DESIGN_W))
    screen_h = max(240, int(screen_height or WINDOW_DESIGN_H))
    if target:
        width, height = target
        fullscreen = False
    elif launched:
        width, height = screen_w, screen_h
        fullscreen = True
    else:
        width = min(WINDOW_DESIGN_W, screen_w)
        height = min(WINDOW_DESIGN_H, screen_h)
        fullscreen = False
    return (max(320, min(int(width), screen_w)),
            max(240, min(int(height), screen_h)),
            fullscreen, borderless)


class CoreMixin:
    """CoreMixin - App lifecycle, hardware/UART setup, screen navigation and shared dialogs."""

    def __init__(self):
        super().__init__()

        # ---- thread-safe worker -> UI delivery ----------------------------
        # Workers (measurement, clean, LED align) must never call Tk directly:
        # `after()` from a non-main thread raises "main thread is not in main
        # loop" whenever the interpreter is not inside mainloop(), and because
        # those calls were wrapped in try/except the callback was simply lost -
        # the UI then waited forever for a result that would never arrive (the
        # "stuck on clean, buttons frozen" report). A plain queue drained by a
        # main-thread timer is always safe.
        self._ui_post_queue = queue.Queue()
        self._ui_post_pump_id = None
        self._start_ui_post_pump()

        # Paint the saved theme before the first widget exists so nothing is
        # created in the wrong mode and then repainted.
        theme_apply_appearance()

        # Initialize managers first
        self.db_manager = DatabaseManager()
        # Configure main window
        # Taskbar/dev-window title only: on the instrument the window is
        # borderless (see _setup_window), so no title bar or window buttons are
        # ever drawn - the way out is the POWER screen.
        self.title("Biospectrometer Analyzer")
        try:
            self.configure(fg_color=theme_colors()["window_bg"])
        except Exception as exc:
            print(f"[THEME] could not color the window: {exc}")
        # Callable that rebuilds whatever screen is on show (set by each
        # show_* method) so toggling the theme repaints the current screen.
        self._screen_rebuild = None
        self.workflow_manager = WorkflowManager(db_manager=self.db_manager, ui=self)
        # Navigation / run epochs. _screen_token is bumped on EVERY screen
        # change (see clear_frames); background threads capture it at start
        # and must ignore their results when it has moved on. This stops a
        # stale LED-align / measurement thread from a previous screen from
        # enabling buttons, writing results, or stealing UART replies that
        # belong to the current screen.
        self._screen_token = 0
        self._closing = False
        self._measurement_screen_active = False
        self._measurement_running = False
        self._hw_poll_after_id = None
        self._graph_after_id = None
        self._ctx_seq = 0
        self.use_factor_var = ctk.BooleanVar(value=False)
        self.use_blank_var = ctk.BooleanVar(value=False)
        self.initialize_hardware()


        # Set default target temperature
        # self.target_temp = 37.0  # Default to 37°C which is a common biochemical analysis temperature

        #-------------------------------------------
        # Starting temperature
        # self.temp_controller = TemperatureController(setpoint=37.0)
        # self.temp_controller = TemperatureController()
        # self.temp_controller.start()
        # self.temp_controller.set_display_status(False)

        # self.temp_thread = threading.Thread(
        #     target=self.temp_controller.control_loop,
        #     daemon=True
        # )
        # self.temp_thread.start()
        # self.after(500, self.update_temperature_display)

        '''--------------------------------Making Responsive-------------------------------------------------'''
        # Start maximized while keeping title bar with minimize/maximize/close

        # Get the screen dimensions
        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        # Size the window for the instrument panel and pick the layout scale.
        # Must happen BEFORE the first screen is built: CustomTkinter applies
        # widget scaling to widgets created after set_widget_scaling().
        self._setup_window()

        # Configure grid for responsive layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        '''--------------------------------------------------------------------------------------------------'''

        self.frames = {}  # Initialize frames dictionary
        self.tests = []  # List to store created tests
        self.param_entries = {}  # Dictionary to store entry widgets

        # Store current test ID
        self.current_test_id = None
        self.current_test_name = None
        self.control_buttons = {}
        # Initialize Dilution related things
        self.dilution_mode_active = False
        self.dilution_factor = None
        self.result_out_of_range = False
        # True while waiting for a diluted SAMPLE re-run; carries the
        # out-of-range value so the dilution panel can explain itself.
        self._dilution_pending = False
        self._last_out_of_range_value = None
        self.ser = None
        self.stabilization_complete = False
        self.stabilization_complete = False
        # Load tests from database
        self.tests = self.db_manager.load_tests()

        # Warm-up clock: ten minutes from GUI start (ui/temperature.py). It
        # starts BEFORE the first screen so the operator's wait is honest from
        # launch, and it keeps counting while they browse other screens.
        self.temp_warmup = TemperatureStabilization()
        self.start_temperature_warmup()

        # Create and show main menu FIRST so the UI appears immediately
        self.show_main_menu()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Connect to hardware in background so the UI is not blocked
        if not SIMULATION_MODE:
            import threading
            threading.Thread(target=self._connect_hardware_async, daemon=True).start()
        else:
            print("[SIM] ESP32 connection skipped")

        # Pre-import matplotlib in background so measurement screen loads instantly
        def _preload_matplotlib():
            import matplotlib.pyplot as _plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _Fig
            import sys
            mod = sys.modules.get('ui.measurement')
            if mod is not None:
                mod.plt = _plt
                mod.FigureCanvasTkAgg = _Fig
            print("[UI] matplotlib pre-loaded")
        import threading as _t
        _t.Thread(target=_preload_matplotlib, daemon=True).start()

        # Map the window once BEFORE the caller enters mainloop().
        #
        # On Windows, entering Tk's mainloop with the window still unmapped, while
        # the startup timers below are queued, can deadlock the event loop: the
        # window is drawn but no event is ever processed, so every button is dead
        # and the only way out is to kill the app. The queued startup timers are
        # Tk calls that act on window state:
        #
        #   after(100) maximize_window          -> state("zoomed")
        #   after(120) pump_stabilization       -> configure() on status widgets
        #   ctk internals check_dpi_scaling / _windows_set_titlebar_icon
        #
        # Processing pending events once here maps the window first, after which
        # those timers run normally (verified: mainloop hangs 4/4 without this
        # call and returns 4/4 with it).
        try:
            self.update_idletasks()
            self.update()
        except Exception as exc:
            print(f"[UI] initial map failed: {exc}")

    def _connect_hardware_async(self):
        """Connect to STM32 in a background thread so the UI appears instantly."""
        if not self.initialize_uart():
            # Show the error on the main thread, in the window's own banner:
            # a native Tk messagebox is small on the 7" panel and can end up
            # behind the borderless full-screen window, where the operator
            # never sees it. duration=0 keeps it up until it is tapped.
            self.after(0, lambda: self.show_notification(
                "Hardware Error: could not connect to the ESP32 Sensor Board. "
                "Tap to dismiss.", duration=0, error=True))

    def initialize_uart(self):
        """Connect to the ESP32 using the test2.py protocol (PING/PONG + gain).

        Opens /dev/serial0, runs the PING/PONG handshake and sets the sensor
        gain - exactly what Hardware/test2.py does successfully on the bench.
        The probe port is closed after the handshake; per-measurement
        acquisition reconnects independently.
        """
        if SIMULATION_MODE:
            print("[SIM] UART initialized")
            self.ser = None
            return True

        try:
            from Hardware.stm32_backend import initialize as stm32_init, send_ping
            if stm32_init():
                print("STM32 connected successfully")
                self.ser = None  # STM32 manages its own connection
                return True
            else:
                print("STM32 connection failed")
                self.ser = None
                return False

        except Exception as e:
            print(f"Failed to initialize STM32 UART: {e}")
            self.ser = None
            return False

    # ==================== worker -> UI delivery ====================

    # Latency of worker -> UI callbacks (status chip, buttons, graph points).
    # Every callback a background thread posts waits for this timer, so at
    # 120 ms a tap could sit on the queue for an eighth of a second before the
    # screen moved - the "the UI takes 10-50 ms to react to anything" feeling.
    # 20 ms is a sixth of that and still just one cheap no-op 50 times a second
    # on the Pi (the pump drains everything the queue holds and re-arms once).
    UI_POST_PUMP_MS = 20

    def _start_ui_post_pump(self):
        """Arm the main-thread timer that drains the worker->UI queue."""
        if getattr(self, '_ui_post_pump_id', None) is not None:
            return
        try:
            self._ui_post_pump_id = self.after(self.UI_POST_PUMP_MS, self._pump_ui_post)
        except Exception:
            self._ui_post_pump_id = None

    def _pump_ui_post(self):
        """Run every callback a worker thread posted, on the Tk main thread."""
        self._ui_post_pump_id = None
        if getattr(self, '_closing', False):
            return
        while True:
            try:
                func, args, kwargs = self._ui_post_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args, **kwargs)
            except Exception as exc:            # noqa: BLE001 - one bad callback
                print(f"[UI] queued callback failed: {exc}")
        self._start_ui_post_pump()

    def ui_post(self, func, *args, **kwargs):
        """Run `func` on the Tk thread - safe to call from ANY thread.

        Never raises: a delivery failure used to mean the screen waited forever
        for a callback that was silently dropped.
        """
        if func is None:
            return
        if threading.current_thread() is threading.main_thread():
            try:
                func(*args, **kwargs)
                return
            except Exception as exc:            # noqa: BLE001 - reported only
                print(f"[UI] callback failed: {exc}")
                return
        try:
            self._ui_post_queue.put((func, args, kwargs))
            self._start_ui_post_pump()
        except Exception as exc:                # noqa: BLE001 - never fatal
            print(f"[UI] could not queue a worker callback: {exc}")

    def on_closing(self):
        """Gracefully stop hardware threads before closing the app.

        Key rule: never close the serial port while a measurement thread
        is still reading from it — that corrupts the MCU's UART state and
        causes 'STM32 not responding' on the next launch.
        """
        print("Shutting down...")

        # 0. Set closing flag so background threads stop calling after()
        self._closing = True

        # 0b. Tell the firmware to stop streaming NOW (and wake every local
        # waiter) so worker threads exit fast instead of running to the end
        # of a minutes-long run while the port is being closed.
        # Skipped in simulation mode (no UART / pyserial there).
        if not SIMULATION_MODE:
            try:
                from Hardware.serial_manager import get_manager
                get_manager().request_abort()
                from Hardware.stm32_backend import send_abort as _send_abort
                _send_abort()
            except Exception:
                pass

        # 1. Stop the hardware-button poller so it can't fire after destroy
        poll_id = getattr(self, '_hw_poll_after_id', None)
        if poll_id:
            try:
                self.after_cancel(poll_id)
            except Exception:
                pass
            self._hw_poll_after_id = None
        self._measurement_screen_active = False

        # 2. Cancel ALL pending after() callbacks to prevent bgerror
        try:
            for after_id in self.tk.eval('after info').split():
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass

        # 3. Unbind keys
        try:
            self.unbind("<Return>")
            self.unbind("<space>")
        except Exception:
            pass

        # 4. If a measurement thread is running, give it a moment to notice
        #    the _closing flag and exit cleanly.  Then close UART.
        if getattr(self, '_measurement_running', False):
            print("[CLOSE] Waiting for measurement thread to finish...")
            for _ in range(40):  # max 2 seconds
                if not getattr(self, '_measurement_running', False):
                    break
                time.sleep(0.05)
            else:
                print("[CLOSE] Measurement thread did not stop in time — closing anyway")

        # 5. Close the STM32 UART connection cleanly (drains buffer)
        try:
            from Hardware.stm32_backend import close_connection
            close_connection()
        except Exception:
            pass

        # 6. Destroy the UI window
        self.destroy()

    # ------------------------------------------------------------------
    # Window / layout scale
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_emulated_screen(value):
        """'1280x720' (or 1280*720 / 1280,720) -> (1280, 720), else None.

        Used by ``BIO_SCREEN`` to rehearse the instrument panel's layout on a
        desktop monitor (and by the layout harness), and by preview shots.
        """
        text = str(value or "").strip().lower().replace("*", "x").replace(",", "x")
        if "x" not in text:
            return None
        left, _, right = text.partition("x")
        try:
            width, height = int(float(left)), int(float(right))
        except ValueError:
            return None
        if width < 320 or height < 240:
            return None
        return width, height

    def _setup_window(self):
        """Fit the window to the panel: no title bar, exact 1280x720 on device.

        Three cases, in order:

        * ``BIO_SCREEN=WxH`` - rehearse that exact panel size. Windowed (with
          decorations) so it can be moved/closed on a desktop; add
          ``BIO_BORDERLESS=1`` for the true borderless panel look (previews).
        * launched from ``main.py`` (``BIO_LAUNCHED=1``) - the real instrument:
          borderless fullscreen on the whole panel. This is what the operator
          sees, so no title bar, no window buttons; the way out is POWER.
        * imported instead of launched (harnesses, scripts) - a decorated
          window the size of the panel, so tests never hijack the desktop.

        Order matters: ``set_widget_scaling`` makes CustomTkinter re-assert the
        window's *recorded* size, so the real geometry has to be applied AFTER
        the scaling, and re-asserted once the 1 s min/max lock it installs has
        been released (see _assert_window_size).
        """
        import os
        sw, sh = self.screen_width, self.screen_height
        width, height, fullscreen, borderless = window_plan(sw, sh, os.environ)
        self._window_fullscreen = fullscreen
        self._window_borderless = borderless
        self.window_width, self.window_height = width, height

        # 1) Layout scale for the size we are about to become. Keeping the
        #    scale and the window proportional is what makes the 1280x720
        #    design look identical on the panel and on a bigger monitor.
        self._apply_layout_scale(width, height)

        # 2) The window itself. CustomTkinter scales the geometry string by the
        #    platform DPI factor, and dividing the widget scaling by that same
        #    factor means the two cancel out: the layout is always exactly the
        #    design's proportions.
        try:
            if borderless:
                # Exact-pixel, decoration-free window in the top-left corner:
                # the operator's view of the panel, reproduced on a monitor.
                self.overrideredirect(True)
                self.geometry(f"{width}x{height}+0+0")
            elif self._window_fullscreen:
                self.geometry(f"{width}x{height}+0+0")
                self.attributes("-fullscreen", True)
            else:
                self.geometry(
                    f"{width}x{height}+{max(0, (sw - width) // 2)}+{max(0, (sh - height) // 2)}")
        except Exception as exc:
            print(f"[UI] window setup fell back to plain geometry: {exc}")
            self.geometry(f"{width}x{height}+0+0")

        # 3) Re-assert once CustomTkinter's min/max lock expires, and once more
        #    shortly after, so a window manager that ignored the first request
        #    still ends up at the exact panel size.
        for delay in (250, 1200):
            try:
                self.after(delay, self._assert_window_size)
            except Exception:
                break
        self._apply_layout_scale(width, height)

    def _assert_window_size(self):
        """Make sure we really are at the intended size (window manager safe)."""
        if getattr(self, '_closing', False):
            return
        try:
            if getattr(self, '_window_fullscreen', False):
                self.attributes("-fullscreen", True)
                return
            width, height = self.window_width, self.window_height
            actual_w, actual_h = int(self.winfo_width()), int(self.winfo_height())
            if abs(actual_w - width) > 8 or abs(actual_h - height) > 8:
                print(f"[UI] resizing window {actual_w}x{actual_h} -> {width}x{height}")
                self.geometry(f"{width}x{height}+0+0")
        except Exception as exc:
            print(f"[UI] size check skipped: {exc}")

    def _apply_layout_scale(self, width=None, height=None):
        """Scale the whole widget tree for a window of the given pixel size.

        CustomTkinter scales widget sizes and font pixel sizes by
        ``set_widget_scaling``; dividing by the platform's DPI factor keeps the
        result exactly proportional to the 1280x720 design on ANY screen (it
        undoes CustomTkinter's automatic high-DPI multiplication).
        """
        if width is None or height is None:
            width, height = self.window_width, self.window_height
        self.ui_scale = window_set_ui_scale(window_scale_for(width, height))
        # The platform's own display scaling is deliberately cancelled out:
        # a kiosk instrument must look the same on every machine, so the design
        # is driven by the WINDOW SIZE alone (panel = 1.0). Dividing the window
        # scaling by it keeps CustomTkinter's geometry handling in raw pixels -
        # the same units winfo_screenwidth() reports - instead of letting a
        # desktop's 125%/150% setting inflate the panel layout past the screen.
        try:
            dpi = float(ctk.ScalingTracker.get_window_dpi_scaling(self))
        except Exception:
            try:
                dpi = float(self.winfo_fpixels('1i')) / 96.0
            except Exception:
                dpi = 1.0
        if not dpi:
            dpi = 1.0

        # CustomTkinter hands every widget `dpi_factor * what we set`, and that
        # dpi factor is not a constant: the scaling tracker re-reads it every
        # 100 ms and re-scales the whole widget tree whenever it changes. On the
        # instrument the panel reports one DPI on the first read and a different
        # one a moment later, so the tree was scaled up ~25% - INSIDE a window
        # that stayed 1280x720. Nothing about that is visible on a desktop
        # (where the two readings agree), and on the panel it looked like every
        # row, label and popup had burst out of its box: clipped form labels,
        # squashed key rows, half-size dialogs.
        #
        # Automatic DPI awareness is therefore switched off: CustomTkinter then
        # uses exactly the numbers below, so the design is driven by the WINDOW
        # SIZE alone (1.0 on the panel) and a later DPI re-read cannot inflate
        # anything. The DPI awareness of the PROCESS (Windows) was already set
        # when the window was created, so this only stops the multiplication.
        try:
            ctk.ScalingTracker.deactivate_automatic_dpi_awareness = True
        except Exception as exc:
            print(f"[UI] could not pin the layout scaling: {exc}")

        # Net effect: widgets, fonts and grid/pack padding scale by exactly
        # ui_scale; window geometry stays in raw pixels. The window number still
        # has to divide the DPI factor out (CustomTkinter multiplies it back in
        # for geometry strings only), otherwise the window is asked for at
        # 1600x900 on a 125% desktop and visibly snaps to 1280x720 a moment
        # later - a whole-layout jump nobody can predict from the design.
        wanted_widget = max(self.ui_scale, 0.4)
        wanted_window = max(1.0 / dpi, 0.4)
        try:
            if abs(float(ctk.ScalingTracker.widget_scaling) - wanted_widget) > 0.001:
                ctk.set_widget_scaling(wanted_widget)
            if abs(float(ctk.ScalingTracker.window_scaling) - wanted_window) > 0.001:
                ctk.set_window_scaling(wanted_window)
        except Exception as exc:
            print(f"[UI] could not apply widget scaling: {exc}")
        print(f"[UI] window {width}x{height} ui_scale={self.ui_scale:.2f} "
              f"platform_dpi={dpi:.2f} (dpi scaling pinned off)")
        return self.ui_scale

    def maximize_window(self):
        """Maximize the window while keeping the title bar and window decorations visible"""
        import platform
        try:
            if platform.system() == 'Windows':
                self.state('zoomed')
            elif platform.system() == 'Linux':
                # state('zoomed') is the most reliable way on Linux/X11/Wayland
                # to maximize while keeping the title bar buttons visible
                try:
                    self.state('zoomed')
                except Exception:
                    try:
                        self.state('zoom')
                    except Exception:
                        # Fallback: resize to 90% of screen so title bar is visible
                        sw = self.winfo_screenwidth()
                        sh = self.winfo_screenheight()
                        w = int(sw * 0.9)
                        h = int(sh * 0.9)
                        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
            else:
                try:
                    self.state('zoomed')
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Could not maximize window: {e}")

    def initialize_hardware(self):
        """Initialize hardware components on startup"""
        if SIMULATION_MODE:
            print("[SIM] Hardware initialization skipped (simulation mode)")
            return
        try:
            # STM32 hardware is initialized via UART connection
            # No GPIO setup needed on RPi side
            print("[HW] Hardware ready (STM32 manages GPIO)")
        except Exception as e:
            print(f"Error during hardware initialization: {e}")

    # How long a message stays on screen when the caller does not say.
    NOTIFICATION_DURATION = 2600

    def show_notification(self, message, duration=None, error=False):
        """Announce something in the window's own top banner.

        This used to be a decoration-free TOPLEVEL parked 100 px above the
        window's bottom edge, 350x50 with a 12 pt label and no wrapping. On the
        7" panel the toplevel was positioned in root coordinates of a window
        the panel only partly shows, and a longer message ("Please enter valid
        numeric values for numeric fields: low") simply did not fit its 350x50
        box - the operator saw the first few words and nothing else.

        The banner is a plain child of this window placed over the screen at
        the TOP, sized to its text (wrapping if the text is long) and clamped
        inside the panel, so a message can never be cut off, can never land
        off-screen, and never depends on a second window existing at all.
        Tapping it dismisses it; otherwise it goes away by itself.
        """
        if duration is None:
            duration = self.NOTIFICATION_DURATION
        self._dismiss_notification()
        text = str(message or "").strip()
        if not text:
            return None

        bg_color = tc("danger") if error else tc("accent")
        fg_color = tc("on_danger") if error else tc("text_on_accent")
        try:
            banner = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=theme_sp(12),
                                  border_width=1, border_color=tc("border_strong"))
            label = ctk.CTkLabel(banner, text=text, justify="left",
                                 font=ctk.CTkFont(size=13, weight="bold"),
                                 text_color=fg_color)
            label.pack(padx=theme_sp(18), pady=theme_sp(10))
        except Exception as exc:
            print(f"[UI] could not show the message: {exc}")
            return None

        for widget in (banner, label):
            try:
                widget.bind("<Button-1>", lambda _e: self._dismiss_notification())
            except Exception:
                pass

        # Size to the message and clamp to the panel: a short line gets a
        # compact pill, a long one wraps onto two or three lines.
        try:
            panel_w = int(self.winfo_width()) or WINDOW_DESIGN_W
        except Exception:
            panel_w = WINDOW_DESIGN_W
        max_w = max(theme_sp(320), panel_w - theme_sp(24))
        try:
            label.configure(wraplength=max(theme_sp(240), max_w - theme_sp(36)))
            banner.update_idletasks()
            need_w = int(banner.winfo_reqwidth())
        except Exception:
            need_w = max_w
        try:
            # Width goes on the widget, not on place(): CustomTkinter's place()
            # override rejects width/height and raises, which silently killed
            # every message this banner was ever asked to show. Height is left
            # to the frame, so the pill is exactly as tall as its text needs.
            banner.configure(width=max(theme_sp(240), min(need_w, max_w)))
            banner.place(relx=0.5, y=theme_sp(8), anchor="n")
            banner.lift()
        except Exception as exc:
            print(f"[UI] could not place the message: {exc}")
            try:
                banner.destroy()
            except Exception:
                pass
            return None

        self._notification = banner
        self.notification_window = None   # the old toplevel is gone
        if duration and duration > 0:
            try:
                self._notification_after = self.after(int(duration),
                                                      self._dismiss_notification)
            except Exception:
                self._notification_after = None
        return banner

    def _dismiss_notification(self):
        """Take the message banner away (also its auto-dismiss timer)."""
        after_id = getattr(self, '_notification_after', None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._notification_after = None
        banner = getattr(self, '_notification', None)
        self._notification = None
        if banner is not None:
            try:
                banner.destroy()
            except Exception:
                pass

    def update_temperature_ui(self):
        temp = self.temp_controller.get_current_temp()

        if temp is not None:
            self.temp_label.configure(text=f"Temp: {temp:.2f} °C")

        # Schedule next UI update (every 500 ms)
        self.after(500, self.update_temperature_ui)

    def show_main_menu(self):
        self.clear_frames()
        self._screen_rebuild = self.show_main_menu
        self.frames['main'] = self.create_main_menu()
        self.polish_screen(self.frames['main'])

    def show_test_screen(self):
        self.clear_frames()
        self._screen_rebuild = self.show_test_screen
        self.frames['test'] = self.create_test_screen()
        self.polish_screen(self.frames['test'])

    def show_test_parameters(self, test_id):
        self.clear_frames()
        self._screen_rebuild = lambda: self.show_test_parameters(test_id)
        self.frames['params'] = self.create_test_parameters(test_id)
        self.polish_screen(self.frames['params'])
        # Update title based on whether it's a new test or existing test
        if self.current_test_name:
            title_text = f"Test Parameters - {self.current_test_name}"
        else:
            title_text = "Test Parameters - New Test"
        # Update the title on the parameters screen (the mixin keeps a direct
        # reference: the old positional winfo_children() lookup broke as soon as
        # the header's own layout changed).
        title = getattr(self, 'params_title_label', None)
        if title is not None:
            try:
                title.configure(text=title_text)
            except Exception as exc:
                print(f"[UI] could not retitle the parameters screen: {exc}")

    def show_measurement_screen(self):
        self.clear_frames()
        self.edit_mode = False
        # A running measurement must never be repainted by rebuilding the
        # screen (its worker thread owns these widgets) - the measurement mixin
        # provides restyle_for_theme() for the in-place repaint instead.
        self._screen_rebuild = None
        self.frames['measure'] = self.create_measurement_screen(0)
        self.polish_screen(self.frames['measure'])

    # ------------------------------------------------------------------
    # Theme plumbing
    # ------------------------------------------------------------------
    @property
    def theme(self):
        """The active palette (the workflow's graph renderer reads this)."""
        return theme_colors()

    def polish_screen(self, frame=None):
        """Apply the active theme to a freshly created screen."""
        try:
            theme_polish_tree(frame)
        except Exception as exc:
            print(f"[THEME] could not polish the screen: {exc}")

    def toggle_theme(self):
        """Switch light <-> dark and repaint the screen on show."""
        mode = theme_manager.toggle()
        try:
            self.configure(fg_color=theme_colors()["window_bg"])
        except Exception:
            pass
        busy = bool(getattr(self, 'is_measuring', False)
                    or getattr(self, '_measurement_running', False))
        rebuild = getattr(self, '_screen_rebuild', None)
        if rebuild is not None and not busy:
            rebuild()
        else:
            restyle = getattr(self, 'restyle_for_theme', None)
            if callable(restyle):
                try:
                    restyle()
                except Exception as exc:
                    print(f"[THEME] in-place restyle failed: {exc}")
        self.show_notification(
            "Dark theme on" if mode == "dark" else "Light theme on")
        print(f"[THEME] mode={mode}")
        return mode

    def clear_frames(self):
        # Every navigation starts a new screen epoch: stale background
        # threads (LED align, measurement) detect the bumped token and exit
        # without touching the new screen's widgets or UART replies.
        self._screen_token = getattr(self, '_screen_token', 0) + 1
        # Cancel a deferred matplotlib canvas build from a previous
        # measurement screen so it can't create an orphan Figure on a
        # destroyed frame (slow leak, one Figure per Back+reopen).
        graph_after_id = getattr(self, '_graph_after_id', None)
        if graph_after_id:
            try:
                self.after_cancel(graph_after_id)
            except Exception:
                pass
            self._graph_after_id = None
        # Stop the measurement screen's hardware-button poller (and its sim-mode
        # key bindings) when navigating away, so a hardware/Enter press on any
        # other screen can't silently start a measurement.
        poll_id = getattr(self, '_hw_poll_after_id', None)
        if poll_id:
            try:
                self.after_cancel(poll_id)
            except Exception:
                pass
            self._hw_poll_after_id = None
        self._measurement_screen_active = False
        try:
            self.unbind("<Return>")
            self.unbind("<space>")
        except Exception:
            pass
        for frame in self.frames.values():
            frame.destroy()
        self.frames = {}
        # A message banner (top of the window) is a child of the WINDOW, not of
        # a screen, on purpose: "Test parameters saved as X" is announced just
        # before navigating to the test list. Sibling widgets created later sit
        # above it, so lift it back over the screen that has just replaced it.
        banner = getattr(self, '_notification', None)
        if banner is not None:
            try:
                banner.lift()
            except Exception:
                pass

    def are_parameters_saved(self):
        """Check if parameters are saved for current test"""
        if not self.current_test_name:  # If no test name is set, parameters aren't saved
            return False
        return True

    def create_popup(self, message):
        popup = ctk.CTkToplevel(self)
        # popup.title("Status")
        popup.title("")
        # popup.grab_set()
        popup.overrideredirect(True)  # Removing window decorations
        # Center popup
        width = 850
        height = 150
        x = self.winfo_x() + (self.winfo_width() - width) // 2
        y = self.winfo_y() + (self.winfo_height() - height) // 2
        popup.geometry(f"{width}x{height}+{x}+{y}")
        try:
            popup.configure(fg_color=theme_colors()["window_bg"])
        except Exception:
            pass
        label = ctk.CTkLabel(popup, text=message, font=ctk.CTkFont(size=16),
                             text_color=theme_colors()["text"])
        label.pack(expand=True)
        self.after(5000, popup.destroy)
        return popup

    def show_help_screen(self):
        self.clear_frames()
        self._screen_rebuild = self.show_help_screen
        frame = ctk.CTkFrame(self, fg_color=theme_colors()["window_bg"], corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        back_btn = ctk.CTkButton(frame, text="←", width=50, command=self.show_main_menu,
                                 fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                                 text_color=tc("btn_text"))
        back_btn.pack(side="top", anchor="nw", padx=20, pady=20)
        label = ctk.CTkLabel(frame, text="Help Screen\nComing Soon!",
                             font=ctk.CTkFont(size=24, weight="bold"),
                             text_color=tc("text"))
        label.pack(expand=True)
        self.frames['help'] = frame

    # NOTE: the old messagebox-based show_confirm_dialog() lived here. Dialogs
    # moved to SystemScreensMixin.show_confirm_dialog() - a themed, touch-sized
    # card (a native messagebox cannot be sized for a 7" panel).

    def show_info_dialog(self, title, message):
        """Show an information dialog"""
        # messagebox.showinfo(title, message)
        self.show_notification(message, error=False)

    def show_error_dialog(self, title, message):
        """Show an error dialog"""
        # messagebox.showerror(title, message)
        self.show_notification(message, error=True)
