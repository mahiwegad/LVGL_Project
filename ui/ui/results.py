"""
results.py - RESULT screen: test list with date/test-name filters and a
polished, color-coded results table per test.

Part of the ui package (split from the original monolithic ui.py).
"""

import customtkinter as ctk
from datetime import datetime

from ui.controls import TouchSelect
from ui.test_screen import method_colors, TESTS_PER_PAGE, TESTS_PER_ROW
from ui.theme import c as tc, card as theme_card, sp, font as theme_font

RUN_TYPE_LABELS = {
    "WATER": "Water", "BLANK": "Blank", "STD": "Std",
    "SAMPLE": "Sample", "QC1": "QC 1", "QC2": "QC 2", "WASH": "Wash",
}


class ResultsMixin:
    """ResultsMixin - test list + filters + polished results table."""

    # ------------------------------------------------------------------
    # RESULT entry screen: tests + date/test-name filters
    # ------------------------------------------------------------------
    def show_result_screen(self):
        """Result screen: test grid with date + test-name filters.

        Laid out like the test list (same 5 x 4 pages, same page bar) so the two
        "pick a test" screens behave identically.
        """
        self.clear_frames()
        self._screen_rebuild = self.show_result_screen

        result_frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        result_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(2, weight=1)  # tests area expands

        # Filter / pagination state
        if not hasattr(self, 'result_current_page'):
            self.result_current_page = 1
        if not hasattr(self, 'result_test_filter'):
            self.result_test_filter = "All tests"
        if not hasattr(self, 'result_date_filter'):
            self.result_date_filter = "All dates"
        # Same page size as the test list: one page = 5 columns x 4 rows.
        self.results_per_page = TESTS_PER_PAGE
        self.tests_per_page = TESTS_PER_PAGE

        # ---------- Header (row 0) ----------
        header_frame = ctk.CTkFrame(result_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=sp(18), pady=(sp(12), sp(4)))
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(header_frame, text="←", width=sp(52), height=sp(46),
                      font=theme_font(18, bold=True),
                      fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                      text_color=tc("btn_text"), corner_radius=sp(10),
                      border_width=1, border_color=tc("border"),
                      command=self.show_main_menu).grid(row=0, column=0, sticky="w")
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", padx=sp(14))
        ctk.CTkLabel(title_box, text="RESULTS",
                     font=theme_font(23, bold=True),
                     text_color=tc("text")).pack(anchor="w")
        ctk.CTkLabel(title_box, text="Select a test to view its measurement results",
                     font=theme_font(12), text_color=tc("text_muted")).pack(anchor="w")

        # ---------- Filter panel (row 1) ----------
        # Touch-safe pickers instead of the native combobox: its popup is drawn
        # on a canvas and a fingertip cannot reliably hit an item in it.
        filter_frame = ctk.CTkFrame(result_frame, **theme_card(radius=sp(12)))
        filter_frame.grid(row=1, column=0, sticky="ew", padx=sp(18), pady=(sp(2), sp(6)))
        filter_frame.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(filter_frame, text="Filter by Test:",
                     font=theme_font(14, bold=True),
                     text_color=tc("text")).grid(row=0, column=0,
                                                 padx=(sp(14), sp(6)), pady=sp(8))
        all_tests = ["All tests"] + [t['name'] for t in self.db_manager.load_tests()]
        if self.result_test_filter not in all_tests:
            self.result_test_filter = "All tests"
        # TouchSelect, not a native combobox: customtkinter's dropdown draws its
        # options on a canvas, and on the panel's touchscreen the tap that opens
        # it is followed by a synthetic release that lands on - and closes - the
        # list before anything can be chosen. TouchSelect opens a modal grid of
        # full-size buttons instead, so the filter is always one clean tap.
        test_filter = TouchSelect(
            filter_frame, values=all_tests, width=sp(240), height=sp(42),
            title="Filter by test", command=self._on_result_test_filter)
        test_filter.set(self.result_test_filter)
        test_filter.grid(row=0, column=1, padx=sp(5), pady=sp(8))

        ctk.CTkLabel(filter_frame, text="Filter by Date:",
                     font=theme_font(14, bold=True),
                     text_color=tc("text")).grid(row=0, column=2,
                                                 padx=(sp(18), sp(6)), pady=sp(8))
        all_dates = ["All dates"] + self.db_manager.get_result_dates()
        if self.result_date_filter not in all_dates:
            self.result_date_filter = "All dates"
        date_filter = TouchSelect(
            filter_frame, values=all_dates, width=sp(210), height=sp(42),
            title="Filter by date", command=self._on_result_date_filter)
        date_filter.set(self.result_date_filter)
        date_filter.grid(row=0, column=3, padx=sp(5), pady=sp(8))

        if self.result_test_filter != "All tests" or self.result_date_filter != "All dates":
            ctk.CTkButton(filter_frame, text="Clear filters", height=sp(42),
                          font=theme_font(14, bold=True),
                          fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                          text_color=tc("btn_text"), corner_radius=sp(10),
                          command=self.reset_result_filters).grid(
                row=0, column=5, padx=sp(14), pady=sp(8))

        # ---------- Tests grid (row 2) ----------
        tests_container = ctk.CTkFrame(result_frame, fg_color="transparent")
        tests_container.grid(row=2, column=0, sticky="nsew", padx=sp(14), pady=0)
        tests_container.grid_columnconfigure(0, weight=1)
        tests_container.grid_rowconfigure(0, weight=1)

        tests_frame = ctk.CTkFrame(tests_container, fg_color="transparent")
        tests_frame.grid(row=0, column=0, sticky="nsew")
        for i in range(TESTS_PER_ROW):
            tests_frame.grid_columnconfigure(i, weight=1, uniform="rtest")
        for r in range(TESTS_PER_PAGE // TESTS_PER_ROW):
            tests_frame.grid_rowconfigure(r, weight=1, uniform="rtestrow")

        # Which tests to show
        counts = self.db_manager.count_results_by_test()
        if self.result_date_filter != "All dates":
            names = self.db_manager.tests_with_results(date=self.result_date_filter)
        else:
            names = [t['name'] for t in self.db_manager.load_tests()]

        shown_tests = []
        for name in names:
            if self.result_test_filter != "All tests" and name != self.result_test_filter:
                continue
            shown_tests.append({'name': name})

        per_page = self.results_per_page
        total_pages = max(1, (len(shown_tests) + per_page - 1) // per_page)
        if self.result_current_page > total_pages:
            self.result_current_page = total_pages
        start_idx = (self.result_current_page - 1) * per_page
        page_tests = shown_tests[start_idx:start_idx + per_page]

        if not page_tests:
            empty = ctk.CTkLabel(tests_frame, text="No results found.\nRun measurements and they will appear here.",
                                 font=theme_font(15), text_color=tc("text_muted"),
                                 justify="center")
            empty.grid(row=0, column=0, columnspan=TESTS_PER_ROW, pady=sp(40))
        else:
            # One query for the whole page instead of one per tile (see
            # backend.tests.load_methods_map): the page can only be drawn once
            # the tile colours are known.
            page_methods = self.db_manager.load_methods_map(
                [test['name'] for test in page_tests])
            palette = method_colors()
            for i, test in enumerate(page_tests):
                method = page_methods.get(test['name'], 'TP')
                colors = palette.get(method, palette['TP'])
                count = counts.get(test['name'], 0)
                card = ctk.CTkFrame(tests_frame, **theme_card(radius=sp(12)))
                card.grid(row=i // TESTS_PER_ROW, column=i % TESTS_PER_ROW,
                          padx=sp(6), pady=sp(6), sticky="nsew")
                btn = ctk.CTkButton(
                    card, text=test['name'],
                    height=sp(56), corner_radius=sp(11),
                    fg_color=colors['fg_color'], hover_color=colors['hover_color'],
                    text_color=colors.get('text_color', "white"),
                    border_width=1, border_color=colors['border_color'],
                    font=theme_font(14, bold=True),
                    command=lambda n=test['name']: self.select_result_test(n))
                btn.pack(padx=sp(8), pady=(sp(6), sp(2)), fill="x")
                ctk.CTkLabel(card, text=f"{method}  ·  {count} result{'s' if count != 1 else ''}",
                             font=theme_font(11),
                             text_color=tc("text_muted")).pack(pady=(0, sp(4)))

        # ---------- Pagination (row 3): 'Page : 1 2 3' below the grid ----------
        self.build_page_bar(result_frame, self.result_current_page, total_pages,
                            self.change_result_page, row=3)

        # ---------- Bottom buttons (row 4) ----------
        bottom_frame = ctk.CTkFrame(result_frame, fg_color="transparent")
        bottom_frame.grid(row=4, column=0, sticky="ew", padx=sp(18), pady=(sp(2), sp(10)))
        for i in range(5):
            bottom_frame.grid_columnconfigure(i, weight=1, uniform="ractions")
        self.result_buttons = {}
        for i, text in enumerate(["Report", "Parameter", "Std.", "QC", "Com."]):
            btn = ctk.CTkButton(bottom_frame, text=text, height=sp(50),
                                font=theme_font(14, bold=True),
                                fg_color=tc("btn_neutral"),
                                hover_color=tc("btn_neutral_hover"),
                                text_color=tc("btn_text"), corner_radius=sp(10),
                                border_width=1, border_color=tc("border"),
                                command=lambda t=text: self.handle_result_button(t))
            btn.grid(row=0, column=i, padx=sp(6), pady=sp(4), sticky="ew")
            self.result_buttons[text] = btn

        self.frames['result'] = result_frame
        self.polish_screen(result_frame)
        self.qc_mode = False

    # ------------------------------------------------------------------
    # Filters / pagination
    # ------------------------------------------------------------------
    def _on_result_test_filter(self, value):
        self.result_test_filter = value
        self.result_current_page = 1
        self.show_result_screen()

    def _on_result_date_filter(self, value):
        self.result_date_filter = value
        self.result_current_page = 1
        self.show_result_screen()

    def reset_result_filters(self):
        self.result_test_filter = "All tests"
        self.result_date_filter = "All dates"
        self.result_current_page = 1
        self.show_result_screen()

    def change_result_page(self, page):
        self.result_current_page = page
        self.show_result_screen()

    def select_result_test(self, test_name):
        """Handle test selection in result screen."""
        self.current_result_test = test_name
        if getattr(self, 'qc_mode', False):
            self.show_qc_screen(test_name)
        else:
            self.show_test_results(test_name)

    def handle_result_button(self, button_type):
        """Handle result screen bottom-button clicks."""
        if button_type == "QC":
            self.qc_mode = not getattr(self, 'qc_mode', False)
            if self.qc_mode:
                self.result_buttons["QC"].configure(fg_color=tc("accent"),
                                                    hover_color=tc("accent_hover"),
                                                    text_color=tc("text_on_accent"))
                self.show_notification("QC Mode ON - click a test to view its QC data.")
            else:
                self.result_buttons["QC"].configure(fg_color=tc("btn_neutral"),
                                                    hover_color=tc("btn_neutral_hover"),
                                                    text_color=tc("btn_text"))
                self.show_notification("QC Mode OFF.")
        elif button_type == "Report":
            self.show_notification("Report functionality not implemented yet.")
        elif button_type == "Parameter":
            self.show_notification("Parameter functionality not implemented yet.")
        elif button_type == "Std.":
            self.show_notification("Standard functionality not implemented yet.")
        elif button_type == "Com.":
            self.show_notification("Comments functionality not implemented yet.")

    # ------------------------------------------------------------------
    # Full-screen results table for one test
    # ------------------------------------------------------------------
    def show_test_results(self, test_name):
        """Polished full-screen results table for a single test."""
        self.clear_frames()
        self._screen_rebuild = lambda: self.show_test_results(test_name)
        self.current_result_test = test_name

        params = self.db_manager.load_parameters(test_name) or {}
        method = params.get('method', 'TP')
        unit = params.get('unit', '-') or '-'
        high_limit = params.get('high_limit')
        low_limit = params.get('low_limit')
        palette = method_colors()
        colors = palette.get(method, palette['TP'])

        # Detail-view filter state. Entering a NEW test resets the filters and
        # seeds the date from the result list's date filter; re-filtering the
        # same test keeps the current selection.
        if getattr(self, '_detail_for_test', None) != test_name:
            self.detail_date_filter = getattr(self, 'result_date_filter', "All dates")
            self.detail_type_filter = "ALL"
            self._detail_for_test = test_name

        frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)

        # ---------- Header ----------
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=sp(18), pady=(sp(14), sp(6)))
        header.grid_columnconfigure(2, weight=1)
        ctk.CTkButton(header, text="←", width=sp(52), height=sp(46),
                      font=theme_font(18, bold=True),
                      fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                      text_color=tc("btn_text"), corner_radius=sp(10),
                      border_width=1, border_color=tc("border"),
                      command=self.show_result_screen).grid(row=0, column=0, sticky="w")

        badge = ctk.CTkLabel(header, text=method, width=sp(80), height=sp(30),
                             corner_radius=sp(8),
                             fg_color=colors['fg_color'],
                             text_color=colors.get('text_color', "white"),
                             font=theme_font(14, bold=True))
        badge.grid(row=0, column=1, padx=(sp(14), 0))
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=2, sticky="w", padx=sp(12))
        ctk.CTkLabel(title_box, text=test_name,
                     font=theme_font(23, bold=True),
                     text_color=tc("text")).pack(anchor="w")
        ctk.CTkLabel(title_box, text=f"Measurement results · unit: {unit}",
                     font=theme_font(12),
                     text_color=tc("text_muted")).pack(anchor="w")

        # ---------- Detail filters ----------
        filter_bar = ctk.CTkFrame(frame, **theme_card(radius=sp(12)))
        filter_bar.grid(row=1, column=0, sticky="ew", padx=sp(18), pady=(sp(4), sp(8)))
        filter_bar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(filter_bar, text="Date:",
                     font=theme_font(14, bold=True),
                     text_color=tc("text")).grid(row=0, column=0,
                                                 padx=(sp(14), sp(6)), pady=sp(8))
        dates = ["All dates"] + self.db_manager.get_result_dates(test_name)
        if self.detail_date_filter not in dates:
            self.detail_date_filter = "All dates"
        # Same touch-safe picker as the result list's filters (see there).
        date_filter = TouchSelect(filter_bar, values=dates, width=sp(210),
                                  height=sp(42), title="Date",
                                  command=self._on_detail_date_filter)
        date_filter.set(self.detail_date_filter)
        date_filter.grid(row=0, column=1, padx=sp(5), pady=sp(8))

        ctk.CTkLabel(filter_bar, text="Type:",
                     font=theme_font(14, bold=True),
                     text_color=tc("text")).grid(row=0, column=2,
                                                 padx=(sp(18), sp(6)), pady=sp(8))
        type_filter = TouchSelect(
            filter_bar,
            values=["ALL", "WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2"],
            width=sp(180), height=sp(42), title="Type",
            command=self._on_detail_type_filter)
        type_filter.set(self.detail_type_filter)
        type_filter.grid(row=0, column=3, padx=sp(5), pady=sp(8))

        # ---------- Summary cards ----------
        # Stats follow the current Type filter. When showing ALL types, average/
        # min/max across mixed run types is meaningless (water is a raw voltage,
        # samples are absorbances), so default the cards to SAMPLE results when
        # any exist - matching how industry analyzers report run statistics.
        stats_type = self.detail_type_filter
        if stats_type == "ALL":
            sample_rows = self.db_manager.load_test_results(
                test_name, date=self._detail_date_or_none(), run_type="SAMPLE")
            stats_type = "SAMPLE" if sample_rows else "ALL"
        summary = self.db_manager.get_result_summary(
            test_name, date=self._detail_date_or_none(), run_type=stats_type)
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=2, column=0, sticky="ew", padx=sp(18), pady=(0, sp(8)))
        for i in range(5):
            cards_frame.grid_columnconfigure(i, weight=1, uniform="rcards")

        # Soft chip colours are theme-aware through the dark remap (polish_tree).
        card_defs = [
            ("Total Results", summary['count'], "#EFF6FF", "#1D4ED8"),
            ("Latest", summary['latest'], "#F0FDF4", "#15803D"),
            ("Average", summary['average'], "#FEFCE8", "#A16207"),
            ("Minimum", summary['minimum'], "#FFF7ED", "#C2410C"),
            ("Maximum", summary['maximum'], "#FDF2F8", "#BE185D"),
        ]
        for i, (label, value, bg, fg) in enumerate(card_defs):
            card = ctk.CTkFrame(cards_frame, fg_color=bg, corner_radius=sp(12))
            card.grid(row=0, column=i, padx=sp(5), sticky="ew")
            ctk.CTkLabel(card, text=label, font=theme_font(12, bold=True),
                         text_color=fg).pack(pady=(sp(8), 0))
            value_text = "—" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))
            ctk.CTkLabel(card, text=value_text, font=theme_font(22, bold=True),
                         text_color=tc("text")).pack(pady=(0, sp(8)))

        scope_label = "SAMPLE results" if stats_type == "SAMPLE" else "all run types"
        ctk.CTkLabel(cards_frame, text=f"Statistics computed over {scope_label} (change the Type filter to see per-type stats)",
                     font=theme_font(11), text_color=tc("text_faint")).grid(
            row=1, column=0, columnspan=5, sticky="w", padx=sp(5), pady=(0, sp(4)))

        # ---------- Results table ----------
        table_wrap = ctk.CTkFrame(frame, fg_color=tc("surface"), corner_radius=sp(12),
                                  border_width=1, border_color=tc("border"))
        table_wrap.grid(row=3, column=0, sticky="nsew", padx=sp(18), pady=(0, sp(14)))
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(1, weight=1)

        # Header row: Type | Abs | Result | Unit | Date & Time
        head = ctk.CTkFrame(table_wrap, fg_color="#1E293B", corner_radius=0)
        head.grid(row=0, column=0, sticky="ew")
        for col in range(5):
            head.grid_columnconfigure(col, weight=1)
        for col, text in enumerate(["Type", "Abs", "Result", "Unit", "Date & Time"]):
            ctk.CTkLabel(head, text=text, font=theme_font(14, bold=True),
                         text_color="white").grid(row=0, column=col, padx=sp(10),
                                                  pady=sp(8), sticky="w")

        # Scrollable body
        body = ctk.CTkScrollableFrame(table_wrap, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        for col in range(5):
            body.grid_columnconfigure(col, weight=1)

        rows = self.db_manager.load_test_results(
            test_name, date=self._detail_date_or_none(), run_type=self.detail_type_filter)

        # Per-day sample numbering: Sample 1, Sample 2, ... per test per day
        # (rows come newest-first, so walk backwards to count chronologically).
        sample_nums = {}
        day_counters = {}
        for i in range(len(rows) - 1, -1, -1):
            if str(rows[i][0]).upper() == "SAMPLE":
                day = str(rows[i][3] or "")[:10]
                day_counters[day] = day_counters.get(day, 0) + 1
                sample_nums[i] = day_counters[day]

        if not rows:
            ctk.CTkLabel(body, text="No results for the current filters.",
                         font=theme_font(15), text_color=tc("text_muted")).grid(
                row=0, column=0, columnspan=5, pady=sp(40))
        else:
            for i, (run_type, result_value, row_unit, created_at, abs_value) in enumerate(rows):
                bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                row_frame = ctk.CTkFrame(body, fg_color=bg, corner_radius=0, height=sp(48))
                row_frame.grid(row=i, column=0, columnspan=5, sticky="ew", pady=1)
                for col in range(5):
                    row_frame.grid_columnconfigure(col, weight=1)

                # Type chip (method-coloured). SAMPLE rows are numbered per
                # day (Sample 1, Sample 2, ...) matching the measurement screen.
                upper_type = str(run_type).upper()
                label = RUN_TYPE_LABELS.get(upper_type, str(run_type))
                if upper_type == "SAMPLE":
                    label = f"Sample {sample_nums.get(i, '')}".strip()
                chip_bg = {"WATER": "#E0F2FE", "BLANK": "#FEF9C3", "STD": "#F3E8FF",
                           "SAMPLE": "#DCFCE7", "QC1": "#FCE7F3", "QC2": "#FCE7F3"}.get(
                    upper_type, "#E2E8F0")
                chip = ctk.CTkLabel(row_frame, text=label, width=sp(96),
                                    height=sp(30), corner_radius=sp(8),
                                    fg_color=chip_bg, text_color="#334155",
                                    font=theme_font(13, bold=True))
                chip.grid(row=0, column=0, padx=sp(10), pady=sp(6), sticky="w")

                # Abs column: the run's AVERAGE absorbance (blank/std/sample),
                # "—" for water and QC runs which have no absorbance.
                try:
                    av = float(abs_value)
                    abs_text = f"{av:.3f}"
                    abs_fg, abs_bg = "#334155", "#F1F5F9"
                except (TypeError, ValueError):
                    abs_text = "—"
                    abs_fg, abs_bg = "#94A3B8", "#F1F5F9"
                ctk.CTkLabel(row_frame, text=abs_text, width=sp(104),
                             height=sp(30), corner_radius=sp(8),
                             fg_color=abs_bg, text_color=abs_fg,
                             font=theme_font(14, bold=True)).grid(
                    row=0, column=1, padx=sp(10), pady=sp(6), sticky="w")

                # Result column: std -> user-input concentration, sample ->
                # calculated concentration, water -> raw reference. Colour coded
                # against high/low limits. Falsy limits mean no range configured.
                try:
                    rv = float(result_value)
                    if high_limit and low_limit:
                        in_range = low_limit <= rv <= high_limit
                        val_fg, val_bg = ("#166534", "#DCFCE7") if in_range else ("#B91C1C", "#FEE2E2")
                    else:
                        val_fg, val_bg = "#0F172A", "#F1F5F9"
                    val_text = f"{rv:.3f}"
                except (TypeError, ValueError):
                    val_fg, val_bg = "#0F172A", "#F1F5F9"
                    val_text = str(result_value) if result_value is not None else "—"
                ctk.CTkLabel(row_frame, text=val_text, width=sp(150),
                             height=sp(32), corner_radius=sp(8),
                             fg_color=val_bg, text_color=val_fg,
                             font=theme_font(16, bold=True)).grid(
                    row=0, column=2, padx=sp(10), pady=sp(6), sticky="w")

                ctk.CTkLabel(row_frame, text=str(row_unit) if row_unit else "-",
                             font=theme_font(13),
                             text_color=tc("text_muted")).grid(
                    row=0, column=3, padx=sp(10), sticky="w")
                created = str(created_at) if created_at else "—"
                try:
                    created = datetime.strptime(created[:19], '%Y-%m-%d %H:%M:%S').strftime('%d %b %Y, %H:%M')
                except ValueError:
                    pass
                ctk.CTkLabel(row_frame, text=created, font=theme_font(13),
                             text_color=tc("text_muted")).grid(row=0, column=4,
                                                                padx=sp(10), sticky="w")

        self.frames['result_detail'] = frame
        self.polish_screen(frame)

    def _detail_date_or_none(self):
        d = getattr(self, 'detail_date_filter', "All dates")
        return None if d == "All dates" else d

    def _on_detail_date_filter(self, value):
        self.detail_date_filter = value
        self.show_test_results(self.current_result_test)

    def _on_detail_type_filter(self, value):
        self.detail_type_filter = value
        self.show_test_results(self.current_result_test)


