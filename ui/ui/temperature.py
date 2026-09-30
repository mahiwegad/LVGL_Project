"""temperature.py - warm-up gate and temperature readout for the instrument.

The analyzer needs its flow cell at 37 °C before the first measurement, so the
software warms up for ten minutes from the moment the GUI starts. While that is
running the operator may explore every screen EXCEPT running a test, which asks
for confirmation first (ui/main_menu.py).

This module owns the two numbers the screens display:

  * the warm-up progress (0..1) and the time left, and
  * the live temperature readout once the warm-up is done: 36.9 -> 37.0 ->
    37.1 -> 37.0, stepping every 30 s and looping back to 36.9.

It is intentionally free of Tk: the main menu and the measurement header both
ask the SAME instance, so the two screens can never disagree, and the harnesses
can drive it with a fake clock instead of waiting ten minutes.
"""

import time

# Ten minutes from GUI start (the operator's warm-up window).
WARMUP_SECONDS = 10 * 60
# The displayed reading steps every 30 s...
CYCLE_STEP_SECONDS = 30
# ...through this loop, forever: 36.9 -> 37.0 -> 37.1 -> 37.0 -> 36.9
CYCLE_VALUES = (36.9, 37.0, 37.1, 37.0)

# Header wording. Kept here (not in the screens) so the main menu and the
# measurement screen always say exactly the same thing.
STABILIZING_TEXT = "Temperature Stabilizing"
READY_PREFIX = "Temperature"


def mmss(seconds):
    """Seconds -> 'MM:SS' (never negative)."""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def minutes_left(seconds):
    """Whole minutes left, rounded UP but never past the window itself.

    The screens used to compute ``int(remaining // 60) + 1``, which reported a
    TEN-minute warm-up as "11 minute(s)" for its first minute (and rounded the
    countdown the same way: 90 s left read as "2:30"). The operator asked why
    the panel said 11 when the wait is 10, so the arithmetic lives here, once.
    """
    try:
        total = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return 0
    if total <= 0:
        return 0
    return int(-(-total // 60))


class TemperatureStabilization:
    """The 10-minute warm-up window, plus the temperature the screens show."""

    def __init__(self, total_seconds=WARMUP_SECONDS, clock=time.monotonic,
                 started_at=None, cycle_step=CYCLE_STEP_SECONDS,
                 cycle_values=CYCLE_VALUES):
        self.total = float(total_seconds)
        self._clock = clock
        self.started_at = self._clock() if started_at is None else float(started_at)
        self.cycle_step = float(cycle_step)
        self.cycle_values = tuple(cycle_values) or CYCLE_VALUES
        # The hardware water-stabilization routine reports separately; a failure
        # there is surfaced on its own line and does not stop this timer.
        self.hardware_failed = False

    # ---- progress ------------------------------------------------------
    @property
    def elapsed(self):
        return max(0.0, self._clock() - self.started_at)

    @property
    def remaining(self):
        return max(0.0, self.total - self.elapsed)

    @property
    def progress(self):
        if self.total <= 0:
            return 1.0
        return max(0.0, min(1.0, self.elapsed / self.total))

    @property
    def is_done(self):
        return self.elapsed >= self.total

    def force_elapsed(self, seconds):
        """Test/preview hook: pretend the warm-up started `seconds` ago."""
        self.started_at = self._clock() - float(seconds)

    # ---- display -------------------------------------------------------
    @property
    def display_temp(self):
        """The temperature to show right now (steps every ``cycle_step``)."""
        step = int(self.elapsed // self.cycle_step) if self.cycle_step > 0 else 0
        return self.cycle_values[step % len(self.cycle_values)]

    def readout_text(self):
        """'Temperature : 36.9 °C' once warm-up is done."""
        return f"{READY_PREFIX} : {self.display_temp:.1f} °C"

    def status_text(self):
        """Short status for the header chips: stabilizing vs the live reading."""
        return self.readout_text() if self.is_done else STABILIZING_TEXT

    def progress_text(self):
        """'07:12 remaining' / 'Warm-up complete' for the main menu card."""
        if self.is_done:
            return "Warm-up complete"
        return f"{mmss(self.remaining)} remaining"

    def countdown_text(self):
        """The card's MM:SS countdown (real minutes, not rounded ones)."""
        return mmss(self.remaining)

    def minutes_left(self):
        """Whole minutes left for the "ready to measure in N minute(s)" line."""
        return minutes_left(self.remaining)


__all__ = [
    "TemperatureStabilization", "WARMUP_SECONDS", "CYCLE_STEP_SECONDS",
    "CYCLE_VALUES", "STABILIZING_TEXT", "READY_PREFIX", "mmss",
    "minutes_left",
]
