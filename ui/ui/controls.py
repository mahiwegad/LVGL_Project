"""
controls.py - touch-first input widgets for the instrument panel.

Two problems are solved here, both of them invisible on a desktop and obvious
on a 7" resistive/capacitive panel:

  * ``OnScreenKeyboard`` - there is no physical keyboard at the instrument, so
    text and number fields get a docked keyboard that appears when a field is
    tapped and disappears when the operator is done with it. It types into the
    field through the widget's own insert/delete API, so every existing
    save/validate path keeps working untouched.

  * ``TouchSelect`` - customtkinter's dropdown opens a toplevel whose option
    list is drawn on a canvas and selected from mouse events. On several touch
    panels the tap that opens it is followed by a synthetic release that lands
    on - and closes - the list before a choice can be made, which is the
    "unable to select options in the dropdown with touch" report. This widget
    replaces it with a modal grid of full-size buttons: every option is a real
    writeable button, so a tap always lands on the thing the operator aimed at.

Both widgets are plain CustomTkinter compositions: no extra dependency, and no
license beyond the one already in use.
"""

import customtkinter as ctk

from ui.theme import c as tc, card as theme_card, sp, font as theme_font


# --------------------------------------------------------------------------
# On-screen keyboard
# --------------------------------------------------------------------------
class OnScreenKeyboard(ctk.CTkFrame):
    """On-screen keyboard for one field at a time.

    ``attach(entry, label, kind)`` wires a field up: tapping it shows the
    keyboard aimed at that field. ``hide()`` (also the Done key) closes it.

    Three key layouts, chosen by the field's ``kind``:

      * ``text``   - full QWERTY (the only field that needs letters),
      * ``number`` - digits on a single row,
      * ``pad``    - a compact phone-style number keypad (3 columns) that is
        small enough to sit BESIDE the field being typed into, so the number
        the operator is entering stays visible while they enter it. See
        ``float_beside()``.
    """

    NUMBER_ROWS = (
        ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
        (".", "-", "00", "⌫", "Clear", "abc", "Done"),
    )
    LETTER_ROWS = (
        tuple("QWERTYUIOP"),
        tuple("ASDFGHJKL"),
        tuple("ZXCVBNM") + ("-", " "),
        ("123", "⌫", "Clear", "space", "Done"),
    )
    PAD_ROWS = (
        ("7", "8", "9"),
        ("4", "5", "6"),
        ("1", "2", "3"),
        (".", "0", "⌫"),
        ("Clear", "Done"),
    )
    # key width, key height, key font size - per layout. The pad's keys are
    # deliberately bigger than a share of a full-width row: on the panel they
    # are tapped with a thumb while the field beside them stays readable.
    KEY_SIZE = {
        "abc": (54, 38, 14),
        "num": (54, 38, 14),
        "pad": (76, 50, 18),
    }
    MODE_FOR_KIND = {"text": "abc", "number": "num", "pad": "pad"}

    def __init__(self, master, on_hide=None, **kwargs):
        super().__init__(master, fg_color=tc("surface"), corner_radius=sp(14),
                         border_width=1, border_color=tc("border"), **kwargs)
        self._target = None
        self._target_kind = "text"
        self._mode = "abc"
        self.on_hide = on_hide
        # How the owner positioned us: docked (pack), gridded, or floating
        # above the screen (place) - see float_over() and float_beside().
        self._dock_kwargs = None
        self._float_spec = None
        # One key grid per layout, built on first use and then kept: switching
        # between letters and digits used to destroy and re-create ~34 CTk
        # buttons, which is the single most expensive thing this screen did.
        self._areas = {}

        # The head row and the keys are deliberately compact: the keyboard is
        # docked under the form on a 720 px panel, so every pixel it gives back
        # is a pixel the form above it keeps (and a keyboard that ran past the
        # panel's bottom edge used to be cut in half).
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=sp(10), pady=(sp(4), 0))
        self.slash_label = ctk.CTkLabel(
            head, text="Typing into: -", font=theme_font(11, bold=True),
            text_color=tc("text_muted"))
        self.slash_label.pack(side="left")
        ctk.CTkButton(
            head, text="Hide keyboard", width=sp(116), height=sp(26),
            font=theme_font(11, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(8),
            command=self.hide).pack(side="right")

        self._key_area = ctk.CTkFrame(self, fg_color="transparent")
        self._key_area.pack(fill="both", expand=True, padx=sp(8), pady=(sp(2), sp(6)))
        # Build the keys once the screen around us has been drawn, not while it
        # is being constructed: 34 buttons are ~170 ms of work on the bench and
        # several hundred on the Pi, and the operator paid it while waiting for
        # the screen to appear. `after_idle` means the screen paints first and
        # the keyboard is ready before a field can be reached.
        try:
            self.after_idle(self._ensure_keys)
        except Exception:
            self._ensure_keys()

    # ---- wiring --------------------------------------------------------
    def attach(self, entry, label="", kind="text"):
        """Open this keyboard when `entry` is tapped (or focused by keyboard).

        Both events are bound on purpose: the tap is what the operator does
        (CTkEntry forwards its bindings to the inner tkinter.Entry, which is
        what a tap lands on and what receives focus), and the FocusIn covers a
        field reached another way.
        """
        handler = lambda _e, e=entry, l=label, k=kind: self.show_for(e, l, k)
        for sequence in ("<FocusIn>", "<Button-1>"):
            try:
                entry.bind(sequence, handler)
            except Exception as exc:
                print(f"[KB] could not attach {sequence} to {label}: {exc}")
        return entry

    def show_for(self, entry, label=None, kind=None):
        self._target = entry
        if kind:
            self._target_kind = kind
        if label:
            try:
                self.slash_label.configure(text=f"Typing into: {label}")
            except Exception:
                pass
        wanted = self.MODE_FOR_KIND.get(str(self._target_kind).lower(), "abc")
        if wanted != self._mode:
            self._mode = wanted
        self.show()
        # Keep the caret in the field the operator is typing into.
        try:
            entry.focus_set()
        except Exception:
            pass

    def dock(self, **kwargs):
        """Reserve the keyboard's place in the layout, hidden until needed."""
        self._dock_kwargs = dict(kwargs)
        try:
            self.pack(**kwargs)
            self.pack_forget()
        except Exception as exc:
            print(f"[KB] could not dock: {exc}")
            self._dock_kwargs = None
        return self

    def float_beside(self, host, margin=None, keep_clear=None):
        """Float the keyboard NEXT TO the field it types into.

        The pad is small (three columns), so it can sit beside the field rather
        than over it - which is what the operator asked for: "for measuring and
        delay time the keyboard appears on the delay time and measuring time
        itself, so what I am typing doesn't get visible". On each show the side
        is chosen from the field's own position: a field in the left half of
        the form gets the pad on the right, a field on the right gets it on the
        left, and it is aligned with the field's row and clamped inside the
        panel.

        ``keep_clear`` is the row (the form's RUN/SAVE/DELETE/CANCEL buttons)
        the pad must not cover: on the instrument the pad came out taller than
        it does on the bench - same panel, a taller font - so centring it on a
        low field pushed its bottom row (Clear / Done) over the action buttons
        and off the bottom of the screen. The pad is now slid up so its LAST ROW
        stays above that row.
        """
        self._float_spec = {"mode": "beside", "host": host,
                            "margin": sp(10) if margin is None else margin,
                            "keep_clear": keep_clear}
        try:
            # Same stronger border as the floating sheet: it reads as a layer
            # above the form rather than part of it.
            self.configure(border_width=2, border_color=tc("border_strong"))
        except Exception as exc:
            print(f"[KB] could not style the pad: {exc}")
        return self

    def float_over(self, **spec):
        """Float the keyboard OVER the screen instead of taking layout space.

        A docked keyboard has to win its room from the layout, and on a 720 px
        panel it loses that fight: the form above asks for its height first,
        the keyboard is packed last and Tk clips it, so the panel showed a
        squashed strip with one key in it. ``place`` takes the keyboard out of
        the layout arithmetic altogether - the screen underneath keeps its own
        size and the keyboard is drawn on top of it, always at full size.
        """
        self._float_spec = dict(spec)
        try:
            # A floating sheet reads as a layer above the form, so it gets the
            # stronger border the flat on-form keyboard does not need.
            self.configure(border_width=2, border_color=tc("border_strong"))
            self.place(**spec)
            self.place_forget()
        except Exception as exc:
            print(f"[KB] could not float: {exc}")
            self._float_spec = None
        return self

    def _place_beside(self):
        """Position the pad on the opposite side of the field being typed."""
        spec = self._float_spec or {}
        host = spec.get("host") or self.master
        margin = int(spec.get("margin") or sp(10))
        try:
            host.update_idletasks()
            panel_w = int(host.winfo_width()) or 1280
            panel_h = int(host.winfo_height()) or 720
        except Exception:
            panel_w, panel_h = 1280, 720
        self.update_idletasks()
        pad_w = min(int(self.winfo_reqwidth() or sp(250)), panel_w - 2 * margin)
        pad_h = min(int(self.winfo_reqheight() or sp(300)), panel_h - 2 * margin)
        try:
            target = self._target
            fx = target.winfo_rootx() - host.winfo_rootx()
            fy = target.winfo_rooty() - host.winfo_rooty()
            fw = int(target.winfo_width())
            fh = int(target.winfo_height())
        except Exception:
            fx = fy = 0
            fw = panel_w // 2
            fh = sp(40)
        if fw <= 1 or fh <= 1:
            # The field has never been laid out (hidden Factor entry): treat it
            # as if it sat in the left half, which is where it lives.
            fx, fy, fw, fh = 0, 0, panel_w // 2, sp(40)
        if fx + fw / 2.0 < panel_w / 2.0:
            x = panel_w - pad_w - margin          # field on the left -> pad right
        else:
            x = margin                            # field on the right -> pad left
        y = fy + fh / 2.0 - pad_h / 2.0
        y = max(margin, min(y, panel_h - pad_h - margin))
        # Never cover the action buttons below the form (see float_beside).
        limit = None
        keep_clear = spec.get("keep_clear")
        if keep_clear is not None:
            try:
                limit = int(keep_clear.winfo_rooty() - host.winfo_rooty()) - margin
            except Exception:
                limit = None
        if limit and limit > margin:
            y = max(margin, min(y, limit - pad_h))
        # The size goes on the WIDGET, not on place(): CustomTkinter overrides
        # place() and raises on width/height, which meant the pad never appeared
        # at all - the field it belonged to was left sitting there uncovered
        # with no keypad, on the exact case this pad exists for.
        self.configure(width=pad_w, height=pad_h)
        self.place(x=int(x), y=int(y))

    def show(self):
        try:
            self._ensure_keys()
            # Two keyboards can share a screen (a wide one for text, a pad for
            # numbers): opening one closes the other, so they never stack.
            sibling = getattr(self, 'sibling', None)
            if sibling is not None:
                try:
                    sibling.hide()
                except Exception:
                    pass
            spec = self._float_spec
            if spec is not None and spec.get("mode") == "beside":
                self._place_beside()
            elif spec is not None:
                self.place(**spec)
            elif self._dock_kwargs is not None:
                self.pack(**self._dock_kwargs)
            else:
                self.grid()
            self.lift()
        except Exception as exc:
            print(f"[KB] could not show: {exc}")

    def hide(self):
        self._target = None
        try:
            if self._float_spec is not None:
                self.place_forget()
            elif self._dock_kwargs is not None:
                self.pack_forget()
            else:
                self.grid_remove()
        except Exception:
            pass
        if callable(self.on_hide):
            try:
                self.on_hide()
            except Exception:
                pass

    @property
    def visible(self):
        try:
            return bool(self.winfo_ismapped())
        except Exception:
            return False

    def target_label(self):
        """What the keyboard says it is typing into (used by the tests)."""
        try:
            return str(self.slash_label.cget("text"))
        except Exception:
            return ""

    # ---- key rendering -------------------------------------------------
    def rows_for(self, mode):
        """The key rows of a layout."""
        return {"abc": self.LETTER_ROWS, "num": self.NUMBER_ROWS,
                "pad": self.PAD_ROWS}.get(mode, self.LETTER_ROWS)

    def _ensure_keys(self, mode=None):
        """Make sure the current layout's keys exist, and only they are shown."""
        mode = mode or self._mode
        if mode not in self._areas:
            try:
                self._areas[mode] = self._build_keys(mode)
            except Exception as exc:
                print(f"[KB] could not build the {mode} keys: {exc}")
                return
        self._show_keys()

    def _show_keys(self):
        for mode, area in list(self._areas.items()):
            try:
                if mode == self._mode:
                    area.pack(fill="both", expand=True, padx=sp(8),
                              pady=(sp(2), sp(6)))
                else:
                    area.pack_forget()
            except Exception:
                pass

    def _build_keys(self, mode):
        """Build one layout's grid of keys (once per layout)."""
        area = ctk.CTkFrame(self._key_area, fg_color="transparent")
        key_w, key_h, key_font = self.KEY_SIZE.get(mode, self.KEY_SIZE["abc"])
        for row_keys in self.rows_for(mode):
            row = ctk.CTkFrame(area, fg_color="transparent")
            row.pack(fill="both", expand=True, pady=sp(1))
            for key in row_keys:
                self._make_key(row, key, key_w, key_h, key_font).pack(
                    side="left", fill="both", expand=True, padx=sp(2))
        return area

    # Kept for compatibility: the harnesses (and the old docked flow) ask for a
    # redraw after changing the mode.
    def _render_keys(self):
        self._ensure_keys()

    def _make_key(self, parent, key, width=54, height=38, font_size=14):
        special = key in ("Done", "⌫", "Clear", "abc", "123")
        accent = key == "Done"
        text = "space" if key in (" ", "space") else key
        if accent:
            fg, hover, text_color = tc("accent"), tc("accent_hover"), tc("text_on_accent")
        elif special:
            fg, hover, text_color = tc("surface_sunken"), tc("border"), tc("text")
        else:
            fg, hover, text_color = tc("btn_neutral"), tc("btn_neutral_hover"), tc("btn_text")
        # A small width only sets the REQUEST: every key expands to its share of
        # the row, so the keyboard never asks for more width than the panel.
        btn = ctk.CTkButton(
            parent, text=text, width=sp(width), height=sp(height),
            font=theme_font(font_size, bold=True),
            fg_color=fg, hover_color=hover, text_color=text_color,
            corner_radius=sp(9), border_width=1, border_color=tc("border"),
            command=lambda k=key: self.press(k))
        return btn

    # ---- key behaviour -------------------------------------------------
    def press(self, key):
        """One key press. Also the entry point the tests drive directly."""
        if key == "Done":
            self.hide()
            return
        if key == "abc":
            self._mode = "abc"
            self._ensure_keys()
            return
        if key == "123":
            self._mode = "num"
            self._ensure_keys()
            return
        if key == "⌫":
            self._backspace()
            return
        if key == "Clear":
            self._clear()
            return
        if key == "space":
            self._insert(" ")
            return
        self._insert(key)

    def _insert(self, text):
        target = self._target
        if target is None:
            return
        try:
            target.focus_set()
            try:
                if target.select_present():
                    target.delete("sel.first", "sel.last")
            except Exception:
                pass
            try:
                index = int(target.index("insert"))
            except Exception:
                index = None
            if index is None:
                target.insert("end", text)
            else:
                target.insert(index, text)
                try:
                    target.icursor(index + len(text))
                except Exception:
                    pass
        except Exception as exc:
            print(f"[KB] insert failed: {exc}")

    def _backspace(self):
        target = self._target
        if target is None:
            return
        try:
            target.focus_set()
            index = int(target.index("insert"))
            if index > 0:
                target.delete(index - 1, index)
                try:
                    target.icursor(index - 1)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[KB] backspace failed: {exc}")

    def _clear(self):
        target = self._target
        if target is None:
            return
        try:
            target.focus_set()
            target.delete(0, "end")
        except Exception as exc:
            print(f"[KB] clear failed: {exc}")


# --------------------------------------------------------------------------
# Touch-friendly option picker
# --------------------------------------------------------------------------
def pick_option(owner, title, values, current=None, on_pick=None, columns=2):
    """Modal grid of big option buttons. Returns the popup.

    Selecting an option calls ``on_pick(value)`` and closes the popup; Cancel
    (or Escape) closes it and changes nothing.
    """
    values = [str(v) for v in values]
    # A long list (every test in the database, say) gets a third column: fewer
    # rows to scroll through, same full-size tap targets.
    if columns == 2 and len(values) > 18:
        columns = 3
    popup = ctk.CTkToplevel(owner)
    popup.overrideredirect(True)
    popup.attributes('-topmost', True)
    # Built while hidden, then opened at the size its own grid needs: the old
    # fixed estimate (150 px + 62 px per row) assumed a 56 px button, and where
    # the font and the buttons run taller - the 7" panel - the last option (the
    # third method, "Kinetic") was half hidden behind the popup's bottom edge.
    try:
        popup.withdraw()
    except Exception:
        pass
    width = sp(700)
    rows = max(1, (len(values) + columns - 1) // columns)
    # Lower bound only, so a long scrollable list still gets a tall popup.
    height_floor = sp(min(660, 150 + 62 * rows))
    try:
        popup.configure(fg_color=tc("window_bg"))
    except Exception:
        pass

    card = ctk.CTkFrame(popup, **theme_card(radius=sp(16)))
    card.pack(fill="both", expand=True, padx=sp(8), pady=sp(8))
    card.grid_columnconfigure(0, weight=1)
    card.grid_rowconfigure(1, weight=1)

    head = ctk.CTkFrame(card, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", padx=sp(16), pady=(sp(12), sp(4)))
    head.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(head, text=title, font=theme_font(18, bold=True),
                 text_color=tc("text")).grid(row=0, column=0, sticky="w")
    ctk.CTkButton(head, text="✕", width=sp(44), height=sp(40),
                  font=theme_font(16, bold=True),
                  fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                  text_color=tc("btn_text"), corner_radius=sp(10),
                  command=popup.destroy).grid(row=0, column=1, sticky="e")

    # A handful of options fits without scrolling, and a plain frame keeps the
    # grid flush - a scrollable frame always parks a (useless) scrollbar beside
    # it, which on a 7" panel looks like a broken control.
    if len(values) > 12:
        area = ctk.CTkScrollableFrame(card, fg_color="transparent")
    else:
        area = ctk.CTkFrame(card, fg_color="transparent")
    area.grid(row=1, column=0, sticky="nsew", padx=sp(10), pady=(0, sp(10)))
    for col in range(columns):
        area.grid_columnconfigure(col, weight=1, uniform="opt")

    def _choose(value):
        try:
            popup.grab_release()
        except Exception:
            pass
        try:
            popup.destroy()
        except Exception:
            pass
        if callable(on_pick):
            on_pick(value)

    for index, value in enumerate(values):
        selected = (current is not None and str(current) == value)
        btn = ctk.CTkButton(
            area, text=value, height=sp(56),
            font=theme_font(16, bold=True),
            fg_color=tc("accent") if selected else tc("btn_neutral"),
            hover_color=tc("accent_hover") if selected else tc("btn_neutral_hover"),
            text_color=tc("text_on_accent") if selected else tc("btn_text"),
            corner_radius=sp(12), border_width=1, border_color=tc("border"),
            command=lambda v=value: _choose(v))
        btn.grid(row=index // columns, column=index % columns,
                 sticky="ew", padx=sp(5), pady=sp(5))

    # Now that the grid exists, open the popup at the size it actually needs
    # (clamped to the instrument window and centred on it, so a finger finds the
    # options in the same place every time).
    try:
        card.update_idletasks()
        need_w = int(card.winfo_reqwidth()) + sp(16)
        need_h = int(card.winfo_reqheight()) + sp(16)
    except Exception:
        need_w, need_h = width, height_floor
    try:
        top = owner.winfo_toplevel()
        panel_w = int(top.winfo_width()) or 1280
        panel_h = int(top.winfo_height()) or 720
        panel_x, panel_y = top.winfo_rootx(), top.winfo_rooty()
    except Exception:
        panel_w, panel_h, panel_x, panel_y = 1280, 720, 0, 0
    width = max(sp(560), min(need_w, panel_w - sp(20)))
    height = min(max(sp(220), need_h, height_floor), panel_h - sp(20))
    px = panel_x + max(0, (panel_w - width) // 2)
    py = panel_y + max(0, (panel_h - height) // 2)
    try:
        popup.geometry(f"{width}x{height}+{px}+{py}")
        popup.deiconify()
        popup.lift()
    except Exception:
        pass

    try:
        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.grab_set()
        popup.focus_set()
    except Exception:
        pass
    polish = getattr(owner, "polish_screen", None)
    if polish is None:
        try:
            polish = getattr(owner.winfo_toplevel(), "polish_screen", None)
        except Exception:
            polish = None
    if callable(polish):
        try:
            polish(popup)
        except Exception:
            pass
    return popup


class TouchSelect(ctk.CTkFrame):
    """A dropdown replacement that a finger can actually operate.

    Same API surface the screens already use for their comboboxes - ``get()``,
    ``set(value)`` and an optional ``command`` - so it drops into
    ``param_entries`` unchanged.
    """

    def __init__(self, master, values=None, command=None, width=None,
                 height=None, placeholder=None, title=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._values = [str(v) for v in (values or [])]
        self._value = ""
        self._command = command
        # ``title`` names the field in the picker this button opens; the text
        # the closed button reads while nothing is chosen DEFAULTED to that same
        # title. The two are separate jobs now, because the parameter form asks
        # for an empty Method / Wavelength / Unit box (placeholder="") - the
        # operator reads the field's own label to its left, and having "Method"
        # sitting inside the box reads as a value that was already chosen - while
        # that box's picker still needs its "Method" heading.
        #   placeholder=None (default) -> the title is the empty text (unchanged
        #                                 for every other screen's filters)
        #   placeholder=""             -> a genuinely blank box
        self._title = title or placeholder or "- select -"
        self._placeholder = (str(self._title) if placeholder is None
                             else str(placeholder))
        self._button = ctk.CTkButton(
            self,
            text=self._value or self._placeholder,
            height=height or sp(42),
            width=width or sp(240),
            font=theme_font(14, bold=True),
            fg_color=tc("surface_sunken"), hover_color=tc("btn_neutral"),
            text_color=tc("text"), corner_radius=sp(10),
            border_width=1, border_color=tc("border"),
            anchor="w",
            command=self.open_picker)
        self._button.pack(fill="both", expand=True)

    # ---- API used by the screens ---------------------------------------
    def get(self):
        return self._value

    def set(self, value):
        self._value = "" if value is None else str(value)
        self._refresh()

    def configure_values(self, values, title=None):
        self._values = [str(v) for v in (values or [])]
        if title:
            self._title = title

    def values(self):
        return list(self._values)

    def _refresh(self):
        try:
            self._button.configure(text=self._value or self._placeholder)
        except Exception:
            pass

    def open_picker(self):
        """Open the modal option grid (also the tests' entry point)."""
        if not self._values:
            return None
        return pick_option(self, self._title, self._values, self._value,
                           on_pick=self._on_pick, columns=2)

    def _on_pick(self, value):
        self.set(value)
        if callable(self._command):
            try:
                self._command(value)
            except TypeError:
                # customtkinter comboboxes call command(value); some legacy
                # callbacks in this app take no argument.
                try:
                    self._command()
                except Exception as exc:
                    print(f"[SELECT] command failed: {exc}")
            except Exception as exc:
                print(f"[SELECT] command failed: {exc}")


__all__ = ["OnScreenKeyboard", "TouchSelect", "pick_option"]
