/**
 * @file analyzer_ui.h
 *
 * LVGL port of the analyzer's CustomTkinter UI (see ui/ui/theme.py and
 * ui/ui/main_menu.py). The Tkinter app is designed for a 1280x720 panel;
 * this module renders the same layout on the LVGL display, scaling every
 * design measurement to the real panel width.
 */

#ifndef ANALYZER_UI_H
#define ANALYZER_UI_H

#include "lvgl.h"
#include <stddef.h>

/* Destination screens reachable from the home screen, in menu order. */
typedef enum
{
    ANALYZER_SCREEN_TEST = 0,
    ANALYZER_SCREEN_RESULT,
    ANALYZER_SCREEN_SYSTEM,
    ANALYZER_SCREEN_MAINTENANCE,
    ANALYZER_SCREEN_POWER,
    ANALYZER_SCREEN_ABOUT,
    ANALYZER_SCREEN_COUNT
} analyzer_screen_t;

/** Build the home screen (the persistent shell). */
void analyzer_ui_build(void);

/** Tear down the open page and return to the home screen. */
void analyzer_ui_go_home(void);

/**
 * Open a destination screen.
 *
 * The outgoing page is deleted BEFORE the incoming page is built, so the two
 * are never alive at the same time. Returns the extra bytes the switch needed
 * above the resident baseline.
 */
size_t analyzer_ui_open(analyzer_screen_t screen);

/** Print a line for every switch (off while running the memory test). */
void analyzer_ui_set_verbose(int enabled);

/** Menu title of a destination screen, for reports and logs. */
const char *analyzer_ui_screen_title(analyzer_screen_t screen);

/* ---- memory reporting (same instrumentation as the memory test) ---- */

size_t analyzer_ui_heap_used(void);
size_t analyzer_ui_heap_peak(void);
size_t analyzer_ui_worst_switch(void);

/** The switch budget the memory test checks against, in bytes. */
#define ANALYZER_SWITCH_BUDGET 2048

#endif /* ANALYZER_UI_H */
