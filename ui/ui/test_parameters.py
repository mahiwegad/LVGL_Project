"""
test_parameters.py - Test creation/editing form and the QC parameter popup.

Part of the ui package (split from the original monolithic ui.py).
"""

import tkinter as tk
import customtkinter as ctk
from customtkinter import CTkComboBox
from tkinter import messagebox
from datetime import datetime, timedelta
from Hardware.config import SIMULATION_MODE
from ui.controls import OnScreenKeyboard, TouchSelect
from ui.theme import c as tc, card as theme_card, sp, font as theme_font

# Which fields are typed into (and therefore need a keyboard), and WHICH
# keyboard each one gets. Everything else on this screen is chosen from a list,
# so it uses the touch-safe TouchSelect picker instead - a list field must not
# raise a keyboard, it has nothing to type into.
#
# The operator's list, verbatim: "keyboard should be opened up only for test
# name, low range, factor, std concentration, measuring time, delay time - not
# for others". High (Range) is kept on the keypad alongside Low because it is
# the same kind of field and the panel has no physical keyboard: without one
# there would be no way to enter a High limit at all.
#
#   kind="text" - the full QWERTY keyboard (one text field: the test name),
#   kind="pad"  - the compact phone-style number keypad, which floats BESIDE
#                 the field (opposite side of the form, on the field's own
#                 row) so the number being entered stays visible - the reason
#                 it exists is "the keyboard appears on the delay time and
#                 measuring time itself, so what I am typing does not get
#                 visible".
KEYBOARD_FIELDS = (
    ("test_name", "Test Name", "text"),
    ("low", "Low (Range)", "pad"),
    ("high", "High (Range)", "pad"),
    ("std_conc", "Std Concentration", "pad"),
    ("delay_time", "Delay Time (s)", "pad"),
    ("measuring_time", "Measuring Time", "pad"),
    ("factor_value", "Factor", "pad"),
)
# Kinds that need the bit keypad rather than the wide keyboard.
PAD_KINDS = ("pad",)

class TestParametersMixin:
    """TestParametersMixin - Test creation/editing form and the QC parameter popup."""

    def create_new_test(self):
        self.current_test_name = None
        self.edit_mode = False  # Reset edit mode when creating a new test

        self.show_test_parameters(0)  # Showing empty parameter form

        # Reset ALL checkbox variables
        self.use_factor_var.set(False)
        self.use_blank_var.set(False)
        self.use_qc_var.set(False)  # Add this line

        # Clearing any existing values in entries
        for key, entry in self.param_entries.items():
            try:
                if key in ["use_factor", "blank", "use_qc"]:  # Add use_qc here
                    # Skip the checkboxes as we already reset the variables
                    continue
                elif isinstance(entry, CTkComboBox):
                    entry.set("")  # Clear CTkComboBox value
                else:
                    # Widget-type safe clear: entries have delete(), comboboxes
                    # have set(). Checkboxes/buttons have neither - skip them
                    # silently instead of raising AttributeError.
                    if hasattr(entry, 'delete'):
                        entry.delete(0, 'end')  # Clear CTkEntry value
                    elif hasattr(entry, 'set'):
                        entry.set('')
            except Exception as e:
                print(f"Error clearing field {key}: {e}")

        # Make sure the toggle functions are called after clearing
        self.toggle_factor_std_conc()
        self.toggle_qc_fields()

    def create_test_parameters(self, test_id):
        """Test parameter form, laid out for the instrument's 1280x720 panel.

        Three stacked bands: the header, the form itself, and the docked
        on-screen keyboard sitting just above the action buttons. The keyboard
        is hidden until a text/number field is tapped (see KEYBOARD_FIELDS) and
        closes itself when the operator presses Done.

        Everything that is chosen from a list (method, wavelength, unit, blank
        type) uses TouchSelect - a modal grid of full-size buttons - because a
        fingertip cannot reliably drive customtkinter's native dropdown popup.
        """
        self.current_section = "parameters"

        # Main container frame
        param_frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        param_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Make the main frame expand with the window
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header with back button and title
        header_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=sp(18), pady=(sp(8), sp(3)))

        back_btn = ctk.CTkButton(
            header_frame,
            text="←",
            width=sp(46),
            height=sp(42),
            font=theme_font(16, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(10),
            border_width=1, border_color=tc("border"),
            command=self.back_from_parameters
        )
        back_btn.pack(side="left")

        # Determine the title text based on test_id
        title_text = "Test Parameters - New Test" if test_id is None else f"Test Parameters - Test {test_id + 1}"

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=sp(14))
        self.params_title_label = ctk.CTkLabel(
            title_box,
            text=title_text,
            font=theme_font(20, bold=True),
            text_color=tc("text")
        )
        self.params_title_label.pack(anchor="w")
        save_hint = ctk.CTkLabel(
            title_box,
            text="Fill the fields, then SAVE. Tap a box to type; tap a list to choose.",
            font=theme_font(11), text_color=tc("text_muted"))
        save_hint.pack(anchor="w")

        '''---------------------Parameters entries --------------------------------'''
        # The action buttons and the keyboard are packed BOTTOM-first so the
        # form can only ever use the space that is actually left over.
        button_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        button_frame.pack(side="bottom", fill="x", padx=sp(18), pady=(sp(2), sp(8)))

        # The keyboard is FLOATED above the form, just clear of the action
        # buttons, once the buttons exist (see the bottom of this method).
        #
        # It used to be packed into the layout, which on the real 7" panel left
        # it fighting the form for height: Tk resolved that fight by squashing
        # the keyboard into a strip one key tall. A floating keyboard is not
        # part of the layout at all, so the form keeps its full size and the
        # keys keep theirs. Sitting it above the action row means neither the
        # form nor RUN/SAVE/DELETE/CANCEL is covered while the operator types.
        self.params_keyboard = None
        self._params_keyboard_docked = False

        # Parameters container
        params_container = ctk.CTkFrame(param_frame, **theme_card(radius=sp(14)))
        params_container.pack(fill="both", expand=True, padx=sp(18), pady=(sp(2), sp(6)))

        # A PLAIN frame, not a scrollable one: every field of the form is sized
        # to fit the 720 px panel together with the floating keyboard, so there
        # is nothing to scroll - and a scrollbar next to a touch form reads as
        # a broken control. Row spacing and control heights below are what keep
        # that promise (6 rows x 48 px).
        params_frame = ctk.CTkFrame(params_container, fg_color="transparent")
        params_frame.pack(fill="both", expand=True, padx=sp(6), pady=sp(6))
        for i in range(4):
            params_frame.grid_columnconfigure(i, weight=1)
        params_frame.grid_columnconfigure(1, weight=2)
        params_frame.grid_columnconfigure(3, weight=2)
        # A guaranteed width for the two label columns. Sized by weight alone,
        # "Standard Concentration" came out wider than its cell on the panel and
        # was cut mid-word at the entry box; the entries only ever need 240 px of
        # their (much wider) columns, so this costs the form nothing. It is only
        # a FLOOR: the loop below widens a column to whatever its own widest
        # label asks for once the real font is known.
        for label_col in (0, 2):
            params_frame.grid_columnconfigure(label_col, minsize=sp(232))

        # Which widget labels which field, and the labels of each column.
        # Both are needed by the two measured layout steps below: the label
        # columns are sized from their labels, and ticking Factor hides the Std
        # Concentration ROW - label included (see toggle_factor_std_conc).
        self.param_labels = {}
        label_columns = {}

        # Initialize checkbox variables if they don't exist yet
        if not hasattr(self, 'use_factor_var'):
            self.use_factor_var = ctk.BooleanVar(value=False)
        if not hasattr(self, 'use_blank_var'):
            self.use_blank_var = ctk.BooleanVar(value=False)
        if not hasattr(self, 'use_qc_var'):
            self.use_qc_var = ctk.BooleanVar(value=False)
        # Define parameters with their variable names


        params = [
            ("Test Name", "test_name"),
            ("Low (Range)", "low"),
            # No "(TP/EP/Kinetic)" here: the list itself shows the options.
            ("Method", "method"),
            ("High (Range)", "high"),
            # ("Temperature (°C)", "temperature"),
            # Just "Wavelength": the value itself reads "480nm", so the unit in
            # the label was only making the label too long for its column.
            ("Wavelength", "wavelength"),
            ("Factor", "use_factor"),
            ("Blank", "blank"),
            # ("Wavelength 2 (nm)", "wavelength2"),
            # ("Factor Value", "factor_value"),
            # ("Decimal Points", "decimal"),
            # "Std Concentration": the label has to name the field in the
            # width the label column has on the panel - the operator asked to
            # shorten it rather than see it clipped at the entry.
            ("Std Concentration", "std_conc"),
            ("Delay Time (s)", "delay_time"),
            # ("Volume (µL)", "volume"),
            ("Measuring Time", "measuring_time"),
            ("Unit", "unit"),
            ("QC", "use_qc")

        ]


        # Create parameter entries in a more compact layout
        for i, (label, var_name) in enumerate(params):
            row, col = divmod(i, 2)

            # Add label for all fields
            label_widget = ctk.CTkLabel(
                params_frame,
                text=label,
                font=theme_font(14, bold=True),
                text_color=tc("text"),
                justify="right",
                # NO wraplength yet: a label's natural width is what the column
                # it lives in has to be sized from, and wrapping caps it. The
                # width each label really gets is set after the columns are
                # measured (see "Label columns: measured, not guessed").
            )
            label_widget.grid(row=row, column=col * 2, padx=(sp(12), sp(8)),
                              pady=sp(4), sticky="e")
            self.param_labels[var_name] = label_widget
            label_columns.setdefault(col * 2, []).append(label_widget)

            # Handle the checkbox for Factor specially
            # if var_name == "use_factor":
            #     checkbox = ctk.CTkCheckBox(
            #         params_frame,
            #         text="",  # No text on the checkbox itself
            #         variable=self.use_factor_var,
            #         command=self.toggle_factor_std_conc,
            #         width=20
            #     )
            #     checkbox.grid(row=row, column=col * 2 + 1, padx=5, pady=5, sticky="w")  # Reduced padding
            #     self.param_entries[var_name] = checkbox
            #     continue

            if var_name == "use_factor":
                checkbox = ctk.CTkCheckBox(
                    params_frame,
                    text="",
                    variable=self.use_factor_var,
                    command=self.toggle_factor_std_conc,
                    width=sp(28),
                    height=sp(28),
                    checkbox_width=sp(26),
                    checkbox_height=sp(26),
                    corner_radius=sp(8),
                    fg_color=tc("accent"), hover_color=tc("accent_hover"),
                    border_color=tc("border_strong")
                )
                checkbox.grid(row=row, column=col * 2 + 1, padx=(sp(8), sp(2)),
                              pady=sp(4), sticky="w")
                self.param_entries[var_name] = checkbox

                # Factor value entry on the same line
                factor_entry = ctk.CTkEntry(
                    params_frame,
                    width=sp(200),
                    height=sp(40),
                    font=theme_font(14),
                    fg_color=tc("surface_sunken"), text_color=tc("text"),
                    border_color=tc("border_strong"), corner_radius=sp(10)
                )
                factor_entry.grid(row=row, column=col * 2 + 1, padx=(sp(52), sp(12)),
                                  pady=sp(4), sticky="w")

                self.param_entries["factor_value"] = factor_entry

                factor_entry.grid_remove()   # Initially hidden

                continue

            if var_name == "use_qc":
                checkbox = ctk.CTkCheckBox(
                    params_frame,
                    text="",
                    variable=self.use_qc_var,
                    command=self.toggle_qc_fields,
                    width=sp(28),
                    height=sp(28),
                    checkbox_width=sp(26),
                    checkbox_height=sp(26),
                    corner_radius=sp(8),
                    fg_color=tc("accent"), hover_color=tc("accent_hover"),
                    border_color=tc("border_strong")
                )
                checkbox.grid(row=row, column=col * 2 + 1, padx=(sp(8), sp(2)),
                              pady=sp(4), sticky="w")
                self.param_entries[var_name] = checkbox

                # Create QC Value button next to the checkbox (initially hidden)
                qc_value_btn = ctk.CTkButton(
                    params_frame,
                    text="QC values",
                    width=sp(160),
                    height=sp(40),
                    font=theme_font(14, bold=True),
                    fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                    text_color=tc("btn_text"), corner_radius=sp(10),
                    border_width=1, border_color=tc("border"),
                    command=self.show_qc_input_popup
                )
                qc_value_btn.grid(row=row, column=col * 2 + 1, padx=(sp(52), sp(12)),
                                  pady=sp(4), sticky="w")
                qc_value_btn.grid_remove()  # Initially hidden
                self.param_entries["qc_value_btn"] = qc_value_btn
                continue

            # Handle the blank field - tickbox + dropdown for every method:
            # ticking the box reveals the R.Blank/S.Blank list for picking
            # (the list closes on selection, natively); unticking hides it.
            if var_name == "blank":
                # Create frame to hold both blank widgets
                blank_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
                blank_frame.grid(row=row, column=col * 2 + 1, padx=sp(8), pady=sp(4),
                                 sticky="w")

                # Create checkbox for blank
                checkbox = ctk.CTkCheckBox(
                    blank_frame,
                    text="",
                    variable=self.use_blank_var,
                    command=self._sync_blank_widgets,
                    width=sp(28),
                    height=sp(28),
                    checkbox_width=sp(26),
                    checkbox_height=sp(26),
                    corner_radius=sp(8),
                    fg_color=tc("accent"), hover_color=tc("accent_hover"),
                    border_color=tc("border_strong")
                )
                checkbox.pack(side="left", padx=(0, sp(8)), pady=0)
                self.param_entries["blank_checkbox"] = checkbox

                # Create the R.Blank / S.Blank choice as a touch-safe picker
                blank_dropdown = TouchSelect(
                    blank_frame,
                    values=["R.Blank", "S.Blank"],
                    width=sp(200),
                    height=sp(40),
                    title="Blank type"
                )
                blank_dropdown.pack(side="left", padx=0, pady=0)
                blank_frame.grid_columnconfigure(0, weight=1)
                # Initially hide the dropdown
                self.param_entries["blank_dropdown"] = blank_dropdown
                continue

            # Create appropriate input widget based on parameter type
            if var_name == "method":
                # A picker of big buttons instead of the native dropdown: a
                # fingertip cannot drive customtkinter's canvas popup reliably.
                entry = TouchSelect(
                    params_frame,
                    values=["TP", "EP", "Kinetic"],
                    width=sp(240),
                    height=sp(40),
                    placeholder="", title="Method",
                    command=self.toggle_blank_field
                )
            elif var_name == "wavelength":
                entry = TouchSelect(
                    params_frame,
                    values=["340nm", "415nm", "445nm", "480nm", "515nm", "555nm",
                            "590nm", "630nm", "680nm"],
                    width=sp(240), height=sp(40), placeholder="",
                    title="Wavelength")
            elif var_name == "temperature":
                entry = TouchSelect(params_frame, values=["25", "30", "37"],
                                    width=sp(240), height=sp(40), title="Temperature")
            elif var_name == "unit":
                entry = TouchSelect(
                    params_frame,
                    values=["mol/L", "mmol/L", "umol/L", "g/L", "mg/L", "ug/L",
                            "U/L", "IU/L", "mol%", "mmol%", "umol%",
                            "g%", "mg%", "ug%"],
                    width=sp(240), height=sp(40), placeholder="",
                    title="Unit")
            else:
                entry = ctk.CTkEntry(
                    params_frame,
                    width=sp(240),
                    height=sp(40),
                    font=theme_font(14),
                    fg_color=tc("surface_sunken"), text_color=tc("text"),
                    placeholder_text_color=tc("text_faint"),
                    border_color=tc("border_strong"), corner_radius=sp(10)
                )

            entry.grid(row=row, column=col * 2 + 1, padx=(sp(8), sp(12)),
                       pady=sp(4), sticky="w")
            self.param_entries[var_name] = entry


            # Initially hide factor_value field
            # if var_name == "factor_value":
            #     entry.grid_remove()  # Hide initially

        # Label columns: measured, not guessed.
        #
        # The columns used to be pinned at 232 px with a 224 px wrap, which is
        # enough for the desktop font and NOT for the font the Raspberry Pi
        # resolves: there "Measuring Time (s)" was reported as not properly
        # visible and the value columns came out pushed right ("the Delay Time
        # box is shifted very right" - a label column that grows pushes the
        # entry column after it, and one that cannot grow clips its label
        # instead). So each label column now gets the width its own widest label
        # actually needs: 232 px floor keeps the two halves aligned, a 300 px
        # ceiling guarantees the two 240 px entry columns their room, and every
        # label is then wrapped to the width its column really received - so a
        # wider font still wraps a long label instead of cutting it in half at
        # the entry box.
        for label_col, widgets in label_columns.items():
            try:
                needed = max(int(w.winfo_reqwidth()) for w in widgets) + sp(20)
            except Exception:
                continue
            needed = max(sp(232), min(needed, sp(300)))
            params_frame.grid_columnconfigure(label_col, minsize=needed)
            for widget in widgets:
                try:
                    widget.configure(wraplength=max(sp(140), needed - sp(16)))
                except Exception as exc:
                    print(f"[PARAMS] could not wrap a label: {exc}")

        # Call toggle function to set initial state
        self.toggle_factor_std_conc()
        self.toggle_blank_field(self.param_entries["method"].get())

        '''-----------------Bottom Buttons --------------------------'''
        buttons = ["RUN", "SAVE", "DELETE", "CANCEL"]
        for i in range(len(buttons)):
            button_frame.grid_columnconfigure(i, weight=1, uniform="params")

        # Create buttons with specific styling (one accent action per meaning:
        # RUN = go, SAVE = keep, DELETE = destructive, CANCEL = back out).
        styles = {
            # RUN is the GO action and must not look like SAVE next to it: it is
            # blue (a deeper blue in dark mode) while SAVE stays green.
            "RUN": dict(fg_color=tc("run_btn"), hover_color=tc("run_btn_hover"),
                        text_color=tc("on_run_btn")),
            "SAVE": dict(fg_color=tc("success"), hover_color=tc("success"),
                         text_color=tc("on_success")),
            "DELETE": dict(fg_color=tc("danger"), hover_color=tc("danger"),
                           text_color=tc("on_danger")),
            "CANCEL": dict(fg_color=tc("btn_neutral"),
                           hover_color=tc("btn_neutral_hover"),
                           text_color=tc("btn_text")),
        }
        for i, text in enumerate(buttons):
            btn = ctk.CTkButton(
                button_frame,
                text=text,
                height=sp(46),
                font=theme_font(14, bold=True),
                corner_radius=sp(12),
                command=lambda t=text: self.handle_parameter_button(t),
                **styles.get(text, {})
            )
            btn.grid(row=0, column=i, padx=sp(6), pady=sp(3), sticky="ew")

        # Now that the action row has its real height, float the wide keyboard
        # just above it (see the note where self.params_keyboard is declared).
        # update_idletasks first: a frame that has never been laid out still
        # reports its default 200 px request, which would park the keyboard in
        # the middle of the form.
        button_frame.update_idletasks()
        self.params_keyboard = OnScreenKeyboard(
            param_frame, on_hide=self._on_keyboard_hidden
        ).float_over(relx=0.5, rely=1.0, anchor="s", relwidth=0.98,
                     y=-(button_frame.winfo_reqheight() + sp(16)))

        # The number keypad for the numeric fields. It is small, so it floats
        # BESIDE whichever field is being typed into (opposite side of the
        # form, aligned with the field's row): the operator asked for exactly
        # this after the wide keyboard covered the field they were typing in
        # ("what I am typing doesn't get visible").
        self.params_pad = OnScreenKeyboard(
            param_frame, on_hide=self._on_keyboard_hidden
        ).float_beside(param_frame, keep_clear=button_frame)
        # Opening one keyboard closes the other (see OnScreenKeyboard.show).
        self.params_keyboard.sibling = self.params_pad
        self.params_pad.sibling = self.params_keyboard

        # Wire the keyboards to the typed-in fields only. Tapping a text field
        # opens the wide keyboard, tapping a number field opens the pad beside
        # it, and tapping a list field opens its picker instead - no keyboard
        # may ever cover a choice list.
        for key, label, kind in KEYBOARD_FIELDS:
            widget = self.param_entries.get(key)
            if widget is None or not hasattr(widget, "insert"):
                continue
            board = self.params_pad if kind in PAD_KINDS else self.params_keyboard
            board.attach(widget, label, kind)

        self.polish_screen(param_frame)
        return param_frame

    def _on_keyboard_hidden(self):
        """The keyboard closed itself: hand its space back to the form."""
        self._params_keyboard_docked = False

    def toggle_parameters_keyboard(self, show=True):
        """Show/hide the on-screen keyboards (used by the tests and by Done)."""
        keyboard = getattr(self, 'params_keyboard', None)
        pad = getattr(self, 'params_pad', None)
        if show:
            if keyboard is not None:
                keyboard.show()
            if pad is not None:
                # Both live in `param_frame`; only one of them is ever wanted at
                # a time, and the wide one is what this call is for.
                pad.hide()
        else:
            for board in (keyboard, pad):
                if board is not None:
                    board.hide()
        return keyboard

    def back_from_parameters(self):
        """Handle back button from parameters screen - disable edit mode"""
        self.edit_mode = False  # Turn off edit mode
        self.show_test_screen()

    def back_to_test_list(self):
        """Handle back button from measurement screen - ensure edit mode is off"""
        self.edit_mode = False  # Ensure edit mode is off
        # Drop the graph of the run we are leaving THIS instant: the run thread
        # may need a moment to notice the abort, and until it does it would
        # keep appending points and animating the curve behind the menu - and,
        # worse, onto the next test's graph once it is opened.
        try:
            self.workflow_manager.reset_plot_for_new_screen()
        except Exception as exc:
            print(f"[WF] Plot reset on Back failed: {exc}")
        if not SIMULATION_MODE:
            # Abort any in-flight hardware op (streaming readings, LED align,
            # aspirate). Two-stage so the UI never freezes:
            #  1. request_abort() only sets a flag + stops capture — instant,
            #     wakes every blocked waiter so stale threads exit instead
            #     of stealing the next screen's UART replies.
            #  2. the ABORT command itself goes out on a daemon thread (it
            #     can take ~1 s for the firmware to answer).
            # show_test_screen() -> clear_frames() bumps _screen_token, so
            # stale threads/callbacks recognise themselves as dead.
            try:
                from Hardware.serial_manager import get_manager
                get_manager().request_abort()
            except Exception as e:
                print(f"[HW] Error signalling abort on back: {e}")
            try:
                import threading as _t
                from Hardware import stm32_backend as _hw
                _t.Thread(target=_hw.send_abort, daemon=True).start()
            except Exception as e:
                print(f"[HW] Error sending abort on back: {e}")
        self.show_test_screen()

    def toggle_qc_fields(self):
        """Toggle QC Values button visibility without requiring immediate input"""
        try:
            # Get the current state of the checkbox
            use_qc = self.use_qc_var.get()

            # Get the QC values button if it exists
            qc_value_btn = self.param_entries.get("qc_value_btn")

            # Show/hide the QC values button based on checkbox state
            if qc_value_btn:
                if use_qc:
                    qc_value_btn.grid()  # Show QC Values button
                else:
                    qc_value_btn.grid_remove()  # Hide QC Values button

            # Update use_qc in database if we're editing a test
            if hasattr(self, 'edit_mode') and self.edit_mode and hasattr(self,
                                                                         'current_test_name') and self.current_test_name:
                # self.db_manager.update_use_qc(self.current_test_name, 1 if use_qc else 0)
                pass

        except Exception as e:
            print(f"Error in toggle_qc_fields: {e}")

    def show_qc_input_popup(self):
        """Show a compact, simplified QC input dialog with optional fields - Fixed for Raspberry Pi"""
        try:
            # Create popup window. Sized for the 7" panel and (below) given its
            # own keyboard: QC mean/SD are typed values, so without one they
            # would be impossible to enter on a touchscreen.
            popup_w, popup_h = sp(760), sp(660)
            qc_popup = ctk.CTkToplevel(self)
            qc_popup.title("QC Parameters")
            qc_popup.geometry(f"{popup_w}x{popup_h}")
            qc_popup.overrideredirect(True)

            # Center the popup
            try:
                qc_popup.update_idletasks()
                x = self.winfo_rootx() + (self.winfo_width() - popup_w) // 2
                y = self.winfo_rooty() + (self.winfo_height() - popup_h) // 2
            except Exception:
                x = (qc_popup.winfo_screenwidth() - popup_w) // 2
                y = (qc_popup.winfo_screenheight() - popup_h) // 2
            qc_popup.geometry(f"{popup_w}x{popup_h}+{max(0, x)}+{max(0, y)}")

            # Make window modal AFTER it's fully created and positioned
            qc_popup.after(100, lambda: self.make_popup_modal(qc_popup))

            # Rest of your popup code remains the same...
            # Main content frame with border
            main_frame = ctk.CTkFrame(qc_popup, corner_radius=10, border_width=2)
            main_frame.pack(fill="both", expand=True, padx=5, pady=5)

            # Title with close button
            title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            title_frame.pack(fill="x", padx=10, pady=(10, 5))

            title = ctk.CTkLabel(
                title_frame,
                text="QC Parameters ",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            title.pack(side="left", padx=10)

            close_btn = ctk.CTkButton(
                title_frame,
                text="×",
                width=30,
                command=qc_popup.destroy,
                fg_color="transparent",
                hover_color="#DDDDDD"
            )
            close_btn.pack(side="right")

            # Input grid frame
            input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            input_frame.pack(fill="both", expand=True, padx=10, pady=10)

            # QC1 fields
            qc1_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
            qc1_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(qc1_frame, text="QC1", font=ctk.CTkFont(weight="bold"),
                         text_color="#3B82F6", width=40).pack(side="left", padx=(5, 10))

            ctk.CTkLabel(qc1_frame, text="Mean:", width=40).pack(side="left", padx=2)
            qc1_mean = ctk.CTkEntry(qc1_frame, width=60)
            qc1_mean.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(qc1_frame, text="SD:", width=30).pack(side="left", padx=2)
            qc1_sd = ctk.CTkEntry(qc1_frame, width=60)
            qc1_sd.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(qc1_frame, text="Label:", width=40).pack(side="left", padx=2)
            qc1_label = ctk.CTkEntry(qc1_frame, width=60)
            qc1_label.pack(side="left")

            # QC2 fields
            qc2_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
            qc2_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(qc2_frame, text="QC2", font=ctk.CTkFont(weight="bold"),
                         text_color="#EF4444", width=40).pack(side="left", padx=(5, 10))

            ctk.CTkLabel(qc2_frame, text="Mean:", width=40).pack(side="left", padx=2)
            qc2_mean = ctk.CTkEntry(qc2_frame, width=60)
            qc2_mean.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(qc2_frame, text="SD:", width=30).pack(side="left", padx=2)
            qc2_sd = ctk.CTkEntry(qc2_frame, width=60)
            qc2_sd.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(qc2_frame, text="Label:", width=40).pack(side="left", padx=2)
            qc2_label = ctk.CTkEntry(qc2_frame, width=60)
            qc2_label.pack(side="left")

            # Info text
            info_text = ctk.CTkLabel(
                input_frame,
                text="Note: All fields are optional. Leave SD blank to auto-calculate as 10% of mean.",
                font=ctk.CTkFont(size=10),
                text_color="gray"
            )
            info_text.pack(pady=5)

            # Error message label (initially hidden)
            error_label = ctk.CTkLabel(
                input_frame,
                text="",
                font=ctk.CTkFont(size=12),
                text_color="#DC2626"
            )
            error_label.pack(pady=5)
            error_label.pack_forget()

            # Button frame
            button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            button_frame.pack(side="bottom", fill="x", pady=sp(10))

            # Cancel button
            cancel_btn = ctk.CTkButton(
                button_frame,
                text="Cancel",
                command=qc_popup.destroy,
                fg_color="#6B7280",
                hover_color="#4B5563"
            )
            cancel_btn.pack(side="left", padx=10)

            # Save button
            save_btn = ctk.CTkButton(
                button_frame,
                text="Save Parameters",
                command=lambda: self.save_qc_parameters_with_validation(
                    qc_popup,
                    qc1_mean.get(),
                    qc1_sd.get(),
                    qc1_label.get(),
                    qc2_mean.get(),
                    qc2_sd.get(),
                    qc2_label.get(),
                    error_label
                )
            )
            save_btn.pack(side="right", padx=10)

            # On-screen keyboard, floated over the popup (hidden until a field is
            # tapped - see OnScreenKeyboard.float_over: a packed keyboard gets
            # squashed to a strip when the layout runs out of height). It is
            # built after the buttons so it can sit just clear of them, and
            # placed last so it is drawn on top of everything.
            button_frame.update_idletasks()
            keyboard = OnScreenKeyboard(qc_popup).float_over(
                relx=0.5, rely=1.0, anchor="s", relwidth=0.96,
                y=-(button_frame.winfo_reqheight() + sp(34)))
            qc_popup._qc_keyboard = keyboard
            for entry, label in ((qc1_mean, "QC1 Mean"), (qc1_sd, "QC1 SD"),
                                 (qc1_label, "QC1 Label"), (qc2_mean, "QC2 Mean"),
                                 (qc2_sd, "QC2 SD"), (qc2_label, "QC2 Label")):
                kind = "text" if "Label" in label else "number"
                keyboard.attach(entry, label, kind)

            # Load existing values if available
            self.load_existing_qc_values(
                qc1_mean,
                qc1_sd,
                qc1_label,
                qc2_mean,
                qc2_sd,
                qc2_label
            )

        except Exception as e:
            print(f"Error in show_qc_input_popup: {e}")

    def make_popup_modal(self, popup):
        """Helper function to make popup modal after it's ready"""
        try:
            if popup.winfo_exists():
                popup.grab_set()
                popup.focus_set()
        except Exception as e:
            print(f"Could not make popup modal: {e}")

    def save_qc_parameters_with_validation(self, popup, qc1_mean, qc1_sd, qc1_label,
                                           qc2_mean, qc2_sd, qc2_label, error_label):
        """Save QC parameters with improved validation"""
        try:
            # Validate inputs - all fields are optional
            qc_data = {
                'serial_num': datetime.now().strftime('%Y%m%d%H%M%S')
            }

            # Check if we have a current test name
            if not hasattr(self, 'current_test_name') or not self.current_test_name:
                # Try to get it from the test_name entry
                if 'test_name' in self.param_entries:
                    self.current_test_name = self.param_entries['test_name'].get()

                if not self.current_test_name:
                    error_label.configure(text="Error: No test selected. Please save the test first.")
                    error_label.pack()
                    return

            # Process QC1 data if provided
            if qc1_mean:
                try:
                    qc1_mean_val = float(qc1_mean)
                    qc_data['qc1_mean'] = qc1_mean_val

                    # Process SD if provided or calculate as 10% of mean
                    if qc1_sd:
                        qc_data['qc1_sd'] = float(qc1_sd)
                    else:
                        qc_data['qc1_sd'] = qc1_mean_val * 0.1

                    # Process label
                    qc_data['qc1_label'] = qc1_label if qc1_label else "QC1"
                except ValueError:
                    error_label.configure(text="Error: QC1 Mean or SD is not a valid number")
                    error_label.pack()
                    return

            # Process QC2 data if provided
            if qc2_mean:
                try:
                    qc2_mean_val = float(qc2_mean)
                    qc_data['qc2_mean'] = qc2_mean_val

                    # Process SD if provided or calculate as 10% of mean
                    if qc2_sd:
                        qc_data['qc2_sd'] = float(qc2_sd)
                    else:
                        qc_data['qc2_sd'] = qc2_mean_val * 0.1

                    # Process label
                    qc_data['qc2_label'] = qc2_label if qc2_label else "QC2"
                except ValueError:
                    error_label.configure(text="Error: QC2 Mean or SD is not a valid number")
                    error_label.pack()
                    return

            # Save to database if we have any QC data
            if 'qc1_mean' in qc_data or 'qc2_mean' in qc_data:
                if hasattr(self, 'current_test_name') and self.current_test_name:
                    success = self.db_manager.save_qc_values(self.current_test_name, qc_data)
                    if success:
                        self.show_notification("QC parameters saved successfully")
                        popup.destroy()
                    else:
                        error_label.configure(text="Failed to save QC parameters")
                        error_label.pack()
                else:
                    error_label.configure(text="Error: No test selected")
                    error_label.pack()
            else:
                # No QC data provided, but that's OK - just close
                popup.destroy()

        except Exception as e:
            error_label.configure(text=f"Error: {str(e)}")
            error_label.pack()

    def load_existing_qc_values(self, qc1_mean_entry, qc1_sd_entry, qc1_label_entry,
                                qc2_mean_entry, qc2_sd_entry, qc2_label_entry):
        """Load existing QC values if available - Fixed clearing method"""
        try:
            if hasattr(self, 'current_test_name') and self.current_test_name:
                qc_data = self.db_manager.load_qc_values(self.current_test_name)

                if qc_data:
                    # Clear existing values - FIXED METHOD
                    entries = [qc1_mean_entry, qc1_sd_entry, qc1_label_entry,
                               qc2_mean_entry, qc2_sd_entry, qc2_label_entry]

                    for entry in entries:
                        try:
                            # Clear entry fields properly
                            if hasattr(entry, 'delete'):
                                entry.delete(0, 'end')
                            elif hasattr(entry, 'set'):
                                entry.set('')
                        except Exception as e:
                            print(f"Error clearing entry: {e}")

                    # Populate fields with existing values
                    if 'qc1_mean' in qc_data and qc_data['qc1_mean'] is not None:
                        qc1_mean_entry.insert(0, str(qc_data.get('qc1_mean', '')))
                    if 'qc1_sd' in qc_data and qc_data['qc1_sd'] is not None:
                        qc1_sd_entry.insert(0, str(qc_data.get('qc1_sd', '')))
                    if 'qc1_label' in qc_data and qc_data['qc1_label'] is not None:
                        qc1_label_entry.insert(0, qc_data.get('qc1_label', ''))
                    if 'qc2_mean' in qc_data and qc_data['qc2_mean'] is not None:
                        qc2_mean_entry.insert(0, str(qc_data.get('qc2_mean', '')))
                    if 'qc2_sd' in qc_data and qc_data['qc2_sd'] is not None:
                        qc2_sd_entry.insert(0, str(qc_data.get('qc2_sd', '')))
                    if 'qc2_label' in qc_data and qc_data['qc2_label'] is not None:
                        qc2_label_entry.insert(0, qc_data.get('qc2_label', ''))
        except Exception as e:
            print(f"Error in load_existing_qc_values: {str(e)}")

    def _sync_blank_widgets(self):
        """Show the R.Blank/S.Blank dropdown exactly when the blank box is ticked.

        Called by the checkbox itself and after any programmatic change
        (method switch, test load). When revealed with no valid choice yet,
        defaults to R.Blank. Uses pack_forget (children are pack-managed).
        """
        try:
            dropdown = self.param_entries.get("blank_dropdown")
            if dropdown is None:
                return
            if self.use_blank_var.get():
                try:
                    current = dropdown.get().strip()
                except Exception:
                    current = ""
                if current not in ("R.Blank", "S.Blank"):
                    try:
                        dropdown.set("R.Blank")
                    except Exception:
                        pass
                dropdown.pack(side="left", padx=0, pady=0)
            else:
                dropdown.pack_forget()
        except Exception as e:
            print(f"Error syncing blank widgets: {e}")

    def toggle_blank_field(self, method_value):
        """Method-driven defaults for the parameters form.

        The blank row itself is method-independent now (tickbox reveals the
        R.Blank/S.Blank list); this only handles per-method defaults and
        the QC/measuring-time visibility rules.
        """
        try:
            # Keep the blank widgets in sync with the tickbox state.
            self._sync_blank_widgets()
            m_time_entry = self.param_entries.get("measuring_time")

            if method_value == "EP":

                # For EP method, show QC checkbox since it's valid
                if "use_qc" in self.param_entries:
                    self.param_entries["use_qc"].grid()

                # Set default measuring time to 5 seconds for EP (only if empty/zero)
                mt_entry = self.param_entries.get("measuring_time")
                if mt_entry and hasattr(mt_entry, 'delete'):
                    current_mt = mt_entry.get().strip()
                    if not current_mt or current_mt in ('0', '0.0'):
                        mt_entry.delete(0, 'end')
                        mt_entry.insert(0, "5.0")

                # Delay time for EP defaults to 0 seconds (still user input:
                # only fills in when the field is empty, never overwrites).
                delay_entry = self.param_entries.get("delay_time")
                if delay_entry and hasattr(delay_entry, 'delete'):
                    current_dt = delay_entry.get().strip()
                    if not current_dt:
                        delay_entry.delete(0, 'end')
                        delay_entry.insert(0, "0")

            elif method_value == "TP" or method_value == "Kinetic":
                # For TP/Kinetic, show measuring time
                if m_time_entry:
                    m_time_entry.grid()  # Show measuring time

                # For TP and Kinetic methods, show QC checkbox
                if "use_qc" in self.param_entries:
                    self.param_entries["use_qc"].grid()

                # TP/Kinetic delay time is purely user input — no auto-fill.
                # (Incubation is hardcoded: EP 2 s, TP/Kinetic 0 s.)

            elif str(method_value or "").strip():
                # A method this form has no QC for (kept for older tests that
                # still carry one): show measuring time, hide QC.
                if m_time_entry:
                    m_time_entry.grid()  # Show measuring time

                if "use_qc" in self.param_entries:
                    self.param_entries["use_qc"].grid_remove()
                    # Also hide QC value button if it exists
                    if "qc_value_btn" in self.param_entries:
                        self.param_entries["qc_value_btn"].grid_remove()

            else:
                # NOTHING chosen yet - a brand-new form, or a test whose method
                # has not been picked on this screen. Every field stays on
                # screen, QC included.
                #
                # This is the "QC tick box is removed or not visible" report:
                # the form used to fall into the branch above as it was built
                # (the Method box is empty until it is tapped), so the QC box
                # was hidden before the operator had a chance to see it - and a
                # tap on Method was the only way to bring it back.
                if m_time_entry:
                    m_time_entry.grid()
                if "use_qc" in self.param_entries:
                    self.param_entries["use_qc"].grid()

        except Exception as e:
            print(f"Error in toggle_blank_field: {e}")

    def toggle_factor_std_conc(self):
        """The two ways of setting the calibration: Factor OR Std Concentration.

        They are alternatives, not a pair, so exactly one of them is on screen:

          * Factor ticked      -> the Factor value box appears next to the tick
                                  and the Std Concentration row is taken away,
          * Factor unticked    -> the Std Concentration row comes back and the
                                  Factor value box goes away.

        The operator asked for this back verbatim ("When Factor is selected, the
        standard concentration input box should not be present there. Earlier it
        was properly working"); a pass in between had left the field on screen
        muted, which is what made the form confusing. The ROW goes, label
        included - a label with no box under it was itself reported as "Standard
        Concentration is still not visible". Saving is unchanged: it writes
        exactly one of the two (see save_parameters).
        """
        try:
            use_factor = self.use_factor_var.get()
            # Get the widgets by key, not by path
            factor_value_entry = self.param_entries.get("factor_value")
            std_conc_entry = self.param_entries.get("std_conc")
            std_conc_label = getattr(self, "param_labels", {}).get("std_conc")
            if factor_value_entry:
                try:
                    if use_factor:
                        factor_value_entry.grid()
                    else:
                        factor_value_entry.grid_remove()
                except tk.TclError as e:
                    print(f"Grid error: {e}")
            for widget in (std_conc_entry, std_conc_label):
                if widget is None:
                    continue
                try:
                    if use_factor:
                        widget.grid_remove()
                    else:
                        widget.grid()
                except tk.TclError as e:
                    print(f"Grid error: {e}")
                except Exception:
                    pass
        except Exception as e:
            print(f"Error in toggle_factor_std_conc: {e}")

    def save_parameters(self):
        try:
            # Collect all parameters from entries
            params = {}

            # Get the selected method
            method = self.param_entries["method"].get()

            # Handle blank (uniform across methods): ticked -> the
            # R.Blank/S.Blank choice, unticked -> 0 (blank disabled).
            # EP sequence logic keys off the R.Blank/S.Blank strings.
            if self.use_blank_var.get():
                try:
                    blank_value = self.param_entries["blank_dropdown"].get().strip()
                except Exception:
                    blank_value = ""
                if blank_value not in ("R.Blank", "S.Blank"):
                    blank_value = "R.Blank"
                params['blank'] = blank_value
            else:
                params['blank'] = 0

            # Add factor checkbox value
            use_factor = self.use_factor_var.get()
            params['use_factor'] = 1 if use_factor else 0

            # Handle QC enabled flag based on method
            if method in ["EP", "TP", "Kinetic"]:
                use_qc = self.use_qc_var.get()
                params['use_qc'] = 1 if use_qc else 0
            else:
                params['use_qc'] = 0

            # Extract parameter values from entries
            for var_name, entry in self.param_entries.items():
                # Skip special handling fields
                if var_name in ["use_factor", "blank_checkbox", "blank_dropdown", "qc_value_btn", "use_qc"]:
                    continue

                # Skip buttons or non-input widgets
                if isinstance(entry, ctk.CTkButton) or isinstance(entry, ctk.CTkCheckBox):
                    continue

                # Skip fields that should be hidden based on factor setting
                if (use_factor and var_name == "std_conc") or (not use_factor and var_name == "factor_value"):
                    continue

                # Get value based on widget type
                value = entry.get()

                # Validate required fields
                required_fields = ['test_name', 'method', 'wavelength','std_conc']
                if var_name in required_fields and not value:
                    entry.configure(border_color="red")
                    # messagebox.showerror("Error", f"Please fill out required field: {var_name}")
                    self.show_notification(f"Please fill out required field: {var_name}", error=True)
                    return

                # Type conversion for numeric fields
                if var_name in ['temperature',  'std_conc',
                                'high', 'low', 'delay_time', 'measuring_time']:
                    value = float(value) if value else 0.0
                # elif var_name == 'decimal':
                #     value = int(value) if value else 0

                params[var_name] = value

            # Handle factor value saving - SIMPLIFIED
            if use_factor:
                factor_value_str = self.param_entries.get('factor_value',
                                                          {}).get() if 'factor_value' in self.param_entries else ""
                factor_value = float(factor_value_str) if factor_value_str else 0.0
                params['factor_value'] = factor_value
            else:
                params['factor_value'] = 0.0

            # Get the test name from params
            test_name = params.get('test_name')
            if not test_name:
                # messagebox.showerror("Error", "Please enter a test name.")
                self.show_notification("Please enter a test name.", error=True)
                return

            # Determine if we're editing an existing test or creating a new one
            is_editing = hasattr(self, 'edit_mode') and self.edit_mode and self.current_test_name

            # Call save_parameters with appropriate arguments
            if is_editing:
                # When editing, pass the current_test_name for updating
                success, saved_name = self.db_manager.save_parameters(params, test_name=self.current_test_name)
                message = "Test parameters updated successfully!"
            else:
                # For new tests, don't pass test_name
                success, saved_name = self.db_manager.save_parameters(params)
                message = f"Test parameters saved as {saved_name}!"

            if success:
                # messagebox.showinfo("Success", message)
                self.show_notification(message, duration=5000, error=False)
                self.tests = self.db_manager.load_tests()  # Reload tests
                self.edit_mode = False
                self.show_test_screen()
            else:
                # messagebox.showerror("Error", "Failed to save test parameters.")
                self.show_notification("Failed to save test parameters.", error=True)

        except ValueError as e:
            # messagebox.showerror("Error", "Please enter valid numeric values for numeric fields.")
            self.show_notification(f"Please enter valid numeric values for numeric fields: {str(e)}", error=True)
        except Exception as e:
            # messagebox.showerror("Error", f"An error occurred while saving: {str(e)}")
            self.show_notification(f"An error occurred while saving: {str(e)}", error=True)
            print(f"Exception details: {e}")  # For debugging

    def load_test_parameters(self, test_name):
        """Load and display test parameters with FIXED wavelength & std_conc mapping"""
        try:
            self.current_test_name = test_name
            params = self.db_manager.load_parameters(test_name)

            if params:
                self.show_test_parameters(0)

                # ---------------- FIX START ----------------
                # Map DB fields to UI fields (CRITICAL FIX)
                if 'wavelength' in params:
                    try:
                        # Handle "505" or "505,546"
                        wavelength_raw = params.get('wavelength')

                        if wavelength_raw is not None:
                            wavelength_parts = str(wavelength_raw).split(',')

                            params['wavelength'] = wavelength_parts[0]

                            if len(wavelength_parts) > 1:
                                params['wavelength2'] = wavelength_parts[1]
                    except Exception as e:
                        print(f"Wavelength parsing error: {e}")

                if 'std_concentration' in params:
                    params['std_conc'] = params.get('std_concentration')
                # ---------------- FIX END ----------------

                method = params.get('method', 'TP')
                self.param_entries["method"].set(method)

                # Handle blank field (uniform tick -> dropdown UX).
                # Legacy rows: 1/0 ints (or '1'/'0' strings via TEXT affinity)
                # from the checkbox era, or R.Blank/S.Blank strings.
                blank_value = params.get('blank', 0)
                try:
                    as_int = int(str(blank_value).strip())
                except (TypeError, ValueError):
                    as_int = None
                if str(blank_value) in ("R.Blank", "S.Blank"):
                    self.use_blank_var.set(True)
                    self.param_entries["blank_dropdown"].set(str(blank_value))
                elif as_int == 1:
                    # Legacy "blank enabled" without a type: tick + R.Blank.
                    self.use_blank_var.set(True)
                    self.param_entries["blank_dropdown"].set("R.Blank")
                else:
                    self.use_blank_var.set(False)
                self.toggle_blank_field(method)

                # Handle factor/std_conc toggle
                use_factor = params.get('use_factor', False)
                self.use_factor_var.set(use_factor)
                self.toggle_factor_std_conc()

                # Handle QC settings
                if method in ["EP", "TP", "Kinetic"]:
                    use_qc = params.get('use_qc')
                    self.use_qc_var.set(bool(use_qc))
                    self.toggle_qc_fields()

                # Handle factor value loading
                if use_factor:
                    factor_value = params.get('factor_value', 0.0)
                    if 'factor_value' in self.param_entries:
                        try:
                            self.param_entries['factor_value'].delete(0, 'end')
                            self.param_entries['factor_value'].insert(0, str(factor_value))
                        except Exception as e:
                            print(f"Error setting factor value: {e}")

                # Populate other fields
                for field, value in params.items():
                    if field in self.param_entries and field not in [
                        'use_factor', 'factor_value', 'blank', 'use_qc', 'method'
                    ]:
                        widget = self.param_entries[field]
                        display_value = '' if value is None else str(value)

                        try:
                            if field in ["wavelength", "temperature","unit"]:
                                widget.set(display_value)
                            else:
                                if hasattr(widget, 'delete'):
                                    widget.delete(0, 'end')
                                    widget.insert(0, display_value)
                                elif hasattr(widget, 'set'):
                                    widget.set(display_value)
                                else:
                                    print(f"Warning: Cannot set value for field {field}")
                        except Exception as e:
                            print(f"Error setting field {field}: {e}")

            else:
                self.show_notification(f"Could not load parameters for {test_name}", error=True)

        except Exception as e:
            print(f"Error in load_test_parameters: {str(e)}")
            self.show_notification(f"Failed to load test parameters: {str(e)}", error=True)

    def _auto_save_parameters(self):
        """Save parameters to DB without navigating away. Returns True on success."""
        try:
            params = {}
            method = self.param_entries["method"].get()

            if self.use_blank_var.get():
                try:
                    _bv = self.param_entries["blank_dropdown"].get().strip()
                except Exception:
                    _bv = ""
                params['blank'] = _bv if _bv in ("R.Blank", "S.Blank") else "R.Blank"
            else:
                params['blank'] = 0

            params['use_factor'] = 1 if self.use_factor_var.get() else 0
            params['use_qc'] = 1 if (method in ["EP", "TP", "Kinetic"] and self.use_qc_var.get()) else 0

            for var_name, entry in self.param_entries.items():
                if var_name in ["use_factor", "blank_checkbox", "blank_dropdown", "qc_value_btn", "use_qc"]:
                    continue
                if isinstance(entry, (ctk.CTkButton, ctk.CTkCheckBox)):
                    continue
                if (params['use_factor'] and var_name == "std_conc") or (not params['use_factor'] and var_name == "factor_value"):
                    continue
                value = entry.get()
                if not value and var_name in ['test_name', 'method', 'wavelength', 'std_conc']:
                    return False
                if var_name in ['temperature', 'std_conc', 'high', 'low', 'delay_time', 'measuring_time']:
                    value = float(value) if value else 0.0
                params[var_name] = value

            if params.get('use_factor'):
                fv = self.param_entries.get('factor_value', {}).get() if 'factor_value' in self.param_entries else ""
                params['factor_value'] = float(fv) if fv else 0.0
            else:
                params['factor_value'] = 0.0

            test_name = params.get('test_name')
            if not test_name:
                return False

            is_editing = hasattr(self, 'edit_mode') and self.edit_mode and self.current_test_name
            if is_editing:
                success, saved_name = self.db_manager.save_parameters(params, test_name=self.current_test_name)
            else:
                success, saved_name = self.db_manager.save_parameters(params)

            if success:
                self.current_test_name = saved_name
                self.tests = self.db_manager.load_tests()
                self.edit_mode = False
            return success
        except Exception as e:
            print(f"Auto-save error: {e}")
            return False

    def handle_parameter_button(self, button_type):
        if button_type == "RUN":
            if self.current_section == "parameters":
                # Auto-save parameters before running if not already saved
                if not self.are_parameters_saved():
                    if not self._auto_save_parameters():
                        self.show_notification("Failed to save parameters. Cannot run test.", error=True)
                        return
                self.show_measurement_screen()
        elif button_type == "CANCEL":
            self.show_test_screen()
        elif button_type == "SAVE":
            self.save_parameters()
        elif button_type == "DELETE":
            if self.current_test_name:  # Check if we have a test selected
                name = self.current_test_name

                def _do_delete():
                    if self.db_manager.delete_test(name):
                        self.show_notification("Test deleted successfully.")
                        self.show_test_screen()
                    else:
                        self.show_notification(f"Could not delete {name}.",
                                               error=True)

                # The app's own Yes/No dialog, not the OS one: the native
                # messagebox drawn by Tk is tiny on the 7" panel and its
                # buttons are not finger-sized (same reason every other
                # confirmation in the app is a CTkToplevel).
                self.show_confirm_dialog(
                    "Delete Test",
                    f"Delete '{name}' and every result recorded for it? "
                    f"This cannot be undone.",
                    on_confirm=_do_delete)
            else:
                self.show_notification("No test selected to delete.", error=True)
