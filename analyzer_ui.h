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

/*
 * Every page in the app.
 *
 * The first six are the home screen's keys, in menu order - that keeps the key
 * index, the menu table and --shot N lined up. TEST and RESULT open the list
 * screens the reference photos show (LIST OF TESTS / RESULTS) rather than
 * jumping straight to a form, so the key is the tab and the sub-screens hang
 * off it.
 *
 * The app is light-theme only, so there is no dark variant of any of these.
 */
typedef enum
{
    ANALYZER_SCREEN_TEST = 0,       /* the TEST tab  -> LIST OF TESTS   */
    ANALYZER_SCREEN_RESULT,         /* the RESULT tab -> RESULTS       */
    ANALYZER_SCREEN_SYSTEM,
    ANALYZER_SCREEN_MAINTENANCE,
    ANALYZER_SCREEN_POWER,
    ANALYZER_SCREEN_ABOUT,

    /* Sub-screens below those tabs. */
    ANALYZER_SCREEN_PARAMETERS,     /* Test Parameters form            */
    ANALYZER_SCREEN_TEST_LIST,      /* LIST OF TESTS                   */
    ANALYZER_SCREEN_RESULTS,        /* RESULTS                         */
    ANALYZER_SCREEN_MEASUREMENT,    /* Measurement: <test>             */
    ANALYZER_SCREEN_RESULT_DETAIL,  /* one test's results table        */

    ANALYZER_SCREEN_COUNT
} analyzer_screen_t;

/* How many of the screens above are home-screen cards. */
#define ANALYZER_HOME_COUNT 6

/** Build the home screen (the persistent shell). */
void analyzer_ui_build(void);

/** Tear down the open page and return to the home screen. */
void analyzer_ui_go_home(void);

/**
 * Go back one step.
 *
 * The app keeps a shallow history of the screens it has opened, so every
 * header's BACK lands where the operator came from: a form returns to the list
 * it was opened from, and a list returns to the dashboard. This is the single
 * back action shared by every screen - no page owns its own idea of "back".
 */
void analyzer_ui_back(void);

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

/**
 * The page currently open, or ANALYZER_SCREEN_COUNT for the home menu.
 *
 * The click test in main.c uses this to prove that a tap on a home key really
 * lands on that key's screen, instead of assuming the callbacks are still
 * wired to the right destinations.
 */
analyzer_screen_t analyzer_ui_current_screen(void);

/**
 * Centre of home key `index` (0..ANALYZER_HOME_COUNT-1), in panel pixels.
 *
 * Read from the live widget, so the click test aims at where the key actually
 * is rather than at a second copy of the menu's geometry. Returns without
 * touching x/y if the home menu is not built.
 */
void analyzer_ui_home_key_center(int index, int32_t *x, int32_t *y);

/**
 * Open one of the TEST form's option pickers.
 *
 * A test hook for the screenshot mode: it opens a picker exactly as tapping
 * its field does, so the modal can be rendered and reviewed without driving
 * the mouse. Indices are 0..3 = Method, Wavelength, Unit, Blank type. Does
 * nothing unless the TEST screen is open.
 */
void analyzer_ui_debug_open_picker(int index);

/* ---- memory reporting (same instrumentation as the memory test) ---- */

size_t analyzer_ui_heap_used(void);
size_t analyzer_ui_heap_peak(void);
size_t analyzer_ui_worst_switch(void);

/** The switch budget the memory test checks against, in bytes. */
#define ANALYZER_SWITCH_BUDGET 2048

#endif /* ANALYZER_UI_H */
