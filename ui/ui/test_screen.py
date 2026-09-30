"""
test_screen.py - List-of-tests screen: pagination, filtering and sorting.

Designed for the instrument's 1280x720 panel:

  row 0  header      - back, title, one-line explanation
  row 1  toolbar     - method filter (TP / EP / Kinetic, which doubles as the
                       colour legend) and the sort direction
  row 2  test grid   - 5 columns x 4 rows = 20 tests per page, big touch buttons
  row 3  pages       - "Page : 1 2 3", only when there is more than one page
  row 4  actions     - Create Test / Edit Test

20 per page is the number that keeps each test button a comfortable 84 px tall
on the panel while still fitting the operator's whole test list in a few pages.
"""

import customtkinter as ctk

from ui.theme import c as tc, card as theme_card, sp, font as theme_font

# Method -> colour (shared with the RESULT screen: tiles, method badge and the
# filter row all read this one table).
#
# The colours are LIGHT TINTS with text in the same hue - blue / red / amber -
# and a border in a mid tone so the tile still reads as a distinct tile against
# the pale window behind it. They used to be saturated fills with white text,
# which turned a full page of tests into a wall of dark blocks on the 7" panel
# ("too dark colour, use light shades").
#
# Every entry carries its own text colour, because one label colour cannot
# serve three tints; call sites read ``colors["text_color"]`` instead of
# assuming white. Built from the palette at call time, so a theme switch
# re-tints the tiles instead of leaving light chips on the black theme.
def method_colors():
    """Tile/badge colours per method, for the theme in force right now."""
    return {
        "TP": {"fg_color": tc("method_tp"), "hover_color": tc("method_tp_hover"),
               "border_color": tc("method_tp_border"),
               "text_color": tc("method_tp_text")},
        "EP": {"fg_color": tc("method_ep"), "hover_color": tc("method_ep_hover"),
               "border_color": tc("method_ep_border"),
               "text_color": tc("method_ep_text")},
        "Kinetic": {"fg_color": tc("method_kinetic"),
                    "hover_color": tc("method_kinetic_hover"),
                    "border_color": tc("method_kinetic_border"),
                    "text_color": tc("method_kinetic_text")},
    }

# 5 columns x 4 rows. See the module docstring for why.
TESTS_PER_PAGE = 20
TESTS_PER_ROW = 5


class TestScreenMixin:
    """TestScreenMixin - List-of-tests screen: pagination, filtering and sorting."""

    def create_test_screen(self):
        self.tests_per_page = TESTS_PER_PAGE

        test_frame = ctk.CTkFrame(self, fg_color=tc("window_bg"), corner_radius=0)
        test_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        test_frame.grid_columnconfigure(0, weight=1)
        test_frame.grid_rowconfigure(2, weight=1)  # the test grid absorbs slack

        # Add variables for sorting and pagination
        if not hasattr(self, 'current_page'):
            self.current_page = 1
        if not hasattr(self, 'sort_method'):
            self.sort_method = None  # None means no method filter
        if not hasattr(self, 'sort_direction'):
            self.sort_direction = "asc"  # Default sort direction

        # Load existing tests from the database
        self.tests = self.db_manager.load_tests()

        # 1. Header
        header_frame = ctk.CTkFrame(test_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=sp(18), pady=(sp(12), sp(4)))
        header_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            header_frame, text="←", width=sp(52), height=sp(46),
            font=theme_font(18, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(10),
            border_width=1, border_color=tc("border"),
            command=self.show_main_menu,
        ).grid(row=0, column=0, sticky="w")

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", padx=sp(14))
        ctk.CTkLabel(title_box, text="LIST OF TESTS", font=theme_font(23, bold=True),
                     text_color=tc("text")).pack(anchor="w")
        ctk.CTkLabel(title_box, text="Tap a test to measure it, or Edit Test to change it",
                     font=theme_font(12), text_color=tc("text_muted")).pack(anchor="w")

        ctk.CTkButton(
            header_frame, text="Create Test", width=sp(150), height=sp(46),
            font=theme_font(15, bold=True),
            fg_color=tc("accent"), hover_color=tc("accent_hover"),
            text_color=tc("text_on_accent"), corner_radius=sp(12),
            command=self.create_new_test,
        ).grid(row=0, column=3, sticky="e")

        # 2. Toolbar: method filter + sort direction
        toolbar = ctk.CTkFrame(test_frame, **theme_card(radius=sp(12)))
        toolbar.grid(row=1, column=0, sticky="ew", padx=sp(18), pady=(sp(2), sp(6)))
        toolbar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(toolbar, text="Filter:", font=theme_font(14, bold=True),
                     text_color=tc("text_muted")).grid(row=0, column=0,
                                                       padx=(sp(14), sp(8)), pady=sp(10))
        for index, (method, colors) in enumerate(method_colors().items()):
            selected = self.sort_method == method
            btn = ctk.CTkButton(
                toolbar, text=method, width=sp(96), height=sp(42),
                font=theme_font(14, bold=True),
                fg_color=colors['fg_color'], hover_color=colors['hover_color'],
                text_color=colors.get('text_color', "white"), corner_radius=sp(10),
                # A tint needs an edge: 1 px normally, a 2 px dark ring when
                # this chip is the active filter.
                border_width=2 if selected else 1,
                border_color=tc("text") if selected else colors['border_color'],
                command=lambda m=method: self.set_method_filter(m))
            btn.grid(row=0, column=index + 1, padx=sp(4), pady=sp(8))

        sort_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        sort_box.grid(row=0, column=4, sticky="e", padx=(sp(10), sp(6)))
        ctk.CTkLabel(sort_box, text="Sort:", font=theme_font(14, bold=True),
                     text_color=tc("text_muted")).pack(side="left", padx=(0, sp(8)))
        for direction, arrow in (("asc", "↑ A-Z"), ("desc", "↓ Z-A")):
            selected = self.sort_direction == direction
            ctk.CTkButton(
                sort_box, text=arrow, width=sp(84), height=sp(42),
                font=theme_font(14, bold=True),
                fg_color=tc("accent") if selected else tc("btn_neutral"),
                hover_color=tc("accent_hover") if selected else tc("btn_neutral_hover"),
                text_color=tc("text_on_accent") if selected else tc("btn_text"),
                corner_radius=sp(10),
                command=lambda d=direction: self.set_sort_direction(d),
            ).pack(side="left", padx=sp(4))

        if self.sort_method is not None or self.sort_direction != "asc":
            ctk.CTkButton(
                toolbar, text="Reset", width=sp(84), height=sp(42),
                font=theme_font(14, bold=True),
                fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
                text_color=tc("btn_text"), corner_radius=sp(10),
                command=self.reset_filters,
            ).grid(row=0, column=5, padx=(sp(4), sp(14)), pady=sp(8))

        # 3. Tests display area
        tests_container = ctk.CTkFrame(test_frame, fg_color="transparent")
        tests_container.grid(row=2, column=0, sticky="nsew", padx=sp(14), pady=0)
        tests_container.grid_columnconfigure(0, weight=1)
        tests_container.grid_rowconfigure(0, weight=1)

        tests_frame = ctk.CTkFrame(tests_container, fg_color="transparent")
        tests_frame.grid(row=0, column=0, sticky="nsew")
        for i in range(TESTS_PER_ROW):
            tests_frame.grid_columnconfigure(i, weight=1, uniform="test")
        for r in range(TESTS_PER_PAGE // TESTS_PER_ROW):
            tests_frame.grid_rowconfigure(r, weight=1, uniform="testrow")

        sorted_tests = self.sort_tests()
        total_pages = max(1, (len(sorted_tests) + self.tests_per_page - 1) // self.tests_per_page)
        if self.current_page > total_pages:
            self.current_page = total_pages
        if self.current_page < 1:
            self.current_page = 1
        self.total_pages = total_pages
        start = (self.current_page - 1) * self.tests_per_page
        page_tests = sorted_tests[start:start + self.tests_per_page]

        if not page_tests:
            ctk.CTkLabel(
                tests_frame,
                text="No tests yet.\nUse Create Test to add the first one.",
                font=theme_font(15), text_color=tc("text_muted"), justify="center",
            ).grid(row=0, column=0, columnspan=TESTS_PER_ROW, pady=sp(40))
        else:
            # One query for the whole page instead of one (two, really) per
            # tile: this loop is the last thing between the tap and the page
            # being visible, and sqlite on the panel is the slow part of it.
            page_methods = self.db_manager.load_methods_map(
                [test['name'] for test in page_tests])
            palette = method_colors()
            for i, test in enumerate(page_tests):
                test_method = page_methods.get(test['name'], 'TP')
                colors = palette.get(test_method, palette['TP'])
                # Single-line label: the method is already the button colour
                # (the toolbar above is the legend), and a second line would
                # make every button taller than the page has room for.
                btn = ctk.CTkButton(
                    tests_frame,
                    text=f"{test['name']}",
                    height=sp(72),
                    corner_radius=sp(12),
                    fg_color=colors['fg_color'],
                    hover_color=colors['hover_color'],
                    text_color=colors.get('text_color', "white"),
                    # 1 px edge in the method's mid tone: what makes a tinted
                    # tile visible as a tile on the pale window background.
                    border_width=1, border_color=colors['border_color'],
                    font=theme_font(15, bold=True),
                    command=lambda name=test['name']: self.handle_test_click(name),
                )
                self.enforce_system_state(btn)
                btn.grid(row=i // TESTS_PER_ROW, column=i % TESTS_PER_ROW,
                         padx=sp(6), pady=sp(6), sticky="nsew")

        # 4. Pages ("Page : 1 2 3" below the grid)
        self.build_page_bar(test_frame, self.current_page, total_pages,
                            self.change_page, row=3)

        # 5. Bottom buttons
        bottom_frame = ctk.CTkFrame(test_frame, fg_color="transparent")
        bottom_frame.grid(row=4, column=0, sticky="ew", padx=sp(18), pady=(sp(2), sp(10)))
        for i in range(2):
            bottom_frame.grid_columnconfigure(i, weight=1, uniform="actions")

        edit_active = getattr(self, 'edit_mode', False)
        ctk.CTkButton(
            bottom_frame, text="Back to menu", height=sp(56),
            font=theme_font(15, bold=True),
            fg_color=tc("btn_neutral"), hover_color=tc("btn_neutral_hover"),
            text_color=tc("btn_text"), corner_radius=sp(12),
            border_width=1, border_color=tc("border"),
            command=self.show_main_menu,
        ).grid(row=0, column=0, sticky="ew", padx=sp(6))

        ctk.CTkButton(
            bottom_frame, text="Edit Test" if not edit_active else "Edit Test (on) - pick a test",
            height=sp(56), font=theme_font(15, bold=True),
            fg_color=tc("warning") if edit_active else tc("btn_neutral"),
            hover_color=tc("warning_hover") if edit_active else tc("btn_neutral_hover"),
            text_color=tc("warning_text") if edit_active else tc("btn_text"),
            corner_radius=sp(12), border_width=1, border_color=tc("border"),
            command=self.enable_edit_mode,
        ).grid(row=0, column=1, sticky="ew", padx=sp(6))

        self.polish_screen(test_frame)
        return test_frame

    # ------------------------------------------------------------------
    # Pagination helpers (shared with the RESULT screen)
    # ------------------------------------------------------------------
    def build_page_bar(self, parent, current_page, total_pages, on_change,
                       row=3, prefix="Page :", pady=(0, 6)):
        """'Page : 1 2 3' button row; empty frame when there is one page only."""
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=sp(18), pady=sp(pady))
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(2, weight=1)
        if total_pages <= 1:
            return bar

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=1)
        ctk.CTkLabel(inner, text=prefix, font=theme_font(14, bold=True),
                     text_color=tc("text_muted")).pack(side="left", padx=(0, sp(10)))

        visible = self.get_visible_page_numbers(current_page, total_pages)
        if visible[0] > 1:
            self._page_button(inner, "1", False, on_change, 1)
            if visible[0] > 2:
                ctk.CTkLabel(inner, text="…", font=theme_font(16, bold=True),
                             text_color=tc("text_muted")).pack(side="left", padx=sp(4))
        for page_num in visible:
            self._page_button(inner, str(page_num), page_num == current_page,
                              on_change, page_num)
        if visible[-1] < total_pages:
            if visible[-1] < total_pages - 1:
                ctk.CTkLabel(inner, text="…", font=theme_font(16, bold=True),
                             text_color=tc("text_muted")).pack(side="left", padx=sp(4))
            self._page_button(inner, str(total_pages), False, on_change, total_pages)
        return bar

    def _page_button(self, parent, text, selected, on_change, page_num):
        btn = ctk.CTkButton(
            parent, text=text, width=sp(52), height=sp(42),
            font=theme_font(15, bold=True),
            fg_color=tc("accent") if selected else tc("btn_neutral"),
            hover_color=tc("accent_hover") if selected else tc("btn_neutral_hover"),
            text_color=tc("text_on_accent") if selected else tc("btn_text"),
            corner_radius=sp(10),
            border_width=0 if selected else 1,
            border_color=tc("border"),
            command=lambda p=page_num: on_change(p),
        )
        btn.pack(side="left", padx=sp(3))
        return btn

    def get_visible_page_numbers(self, current_page, total_pages):
        """Generate a list of page numbers to display in pagination"""
        if total_pages <= 5:
            # If 5 or fewer pages, show all
            return list(range(1, total_pages + 1))

        # Calculate range to display (current page and up to 2 on either side)
        start = max(1, current_page - 2)
        end = min(total_pages, current_page + 2)

        # Adjust range to always show 5 pages when possible
        if end - start + 1 < 5:
            if start == 1:
                end = min(5, total_pages)
            elif end == total_pages:
                start = max(1, total_pages - 4)

        return list(range(start, end + 1))

    # ------------------------------------------------------------------
    # Filter / sort / navigation
    # ------------------------------------------------------------------
    def sort_tests(self):
        """Sort tests according to current filter and sort settings"""
        # Create a copy to avoid modifying the original test list
        sorted_tests = self.tests.copy()

        # If a method filter is applied, prepare for two-tier sorting
        if self.sort_method:
            # Create two lists - one for matching method, one for others
            method_tests = []
            other_tests = []

            # One query for the whole list (this used to be two per test - over
            # a hundred round trips on a full database just to sort a page).
            methods = self.db_manager.load_methods_map(
                [test['name'] for test in sorted_tests])
            # Separate tests into the two lists
            for test in sorted_tests:
                # Get the test's method
                test_method = methods.get(test['name'], 'TP')

                # Add to appropriate list
                if test_method == self.sort_method:
                    method_tests.append(test)
                else:
                    other_tests.append(test)

            # Sort each list by name according to sort direction
            method_tests.sort(key=lambda x: x['name'].lower(), reverse=(self.sort_direction == "desc"))
            other_tests.sort(key=lambda x: x['name'].lower(), reverse=(self.sort_direction == "desc"))

            # Combine the lists - filtered method first, then others
            sorted_tests = method_tests + other_tests
        else:
            # No method filter, sort all tests by name
            sorted_tests.sort(key=lambda x: x['name'].lower(), reverse=(self.sort_direction == "desc"))

        return sorted_tests

    def set_method_filter(self, method):
        """Set the method filter for sorting tests"""
        # Toggle filter if the same method is clicked again
        if self.sort_method == method:
            self.sort_method = None
        else:
            self.sort_method = method

        # Reset to page 1 when changing filters
        self.current_page = 1

        # Refresh the test screen
        self.show_test_screen()

    def set_sort_direction(self, direction):
        """Set the sort direction (asc or desc)"""
        self.sort_direction = direction

        # Refresh the test screen
        self.show_test_screen()

    def reset_filters(self):
        """Reset all filters and sorting to defaults"""
        self.sort_method = None
        self.sort_direction = "asc"
        self.current_page = 1

        # Refresh the test screen
        self.show_test_screen()

    def change_page(self, page_num):
        """Change to the specified page number"""
        self.current_page = page_num

        # Refresh the test screen
        self.show_test_screen()

    def handle_test_click(self, test_name):
        """Handle test button clicks based on edit mode"""
        if hasattr(self, 'edit_mode') and self.edit_mode:
            # In edit mode, clicking opens parameter screen
            self.load_test_parameters(test_name)
        else:
            # In normal mode, clicking goes directly to measurement screen
            self.current_test_name = test_name
            self.show_measurement_screen()

    def enable_edit_mode(self):
        """Enable edit mode and refresh the test screen"""
        self.edit_mode = True
        self.show_test_screen()
