"""
dilution.py - Out-of-range / dilution workflow interface.

Part of the ui package (split from the original monolithic ui.py).
"""

import customtkinter as ctk

from ui.theme import c as tc, sp, font as theme_font


class DilutionMixin:
    """DilutionMixin - Out-of-range / dilution workflow interface."""

    def clear_dilution_message(self):
        """Clear the dilution message from results frame"""
        # Remove any widgets in row 2 (the message overlay)
        for widget in self.results_frame.grid_slaves(row=2):
            widget.destroy()

    def show_out_of_range_message(self):
        """Show out of range message by replacing the results table"""
        print("SHOWING OUT OF RANGE MESSAGE")

        # Clear the entire results frame
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        print("CLEARED RESULTS FRAME")
        # Create message in the same space as results table
        message_label = ctk.CTkLabel(
            self.results_frame,
            text="Result out of range - Dilution needed",
            font=theme_font(12, bold=True),
            text_color=tc("danger"),
            fg_color=tc("danger_soft"),
            corner_radius=6
        )
        message_label.pack(expand=True, fill="both", padx=sp(10), pady=sp(10))

    def show_dilution_interface(self):
        """Show dilution interface by replacing the results table"""
        print("SHOWING DILUTION INTERFACE")

        # Clear the entire results frame
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        # Re-configure grid to match the original table structure EXACTLY
        self.results_frame.grid_rowconfigure(0, weight=1)
        self.results_frame.grid_rowconfigure(1, weight=1)
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_columnconfigure(1, weight=1)
        self.results_frame.grid_columnconfigure(2, weight=1)

        # Create header that spans all columns - matching original table cell style
        header_frame = ctk.CTkFrame(
            self.results_frame,                fg_color=tc("btn_neutral"),
                corner_radius=0,
        )
        header_frame.grid(row=0, column=0, columnspan=5, padx=1, pady=1, sticky="nsew")

        # Show WHY a dilution is needed (the out-of-range value), then the
        # factor buttons the user picks from.
        out_of_range = getattr(self, '_last_out_of_range_value', None)
        header_text = "Choose Dilution Factor"
        if out_of_range not in (None, "-"):
            header_text = f"Result out of range ({out_of_range}) - Choose Dilution Factor"
        # Explicit heights (a CTkLabel otherwise asks for 28 px whatever its
        # font) and a slim button row, so the whole dilution panel fits inside
        # the results band's height. It used to be taller than the band, which
        # grew the band and shrank the graph above it - the plot visibly jumped
        # the moment an out-of-range result came in.
        header_label = ctk.CTkLabel(
            header_frame,
            text=header_text,
            height=sp(20),
            font=theme_font(11, bold=True)
        )
        header_label.pack(expand=True, fill="both", padx=sp(2), pady=sp(1))

        # Create buttons container that spans all columns - matching original table cell style
        buttons_container = ctk.CTkFrame(
            self.results_frame,                fg_color=tc("surface_sunken"),
                corner_radius=0,
        )
        buttons_container.grid(row=1, column=0, columnspan=3, padx=1, pady=1, sticky="nsew")

        # Create a nested frame for buttons to control their layout better
        buttons_inner_frame = ctk.CTkFrame(buttons_container, fg_color="transparent")
        buttons_inner_frame.pack(expand=True, fill="both", padx=3, pady=3)

        # Configure columns for equal spacing within the inner frame
        for i in range(5):
            buttons_inner_frame.grid_columnconfigure(i, weight=1)

        # Dilution factor buttons: finger-sized on the panel (they sit in the
        # results table's own row, so they scale with it).
        factors = [2, 3, 4, 5, 10]
        for i, factor in enumerate(factors):
            btn = ctk.CTkButton(
                buttons_inner_frame,
                text=str(factor),
                width=sp(56),
                height=sp(32),
                font=theme_font(12, bold=True),
                corner_radius=sp(10),
                command=lambda f=factor: self.select_dilution_factor(f)
            )
            btn.grid(row=0, column=i, padx=sp(2), pady=sp(1), sticky="ew")

        # Set dilution mode
        self.dilution_mode_active = True
        self.dilution_factor = None

    def select_dilution_factor(self, factor):
        """Select dilution factor and prepare for re-measurement"""
        self.dilution_factor = factor
        self.dilution_mode_active = True
        print(f"DILUTION FACTOR SELECTED: {factor}, dilution_mode_active: {self.dilution_mode_active}")

        # Clear dilution interface
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        # Show confirmation message in the same space
        confirmation = ctk.CTkLabel(
            self.results_frame,
            text=f"Dilution Factor {factor} Selected\nRun Sample Again",
            font=theme_font(13, bold=True),
            fg_color=tc("success_soft"),
            text_color=tc("accent_text"),
            corner_radius=6
        )
        confirmation.pack(expand=True, fill="both", padx=sp(8), pady=sp(8))

        # Reset out of range flag but KEEP dilution mode active so the next
        # SAMPLE run is scaled by the chosen factor.
        self.result_out_of_range = False

        # Immediately recommend/select SAMPLE for the diluted re-measurement.
        self.selected_button = "SAMPLE"
        if hasattr(self, '_recommend_button'):
            try:
                self._recommend_button("SAMPLE")
                return
            except Exception as e:
                print(f"DILUTION: could not re-highlight SAMPLE: {e}")
        if hasattr(self, 'highlight_button'):
            self.highlight_button("SAMPLE")

    def restore_results_table_after_dilution(self):
        """Restore the results table after dilution measurement"""
        print("RESTORING RESULTS TABLE AFTER DILUTION")

        # Clear current content
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        # Reinitialize the results table
        self.initialize_results_table()

        # If we have stored results, display them
        if hasattr(self, 'last_result_values'):
            self.type_value_label.configure(text=self.last_result_values.get('type', '-'))
            self.result_value_label.configure(text=self.last_result_values.get('result', '-'))
            self.unit_value_label.configure(text=self.last_result_values.get('unit', '-'))

    def reset_dilution_mode(self):
        """
        Simple reset
        """
        print("RESETTING DILUTION MODE")
        self.dilution_mode_active = False
        self.dilution_factor = None
        if hasattr(self, 'result_out_of_range'):
            self.result_out_of_range = False

        # Recreate results table
        if hasattr(self, 'initialize_results_table'):
            self.initialize_results_table()

    def check_result_range(self, result, test_name):
        """True when `result` sits inside the test's Low/High limits.

        Limits are OPTIONAL and each side is independent: a missing/blank side
        is an open bound, and only when BOTH sides are unset (None, blank or 0)
        does the test count as "no range configured" (nothing to compare, so
        the result is accepted).

        NOTE: a Low of 0 with a real High (e.g. Low 0, High 10) IS a range -
        the old implementation treated any 0 as "no range", which silently
        disabled the dilution prompt for the most common lower limit.
        """
        try:
            params = self.db_manager.load_parameters(test_name)
            if not params:
                return True  # no parameters -> cannot judge, accept

            def _num(value):
                if value is None or value == '':
                    return None
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            low_range = _num(params.get('low'))
            high_range = _num(params.get('high'))

            if low_range is None and high_range is None:
                print(f"RANGE CHECK: No range configured (low={params.get('low')!r}, "
                      f"high={params.get('high')!r}) - assuming IN RANGE")
                return True
            if (low_range in (None, 0.0)) and (high_range in (None, 0.0)):
                # Both sides are 0/blank: the test simply has no limits yet.
                print("RANGE CHECK: Limits are unset (0) - assuming IN RANGE")
                return True

            try:
                value = float(result)
            except (TypeError, ValueError):
                print("RANGE CHECK: Result is not numeric - assuming IN RANGE")
                return True

            low_ok = True if low_range is None else (value >= low_range)
            high_ok = True if high_range is None else (value <= high_range)
            in_range = low_ok and high_ok
            bound_text = f"[{low_range if low_range is not None else '-inf'} - " \
                         f"{high_range if high_range is not None else '+inf'}]"
            print(f"RANGE CHECK: {value} is {'IN' if in_range else 'OUT OF'} range {bound_text}")
            return in_range

        except Exception as e:
            print(f"RANGE CHECK: failed ({e}) - assuming IN RANGE")
            return True
