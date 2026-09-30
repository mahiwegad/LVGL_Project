"""
qc.py - Quality-control screens: Levey-Jennings charts, Westgard rules and QC data tables.

Part of the ui package (split from the original monolithic ui.py).
"""

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta

from ui.theme import (
    remap_figure as theme_remap_figure,
    c as tc,
    sp,
    font as theme_font,
)

# matplotlib imported lazily in show_qc_screen to speed up startup
plt = None
FigureCanvasTkAgg = None

class QCMixin:
    """QCMixin - Quality-control screens: Levey-Jennings charts, Westgard rules and QC data tables."""

    def show_qc_screen(self, test_name):
        """Show QC chart and data for a test - Optimized for Raspberry Pi"""
        global plt, FigureCanvasTkAgg
        if plt is None:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        # Clear previous frames
        self.clear_frames()
        self._screen_rebuild = lambda: self.show_qc_screen(test_name)

        # Create main frame with adjusted sizing for RPi
        qc_frame = ctk.CTkFrame(self)
        qc_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Configure grid weights for proper scaling
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        qc_frame.grid_rowconfigure(1, weight=1)  # Content area gets most space
        qc_frame.grid_columnconfigure(0, weight=1)

        # Header with back button and title (sized for the 7" panel)
        header_frame = ctk.CTkFrame(qc_frame, fg_color="transparent", height=sp(58))
        header_frame.grid(row=0, column=0, sticky="ew", padx=sp(14), pady=sp(8))
        header_frame.grid_propagate(False)  # Prevent shrinking

        back_btn = ctk.CTkButton(header_frame, text="←", width=sp(52), height=sp(46),
                                 font=theme_font(18, bold=True),
                                 fg_color=tc("btn_neutral"),
                                 hover_color=tc("btn_neutral_hover"),
                                 text_color=tc("btn_text"), corner_radius=sp(10),
                                 border_width=1, border_color=tc("border"),
                                 command=self.show_result_screen)
        back_btn.pack(side="left", padx=sp(4))

        title = ctk.CTkLabel(header_frame, text=f"QC: {test_name}",
                             font=theme_font(22, bold=True),
                             text_color=tc("text"))
        title.pack(side="left", padx=sp(12))

        # Initialize QC state variables if not already set
        if not hasattr(self, 'current_qc'):
            self.current_qc = 1
        if not hasattr(self, 'current_qc_view'):
            self.current_qc_view = 'chart'
        if not hasattr(self, 'current_qc_month'):
            self.current_qc_month = 0

        # Content area for chart/data - Optimized for RPi screen
        content_frame = ctk.CTkFrame(qc_frame)
        content_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)

        # Create both chart and data frames
        self.qc_chart_frame = self.create_qc_chart_frame(content_frame, test_name)
        self.qc_data_frame = self.create_qc_data_frame(content_frame, test_name)

        # Show the appropriate one based on current view
        if self.current_qc_view == 'chart':
            self.qc_chart_frame.grid(row=0, column=0, sticky="nsew")
            self.qc_data_frame.grid_remove()
        else:
            self.qc_data_frame.grid(row=0, column=0, sticky="nsew")
            self.qc_chart_frame.grid_remove()

        # Bottom buttons - Made more compact for RPi
        button_frame = ctk.CTkFrame(qc_frame, height=sp(62))
        button_frame.grid(row=2, column=0, sticky="ew", padx=sp(14), pady=sp(6))
        button_frame.grid_propagate(False)

        # Create buttons with equal spacing
        for i in range(4):
            button_frame.grid_columnconfigure(i, weight=1, uniform="qcbtn")

        _qc_btn = dict(height=sp(48), font=theme_font(14, bold=True),
                       corner_radius=sp(10))
        chart_btn = ctk.CTkButton(
            button_frame, text="Chart", command=self.show_qc_chart,
            fg_color="#3498db", **_qc_btn
        )
        chart_btn.grid(row=0, column=0, padx=sp(3), pady=sp(5), sticky="ew")

        data_btn = ctk.CTkButton(
            button_frame, text="Data", command=self.show_qc_data,
            fg_color="#3498db", **_qc_btn
        )
        data_btn.grid(row=0, column=1, padx=sp(3), pady=sp(5), sticky="ew")

        print_btn = ctk.CTkButton(
            button_frame, text="Print", command=self.print_qc_report, **_qc_btn
        )
        print_btn.grid(row=0, column=2, padx=sp(3), pady=sp(5), sticky="ew")

        switch_btn = ctk.CTkButton(
            button_frame, text="Switch",
            command=self.switch_qc_data, **_qc_btn
        )
        switch_btn.grid(row=0, column=3, padx=sp(3), pady=sp(5), sticky="ew")

        self.frames['qc'] = qc_frame
        self.polish_screen(qc_frame)

    def create_qc_chart_frame(self, parent, test_name):
        """Create Levey-Jennings chart optimized for Raspberry Pi display"""
        chart_frame = ctk.CTkFrame(parent)
        chart_frame.grid_rowconfigure(0, weight=1)
        chart_frame.grid_columnconfigure(0, weight=1)

        try:
            # Get QC parameters
            qc_params = self.db_manager.load_qc_values(test_name)
            if not qc_params:
                message = ctk.CTkLabel(
                    chart_frame, text="No QC parameters set.\nPlease set QC parameters first.",
                    font=theme_font(15)
                )
                message.grid(row=0, column=0, sticky="nsew")
                return chart_frame

            # Get QC results - one entry per QC RUN (created_at, value, abs)
            qc_results = self.db_manager.get_qc_series(
                test_name, self.current_qc, self.current_qc_month
            )

            # Get mean and SD from parameters
            if self.current_qc == 1:
                mean = qc_params.get('qc1_mean', 0.0) or 0.0
                sd = qc_params.get('qc1_sd', 1.0) or 1.0
                label = qc_params.get('qc1_label', f'QC{self.current_qc}') or f'QC{self.current_qc}'
            else:
                mean = qc_params.get('qc2_mean', 0.0) or 0.0
                sd = qc_params.get('qc2_sd', 1.0) or 1.0
                label = qc_params.get('qc2_label', f'QC{self.current_qc}') or f'QC{self.current_qc}'

            # Create matplotlib figure optimized for RPi screen
            fig = plt.Figure(figsize=(8, 5), dpi=80)  # Reduced size and DPI for RPi
            ax = fig.add_subplot(111)

            # Adjust margins for RPi screen
            fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.15)

            # Set professional colors
            fig.patch.set_facecolor('#F8F9FA')
            ax.set_facecolor('white')

            # Set y-axis limits
            y_range = max(6 * sd, 1.0)
            y_min = mean - y_range / 2
            y_max = mean + y_range / 2
            ax.set_ylim(y_min, y_max)

            # Plot control lines with better visibility for RPi
            ax.axhline(y=mean, color='#2E8B57', linestyle='-', linewidth=2.5, label='Mean')
            ax.axhline(y=mean + sd, color='#4169E1', linestyle='--', linewidth=2, alpha=0.9)
            ax.axhline(y=mean - sd, color='#4169E1', linestyle='--', linewidth=2, alpha=0.9)
            ax.axhline(y=mean + 2 * sd, color='#FF8C00', linestyle='--', linewidth=2, alpha=0.9)
            ax.axhline(y=mean - 2 * sd, color='#FF8C00', linestyle='--', linewidth=2, alpha=0.9)
            ax.axhline(y=mean + 3 * sd, color='#DC143C', linestyle='-', linewidth=2.5, alpha=0.9)
            ax.axhline(y=mean - 3 * sd, color='#DC143C', linestyle='-', linewidth=2.5, alpha=0.9)

            # Add shaded regions
            ax.fill_between([-1, 50], mean - sd, mean + sd, alpha=0.15, color='green')
            ax.fill_between([-1, 50], mean - 2 * sd, mean - sd, alpha=0.1, color='yellow')
            ax.fill_between([-1, 50], mean + sd, mean + 2 * sd, alpha=0.1, color='yellow')
            ax.fill_between([-1, 50], mean - 3 * sd, mean - 2 * sd, alpha=0.15, color='red')
            ax.fill_between([-1, 50], mean + 2 * sd, mean + 3 * sd, alpha=0.15, color='red')

            # Add SD labels optimized for RPi
            sd_labels = [
                (mean + 3 * sd, '+3SD', '#DC143C'),
                (mean + 2 * sd, '+2SD', '#FF8C00'),
                (mean + sd, '+1SD', '#4169E1'),
                (mean, 'Mean', '#2E8B57'),
                (mean - sd, '-1SD', '#4169E1'),
                (mean - 2 * sd, '-2SD', '#FF8C00'),
                (mean - 3 * sd, '-3SD', '#DC143C')
            ]

            for y_pos, text, color in sd_labels:
                if y_min <= y_pos <= y_max:
                    ax.text(0.98, y_pos, text, transform=ax.get_yaxis_transform(),
                        ha='right', va='center', fontsize=10, color=color,
                        weight='bold', bbox=dict(boxstyle='round,pad=0.3',
                                                 facecolor='white', alpha=0.9, edgecolor=color))


            # Plot QC results with enhanced visibility
            if qc_results:
                dates = self._qc_labels([r[0] for r in qc_results])
                values = [r[1] for r in qc_results]

                westgard_violations = self.check_westgard_rules(values, mean, sd)

                # Draw connecting line
                ax.plot(range(len(dates)), values, '-', color='#2E8B57',
                        linewidth=1.5, alpha=0.6)

                # Plot points with larger size for RPi visibility
                for i, value in enumerate(values):
                    violation_type = westgard_violations.get(i, None)

                    if violation_type:
                        if '3s' in violation_type or 'R4s' in violation_type:
                            color = '#DC143C'
                            marker_size = 150
                        elif '2s' in violation_type or 'trend' in violation_type.lower():
                            color = '#FF8C00'
                            marker_size = 130
                        else:
                            color = '#FFD700'
                            marker_size = 120
                    else:
                        if abs(value - mean) > 3 * sd:
                            color = '#DC143C'
                            marker_size = 150
                        elif abs(value - mean) > 2 * sd:
                            color = '#FF8C00'
                            marker_size = 130
                        else:
                            color = '#2E8B57'
                            marker_size = 120

                    ax.scatter(i, value, s=marker_size, color=color, edgecolor='white',
                               linewidth=3, zorder=10)

                # Set x-axis with readable labels for RPi
                if len(dates) > 10:
                    # Show every nth date to avoid crowding on small screen
                    step = max(1, len(dates) // 8)
                    tick_positions = range(0, len(dates), step)
                    tick_labels = [dates[i] for i in tick_positions]
                    ax.set_xticks(tick_positions)
                    ax.set_xticklabels(tick_labels, rotation=0, ha='right', fontsize=11)
                else:
                    ax.set_xticks(range(len(dates)))
                    ax.set_xticklabels(dates, rotation=0, ha='right', fontsize=11)
                ax.set_xlim(-0.5, len(dates) - 0.5)
            else:
                ax.set_xlim(0, 30)
                ax.text(0.5, 0.5, 'No QC data available', ha='center', va='center',
                        transform=ax.transAxes, fontsize=16, color='gray', weight='bold')

            # Style improvements for RPi
            ax.grid(True, alpha=0.4, linestyle=':')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#CCCCCC')
            ax.spines['bottom'].set_color('#CCCCCC')

            # Larger fonts for RPi readability
            ax.set_title(f'Levey-Jennings Chart - QC{self.current_qc}',
                         fontsize=16, fontweight='bold', color='#2C3E50', pad=15)
            ax.set_ylabel('Control Values', fontsize=13, color='#2C3E50')
            ax.set_xlabel('Date', fontsize=13, color='#2C3E50')

            # Adjust tick label sizes
            ax.tick_params(axis='both', which='major', labelsize=12)

            # Information box positioned better for RPi
            cv_percent = (sd / mean * 100) if mean != 0 else 0
            info_text = f'Target: {mean:.2f}±{sd:.2f}\nCV: {cv_percent:.1f}%\nQC{self.current_qc}'
            ax.text(0.02, 0.98, info_text, transform=ax.transAxes, fontsize=11,
                    verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5',
                                                      facecolor='lightblue', alpha=0.9))


            # The chart keeps a fixed "lab report" palette; in dark mode the
            # figure is remapped so it does not sit as a white block on the
            # dark screen. (No-op in light mode.)
            try:
                theme_remap_figure(fig)
            except Exception as theme_err:
                print(f"[THEME] QC chart theme skipped: {theme_err}")

            # Create canvas with proper sizing for RPi
            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            canvas.draw()
            canvas_widget = canvas.get_tk_widget()
            canvas_widget.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

            # Add month navigation if needed
            month_count = self.db_manager.get_qc_month_count(test_name, self.current_qc)
            if month_count > 1:
                nav_frame = ctk.CTkFrame(chart_frame, height=40)
                nav_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
                nav_frame.grid_propagate(False)

                prev_btn = ctk.CTkButton(
                    nav_frame, text="◀ Prev", command=self.prev_qc_month,
                    width=80, height=30,
                    state="disabled" if self.current_qc_month >= month_count - 1 else "normal"
                )
                prev_btn.pack(side="left", padx=5, pady=5)

                month_label = ctk.CTkLabel(
                    nav_frame, text=f"Month {month_count - self.current_qc_month}/{month_count}",
                    font=ctk.CTkFont(size=12)
                )
                month_label.pack(side="left", expand=True)

                next_btn = ctk.CTkButton(
                    nav_frame, text="Next ▶", command=self.next_qc_month,
                    width=80, height=30,
                    state="disabled" if self.current_qc_month <= 0 else "normal"
                )
                next_btn.pack(side="right", padx=5, pady=5)

        except Exception as e:
            print(f"Error in create_qc_chart_frame_rpi: {e}")
            error_label = ctk.CTkLabel(
                chart_frame, text=f"Chart Error: {str(e)[:50]}...",
                text_color="red", font=ctk.CTkFont(size=12)
            )
            error_label.grid(row=0, column=0, sticky="nsew")

        return chart_frame

    @staticmethod
    def _qc_labels(timestamps):
        """Chart/table labels for QC runs, aligned with the caller's list.

        An entry is MM/DD when that day has a single QC run, and MM/DD HH:MM
        when several runs share the same day (so each point stays readable).
        """
        parsed = []
        days = []
        for ts in timestamps:
            text = str(ts or '')
            dt = None
            for fmt, size in (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d', 10)):
                try:
                    dt = datetime.strptime(text[:size], fmt)
                    break
                except ValueError:
                    continue
            parsed.append(dt)
            days.append(dt.strftime('%Y-%m-%d') if dt else text[:10])

        counts = {}
        for day in days:
            counts[day] = counts.get(day, 0) + 1

        labels = []
        for dt, day in zip(parsed, days):
            if dt is None:
                labels.append(day or '-')
            elif counts.get(day, 0) > 1:
                labels.append(dt.strftime('%m/%d %H:%M'))
            else:
                labels.append(dt.strftime('%m/%d'))
        return labels

    def check_westgard_rules(self, values, mean, sd):
        """
        Check Westgard multi-rules for QC violations
        Returns dictionary with index as key and violation type as value
        """
        violations = {}
        n = len(values)

        if n < 2:
            return violations

        for i in range(n):
            current_value = values[i]
            sd_from_mean = (current_value - mean) / sd if sd != 0 else 0

            # 1-3s rule: One control result exceeds ±3s
            if abs(sd_from_mean) > 3:
                violations[i] = "1-3s rule violation"
                continue

            # 2-2s rule: Two consecutive control results exceed +2s or -2s
            if i > 0:
                prev_sd = (values[i - 1] - mean) / sd if sd != 0 else 0
                if (sd_from_mean > 2 and prev_sd > 2) or (sd_from_mean < -2 and prev_sd < -2):
                    violations[i] = "2-2s rule violation"
                    violations[i - 1] = "2-2s rule violation"

            # R-4s rule: One control exceeds +2s and another exceeds -2s (range > 4s)
            if i > 0:
                prev_sd = (values[i - 1] - mean) / sd if sd != 0 else 0
                if (sd_from_mean > 2 and prev_sd < -2) or (sd_from_mean < -2 and prev_sd > 2):
                    violations[i] = "R-4s rule violation"
                    violations[i - 1] = "R-4s rule violation"

            # 4-1s rule: Four consecutive controls exceed +1s or -1s
            if i >= 3:
                last_four_sds = [(values[j] - mean) / sd for j in range(i - 3, i + 1)] if sd != 0 else [0] * 4
                if all(x > 1 for x in last_four_sds) or all(x < -1 for x in last_four_sds):
                    for j in range(i - 3, i + 1):
                        violations[j] = "4-1s rule violation"

            # 10x rule: Ten consecutive controls on same side of mean
            if i >= 9:
                last_ten = values[i - 9:i + 1]
                last_ten_sides = [(v - mean) > 0 for v in last_ten]
                if all(last_ten_sides) or not any(last_ten_sides):
                    for j in range(i - 9, i + 1):
                        violations[j] = "10x rule violation"

        return violations

    def create_qc_data_frame(self, parent, test_name):
        """Create QC data table optimized for Raspberry Pi display with industry standard functionality"""
        data_frame = ctk.CTkFrame(parent)
        data_frame.grid_rowconfigure(2, weight=1)  # Table area gets most space
        data_frame.grid_columnconfigure(0, weight=1)

        # Get QC parameters
        qc_params = self.db_manager.load_qc_values(test_name)

        # Compact header for RPi
        header_frame = ctk.CTkFrame(data_frame, fg_color="transparent", height=sp(42))
        header_frame.grid(row=0, column=0, sticky="ew", padx=sp(8), pady=sp(2))
        header_frame.grid_propagate(False)

        header_label = ctk.CTkLabel(
            header_frame, text=f"QC{self.current_qc} Data",
            font=theme_font(17, bold=True), text_color="#1E3A8A"
        )
        header_label.pack(side="left", padx=sp(10))

        # Get current QC target values (industry standard logic)
        if self.current_qc == 1:
            target_mean = qc_params.get('qc1_mean', 0) if qc_params else 0
            target_sd = qc_params.get('qc1_sd', 0) if qc_params else 0
            target_label = qc_params.get('qc1_label', '') if qc_params else ''
        else:
            target_mean = qc_params.get('qc2_mean', 0) if qc_params else 0
            target_sd = qc_params.get('qc2_sd', 0) if qc_params else 0
            target_label = qc_params.get('qc2_label', '') if qc_params else ''

        # Handle None values properly
        if target_mean is None:
            target_mean = 0.0
        if target_sd is None:
            target_sd = 1.0  # Default to 1 to prevent division by zero

        # Calculate target CV (industry standard)
        target_cv = (target_sd / target_mean * 100) if target_mean != 0 else 0

        # Compact target info for RPi with CV
        target_info = ctk.CTkLabel(
            header_frame, text=f"Target: {target_mean:.2f}±{target_sd:.2f} (CV:{target_cv:.1f}%)",
            font=theme_font(12), text_color="#4B5563"
        )
        target_info.pack(side="right", padx=10)

        # Initialize pagination
        if not hasattr(self, 'qc_data_page'):
            self.qc_data_page = 1

        items_per_page = 8  # Reduced for RPi screen

        # Get results - one entry per QC run: (created_at, value, abs)
        all_results = self.db_manager.get_qc_series(
            test_name, self.current_qc, self.current_qc_month
        )
        result_labels = self._qc_labels([r[0] for r in all_results])

        total_pages = max(1, (len(all_results) + items_per_page - 1) // items_per_page)
        if self.qc_data_page > total_pages:
            self.qc_data_page = total_pages

        start_idx = (self.qc_data_page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(all_results))
        page_results = all_results[start_idx:end_idx]

        # Create compact table for RPi
        table_frame = ctk.CTkFrame(data_frame, fg_color="#F9FAFB")
        table_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        table_frame.grid_rowconfigure(1, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Compact header row with industry standard columns
        header_row = ctk.CTkFrame(table_frame, fg_color="#E5E7EB", height=sp(40))
        header_row.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        header_row.grid_propagate(False)

        # Industry standard headers optimized for RPi (Abs = the run's
        # absorbance, stored alongside every QC concentration)
        headers = ["Date", "Result", "Abs", "SD from Mean", "Status", "Rule"]
        header_widths = [70, 60, 60, 60, 55, 50]

        for i, (header, width) in enumerate(zip(headers, header_widths)):
            header_row.grid_columnconfigure(i, weight=1, minsize=width)
            label = ctk.CTkLabel(
                header_row, text=header, font=theme_font(12, bold=True),
                text_color="#1F2937"
            )
            label.grid(row=0, column=i, padx=2, pady=5, sticky="ew")

        # Scrollable data area
        data_container = ctk.CTkFrame(table_frame, fg_color="#F9FAFB")
        data_container.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)

        if page_results:
            # Get all values for Westgard rule checking (industry standard)
            all_values = [r[1] for r in all_results]
            westgard_violations = self.check_westgard_rules(all_values, target_mean, target_sd)

            for i, qc_row in enumerate(page_results):
                date, value = qc_row[0], qc_row[1]
                qc_abs = qc_row[2] if len(qc_row) > 2 else None
                row_color = "#F3F4F6" if i % 2 == 0 else "#FFFFFF"
                row_frame = ctk.CTkFrame(data_container, fg_color=row_color, height=sp(38))
                row_frame.grid(row=i, column=0, sticky="ew", padx=1, pady=1)
                data_container.grid_columnconfigure(0, weight=1)
                row_frame.pack_propagate(False)

                # Configure grid for equal spacing
                # Configure grid for equal spacing with minimum widths
                header_widths = [55, 65, 75, 60, 50, 45]  # Same as headers
                for col, width in enumerate(header_widths):
                    row_frame.grid_columnconfigure(col, weight=1, minsize=width)

                # Format data for RPi display
                actual_index = start_idx + i
                display_date = (result_labels[actual_index]
                                if actual_index < len(result_labels)
                                else str(date)[:10])
                formatted_result = f"{value:.2f}" if isinstance(value, (int, float)) else "-"
                try:
                    formatted_abs = f"{float(qc_abs):.3f}"
                except (TypeError, ValueError):
                    formatted_abs = " - "

                # Calculate SD from mean (Industry Standard)
                if target_sd != 0:
                    sd_from_mean = (value - target_mean) / target_sd
                else:
                    sd_from_mean = 0
                formatted_sd_from_mean = f"{sd_from_mean:+.1f}"  # Compact format for RPi

                # Determine status and rule violation (industry standard logic)
                violation = westgard_violations.get(actual_index, None)

                if violation:
                    if '3s' in violation or 'R4s' in violation:
                        status = "Unregulated"
                        status_color = "#DC2626"  # Red
                        rule_text = violation.split()[0]  # Get rule name
                    elif '2s' in violation or '4-1s' in violation or '10x' in violation:
                        status = "Warning"
                        status_color = "#F59E0B"  # Amber
                        rule_text = violation.split()[0]  # Get rule name
                    else:
                        status = "Review"
                        status_color = "#8B5CF6"  # Purple
                        rule_text = violation.split()[0]  # Get rule name
                else:
                    # Standard rules
                    if abs(sd_from_mean) > 3:
                        status = "Unregulated"
                        status_color = "#DC2626"  # Red
                        rule_text = "1-3s"
                    elif abs(sd_from_mean) > 2:
                        status = "Warning"
                        status_color = "#F59E0B"  # Amber
                        rule_text = "1-2s"
                    else:
                        status = "OK"
                        status_color = "#10B981"  # Green
                        rule_text = "OK"

                # SD from mean color coding
                sd_color = "#374151"
                if abs(sd_from_mean) > 3:
                    sd_color = "#DC2626"
                elif abs(sd_from_mean) > 2:
                    sd_color = "#F59E0B"
                elif abs(sd_from_mean) > 1:
                    sd_color = "#0891B2"

                # 12 pt cells: the panel has room, and 8-9 pt was unreadable.
                ctk.CTkLabel(row_frame, text=display_date, text_color="#374151",
                            font=theme_font(12)).grid(row=0, column=0, padx=1, pady=3, sticky="ew")

                ctk.CTkLabel(row_frame, text=formatted_result, text_color="#374151",
                            font=theme_font(12)).grid(row=0, column=1, padx=1, pady=3, sticky="ew")

                ctk.CTkLabel(row_frame, text=formatted_abs, text_color="#374151",
                            font=theme_font(12)).grid(row=0, column=2, padx=1, pady=3, sticky="ew")

                ctk.CTkLabel(row_frame, text=formatted_sd_from_mean, text_color=sd_color,
                            font=theme_font(12)).grid(row=0, column=3, padx=1, pady=3, sticky="ew")

                ctk.CTkLabel(row_frame, text=status, text_color=status_color,
                            font=theme_font(12, bold=True)).grid(row=0, column=4, padx=1, pady=3, sticky="ew")

                ctk.CTkLabel(row_frame, text=rule_text, text_color=status_color,
                            font=theme_font(12, bold=True)).grid(row=0, column=5, padx=1, pady=3, sticky="ew")
        else:
            no_data = ctk.CTkLabel(
                data_container, text="No QC data available",
                font=theme_font(14), text_color="#9CA3AF"
            )
            no_data.pack(pady=30)

        # Compact pagination for RPi
        if total_pages > 1:
            pagination_frame = ctk.CTkFrame(data_frame, height=40)
            pagination_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=2)
            pagination_frame.grid_propagate(False)

            prev_btn = ctk.CTkButton(
                pagination_frame, text="◀", command=self.prev_qc_data_page,
                width=sp(64), height=sp(44), font=theme_font(14, bold=True),
                state="disabled" if self.qc_data_page <= 1 else "normal"
            )
            prev_btn.pack(side="left", padx=sp(5), pady=sp(5))

            page_info = ctk.CTkLabel(
                pagination_frame, text=f"{self.qc_data_page}/{total_pages}",
                font=theme_font(14, bold=True)
            )
            page_info.pack(side="left", expand=True)

            next_btn = ctk.CTkButton(
                pagination_frame, text="▶", command=self.next_qc_data_page,
                width=sp(64), height=sp(44), font=theme_font(14, bold=True),
                state="disabled" if self.qc_data_page >= total_pages else "normal"
            )
            next_btn.pack(side="right", padx=5, pady=5)

        # Industry standard summary statistics (compact for RPi)
        if all_results:
            summary_frame = ctk.CTkFrame(data_frame, fg_color="#F0F9FF", height=50)
            summary_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=2)
            summary_frame.grid_propagate(False)

            # Calculate summary statistics (industry standard)
            all_values = [r[1] for r in all_results]
            actual_mean = sum(all_values) / len(all_values)
            actual_sd = (sum((x - actual_mean) ** 2 for x in all_values) / len(all_values)) ** 0.5
            actual_cv = (actual_sd / actual_mean * 100) if actual_mean != 0 else 0

            # Count violations (industry standard)
            violations = self.check_westgard_rules(all_values, target_mean, target_sd)
            out_of_control = len([v for v in violations.values() if '3s' in v or 'R4s' in v])
            warnings = len([v for v in violations.values() if '2s' in v or '4-1s' in v or '10x' in v])

            # Compact summary for RPi (split into two lines for better readability)
            summary_text1 = f"Period: Mean={actual_mean:.2f}, SD={actual_sd:.2f}, CV={actual_cv:.1f}%"
            summary_text2 = f"Results: {len(all_values)} | OOC: {out_of_control} | Warnings: {warnings}"

            ctk.CTkLabel(
                summary_frame, text=summary_text1, font=ctk.CTkFont(size=9),
                text_color="#1E40AF"
            ).pack(pady=(5, 0))

            ctk.CTkLabel(
                summary_frame, text=summary_text2, font=ctk.CTkFont(size=9),
                text_color="#1E40AF"
            ).pack(pady=(0, 5))

        return data_frame

    def prev_qc_data_page(self):
        """Go to previous page in QC data table"""
        if hasattr(self, 'qc_data_page') and self.qc_data_page > 1:
            self.qc_data_page -= 1
            self.refresh_qc_display()

    def next_qc_data_page(self):
        """Go to next page in QC data table"""
        # Get total pages (same page size as create_qc_data_frame)
        all_results = self.db_manager.get_qc_series(
            self.current_result_test,
            self.current_qc,
            self.current_qc_month
        )
        items_per_page = 8
        total_pages = max(1, (len(all_results) + items_per_page - 1) // items_per_page)

        if hasattr(self, 'qc_data_page') and self.qc_data_page < total_pages:
            self.qc_data_page += 1
            self.refresh_qc_display()

    def show_qc_chart(self):
        """Switch to chart view - RPi optimized"""
        self.current_qc_view = 'chart'
        self.qc_chart_frame.grid(row=0, column=0, sticky="nsew")
        self.qc_data_frame.grid_remove()

    def show_qc_data(self):
        """Switch to data view - RPi optimized"""
        self.current_qc_view = 'data'
        self.qc_data_frame.grid(row=0, column=0, sticky="nsew")
        self.qc_chart_frame.grid_remove()

    def switch_qc_data(self):
        """Toggle between QC1 and QC2"""
        try:
            # Toggle QC number
            self.current_qc = 2 if self.current_qc == 1 else 1

            # Check if we have the current_result_test attribute
            if not hasattr(self, 'current_result_test') or not self.current_result_test:
                self.show_notification("No test selected", error=True)
                return

            # Reset pagination to first page
            if not hasattr(self, 'qc_data_page'):
                self.qc_data_page = 1
            else:
                self.qc_data_page = 1

            if not hasattr(self, 'current_qc_month'):
                self.current_qc_month = 0
            else:
                self.current_qc_month = 0  # Reset to current month

            # Recreate frames with new QC data
            parent = None
            if hasattr(self, 'qc_chart_frame') and self.qc_chart_frame:
                parent = self.qc_chart_frame.master
                self.qc_chart_frame.destroy()

            if hasattr(self, 'qc_data_frame') and self.qc_data_frame:
                if not parent and self.qc_data_frame.master:
                    parent = self.qc_data_frame.master
                self.qc_data_frame.destroy()

            if not parent:
                # If we couldn't find a parent, show an error and return
                self.show_notification("Error: Could not find parent frame", error=True)
                return

            # Create new frames
            self.qc_chart_frame = self.create_qc_chart_frame(parent, self.current_result_test)
            self.qc_data_frame = self.create_qc_data_frame(parent, self.current_result_test)

            # Show the current view
            if hasattr(self, 'current_qc_view') and self.current_qc_view == 'data':
                self.qc_data_frame.grid(row=0, column=0, sticky="nsew")
                self.qc_chart_frame.grid_remove()
            else:
                self.qc_chart_frame.grid(row=0, column=0, sticky="nsew")
                self.qc_data_frame.grid_remove()


            # Update QC screen to reflect changes - use a safer approach
            # Instead of calling show_qc_screen which might create recursion,
            # just update the title and button text
            if hasattr(self, 'frames') and 'qc' in self.frames:
                # Find the title label and update it
                for widget in self.frames['qc'].winfo_children():
                    if isinstance(widget, ctk.CTkFrame) and widget.winfo_class() == "CTkFrame":
                        for child in widget.winfo_children():
                            if isinstance(child, ctk.CTkLabel) and "QC Data:" in child._text:
                                child.configure(text=f"QC Data: {self.current_result_test}")
                                break

                # Find the switch button and update its text
                for widget in self.frames['qc'].winfo_children():
                    if isinstance(widget, ctk.CTkFrame) and widget == self.frames['qc'].winfo_children()[-1]:
                        for child in widget.winfo_children():
                            if isinstance(child, ctk.CTkButton) and "Switch" in child._text:
                                child.configure(text=f"Switch(QC{1 if self.current_qc == 2 else 2})")
                                break

        except Exception as e:
            print(f"Error in switch_qc_data: {e}")
            import traceback
            traceback.print_exc()
            self.show_notification(f"Error switching QC data", error=True)

    def print_qc_report(self):
        """Print the current QC report"""
        # The window's own banner rather than a native messagebox: everything
        # the operator is told has to be readable on the 7" panel and must not
        # hide behind the borderless window.
        self.show_notification("Printing will be available in a later release.")

    def prev_qc_month(self):
        """Go to previous month in QC chart"""
        # Increment month offset (higher number = older month)
        self.current_qc_month += 1

        # Refresh the QC display
        self.refresh_qc_display()

    def next_qc_month(self):
        """Go to next month in QC chart"""
        # Decrement month offset (lower number = newer month)
        if self.current_qc_month > 0:
            self.current_qc_month -= 1

        # Refresh the QC display
        self.refresh_qc_display()

    def refresh_qc_display(self):
        """Refresh the QC display (chart and data)"""
        try:
            if not hasattr(self, 'current_result_test') or not self.current_result_test:
                return

            parent = None
            if hasattr(self, 'qc_chart_frame') and self.qc_chart_frame:
                parent = self.qc_chart_frame.master
                self.qc_chart_frame.destroy()

            if hasattr(self, 'qc_data_frame') and self.qc_data_frame:
                if not parent:
                    parent = self.qc_data_frame.master
                self.qc_data_frame.destroy()

            if not parent:
                return

            self.qc_chart_frame = self.create_qc_chart_frame(parent, self.current_result_test)
            self.qc_data_frame = self.create_qc_data_frame(parent, self.current_result_test)

            # Show the current view
            if self.current_qc_view == 'data':
                self.qc_data_frame.grid(row=0, column=0, sticky="nsew")
                self.qc_chart_frame.grid_remove()
            else:
                self.qc_chart_frame.grid(row=0, column=0, sticky="nsew")
                self.qc_data_frame.grid_remove()

        except Exception as e:
            print(f"Error in refresh_qc_display: {e}")
