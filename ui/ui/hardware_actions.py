"""hardware_actions.py - Simulated vs. real hardware actions.

Simulation-mode no-ops keep the UI runnable on any machine; the real
hardware functions are imported from Hardware.stm32_backend when
SIMULATION_MODE is disabled.

Part of the ui package (split from the original monolithic ui.py).
"""
from Hardware.config import SIMULATION_MODE

if SIMULATION_MODE:

    def run_water(*args, **kwargs):
        print("[SIM] run_water")

    def reverse(*args, **kwargs):
        print("[SIM] reverse")

    def flow_water(*args, **kwargs):
        print("[SIM] flow_water")

    def clean(*args, **kwargs):
        print("[SIM] clean")
        return True

else:
    from Hardware.stm32_backend import flow_water as run_water, reverse, flow_water, clean
