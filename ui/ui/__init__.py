"""ui package - Biochemistry Analyzer GUI.

The original monolithic ui.py was split into screen-focused mixin classes so
each part of the interface can be located and edited independently:

- core.py            : app lifecycle, hardware/UART setup, navigation, shared dialogs
- main_menu.py       : main menu + water-stabilization startup flow
- test_screen.py     : list-of-tests screen (pagination, filtering, sorting)
- test_parameters.py : test creation/editing form + QC parameter popup
- system_screens.py  : SYSTEM, MAINTENANCE, POWER (shut down / reboot / standby), ABOUT
- controls.py        : touch input widgets - on-screen keyboard, option picker
- temperature.py     : ten-minute warm-up gate and the temperature readout
- measurement.py     : live measurement screen, realtime data, workflow buttons
- system_screens.py : SYSTEM (diagnostics), MAINTENANCE (pump/fluid), POWER, ABOUT
- results.py         : results list screen
- qc.py              : QC charts, Westgard rules, QC data tables
- dilution.py        : out-of-range / dilution workflow interface
- hardware_actions.py: simulated vs. real hardware actions

`BiochemistryAnalyzerUI` below assembles all mixins into the single window
class used by main.py.

Layout target: the instrument's 1280x720 (7") panel. Screens are written in
panel pixels and the whole tree is scaled from the window size, so a monitor
bigger than the panel shows the same proportions (theme.ui_scale / theme.sp).
"""
import customtkinter as ctk

from ui.core import CoreMixin
from ui.main_menu import MainMenuMixin
from ui.system_screens import SystemScreensMixin
from ui.test_screen import TestScreenMixin
from ui.test_parameters import TestParametersMixin
from ui.measurement import MeasurementMixin
from ui.results import ResultsMixin
from ui.qc import QCMixin
from ui.dilution import DilutionMixin


class BiochemistryAnalyzerUI(
    CoreMixin,
    MainMenuMixin,
    SystemScreensMixin,
    TestScreenMixin,
    TestParametersMixin,
    MeasurementMixin,
    ResultsMixin,
    QCMixin,
    DilutionMixin,
    ctk.CTk,
):
    """Main application window (assembled from the screen mixins above)."""
    pass


__all__ = ["BiochemistryAnalyzerUI"]
