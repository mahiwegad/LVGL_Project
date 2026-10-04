/**
 * @file analyzer_ui.c
 *
 * LVGL port of the analyzer's home screen.
 *
 * Source of truth: ui/ui/theme.py (palette + card metrics) and
 * ui/ui/main_menu.py (create_main_menu). The Tkinter layout is designed for a
 * 1280x720 panel; every measurement below is written in those design pixels
 * and pushed through sc() so the true panel size decides the result. On an
 * 800x480 display that is a factor of 0.625.
 *
 * Text weight: the Tkinter screens use bold for headings and card titles.
 * LVGL's built-in Montserrat faces ship in one weight only, so headings here
 * are regular. A bold face would have to be added as a custom font.
 */

#include "analyzer_ui.h"
#include "home_icons.h"

#include <stdio.h>
#include <string.h>

/* =========================================================
 * PALETTE
 *
 * The LIGHT table from ui/ui/theme.py, as plain hex.
 *
 * There is exactly one theme. The panel is a light-theme instrument (the lab
 * SOP - theme.py's START_IN_LIGHT - and now a hard requirement), so the dark
 * table, the runtime palette pointer and the theme switch are all gone: a
 * colour can no longer be a function of which theme is active, because there
 * is only one. Screens are built once, in these colours, and never rebuilt to
 * repaint.
 * ========================================================= */


/* Index into the method tables below. */
enum
{
    METHOD_TP = 0,
    METHOD_EP,
    METHOD_KINETIC,
    METHOD_COUNT
};

static const uint32_t METHOD_FILL_HEX[METHOD_COUNT]   = { 0xDBEAFE, 0xFEE2E2, 0xFEF3C7 };
static const uint32_t METHOD_BORDER_HEX[METHOD_COUNT] = { 0x93C5FD, 0xFCA5A5, 0xFCD34D };
static const uint32_t METHOD_TEXT_HEX[METHOD_COUNT]   = { 0x1E40AF, 0x991B1B, 0x92400E };

/*
 * Every colour the UI draws, written once as a named hex constant and read
 * through the CLR_* macros below (or directly as HEX_* where a function has
 * to choose between two of them). There is only one theme, so nothing is
 * looked up at runtime and nothing swaps; each value is the one
 * ui/ui/theme.py's LIGHT table uses.
 */
#define HEX_WINDOW_BG          0xEEF2F7
#define HEX_SURFACE            0xFFFFFF
#define HEX_SURFACE_SUNKEN     0xF1F5F9
#define HEX_BORDER             0xE2E8F0
#define HEX_BORDER_STRONG      0xCBD5E1
#define HEX_TEXT               0x0F172A
#define HEX_TEXT_MUTED         0x64748B
#define HEX_TEXT_FAINT         0x94A3B8
#define HEX_TEXT_ON_ACCENT     0xFFFFFF
#define HEX_ACCENT             0x0F766E
#define HEX_ACCENT_HOVER       0x0E6E67
#define HEX_ACCENT_TEXT        0x0F766E
#define HEX_SUCCESS            0x15803D
#define HEX_ON_SUCCESS         0xFFFFFF
#define HEX_WARNING            0xF59E0B
#define HEX_DANGER             0xDC2626
#define HEX_ON_DANGER          0xFFFFFF
#define HEX_BTN_NEUTRAL        0xE2E8F0
#define HEX_BTN_NEUTRAL_HOVER  0xCBD5E1
#define HEX_BTN_TEXT           0x0F172A
#define HEX_RUN_BTN            0x2563EB
#define HEX_RUN_BTN_HOVER      0x1D4ED8
#define HEX_ON_RUN_BTN         0xFFFFFF

#define CLR_WINDOW_BG          (lv_color_hex(HEX_WINDOW_BG))
#define CLR_SURFACE            (lv_color_hex(HEX_SURFACE))
#define CLR_SURFACE_SUNKEN     (lv_color_hex(HEX_SURFACE_SUNKEN))
#define CLR_BORDER             (lv_color_hex(HEX_BORDER))
#define CLR_BORDER_STRONG      (lv_color_hex(HEX_BORDER_STRONG))
#define CLR_TEXT               (lv_color_hex(HEX_TEXT))
#define CLR_TEXT_MUTED         (lv_color_hex(HEX_TEXT_MUTED))
#define CLR_TEXT_FAINT         (lv_color_hex(HEX_TEXT_FAINT))
#define CLR_TEXT_ON_ACCENT     (lv_color_hex(HEX_TEXT_ON_ACCENT))
#define CLR_ACCENT             (lv_color_hex(HEX_ACCENT))
#define CLR_ACCENT_HOVER       (lv_color_hex(HEX_ACCENT_HOVER))
#define CLR_ACCENT_TEXT        (lv_color_hex(HEX_ACCENT_TEXT))
#define CLR_SUCCESS            (lv_color_hex(HEX_SUCCESS))
#define CLR_ON_SUCCESS         (lv_color_hex(HEX_ON_SUCCESS))
#define CLR_WARNING            (lv_color_hex(HEX_WARNING))
#define CLR_DANGER             (lv_color_hex(HEX_DANGER))
#define CLR_ON_DANGER          (lv_color_hex(HEX_ON_DANGER))
#define CLR_BTN_NEUTRAL        (lv_color_hex(HEX_BTN_NEUTRAL))
#define CLR_BTN_NEUTRAL_HOV    (lv_color_hex(HEX_BTN_NEUTRAL_HOVER))
#define CLR_BTN_TEXT           (lv_color_hex(HEX_BTN_TEXT))
#define CLR_RUN_BTN            (lv_color_hex(HEX_RUN_BTN))
#define CLR_RUN_BTN_HOVER      (lv_color_hex(HEX_RUN_BTN_HOVER))
#define CLR_ON_RUN_BTN         (lv_color_hex(HEX_ON_RUN_BTN))

#define CLR_METHOD_FILL(m)   (lv_color_hex(METHOD_FILL_HEX[m]))
#define CLR_METHOD_BORDER(m) (lv_color_hex(METHOD_BORDER_HEX[m]))
#define CLR_METHOD_TEXT(m)   (lv_color_hex(METHOD_TEXT_HEX[m]))

/*
 * Home menu. The label colour is the navy the reference artwork uses for its
 * captions; the separator is its hairline between the menu cells; the press
 * tint is the light wash the cell takes while a finger is on it.
 */
#define CLR_HOME_LABEL      (lv_color_hex(0x0B2A4E))
#define CLR_HOME_SEPARATOR  (lv_color_hex(0xC8DAEC))
#define CLR_HOME_PRESS      (lv_color_hex(0xDCE6F2))

/* =========================================================
 * TYPE SCALE
 *
 * Design font size -> the nearest Montserrat face compiled in.
 *
 * The small end of the scale is deliberately raised above the
 * strict 0.625 scale of the 1280x720 design: at 8 px the
 * subtitles and captions were unreadable on the real panel.
 * Headings keep their size, so the hierarchy still reads.
 *
 *   22 -> 14   (card icon)     19 -> 14  (card arrow)
 *   17 -> 14   (card title)    12 -> 12  (card subtitle)
 *   16 -> 14   (status line)   20 -> 14  (countdown value)
 *   11 -> 12   (unit caption)  12 -> 12  (progress caption)
 * ========================================================= */

#define F_CARD_TITLE  (&lv_font_montserrat_14)
#define F_STATUS      (&lv_font_montserrat_14)
#define F_VALUE       (&lv_font_montserrat_14)
#define F_CAPTION     (&lv_font_montserrat_12)
#define F_PAGE_TITLE  (&lv_font_montserrat_20)

/* Ported screens (test_parameters.py uses theme_font(14) for field text and
 * theme_font(14, bold=True) for row labels and action buttons). */
#define F_HINT        (&lv_font_montserrat_12)
#define F_ROW_LABEL   (&lv_font_montserrat_14)
#define F_FIELD       (&lv_font_montserrat_14)
#define F_ACTION      (&lv_font_montserrat_14)
#define F_PICKER      (&lv_font_montserrat_14)

/* List tiles and their meta line (test_screen.py: theme_font(15) / (11)). */
#define F_TILE        (&lv_font_montserrat_14)
#define F_TILE_META   (&lv_font_montserrat_12)

/*
 * Home menu name.
 *
 * The reference draws each caption at very nearly this size - its "TEST" is
 * 40 px wide and its "MAINTENANCE" 111 px at 800x480, which is what Montserrat
 * 16 measures. Only the six home keys use it.
 */
#define F_HOME_LABEL  (&lv_font_montserrat_16)

/* =========================================================
 * MENU DEFINITION (ui/ui/main_menu.py: create_main_menu)
 * ========================================================= */

typedef struct
{
    const char *icon;
    const char *title;
    const char *subtitle;
    int accent;             /* TEST is the accented entry */
} menu_entry_t;

/*
 * One row per screen, indexed by analyzer_screen_t. The first
 * ANALYZER_HOME_COUNT rows are the dashboard cards; the rest title the
 * sub-screens those cards open, and their subtitles are the one-line
 * explanation each reference screen shows under its heading.
 */
static const menu_entry_t menu_entries[ANALYZER_SCREEN_COUNT] =
{
    {
        LV_SYMBOL_TINT,
        "TEST",
        "Create tests and start a measurement.",
        1
    },
    {
        LV_SYMBOL_LIST,
        "RESULT",
        "Browse runs and open QC charts.",
        0
    },
    {
        LV_SYMBOL_SETTINGS,
        "SYSTEM",
        "Instrument status and diagnostics.",
        0
    },
    {
        LV_SYMBOL_LOOP,
        "MAINTENANCE",
        "Pump and fluid controls.",
        0
    },
    {
        LV_SYMBOL_POWER,
        "POWER",
        "Shut down, reboot or sleep.",
        0
    },
    {
        "i",
        "ABOUT",
        "Manufacturer and software build.",
        0
    },

    /* ---- sub-screens (test_screen.py / results.py / measurement.py) ---- */
    {
        "",
        "TEST PARAMETERS",
        "Fill the fields, then SAVE. Tap a box to type; tap a list to choose.",
        0
    },
    {
        "",
        "LIST OF TESTS",
        "Tap a test to measure it, or Edit Test to change it",
        0
    },
    {
        "",
        "RESULTS",
        "Select a test to view its measurement results",
        0
    },
    {
        "",
        "MEASUREMENT",
        "Live readout while the run is in progress",
        0
    },
    {
        "",
        "MEASUREMENT RESULTS",
        "Measurement results, unit: -",
        0
    }
};

/*
 * The six home keys' artwork, in the same order as the menu entries above.
 * Cut from the supplied reference artwork by tools/makeicons.py.
 */
static const lv_image_dsc_t *const home_images[ANALYZER_HOME_COUNT] =
{
    &home_icon_test,
    &home_icon_result,
    &home_icon_system,
    &home_icon_maintenance,
    &home_icon_power,
    &home_icon_about
};

/* =========================================================
 * STATE
 * ========================================================= */

static lv_obj_t *home_layer;

/* The six home keys, in menu order. Kept only so the click test can ask where
 * a key is instead of repeating the menu's geometry. */
static lv_obj_t *home_keys[ANALYZER_HOME_COUNT];

static lv_obj_t *current_page;
static size_t worst_switch_overhead;
static int verbose_nav = 1;

/* Which destination screen current_page is, so a theme change can rebuild
 * the screen the operator is looking at instead of dropping them home. */
static analyzer_screen_t current_screen = ANALYZER_SCREEN_TEST;
static int page_open = 0;

/* One focus group for the whole app. Text fields join it so the SDL keyboard
 * indev can type into whichever box was tapped. The group is one small object
 * for the app, not one per screen. */
static lv_group_t *ui_group;

/*
 * Shallow history, so every header's BACK lands where the operator came from.
 * Home is the root and is not pushed: opening a page from the dashboard pushes
 * nothing, and BACK from that page falls through to go_home(). An 8-deep stack
 * is several steps more than the app's deepest flow (dashboard > list > form >
 * measurement) and costs 8 enum-sized bytes, once, for the whole app.
 */
#define NAV_STACK_MAX 8

static analyzer_screen_t nav_stack[NAV_STACK_MAX];
static int nav_depth = 0;

/* Build `screen` now: deletes the outgoing page BEFORE creating the incoming
 * one. Kept separate from analyzer_ui_open() so a rebuild that must NOT touch
 * the history (filter, page change, theme switch) can call it directly. */
static size_t open_page(analyzer_screen_t screen);


/* =========================================================
 * DESIGN-PIXEL SCALE
 * ========================================================= */

#define DESIGN_W 1280

static int32_t sc(int32_t design_px)
{
    lv_display_t *disp = lv_display_get_default();

    int32_t width = disp ?
        lv_display_get_horizontal_resolution(disp) :
        DESIGN_W;

    return (int32_t)((int64_t)design_px * width / DESIGN_W);
}


/* =========================================================
 * MEMORY HELPERS
 * ========================================================= */

size_t analyzer_ui_heap_used(void)
{
    lv_mem_monitor_t mon;

    lv_mem_monitor(&mon);

    return mon.total_size - mon.free_size;
}

size_t analyzer_ui_heap_peak(void)
{
    lv_mem_monitor_t mon;

    lv_mem_monitor(&mon);

    return mon.max_used;
}

size_t analyzer_ui_worst_switch(void)
{
    return worst_switch_overhead;
}

void analyzer_ui_set_verbose(int enabled)
{
    verbose_nav = enabled;
}

const char *analyzer_ui_screen_title(analyzer_screen_t screen)
{
    if((int)screen < 0 || screen >= ANALYZER_SCREEN_COUNT)
    {
        return "?";
    }

    return menu_entries[screen].title;
}


/* =========================================================
 * SHARED STYLE HELPERS
 * ========================================================= */

static void make_transparent(lv_obj_t *obj)
{
    lv_obj_set_style_bg_opa(obj, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(obj, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(obj, 0, LV_PART_MAIN);
}

/*
 * ONE BUTTON BUILDER FOR THE WHOLE APP.
 *
 * Every button on every screen is made here, and its height is never a number
 * chosen by eye - it is the caller's bar height (see bar_height()), which is
 * derived from the button's OWN font. A label is exactly one line high and is
 * centred in a box that is at least that tall plus its padding, so a button
 * cannot clip its own text no matter which screen it is on that is the single
 * reusable fix for the clipping class of bug, applied everywhere at once.
 */
static lv_obj_t *make_button(
    lv_obj_t *parent,
    const char *text,
    const lv_font_t *font,
    uint32_t bg,
    uint32_t bg_hover,
    uint32_t fg,
    int32_t height,
    lv_event_cb_t cb,
    void *user
)
{
    lv_obj_t *btn = lv_button_create(parent);

    /* height <= 0 asks for the font-derived default. */
    lv_obj_set_height(
        btn,
        height > 0 ? height : lv_font_get_line_height(font) + sc(18)
    );

    lv_obj_set_style_bg_color(btn, lv_color_hex(bg), LV_PART_MAIN);
    lv_obj_set_style_bg_color(btn, lv_color_hex(bg_hover), LV_STATE_HOVERED);
    lv_obj_set_style_text_color(btn, lv_color_hex(fg), LV_PART_MAIN);
    lv_obj_set_style_radius(btn, sc(12), LV_PART_MAIN);
    lv_obj_set_style_border_width(btn, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(btn, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_text_font(btn, font, LV_PART_MAIN);
    lv_obj_set_style_shadow_width(btn, 0, LV_PART_MAIN);
    /* Horizontal padding only: the vertical room belongs to the label, which
     * is what stops a button from shaving the top or bottom off its glyphs. */
    lv_obj_set_style_pad_ver(btn, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_hor(btn, sc(6), LV_PART_MAIN);

    if(cb != NULL)
    {
        lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, user);
    }

    lv_obj_t *label = lv_label_create(btn);

    lv_label_set_text(label, text);

    /* A label whose width is its content can be one long line wider than the
     * button; wrapping to the button's inner width keeps a long name INSIDE
     * the tile rather than off its edge. */
    lv_obj_set_width(label, lv_pct(100));
    lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_center(label);

    return btn;
}

/* A plain label. Every label in the app gets its font and colour here, so a
 * label is never created without an explicit font - a label with no font is
 * one size on the simulator and another on the target, which is how a layout
 * that looks right ends up clipping. */
static lv_obj_t *make_label(
    lv_obj_t *parent,
    const char *text,
    const lv_font_t *font,
    uint32_t color
)
{
    lv_obj_t *label = lv_label_create(parent);

    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, LV_PART_MAIN);
    lv_obj_set_style_text_color(label, lv_color_hex(color), LV_PART_MAIN);

    return label;
}

/* Back to the dashboard, whatever depth the operator is at. */
static void home_event_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    analyzer_ui_go_home();
}

/*
 * Turn the shared content card (see create_page) into a vertical stack.
 * create_page builds it as a ROW so the parameter form's two columns sit side
 * by side; a screen whose content is a single column says so with this rather
 * than re-implementing the card.
 */
static void card_as_column(lv_obj_t *card)
{
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        card,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );
    lv_obj_set_style_pad_row(card, sc(8), LV_PART_MAIN);
}


/* =========================================================
 * HOME MENU  (the supplied reference panel's menu screen)
 *
 * The menu is nothing but six illustrated blue keys and their names: no
 * header, no status strip, no footer. Each key is one of the reference's own
 * icon images (home_icons.h), its name sits underneath in the reference's
 * navy, and hairlines divide the 3 x 2 cells.
 *
 * The geometry is the reference's own, read off the artwork and expressed in
 * design px so sc() maps it onto the real panel: the cells have a 242.5 px
 * pitch across and a 202 px pitch down at 800x480, which puts the menu's outer
 * margin at 36 x 38 px, the icons at 130 x 121 px, and the hairlines about
 * 9 px past the menu box on every side. Nothing here is a coordinate picked by
 * eye, and nothing is written as a fixed panel position.
 *
 * Only the presentation lives here. Each key still opens exactly the screen
 * its card opened before, through the same analyzer_ui_open() call.
 * ========================================================= */

/* Menu box, inset from the panel edges. */
#define HOME_MARGIN_X   sc(58)      /*  36 px at 800x480 */
#define HOME_MARGIN_Y   sc(61)      /*  38 px at 800x480 */

/* How far the hairlines reach past the menu box. */
#define HOME_SEP_OVER   sc(15)      /*   9 px at 800x480 */

/* One icon, at the reference tile's proportions. */
#define HOME_ICON_W     sc(208)     /* 130 px at 800x480 */
#define HOME_ICON_H     sc(194)     /* 121 px at 800x480 */

/* Between an icon and its name. */
#define HOME_ICON_GAP   sc(20)      /*  12 px at 800x480 */

static void tile_event_cb(lv_event_t *e)
{
    analyzer_screen_t screen =
        (analyzer_screen_t)(intptr_t)lv_event_get_user_data(e);

    analyzer_ui_open(screen);
}

/*
 * Hairline between two cells.
 *
 * The reference divides its menu with full-length hairlines rather than a
 * frame per cell, so the menu draws them once, in their own layer over the
 * keys. ``across`` picks the orientation and ``pct`` the share of the menu
 * area to inset it by (33 / 67 for the two columns, 50 for the row).
 *
 * The layer is not clickable, so every tap falls through to the key beneath
 * it.
 */
static void create_grid_separator(lv_obj_t *parent, int across, int pct)
{
    lv_obj_t *line = lv_obj_create(parent);

    lv_obj_align(line, LV_ALIGN_TOP_LEFT, 0, 0);

    if(across)
    {
        /* full width, one pixel tall, sitting ``pct`` down the menu area */
        lv_obj_set_size(line, lv_pct(100), 1);
        lv_obj_set_style_y(line, lv_pct(pct), LV_PART_MAIN);
    }
    else
    {
        /* full height, one pixel wide, sitting ``pct`` across it */
        lv_obj_set_size(line, 1, lv_pct(100));
        lv_obj_set_style_x(line, lv_pct(pct), LV_PART_MAIN);
    }

    lv_obj_set_style_bg_color(line, CLR_HOME_SEPARATOR, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(line, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(line, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(line, 0, LV_PART_MAIN);

    lv_obj_clear_flag(line, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(line, LV_OBJ_FLAG_CLICKABLE);
}

/*
 * One menu key: the reference's icon with its name underneath, centred in the
 * cell that opens its screen.
 *
 * Only the cell is clickable. The icon and the name are plain children, so a
 * tap anywhere on either of them reaches the cell and presses it - there is
 * exactly one tap target per destination, and it covers both.
 */
static lv_obj_t *create_menu_tile(
    lv_obj_t *parent,
    const menu_entry_t *entry,
    const lv_image_dsc_t *icon,
    analyzer_screen_t screen
)
{
    lv_obj_t *cell = lv_obj_create(parent);

    lv_obj_set_style_bg_opa(cell, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(cell, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(cell, sc(14), LV_PART_MAIN);
    lv_obj_set_style_pad_all(cell, 0, LV_PART_MAIN);

    /* The wash the cell takes while a finger is on it. */
    lv_obj_set_style_bg_color(cell, CLR_HOME_PRESS, LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(cell, LV_OPA_COVER, LV_STATE_PRESSED);

    lv_obj_set_flex_flow(cell, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        cell,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_set_style_pad_row(cell, HOME_ICON_GAP, LV_PART_MAIN);

    lv_obj_clear_flag(cell, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_add_flag(cell, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(
        cell,
        tile_event_cb,
        LV_EVENT_CLICKED,
        (void *)(intptr_t)screen
    );


    /* ---------------- the reference's own artwork ---------------- */

    lv_obj_t *art = lv_image_create(cell);

    lv_image_set_src(art, icon);

    /* Explicit, so the icon still fills its slot if the panel size changes
     * and sc() scales the slot away from the image's natural pixels. */
    lv_obj_set_size(art, HOME_ICON_W, HOME_ICON_H);


    /* ---------------- and the destination's existing name ---------------- */

    lv_obj_t *title = lv_label_create(cell);

    lv_label_set_text(title, entry->title);
    lv_obj_set_width(title, lv_pct(100));
    lv_label_set_long_mode(title, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_set_style_text_font(title, F_HOME_LABEL, LV_PART_MAIN);
    lv_obj_set_style_text_color(title, CLR_HOME_LABEL, LV_PART_MAIN);

    return cell;
}


/* =========================================================
 * HOME SCREEN
 * ========================================================= */

static void build_home(void)
{
    lv_obj_t *screen = lv_screen_active();

    lv_obj_set_style_bg_color(screen, CLR_WINDOW_BG, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);

    home_layer = lv_obj_create(screen);

    lv_obj_set_size(home_layer, lv_pct(100), lv_pct(100));
    lv_obj_align(home_layer, LV_ALIGN_CENTER, 0, 0);

    make_transparent(home_layer);

    lv_obj_clear_flag(home_layer, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- the six destinations ---------------- */

    /* The menu box is the whole panel inset by HOME_MARGIN_*, and it is itself
     * the grid: a 3 x 2 array of equal cells, so the keys are evenly spaced
     * whatever the panel measures. */
    lv_obj_t *menu = lv_obj_create(home_layer);

    make_transparent(menu);

    lv_obj_set_size(menu, lv_pct(100), lv_pct(100));
    lv_obj_align(menu, LV_ALIGN_CENTER, 0, 0);

    lv_obj_set_style_pad_left(menu, HOME_MARGIN_X, LV_PART_MAIN);
    lv_obj_set_style_pad_right(menu, HOME_MARGIN_X, LV_PART_MAIN);
    lv_obj_set_style_pad_top(menu, HOME_MARGIN_Y, LV_PART_MAIN);
    lv_obj_set_style_pad_bottom(menu, HOME_MARGIN_Y, LV_PART_MAIN);
    lv_obj_set_style_pad_row(menu, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_column(menu, 0, LV_PART_MAIN);

    lv_obj_clear_flag(menu, LV_OBJ_FLAG_SCROLLABLE);

    static int32_t columns[] =
    {
        LV_GRID_FR(1),
        LV_GRID_FR(1),
        LV_GRID_FR(1),
        LV_GRID_TEMPLATE_LAST
    };

    static int32_t rows[] =
    {
        LV_GRID_FR(1),
        LV_GRID_FR(1),
        LV_GRID_TEMPLATE_LAST
    };

    lv_obj_set_grid_dsc_array(menu, columns, rows);

    /* The six home destinations, in menu order. Only the dashboard keys, not
     * the sub-screens they open, and the index IS the screen (see
     * analyzer_ui.h). */
    for(size_t i = 0; i < ANALYZER_HOME_COUNT; i++)
    {
        lv_obj_t *tile = create_menu_tile(
            menu,
            &menu_entries[i],
            home_images[i],
            (analyzer_screen_t)i
        );

        home_keys[i] = tile;

        lv_obj_set_grid_cell(
            tile,
            LV_GRID_ALIGN_STRETCH,
            (int32_t)(i % 3),
            1,
            LV_GRID_ALIGN_STRETCH,
            (int32_t)(i / 3),
            1
        );
    }


    /* ---------------- hairlines ----------------
     *
     * Their own layer, a little larger than the menu box so they read as
     * rules running past the keys rather than as a frame around them, and
     * above the keys so nothing paints over them.
     */

    lv_obj_t *rules = lv_obj_create(home_layer);

    make_transparent(rules);

    lv_obj_set_size(rules, lv_pct(100), lv_pct(100));
    lv_obj_align(rules, LV_ALIGN_CENTER, 0, 0);

    lv_obj_set_style_pad_left(rules, HOME_MARGIN_X - HOME_SEP_OVER, LV_PART_MAIN);
    lv_obj_set_style_pad_right(rules, HOME_MARGIN_X - HOME_SEP_OVER, LV_PART_MAIN);
    lv_obj_set_style_pad_top(rules, HOME_MARGIN_Y - HOME_SEP_OVER, LV_PART_MAIN);
    lv_obj_set_style_pad_bottom(rules, HOME_MARGIN_Y - HOME_SEP_OVER, LV_PART_MAIN);

    lv_obj_clear_flag(rules, LV_OBJ_FLAG_SCROLLABLE);

    /* Not a click target: taps belong to the keys underneath. */
    lv_obj_clear_flag(rules, LV_OBJ_FLAG_CLICKABLE);

    create_grid_separator(rules, 0, 33);
    create_grid_separator(rules, 0, 67);
    create_grid_separator(rules, 1, 50);
}


/* =========================================================
 * REUSABLE SCREEN COMPONENT LIBRARY
 *
 * Every destination screen is assembled from the same five
 * parts, so each part exists once instead of once per screen:
 *
 *   create_page()          header (back + title + hint) + content card
 *   form_row()             one labelled line of a form
 *   field_text()           editable text box
 *   field_picker()         touch picker button (controls.py: TouchSelect)
 *   field_checkbox()       square tick box (theme.py: CTkCheckBox)
 *   create_action_row()    RUN / SAVE / DELETE / CANCEL
 *   picker_open()          the modal option grid (controls.py: pick_option)
 *
 * Metrics come from ui/ui/test_parameters.py, ui/ui/controls.py and
 * ui/ui/theme.py, in design pixels pushed through sc().
 *
 * Memory: a screen is a fixed set of small objects and nothing is
 * copied per open - the pages are deleted before the next one is
 * built (see analyzer_ui_open), so two screens are never resident.
 * ========================================================= */


/* ---------------------------------------------------------
 * PICKER LISTS  (ui/ui/test_parameters.py)
 *
 * Compile-time tables, so a picker costs only the buttons
 * it actually shows. The form asks for an empty Method /
 * Wavelength / Unit box - the label to its left names the
 * field - while the picker still needs its own heading.
 * --------------------------------------------------------- */

static const char *const VALUES_METHOD[] =
{
    "TP", "EP", "Kinetic"
};

static const char *const VALUES_WAVELENGTH[] =
{
    "340nm", "415nm", "445nm", "480nm", "515nm",
    "555nm", "590nm", "630nm", "680nm"
};

static const char *const VALUES_UNIT[] =
{
    "mol/L", "mmol/L", "umol/L", "g/L", "mg/L", "ug/L",
    "U/L", "IU/L", "mol%", "mmol%", "umol%", "g%",
    "mg%", "ug%"
};

static const char *const VALUES_BLANK[] =
{
    "R.Blank", "S.Blank"
};

#define ARRAY_LEN(a) ((int)(sizeof(a) / sizeof((a)[0])))

typedef struct
{
    const char *title;
    const char *const *values;
    int count;
} picker_def_t;

enum
{
    PICK_METHOD = 0,
    PICK_WAVELENGTH,
    PICK_UNIT,
    PICK_BLANK,
    PICK_COUNT
};

static const picker_def_t PICKERS[PICK_COUNT] =
{
    { "Method",     VALUES_METHOD,     ARRAY_LEN(VALUES_METHOD)     },
    { "Wavelength", VALUES_WAVELENGTH, ARRAY_LEN(VALUES_WAVELENGTH) },
    { "Unit",       VALUES_UNIT,       ARRAY_LEN(VALUES_UNIT)       },
    { "Blank type", VALUES_BLANK,      ARRAY_LEN(VALUES_BLANK)      }
};


/* ---------------------------------------------------------
 * MODAL PICKER  (ui/ui/controls.py: pick_option)
 *
 * A fingertip cannot drive a native dropdown popup, so every
 * list opens as a centred card of full-size buttons. The
 * card lives on lv_layer_top() - above every page - and is
 * deleted as soon as a value is chosen, so it is resident
 * only while it is open. picker_close() is called by every
 * teardown path (navigate, go home, theme switch) so a page
 * change can never strand one.
 * --------------------------------------------------------- */

static lv_obj_t *picker_overlay;
static lv_obj_t *picker_subject;    /* label the chosen value is written into */

/*
 * Optional "a value was chosen" hook. A picker that only ever writes into its
 * own subject label (the TEST form) leaves this NULL. A filter picker - whose
 * choice has to survive the rebuild that redraws the screen - installs one, so
 * the screen can remember the value instead of reading it back off a label
 * that is about to be deleted.
 */
static void (*picker_pick_hook)(const char *value) = NULL;

/* The value label of each picker on the current TEST form. Only the test hook
 * below reads this; taps go straight through the button's own child label. */
static lv_obj_t *picker_subject_for[PICK_COUNT];

static void picker_open(int def_index, lv_obj_t *subject);
static void picker_open_def(const picker_def_t *def, lv_obj_t *subject);

void analyzer_ui_debug_open_picker(int index)
{
    if(index < 0 || index >= PICK_COUNT)
    {
        return;
    }

    if(picker_subject_for[index] == NULL)
    {
        return;
    }

    picker_open(index, picker_subject_for[index]);
}

static void picker_close(void)
{
    if(picker_overlay != NULL)
    {
        lv_obj_delete(picker_overlay);
        picker_overlay = NULL;
    }

    picker_subject = NULL;
}

static void picker_scrim_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    /* LVGL does not bubble events by default and the card is the scrim's
     * child, so this fires only for a tap on the scrim itself. */
    picker_pick_hook = NULL;
    picker_close();
}

static void picker_option_cb(lv_event_t *e)
{
    lv_obj_t *btn = lv_event_get_target_obj(e);
    lv_obj_t *label = lv_obj_get_child(btn, 0);

    if(picker_subject != NULL && label != NULL)
    {
        /* A chosen value is a real value: it stops reading as a placeholder. */
        lv_label_set_text(picker_subject, lv_label_get_text(label));
        lv_obj_set_style_text_color(picker_subject, CLR_TEXT, LV_PART_MAIN);
    }

    /* Fire before closing: the hook may rebuild the screen, which tears the
     * picker down itself. */
    if(picker_pick_hook != NULL && label != NULL)
    {
        void (*hook)(const char *) = picker_pick_hook;

        picker_pick_hook = NULL;
        hook(lv_label_get_text(label));

        return;
    }

    picker_close();
}

/* Is `value` one of this list's options? Used to highlight the current choice. */
static int picker_is_value(const picker_def_t *def, const char *value)
{
    if(value == NULL || value[0] == '\0')
    {
        return 0;
    }

    for(int i = 0; i < def->count; i++)
    {
        if(strcmp(def->values[i], value) == 0)
        {
            return 1;
        }
    }

    return 0;
}

static void picker_open(int def_index, lv_obj_t *subject)
{
    picker_open_def(&PICKERS[def_index], subject);
}

/*
 * The picker itself, over any value list. The TEST form passes one of the
 * compile-time PICKERS; the RESULTS filters pass a list built at runtime from
 * the test library, so a filter picker costs no duplicate string table.
 */
static void picker_open_def(const picker_def_t *def, lv_obj_t *subject)
{
    /* controls.py: TouchSelect.open_picker always asks for two columns. */
    const int columns = 2;

    const char *current;

    if(subject == NULL)
    {
        return;
    }

    current = lv_label_get_text(subject);

    picker_close();

    picker_subject = subject;

    lv_display_t *disp = lv_display_get_default();

    int32_t panel_w = disp ? lv_display_get_horizontal_resolution(disp) : 800;
    int32_t panel_h = disp ? lv_display_get_vertical_resolution(disp) : 480;

    int32_t option_h = sc(56);
    int32_t rows = (def->count + columns - 1) / columns;

    /* controls.py: width = max(sp(560), need) clamped to the panel;
     * height is driven by the grid, then clamped to the panel. */
    int32_t card_w = sc(700);
    int32_t card_h = sc(96) + rows * (option_h + sc(10));

    /* Option width, worked out from the card instead of flex: a button whose
     * width style is LV_SIZE_CONTENT gets re-sized from its own label by
     * lv_obj_refr_size, which would undo an equal share of the row. */
    int32_t gap = sc(10);
    int32_t scrollbar_gutter = (def->count > 12) ? sc(6) : 0;
    int32_t option_w =
        (card_w - sc(12) * 2 - scrollbar_gutter - gap * (columns - 1)) / columns;

    if(card_w > panel_w - sc(24))
    {
        card_w = panel_w - sc(24);
    }

    if(card_h > panel_h - sc(24))
    {
        card_h = panel_h - sc(24);
    }


    /* ---------------- scrim ---------------- */

    lv_obj_t *scrim = lv_obj_create(lv_layer_top());

    picker_overlay = scrim;

    lv_obj_set_size(scrim, lv_pct(100), lv_pct(100));
    lv_obj_align(scrim, LV_ALIGN_CENTER, 0, 0);

    lv_obj_set_style_bg_color(scrim, lv_color_black(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(scrim, LV_OPA_60, LV_PART_MAIN);
    lv_obj_set_style_border_width(scrim, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(scrim, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(scrim, 0, LV_PART_MAIN);

    lv_obj_clear_flag(scrim, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_add_event_cb(scrim, picker_scrim_cb, LV_EVENT_CLICKED, NULL);


    /* ---------------- card (theme_card(radius=sp(16))) ---------------- */

    lv_obj_t *card = lv_obj_create(scrim);

    lv_obj_set_size(card, card_w, card_h);
    lv_obj_center(card);

    /* Swallow taps on the card so only the scrim dismisses. */
    lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_set_style_bg_color(card, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(card, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(card, sc(16), LV_PART_MAIN);
    lv_obj_set_style_pad_all(card, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_row(card, sc(8), LV_PART_MAIN);

    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        card,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- head: title + close ---------------- */

    lv_obj_t *head = lv_obj_create(card);

    make_transparent(head);

    lv_obj_set_width(head, lv_pct(100));
    lv_obj_set_height(head, sc(44));
    lv_obj_set_flex_flow(head, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        head,
        LV_FLEX_ALIGN_SPACE_BETWEEN,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_clear_flag(head, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = lv_label_create(head);

    lv_label_set_text(title, def->title);

    lv_obj_set_style_text_font(title, F_PAGE_TITLE, LV_PART_MAIN);
    lv_obj_set_style_text_color(title, CLR_TEXT, LV_PART_MAIN);

    lv_obj_t *close = lv_button_create(head);

    lv_obj_set_size(close, sc(44), sc(40));

    lv_obj_set_style_bg_color(close, CLR_BTN_NEUTRAL, LV_PART_MAIN);
    lv_obj_set_style_bg_color(close, CLR_BTN_NEUTRAL_HOV, LV_STATE_HOVERED);
    lv_obj_set_style_text_color(close, CLR_BTN_TEXT, LV_PART_MAIN);
    lv_obj_set_style_radius(close, sc(10), LV_PART_MAIN);
    lv_obj_set_style_shadow_width(close, 0, LV_PART_MAIN);

    lv_obj_add_event_cb(close, picker_scrim_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *close_label = lv_label_create(close);

    lv_label_set_text(close_label, LV_SYMBOL_CLOSE);

    lv_obj_center(close_label);


    /* ---------------- options ---------------- */

    lv_obj_t *options = lv_obj_create(card);

    make_transparent(options);

    /* An explicit height rather than flex_grow: the card's own height is
     * fixed, so this is exactly the space left under the head, and a list that
     * is taller than that scrolls (controls.py does the same past 12 options). */
    lv_obj_set_width(options, lv_pct(100));
    lv_obj_set_height(options, card_h - sc(12) * 2 - sc(44) - sc(8));

    lv_obj_set_flex_flow(options, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        options,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );
    lv_obj_set_style_pad_row(options, sc(10), LV_PART_MAIN);

    /* controls.py scrolls the list past 12 options and keeps a plain frame
     * below that, so a short list never shows a useless scrollbar. */
    if(def->count > 12)
    {
        lv_obj_set_style_pad_right(options, sc(6), LV_PART_MAIN);
    }
    else
    {
        lv_obj_clear_flag(options, LV_OBJ_FLAG_SCROLLABLE);
    }

    /* One container per grid row, each row's buttons sharing the width
     * equally: this is what makes the columns line up at any panel size. */
    for(int r = 0; r < rows; r++)
    {
        lv_obj_t *row = lv_obj_create(options);

        make_transparent(row);

        lv_obj_set_width(row, lv_pct(100));
        lv_obj_set_height(row, option_h);
        lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
        lv_obj_set_style_pad_column(row, gap, LV_PART_MAIN);
        lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

        for(int c = 0; c < columns; c++)
        {
            int index = r * columns + c;

            if(index >= def->count)
            {
                /* A short last row simply stops; nothing is needed to keep
                 * the columns lined up because every option has a width. */
                continue;
            }

            const char *value = def->values[index];
            int selected = picker_is_value(def, current) &&
                           strcmp(current, value) == 0;

            lv_obj_t *btn = lv_button_create(row);

            lv_obj_set_width(btn, option_w);
            lv_obj_set_height(btn, option_h);

            lv_obj_set_style_bg_color(
                btn,
                selected ? CLR_ACCENT : CLR_BTN_NEUTRAL,
                LV_PART_MAIN
            );

            lv_obj_set_style_bg_color(
                btn,
                selected ? CLR_ACCENT_HOVER : CLR_BTN_NEUTRAL_HOV,
                LV_STATE_HOVERED
            );

            lv_obj_set_style_text_color(
                btn,
                selected ? CLR_TEXT_ON_ACCENT : CLR_BTN_TEXT,
                LV_PART_MAIN
            );

            lv_obj_set_style_radius(btn, sc(12), LV_PART_MAIN);
            lv_obj_set_style_border_width(btn, 1, LV_PART_MAIN);
            lv_obj_set_style_border_color(btn, CLR_BORDER, LV_PART_MAIN);
            lv_obj_set_style_text_font(btn, F_PICKER, LV_PART_MAIN);
            lv_obj_set_style_shadow_width(btn, 0, LV_PART_MAIN);
            lv_obj_set_style_pad_all(btn, 0, LV_PART_MAIN);

            lv_obj_add_event_cb(
                btn,
                picker_option_cb,
                LV_EVENT_CLICKED,
                NULL
            );

            lv_obj_t *label = lv_label_create(btn);

            lv_label_set_text(label, value);

            lv_obj_center(label);
        }
    }
}


/* ---------------------------------------------------------
 * SCREEN SHELL  (test_parameters.py: create_test_parameters)
 * --------------------------------------------------------- */

static void back_event_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    analyzer_ui_back();
}


/* ---------------------------------------------------------
 * TEXT METRICS
 *
 * Everything that has to fit a line of text is sized from
 * the font rather than from a number picked by eye, so a
 * bigger font or a smaller panel cannot silently clip a
 * heading. This is the one place the app asks LVGL how tall
 * a line is.
 * --------------------------------------------------------- */

static int32_t line_height(const lv_font_t *font)
{
    return lv_font_get_line_height(font);
}

/*
 * Height for a horizontal bar (a toolbar, a control strip, a footer) that
 * holds one line of `font` with `pad` design px of breathing room. Every bar
 * in the app asks for its height this way, so a bar can never be shorter than
 * the line of text inside it - which is the vertical half of the clipping fix.
 */
static int32_t bar_height(const lv_font_t *font, int32_t pad)
{
    return line_height(font) + pad;
}

/*
 * Height for a band that stacks `count` lines of `font` (plus `extra` px of
 * breathing room). A heading band that is only tall enough for its title and
 * not for the hint under it is exactly how text ends up cut in half.
 */
static int32_t stacked_height(
    const lv_font_t *font,
    int count,
    int32_t extra
)
{
    return line_height(font) * count + extra;
}

/*
 * Height of a band that shows both a title and a hint: the two line heights
 * plus the gap between them. Used by the header band, which every screen
 * shares, so no screen can be built with a header too short for its own text.
 */
static int32_t header_text_height(void)
{
    return line_height(F_PAGE_TITLE) + line_height(F_HINT) + sc(4);
}

/*
 * Builds the page frame every screen shares: the header band (back button,
 * title, one-line hint) and the content card that fills what is left. The
 * card is handed back through *content_out for the caller to fill.
 */
static lv_obj_t *create_page(
    const char *title,
    const char *hint,
    lv_obj_t **content_out
)
{
    lv_obj_t *page = lv_obj_create(lv_screen_active());

    lv_obj_set_size(page, lv_pct(100), lv_pct(100));
    lv_obj_align(page, LV_ALIGN_CENTER, 0, 0);

    lv_obj_set_style_bg_color(page, CLR_WINDOW_BG, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(page, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(page, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(page, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(page, sc(18), LV_PART_MAIN);
    lv_obj_set_style_pad_row(page, sc(10), LV_PART_MAIN);

    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        page,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_clear_flag(page, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- header band ---------------- */

    lv_obj_t *header = lv_obj_create(page);

    make_transparent(header);

    /*
     * The header's height is DERIVED from the two fonts it stacks, not chosen
     * by eye. It used to be a fixed 50 design px, which at 800x480 is 31 px -
     * less than the title line (20 px) plus the hint line (12 px) need, so the
     * hint was drawn under the content card and its bottom half was covered.
     * Deriving it means a font or panel change cannot reintroduce that: the
     * band grows with the text it has to hold.
     */
    lv_obj_set_width(header, lv_pct(100));
    lv_obj_set_height(header, header_text_height() + sc(12));
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        header,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(header, sc(14), LV_PART_MAIN);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- back button ---------------- */

    lv_obj_t *back = lv_button_create(header);

    lv_obj_set_size(back, sc(46), sc(42));

    lv_obj_set_style_bg_color(back, CLR_BTN_NEUTRAL, LV_PART_MAIN);
    lv_obj_set_style_bg_color(back, CLR_BTN_NEUTRAL_HOV, LV_STATE_HOVERED);
    lv_obj_set_style_text_color(back, CLR_BTN_TEXT, LV_PART_MAIN);
    lv_obj_set_style_radius(back, sc(10), LV_PART_MAIN);
    lv_obj_set_style_border_width(back, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(back, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_text_font(back, F_STATUS, LV_PART_MAIN);
    lv_obj_set_style_shadow_width(back, 0, LV_PART_MAIN);

    lv_obj_add_event_cb(back, back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *back_label = lv_label_create(back);

    lv_label_set_text(back_label, LV_SYMBOL_LEFT);

    lv_obj_center(back_label);


    /* ---------------- title + hint ---------------- */

    lv_obj_t *title_box = lv_obj_create(header);

    make_transparent(title_box);

    lv_obj_set_flex_grow(title_box, 1);
    lv_obj_set_flex_flow(title_box, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        title_box,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );
    lv_obj_clear_flag(title_box, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title_label = lv_label_create(title_box);

    lv_label_set_text(title_label, title);

    lv_obj_set_style_text_font(title_label, F_PAGE_TITLE, LV_PART_MAIN);
    lv_obj_set_style_text_color(title_label, CLR_TEXT, LV_PART_MAIN);

    if(hint != NULL)
    {
        lv_obj_t *hint_label = lv_label_create(title_box);

        lv_label_set_text(hint_label, hint);

        lv_obj_set_style_text_font(hint_label, F_HINT, LV_PART_MAIN);
        lv_obj_set_style_text_color(hint_label, CLR_TEXT_MUTED, LV_PART_MAIN);

        /* A hint longer than the panel wraps instead of running off the edge
         * or being cut; the band above is sized for the lines it can take. */
        lv_obj_set_width(hint_label, lv_pct(100));
        lv_label_set_long_mode(hint_label, LV_LABEL_LONG_MODE_WRAP);
    }


    /* ---------------- content card (theme_card(radius=sp(14))) ---------------- */

    lv_obj_t *card = lv_obj_create(page);

    /* flex_grow takes the height the header and the action row leave over.
     * The explicit pct(100) is here so the card's height STYLE is not
     * LV_SIZE_CONTENT: the form inside it sizes itself against the card's
     * height, and a parent that sizes from its children while its children
     * size from it does not converge (LVGL's layout loop spins on it).
     * flex_grow overrides the value for layout, so this changes nothing
     * visually - it only makes the constraint one-directional. */
    lv_obj_set_width(card, lv_pct(100));
    lv_obj_set_height(card, lv_pct(100));
    lv_obj_set_flex_grow(card, 1);

    lv_obj_set_style_bg_color(card, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(card, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(card, sc(14), LV_PART_MAIN);
    lv_obj_set_style_pad_all(card, sc(10), LV_PART_MAIN);

    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        card,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    *content_out = card;

    return page;
}


/* ---------------------------------------------------------
 * FORM ROW  (test_parameters.py: the params grid)
 *
 * One labelled line: a right-aligned label of a fixed design
 * width, then the field. Every width here is either a fixed
 * design measurement pushed through sc() or a percentage of
 * the panel - never "as wide as my content".
 *
 * That last point is the important one. A container whose
 * width is LV_SIZE_CONTENT and that holds a child sized by
 * flex_grow is a circular constraint (the parent sizes from
 * the child, the child grows into the parent) and LVGL's
 * layout loop does not converge on it - it spins forever.
 * test_parameters.py reaches for fixed design widths for the
 * same reason (232 px label column, 240 px entries), so this
 * is both the safe and the faithful choice.
 * --------------------------------------------------------- */

#define FORM_FIELD_W 300     /* field width, design px    */
#define FORM_ROW_H 68        /* row pitch, design px      */
#define FORM_FIELD_H 48      /* field height, design px   */
#define FORM_TOGGLE_W 30     /* tick box, design px       */

/* Pixel width of `text` in `font`. Used to size the label column from the
 * labels themselves instead of a guess. */
static int32_t text_width(const char *text, const lv_font_t *font)
{
    lv_point_t size;

    lv_text_get_size(&size, text, font, 0, 0, LV_COORD_MAX, (lv_text_flag_t)0);

    return size.x;
}

/* Content width available to one form row: half the card, less the page, card
 * and column gutters. */
static int32_t form_row_width(void)
{
    lv_display_t *disp = lv_display_get_default();

    int32_t panel_w = disp ?
        lv_display_get_horizontal_resolution(disp) : DESIGN_W;
    int32_t inner = panel_w - sc(18) * 2 - sc(10) * 2;

    return (inner / 2) - sc(8) * 2;
}

/*
 * The label column for a set of rows, MEASURED from the labels rather than
 * guessed at: the Tk form does exactly this (test_parameters.py sizes its
 * label columns from winfo_reqwidth with a 232 px floor and a 300 px ceiling,
 * and says why - a column that cannot grow clips its own label).
 *
 * The floor is what keeps the two halves lined up, so it is applied to the
 * whole column rather than to each label: sizing each label independently
 * would push each field to a different x, which is the other half of the same
 * problem.
 */
#define FORM_LABEL_MIN_W 250     /* floor, design px - keeps the halves aligned */

static int32_t column_label_width(const char *const *labels, int count)
{
    int32_t widest = 0;

    for(int i = 0; i < count; i++)
    {
        int32_t w = text_width(labels[i], F_ROW_LABEL);

        if(w > widest)
        {
            widest = w;
        }
    }

    int32_t needed = widest + sc(10);
    int32_t floor_w = sc(FORM_LABEL_MIN_W);

    /* The ceiling is whatever still leaves the fixed-width field its room. */
    int32_t room = form_row_width() - sc(10) - sc(FORM_FIELD_W);

    if(needed < floor_w)
    {
        needed = floor_w;
    }

    if(room > floor_w && needed > room)
    {
        needed = room;
    }

    return needed;
}

/*
 * Builds the row and its label and hands the row back for the caller to add
 * the field to, so a tick box and its companion widget share one line.
 */
static lv_obj_t *form_row(lv_obj_t *parent, const char *label_text, int32_t label_w)
{
    lv_obj_t *row = lv_obj_create(parent);

    make_transparent(row);

    lv_obj_set_width(row, lv_pct(100));
    lv_obj_set_height(row, sc(FORM_ROW_H));
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        row,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(row, sc(10), LV_PART_MAIN);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *label = lv_label_create(row);

    lv_label_set_text(label, label_text);

    lv_obj_set_width(label, label_w);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
    lv_obj_set_style_text_font(label, F_ROW_LABEL, LV_PART_MAIN);
    lv_obj_set_style_text_color(label, CLR_TEXT, LV_PART_MAIN);

    return row;
}

/* A text box. The placeholder is the value the field shows while unset and
 * is drawn in text_faint, exactly as theme.py colours placeholder_text_color. */
static lv_obj_t *field_text(lv_obj_t *row, const char *text)
{
    lv_obj_t *box = lv_textarea_create(row);

    lv_obj_set_width(box, sc(FORM_FIELD_W));
    lv_obj_set_height(box, sc(FORM_FIELD_H));

    lv_textarea_set_one_line(box, true);
    lv_textarea_set_max_length(box, 16);
    lv_textarea_set_placeholder_text(box, "");

    lv_obj_set_style_bg_color(box, CLR_SURFACE_SUNKEN, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(box, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(box, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(box, CLR_BORDER_STRONG, LV_PART_MAIN);
    lv_obj_set_style_radius(box, sc(10), LV_PART_MAIN);
    lv_obj_set_style_pad_hor(box, sc(10), LV_PART_MAIN);
    lv_obj_set_style_pad_ver(box, 0, LV_PART_MAIN);

    lv_obj_set_style_text_font(box, F_FIELD, LV_PART_MAIN);
    lv_obj_set_style_text_color(box, CLR_TEXT, LV_PART_MAIN);
    lv_obj_set_style_text_align(box, LV_TEXT_ALIGN_LEFT, LV_PART_MAIN);

    /* The cursor is the accent colour, so the focused field is obvious. */
    lv_obj_set_style_border_color(box, CLR_ACCENT, LV_STATE_FOCUSED);
    lv_obj_set_style_border_width(box, 2, LV_STATE_FOCUSED);

    if(text != NULL && text[0] != '\0')
    {
        lv_textarea_set_text(box, text);
    }

    /* Join the app-wide focus group so the SDL keyboard indev can type into
     * whichever field was tapped. Not added when there is no group, so the
     * screens stay usable on a target with no keyboard at all. */
    if(ui_group != NULL)
    {
        lv_group_add_obj(ui_group, box);
    }

    return box;
}

static void picker_field_cb(lv_event_t *e)
{
    lv_obj_t *btn = lv_event_get_target_obj(e);
    int def = (int)(intptr_t)lv_event_get_user_data(e);

    /* The value label is this button's only child, so the button carries
     * no extra state and the field cannot drift out of sync with it. */
    picker_pick_hook = NULL;
    picker_open(def, lv_obj_get_child(btn, 0));
}

/* A picker button. It reads like the Tk TouchSelect: surface_sunken while
 * unset, the chosen value once one is picked. */
static lv_obj_t *field_picker(lv_obj_t *row, int def_index, const char *value)
{
    lv_obj_t *btn = lv_button_create(row);

    lv_obj_set_width(btn, sc(FORM_FIELD_W));
    lv_obj_set_height(btn, sc(FORM_FIELD_H));

    lv_obj_set_style_bg_color(btn, CLR_SURFACE_SUNKEN, LV_PART_MAIN);
    lv_obj_set_style_bg_color(btn, CLR_BTN_NEUTRAL, LV_STATE_HOVERED);
    lv_obj_set_style_border_width(btn, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(btn, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(btn, sc(10), LV_PART_MAIN);
    lv_obj_set_style_shadow_width(btn, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_left(btn, sc(10), LV_PART_MAIN);
    lv_obj_set_style_pad_right(btn, sc(8), LV_PART_MAIN);

    lv_obj_set_flex_flow(btn, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        btn,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_add_event_cb(
        btn,
        picker_field_cb,
        LV_EVENT_CLICKED,
        (void *)(intptr_t)def_index
    );

    lv_obj_t *label = lv_label_create(btn);

    lv_label_set_text(label, value != NULL ? value : "");

    lv_obj_set_style_text_font(label, F_FIELD, LV_PART_MAIN);
    lv_obj_set_style_text_color(
        label,
        picker_is_value(&PICKERS[def_index], value) ? CLR_TEXT : CLR_TEXT_FAINT,
        LV_PART_MAIN
    );

    picker_subject_for[def_index] = label;

    return btn;
}

/*
 * A tick box (theme.py colours CTkCheckBox with tc("accent") and
 * corner_radius sp(8)). "Ticked" lives in LV_STATE_CHECKED rather than in a
 * parallel variable, so there is no second copy of the form's state.
 */
static void checkbox_apply(lv_obj_t *box, int on)
{
    lv_obj_t *tick = lv_obj_get_child(box, 0);

    if(on)
    {
        lv_obj_add_state(box, LV_STATE_CHECKED);

        lv_obj_set_style_bg_color(box, CLR_ACCENT, LV_PART_MAIN);
        lv_obj_set_style_border_color(box, CLR_ACCENT, LV_PART_MAIN);

        if(tick != NULL)
        {
            lv_obj_remove_flag(tick, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_text_color(tick, CLR_TEXT_ON_ACCENT, LV_PART_MAIN);
        }
    }
    else
    {
        lv_obj_remove_state(box, LV_STATE_CHECKED);

        lv_obj_set_style_bg_color(box, CLR_SURFACE, LV_PART_MAIN);
        lv_obj_set_style_border_color(box, CLR_BORDER_STRONG, LV_PART_MAIN);

        if(tick != NULL)
        {
            lv_obj_add_flag(tick, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

/* One tick box plus the widget it reveals. Only one TEST form is alive at a
 * time, so a small static table is all the linkage that is needed - no
 * per-widget allocation just to remember a pointer. */
#define MAX_TOGGLES 3

static struct
{
    lv_obj_t *box;
    lv_obj_t *extra;
} toggle_link[MAX_TOGGLES];

static void toggle_event_cb(lv_event_t *e)
{
    lv_obj_t *box = lv_event_get_target_obj(e);
    int index = (int)(intptr_t)lv_event_get_user_data(e);
    int on = lv_obj_has_state(box, LV_STATE_CHECKED);

    checkbox_apply(box, on);

    if(index < 0 || index >= MAX_TOGGLES)
    {
        return;
    }

    if(toggle_link[index].extra != NULL)
    {
        if(on)
        {
            lv_obj_remove_flag(toggle_link[index].extra, LV_OBJ_FLAG_HIDDEN);
        }
        else
        {
            lv_obj_add_flag(toggle_link[index].extra, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

static lv_obj_t *field_checkbox(lv_obj_t *row, int slot, int checked)
{
    lv_obj_t *box = lv_button_create(row);

    lv_obj_set_size(box, sc(FORM_TOGGLE_W), sc(FORM_TOGGLE_W));

    lv_obj_set_style_bg_opa(box, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(box, 1, LV_PART_MAIN);
    lv_obj_set_style_radius(box, sc(8), LV_PART_MAIN);
    lv_obj_set_style_shadow_width(box, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(box, 0, LV_PART_MAIN);

    lv_obj_t *tick = lv_label_create(box);

    lv_label_set_text(tick, LV_SYMBOL_OK);

    lv_obj_set_style_text_font(tick, F_FIELD, LV_PART_MAIN);

    lv_obj_center(tick);

    checkbox_apply(box, checked);

    if(slot >= 0 && slot < MAX_TOGGLES)
    {
        toggle_link[slot].box = box;
        toggle_link[slot].extra = NULL;

        lv_obj_add_event_cb(
            box,
            toggle_event_cb,
            LV_EVENT_CLICKED,
            (void *)(intptr_t)slot
        );
    }

    return box;
}

/*
 * Row helpers. Each one fills the control cell of a form row and returns a
 * pointer to what it made, so a screen reads as a list of fields.
 */
static lv_obj_t *add_text_row(
    lv_obj_t *column,
    const char *label_text,
    int32_t label_w,
    const char *value
)
{
    return field_text(form_row(column, label_text, label_w), value);
}

static lv_obj_t *add_picker_row(
    lv_obj_t *column,
    const char *label_text,
    int32_t label_w,
    int def_index,
    const char *value
)
{
    return field_picker(
        form_row(column, label_text, label_w),
        def_index,
        value
    );
}


/* ---------------------------------------------------------
 * ACTION ROW
 *
 * RUN = go (blue, so it never reads as SAVE), SAVE = keep
 * (green), DELETE = destructive (red), CANCEL = back out
 * (neutral). test_parameters.py gives each meaning one
 * accent, and this keeps that contract.
 * --------------------------------------------------------- */

enum
{
    ACT_RUN = 0,
    ACT_SAVE,
    ACT_DELETE,
    ACT_CANCEL
};

typedef struct
{
    const char *text;
    int action;
} action_def_t;

static const action_def_t ACTIONS[] =
{
    { "RUN",    ACT_RUN    },
    { "SAVE",   ACT_SAVE   },
    { "DELETE", ACT_DELETE },
    { "CANCEL", ACT_CANCEL }
};

#define ACTION_COUNT ARRAY_LEN(ACTIONS)

static void action_event_cb(lv_event_t *e)
{
    int action = (int)(intptr_t)lv_event_get_user_data(e);

    switch(action)
    {
        case ACT_RUN:
            /* The test has been configured: run it. The run is watched on the
             * MEASUREMENT screen, so that is where RUN leads (test_screen.py
             * and test_parameters.py both go to show_measurement_screen). */
            analyzer_ui_open(ANALYZER_SCREEN_MEASUREMENT);
            break;

        case ACT_CANCEL:
            analyzer_ui_go_home();
            break;

        default:
            /* SAVE keeps what is on screen; DELETE discards it. Neither
             * navigates, so both stay on the form - this is what the
             * Tkinter handlers do once their confirmation step is done. */
            if(verbose_nav)
            {
                printf(
                    "[action] %s (%s)\n",
                    ACTIONS[action].text,
                    action == ACT_SAVE ? "kept" : "discarded"
                );
            }
            break;
    }
}

static void create_action_row(lv_obj_t *page, const int *actions, int count)
{
    lv_obj_t *row = lv_obj_create(page);

    make_transparent(row);

    lv_obj_set_width(row, lv_pct(100));
    lv_obj_set_height(row, sc(56));
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(row, sc(12), LV_PART_MAIN);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

    for(int i = 0; i < count; i++)
    {
        int action = actions[i];

        uint32_t bg;
        uint32_t hover;
        uint32_t fg;

        switch(action)
        {
            case ACT_RUN:
                bg = HEX_RUN_BTN;
                hover = HEX_RUN_BTN_HOVER;
                fg = HEX_ON_RUN_BTN;
                break;

            case ACT_SAVE:
                bg = HEX_SUCCESS;
                hover = HEX_SUCCESS;
                fg = HEX_ON_SUCCESS;
                break;

            case ACT_DELETE:
                bg = HEX_DANGER;
                hover = HEX_DANGER;
                fg = HEX_ON_DANGER;
                break;

            default:
                bg = HEX_BTN_NEUTRAL;
                hover = HEX_BTN_NEUTRAL_HOVER;
                fg = HEX_BTN_TEXT;
                break;
        }

        lv_obj_t *btn = lv_button_create(row);

        lv_obj_set_flex_grow(btn, 1);
        lv_obj_set_height(btn, lv_pct(100));

        lv_obj_set_style_bg_color(btn, lv_color_hex(bg), LV_PART_MAIN);
        lv_obj_set_style_bg_color(btn, lv_color_hex(hover), LV_STATE_HOVERED);
        lv_obj_set_style_text_color(btn, lv_color_hex(fg), LV_PART_MAIN);
        lv_obj_set_style_radius(btn, sc(12), LV_PART_MAIN);
        lv_obj_set_style_text_font(btn, F_ACTION, LV_PART_MAIN);
        lv_obj_set_style_shadow_width(btn, 0, LV_PART_MAIN);

        lv_obj_add_event_cb(
            btn,
            action_event_cb,
            LV_EVENT_CLICKED,
            (void *)(intptr_t)action
        );

        lv_obj_t *label = lv_label_create(btn);

        lv_label_set_text(label, ACTIONS[action].text);

        lv_obj_center(label);
    }
}


/* =========================================================
 * TEST  ->  "Test Parameters"  (test_parameters.py)
 *
 * The reference screenshots define this screen, so it
 * follows them field for field: the same twelve rows in the
 * same two-column order, the same three tick boxes with the
 * widget each one reveals, and the same four action buttons.
 * The values the reference shows ("ee", "EP", "340nm", ...)
 * are seeded so the render can be compared against it
 * directly - they are what is on the panel in the photos.
 * ========================================================= */

/* Toggle slots for this screen (Blank, Factor, QC). */
enum
{
    TOGGLE_BLANK = 0,
    TOGGLE_FACTOR,
    TOGGLE_QC
};

/*
 * The twelve rows, in the order test_parameters.py lays them out: the list is
 * read in pairs, so index 0/1 make the first line, 2/3 the second, and so on.
 * These two arrays are also what the label columns are measured from.
 */
static const char *const TEST_LEFT_LABELS[] =
{
    "Test Name", "Method", "Wavelength", "Blank", "Delay Time (s)", "Unit"
};

static const char *const TEST_RIGHT_LABELS[] =
{
    "Low (Range)", "High (Range)", "Factor",
    "Std Concentration", "Measuring Time", "QC"
};

#define TEST_ROWS ARRAY_LEN(TEST_LEFT_LABELS)

static lv_obj_t *create_test_screen(void)
{
    lv_obj_t *card;
    lv_obj_t *page = create_page(
        "Test Parameters - ee",
        "Fill the fields, then SAVE. Tap a box to type; tap a list to choose.",
        &card
    );

    /* Stale links would point at freed objects: the page that owned them was
     * deleted before this one was built (see analyzer_ui_open). */
    for(int i = 0; i < MAX_TOGGLES; i++)
    {
        toggle_link[i].box = NULL;
        toggle_link[i].extra = NULL;
    }

    for(int i = 0; i < PICK_COUNT; i++)
    {
        picker_subject_for[i] = NULL;
    }

    /* The two halves of the form: grid columns 0/1 and 2/3 in
     * test_parameters.py. Half the card each, so they stay aligned at any
     * panel width, and the gutter is the columns' own horizontal padding so
     * two 50%% children still add up to 100%% of the card. */
    lv_obj_t *left = lv_obj_create(card);
    lv_obj_t *right = lv_obj_create(card);

    lv_obj_t *columns[2] = { left, right };

    for(int i = 0; i < 2; i++)
    {
        make_transparent(columns[i]);

        lv_obj_set_width(columns[i], lv_pct(50));
        lv_obj_set_height(columns[i], lv_pct(100));
        lv_obj_set_style_pad_hor(columns[i], sc(8), LV_PART_MAIN);
        lv_obj_set_flex_flow(columns[i], LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            columns[i],
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_START,
            LV_FLEX_ALIGN_START
        );
        lv_obj_clear_flag(columns[i], LV_OBJ_FLAG_SCROLLABLE);
    }    /* Both label columns are measured, so the two fields on a line start at
     * the same x and no label is cut or wrapped. */
    int32_t lw_left = column_label_width(TEST_LEFT_LABELS, TEST_ROWS);
    int32_t lw_right = column_label_width(TEST_RIGHT_LABELS, TEST_ROWS);


    /* ---------------- left column ---------------- */

    add_text_row(left, "Test Name", lw_left, "ee");
    add_picker_row(left, "Method", lw_left, PICK_METHOD, "EP");
    add_picker_row(left, "Wavelength", lw_left, PICK_WAVELENGTH, "340nm");

    /* Blank: the tick box reveals the R.Blank / S.Blank picker. */
    {
        lv_obj_t *row = form_row(left, "Blank", lw_left);

        field_checkbox(row, TOGGLE_BLANK, 0);

        toggle_link[TOGGLE_BLANK].extra = field_picker(row, PICK_BLANK, NULL);

        lv_obj_add_flag(toggle_link[TOGGLE_BLANK].extra, LV_OBJ_FLAG_HIDDEN);
    }

    add_text_row(left, "Delay Time (s)", lw_left, "0.0");

    /* Unit is unset on the reference panel, so the box is empty rather than
     * showing the field's own name. */
    add_picker_row(left, "Unit", lw_left, PICK_UNIT, NULL);


    /* ---------------- right column ---------------- */

    add_text_row(right, "Low (Range)", lw_right, "0.0");
    add_text_row(right, "High (Range)", lw_right, "0.0");

    /* Factor: the tick box reveals the factor value box beside it. */
    {
        lv_obj_t *row = form_row(right, "Factor", lw_right);

        field_checkbox(row, TOGGLE_FACTOR, 0);

        toggle_link[TOGGLE_FACTOR].extra = field_text(row, NULL);

        lv_obj_add_flag(toggle_link[TOGGLE_FACTOR].extra, LV_OBJ_FLAG_HIDDEN);
    }

    add_text_row(right, "Std Concentration", lw_right, "5.0");
    add_text_row(right, "Measuring Time", lw_right, "5.0");

    /* QC: the tick box reveals its "QC values" button (test_parameters.py:
     * show_qc_input_popup). */
    {
        lv_obj_t *row = form_row(right, "QC", lw_right);

        field_checkbox(row, TOGGLE_QC, 0);

        lv_obj_t *values = lv_button_create(row);

        lv_obj_set_width(values, sc(FORM_FIELD_W));
        lv_obj_set_height(values, sc(FORM_FIELD_H));
        lv_obj_set_style_bg_color(values, CLR_BTN_NEUTRAL, LV_PART_MAIN);
        lv_obj_set_style_bg_color(values, CLR_BTN_NEUTRAL_HOV, LV_STATE_HOVERED);
        lv_obj_set_style_text_color(values, CLR_BTN_TEXT, LV_PART_MAIN);
        lv_obj_set_style_radius(values, sc(10), LV_PART_MAIN);
        lv_obj_set_style_border_width(values, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(values, CLR_BORDER, LV_PART_MAIN);
        lv_obj_set_style_text_font(values, F_ACTION, LV_PART_MAIN);
        lv_obj_set_style_shadow_width(values, 0, LV_PART_MAIN);

        /* The QC dialog is not ported yet, so this one is deliberately not
         * clickable: a button that visibly does nothing is worse than one
         * that is plainly absent. */
        lv_obj_remove_flag(values, LV_OBJ_FLAG_CLICKABLE);

        lv_obj_t *label = lv_label_create(values);

        lv_label_set_text(label, "QC values");

        lv_obj_center(label);

        toggle_link[TOGGLE_QC].extra = values;

        lv_obj_add_flag(values, LV_OBJ_FLAG_HIDDEN);
    }


    /* ---------------- action row ---------------- */

    static const int test_actions[ACTION_COUNT] =
    {
        ACT_RUN, ACT_SAVE, ACT_DELETE, ACT_CANCEL
    };


    create_action_row(page, test_actions, ACTION_COUNT);

    return page;
}


/* =========================================================
 * TEST LIBRARY
 *
 * The instrument's tests, as the reference photos show them
 * in the LIST OF TESTS grid: a name and the method it runs
 * under. The method is the tile's colour (test_screen.py:
 * method_colors), so the toolbar above the grid doubles as
 * the colour legend - a tile's colour always means the same
 * method, here and on the RESULTS screen.
 * ========================================================= */

static const char *const METHOD_NAMES[METHOD_COUNT] =
{
    "TP", "EP", "Kinetic"
};

typedef struct
{
    const char *name;
    int method;
} test_row_t;

static const test_row_t TESTS[] =
{
    { "ee",              METHOD_EP      },
    { "Glucose",         METHOD_TP      },
    { "Cholesterol",     METHOD_EP      },
    { "Creatinine",      METHOD_KINETIC },
    { "Urea",            METHOD_TP      },
    { "Uric Acid",       METHOD_EP      },
    { "Total Protein",   METHOD_TP      },
    { "Albumin",         METHOD_EP      },
    { "Bilirubin",       METHOD_KINETIC },
    { "AST (GOT)",       METHOD_TP      },
    { "ALT (GPT)",       METHOD_TP      },
    { "ALP",             METHOD_KINETIC },
    { "Calcium",         METHOD_EP      },
    { "Phosphorus",      METHOD_EP      },
    { "Magnesium",       METHOD_TP      },
    { "Amylase",         METHOD_KINETIC },
    { "Lipase",          METHOD_KINETIC },
    { "LDH",             METHOD_KINETIC },
    { "CK-MB",           METHOD_KINETIC },
    { "HbA1c",           METHOD_EP      },
    { "Total Bilirubin", METHOD_KINETIC },
    { "Direct Bili",     METHOD_KINETIC },
    { "Iron",            METHOD_EP      },
    { "Zinc",            METHOD_EP      },
    { "Copper",          METHOD_EP      },
    { "Sodium",          METHOD_TP      },
    { "Potassium",       METHOD_TP      },
    { "Chloride",        METHOD_TP      },
    { "Bicarbonate",     METHOD_TP      },
    { "Total CO2",       METHOD_TP      },
    { "Triglyceride",    METHOD_EP      },
    { "HDL",             METHOD_EP      },
    { "LDL",             METHOD_EP      },
    { "VLDL",            METHOD_EP      },
    { "HDL Ratio",       METHOD_EP      },
    { "Creatine",        METHOD_KINETIC },
    { "Lactate",         METHOD_KINETIC },
    { "Ammonia",         METHOD_KINETIC },
    { "Ethanol",         METHOD_KINETIC },
    { "Salicylate",      METHOD_KINETIC },
    { "Acetaminophen",   METHOD_KINETIC },
    { "Theophylline",    METHOD_EP      },
    { "Vancomycin",      METHOD_EP      },
    { "Gentamicin",      METHOD_EP      }
};

#define TESTS_COUNT ARRAY_LEN(TESTS)

/* Which test the MEASUREMENT screen is running (index into TESTS). Set when a
 * tile is tapped, so the screen can name it in its own title. */
static int measurement_test = 0;

/* A stable, plausible result count so the RESULTS meta line reads like the
 * reference without a database behind it. */
static int test_result_count(int index)
{
    return (index * 13) % 37;
}


/*
 * 'Page : 1 2 3' - the bar both list screens put under their grid
 * (test_screen.py: build_page_bar). Empty for a single page, exactly as the
 * Tk helper returns an empty frame there.
 *
 * The buttons carry the page number as their event data, so one callback
 * serves every page on every screen.
 */
static lv_obj_t *build_page_bar(
    lv_obj_t *parent,
    int current,
    int total,
    lv_event_cb_t cb
)
{
    lv_obj_t *bar = lv_obj_create(parent);

    make_transparent(bar);

    lv_obj_set_width(bar, lv_pct(100));
    lv_obj_set_height(bar, bar_height(F_TILE, sc(16)));
    lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        bar,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(bar, sc(4), LV_PART_MAIN);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);

    if(total <= 1)
    {
        return bar;
    }

    lv_obj_t *prefix = make_label(bar, "Page :", F_TILE, HEX_TEXT_MUTED);

    lv_obj_set_style_pad_right(prefix, sc(6), LV_PART_MAIN);

    for(int p = 1; p <= total; p++)
    {
        char text[8];

        lv_snprintf(text, sizeof(text), "%d", p);

        int selected = (p == current);

        lv_obj_t *btn = make_button(
            bar,
            text,
            F_TILE,
            selected ? HEX_ACCENT : HEX_BTN_NEUTRAL,
            selected ? HEX_ACCENT_HOVER : HEX_BTN_NEUTRAL_HOVER,
            selected ? HEX_TEXT_ON_ACCENT : HEX_BTN_TEXT,
            bar_height(F_TILE, sc(16)),
            cb,
            (void *)(intptr_t)p
        );

        lv_obj_set_width(btn, sc(52));
    }

    return bar;
}


/* =========================================================
 * TEST  ->  "LIST OF TESTS"  (test_screen.py)
 *
 * The reference photo, top to bottom: header (back, title,
 * hint, Create Test), a method-filter toolbar that is also
 * the colour legend, a 5 x 4 grid of method-tinted tiles,
 * the page bar, and Back to menu / Edit Test.
 *
 * Filter, sort, page and edit-mode are static state, so they
 * survive the rebuild that changing any of them triggers -
 * exactly how test_screen.py keeps them on self and calls
 * show_test_screen() again.
 * ========================================================= */

#define LIST_COLUMNS 5
#define LIST_ROWS 4
#define LIST_PER_PAGE (LIST_COLUMNS * LIST_ROWS)

static int list_filter_method = -1;     /* -1 = no filter        */
static int list_sort_desc = 0;          /* 0 = A-Z, 1 = Z-A      */
static int list_page = 1;
static int list_edit_mode = 0;
static int list_order[TESTS_COUNT];
static int list_order_count = 0;

/* Insertion sort of list_order[start .. start + count) by test name. */
static void list_sort_run(int start, int count)
{
    for(int i = start + 1; i < start + count; i++)
    {
        int key = list_order[i];
        int j = i - 1;

        while(j >= start)
        {
            int cmp = strcmp(TESTS[list_order[j]].name, TESTS[key].name);

            if(list_sort_desc ? (cmp <= 0) : (cmp >= 0))
            {
                break;
            }

            list_order[j + 1] = list_order[j];
            j--;
        }

        list_order[j + 1] = key;
    }
}

/*
 * test_screen.py: sort_tests - with a method filter the matching tests come
 * first, then the rest, each group sorted by name in the chosen direction.
 * Without a filter everything is sorted as one group.
 */
static void list_compute_order(void)
{
    int n = 0;

    if(list_filter_method < 0)
    {
        for(int i = 0; i < TESTS_COUNT; i++)
        {
            list_order[n++] = i;
        }

        list_sort_run(0, n);
    }
    else
    {
        for(int i = 0; i < TESTS_COUNT; i++)
        {
            if(TESTS[i].method == list_filter_method)
            {
                list_order[n++] = i;
            }
        }

        list_sort_run(0, n);

        int other = n;

        for(int i = 0; i < TESTS_COUNT; i++)
        {
            if(TESTS[i].method != list_filter_method)
            {
                list_order[n++] = i;
            }
        }

        list_sort_run(other, n - other);
    }

    list_order_count = n;
}

static void list_refresh(void)
{
    /* Rebuild in place: the history is untouched (open_page, not open), so a
     * filter or a page change is not a navigation step. */
    open_page(ANALYZER_SCREEN_TEST_LIST);
}

static void list_filter_cb(lv_event_t *e)
{
    int method = (int)(intptr_t)lv_event_get_user_data(e);

    /* test_screen.py: set_method_filter toggles the same chip back off. */
    list_filter_method = (list_filter_method == method) ? -1 : method;
    list_page = 1;

    list_refresh();
}

static void list_sort_cb(lv_event_t *e)
{
    list_sort_desc = (int)(intptr_t)lv_event_get_user_data(e);
    list_page = 1;

    list_refresh();
}

static void list_reset_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    list_filter_method = -1;
    list_sort_desc = 0;
    list_page = 1;

    list_refresh();
}

static void list_page_cb(lv_event_t *e)
{
    list_page = (int)(intptr_t)lv_event_get_user_data(e);

    list_refresh();
}

static void list_edit_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    list_edit_mode = !list_edit_mode;

    list_refresh();
}

static void list_tile_cb(lv_event_t *e)
{
    /* test_screen.py: handle_test_click - in Edit mode a tile opens the
     * parameters, otherwise it goes straight to the measurement. */
    measurement_test = (int)(intptr_t)lv_event_get_user_data(e);

    if(list_edit_mode)
    {
        analyzer_ui_open(ANALYZER_SCREEN_PARAMETERS);
    }
    else
    {
        analyzer_ui_open(ANALYZER_SCREEN_MEASUREMENT);
    }
}

static void list_method_chip(lv_obj_t *parent, int method)
{
    int selected = (list_filter_method == method);

    lv_obj_t *chip = make_button(
        parent,
        METHOD_NAMES[method],
        F_TILE,
        METHOD_FILL_HEX[method],
        METHOD_BORDER_HEX[method],
        METHOD_TEXT_HEX[method],
        bar_height(F_TILE, sc(18)),
        list_filter_cb,
        (void *)(intptr_t)method
    );

    lv_obj_set_width(chip, sc(96));

    /* A tint needs an edge: 1 px normally, a 2 px dark ring when it is the
     * active filter (test_screen.py draws it the same way). */
    lv_obj_set_style_border_width(chip, selected ? 2 : 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(
        chip,
        selected ? CLR_TEXT : CLR_METHOD_BORDER(method),
        LV_PART_MAIN
    );
}

static lv_obj_t *create_test_list_screen(void)
{
    lv_obj_t *card;
    lv_obj_t *page = create_page(
        "LIST OF TESTS",
        "Tap a test to measure it, or Edit Test to change it",
        &card
    );

    card_as_column(card);

    list_compute_order();


    /* ---------------- toolbar: filter + sort ---------------- */

    lv_obj_t *toolbar = lv_obj_create(card);

    make_transparent(toolbar);

    lv_obj_set_width(toolbar, lv_pct(100));
    lv_obj_set_height(toolbar, bar_height(F_TILE, sc(18)));
    lv_obj_set_flex_flow(toolbar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        toolbar,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(toolbar, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(toolbar, LV_OBJ_FLAG_SCROLLABLE);

    make_label(toolbar, "Filter:", F_TILE, HEX_TEXT_MUTED);

    for(int m = 0; m < METHOD_COUNT; m++)
    {
        list_method_chip(toolbar, m);
    }

    /* A spacer so the sort controls sit at the right edge. */
    lv_obj_t *spacer = lv_obj_create(toolbar);

    make_transparent(spacer);

    /* Explicit width before flex_grow, so the constraint stays one-directional
     * (see the note on create_page's card). */
    lv_obj_set_width(spacer, sc(10));
    lv_obj_set_height(spacer, sc(10));
    lv_obj_set_flex_grow(spacer, 1);

    make_label(toolbar, "Sort:", F_TILE, HEX_TEXT_MUTED);

    for(int dir = 0; dir < 2; dir++)
    {
        int selected = (list_sort_desc == dir);

        lv_obj_t *btn = make_button(
            toolbar,
            dir == 0 ? "A-Z" : "Z-A",
            F_TILE,
            selected ? HEX_ACCENT : HEX_BTN_NEUTRAL,
            selected ? HEX_ACCENT_HOVER : HEX_BTN_NEUTRAL_HOVER,
            selected ? HEX_TEXT_ON_ACCENT : HEX_BTN_TEXT,
            bar_height(F_TILE, sc(18)),
            list_sort_cb,
            (void *)(intptr_t)dir
        );

        lv_obj_set_width(btn, sc(84));
    }

    if(list_filter_method >= 0 || list_sort_desc != 0)
    {
        lv_obj_t *reset = make_button(
            toolbar,
            "Reset",
            F_TILE,
            HEX_BTN_NEUTRAL,
            HEX_BTN_NEUTRAL_HOVER,
            HEX_BTN_TEXT,
            bar_height(F_TILE, sc(18)),
            list_reset_cb,
            NULL
        );

        lv_obj_set_width(reset, sc(84));
    }


    /* ---------------- the grid ---------------- */

    lv_obj_t *grid = lv_obj_create(card);

    make_transparent(grid);

    /* Explicit size before flex_grow: a grid whose height is LV_SIZE_CONTENT
     * and whose children stretch would size itself from those children (see
     * the note on create_page's card). */
    lv_obj_set_width(grid, lv_pct(100));
    lv_obj_set_height(grid, lv_pct(100));
    lv_obj_set_flex_grow(grid, 1);

    lv_obj_set_style_pad_all(grid, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_column(grid, sc(6), LV_PART_MAIN);
    lv_obj_set_style_pad_row(grid, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(grid, LV_OBJ_FLAG_SCROLLABLE);

    static int32_t list_cols[LIST_COLUMNS + 1] =
    {
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_FR(1),
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST
    };

    static int32_t list_row_dsc[LIST_ROWS + 1] =
    {
        LV_GRID_FR(1), LV_GRID_FR(1),
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST
    };

    lv_obj_set_grid_dsc_array(grid, list_cols, list_row_dsc);

    int total_pages = (list_order_count + LIST_PER_PAGE - 1) / LIST_PER_PAGE;

    if(total_pages < 1)
    {
        total_pages = 1;
    }

    if(list_page > total_pages)
    {
        list_page = total_pages;
    }

    if(list_page < 1)
    {
        list_page = 1;
    }

    int start = (list_page - 1) * LIST_PER_PAGE;
    int shown = list_order_count - start;

    if(shown > LIST_PER_PAGE)
    {
        shown = LIST_PER_PAGE;
    }

    if(shown <= 0)
    {
        /* test_screen.py: the empty state, centred over the whole grid. */
        lv_obj_t *empty = make_label(
            grid,
            "No tests yet.\nUse Create Test to add the first one.",
            F_TILE,
            HEX_TEXT_MUTED
        );

        lv_obj_set_style_text_align(empty, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        lv_obj_set_grid_cell(
            empty,
            LV_GRID_ALIGN_CENTER, 0, LIST_COLUMNS,
            LV_GRID_ALIGN_CENTER, 0, LIST_ROWS
        );
    }

    for(int i = 0; i < shown; i++)
    {
        int test_index = list_order[start + i];
        int method = TESTS[test_index].method;

        lv_obj_t *tile = make_button(
            grid,
            TESTS[test_index].name,
            F_TILE,
            METHOD_FILL_HEX[method],
            METHOD_BORDER_HEX[method],
            METHOD_TEXT_HEX[method],
            0,
            list_tile_cb,
            (void *)(intptr_t)test_index
        );

        /* 1 px edge in the method's mid tone: what makes a tinted tile read
         * as a tile against the pale window behind it. */
        lv_obj_set_style_border_width(tile, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(tile, CLR_METHOD_BORDER(method), LV_PART_MAIN);
        lv_obj_set_style_radius(tile, sc(12), LV_PART_MAIN);
        lv_obj_set_style_pad_hor(tile, sc(4), LV_PART_MAIN);

        lv_obj_set_grid_cell(
            tile,
            LV_GRID_ALIGN_STRETCH, i % LIST_COLUMNS, 1,
            LV_GRID_ALIGN_STRETCH, i / LIST_COLUMNS, 1
        );
    }


    /* ---------------- page bar ---------------- */

    build_page_bar(card, list_page, total_pages, list_page_cb);


    /* ---------------- bottom bar ---------------- */

    lv_obj_t *bottom = lv_obj_create(card);

    make_transparent(bottom);

    lv_obj_set_width(bottom, lv_pct(100));
    lv_obj_set_height(bottom, bar_height(F_ACTION, sc(22)));
    lv_obj_set_flex_flow(bottom, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        bottom,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(bottom, sc(10), LV_PART_MAIN);
    lv_obj_clear_flag(bottom, LV_OBJ_FLAG_SCROLLABLE);

    /* Widths are explicit halves rather than flex_grow: two 49%% children plus
     * their gutter always add up to less than the bar, at any panel size. */
    lv_obj_t *to_menu = make_button(
        bottom,
        "Back to menu",
        F_ACTION,
        HEX_BTN_NEUTRAL,
        HEX_BTN_NEUTRAL_HOVER,
        HEX_BTN_TEXT,
        0,
        home_event_cb,
        NULL
    );

    lv_obj_set_width(to_menu, lv_pct(49));

    lv_obj_t *edit = make_button(
        bottom,
        list_edit_mode ? "Edit Test (on) - pick a test" : "Edit Test",
        F_ACTION,
        list_edit_mode ? HEX_WARNING : HEX_BTN_NEUTRAL,
        list_edit_mode ? HEX_WARNING : HEX_BTN_NEUTRAL_HOVER,
        list_edit_mode ? HEX_TEXT : HEX_BTN_TEXT,
        0,
        list_edit_cb,
        NULL
    );

    lv_obj_set_width(edit, lv_pct(49));

    return page;
}


/* =========================================================
 * RESULT  ->  "RESULTS"  (results.py: show_result_screen)
 *
 * Header, a filter card (Filter by Test / Filter by Date),
 * a 5 x 4 grid of result cards - each a method-tinted test
 * button over a "METHOD · N result(s)" meta line - the page
 * bar, and five action buttons.
 *
 * Unlike the TEST list, a result card opens the results TABLE
 * for that test (results.py: select_result_test ->
 * show_test_results).
 * ========================================================= */

static char result_test_filter[32] = "All tests";
static char result_date_filter[32] = "All dates";
static int result_page = 1;
static int result_qc_mode = 0;
static int result_test_choice = 0;      /* index into the built value list */
static int result_test_shown[TESTS_COUNT];
static int result_test_shown_count = 0;

#define RESULT_FILTER_MAX (TESTS_COUNT + 1)

static const char *result_filter_values[RESULT_FILTER_MAX];
static picker_def_t result_filter_def;

static const char *const RESULT_DATES[] =
{
    "All dates", "2026-09-30", "2026-09-29", "2026-09-28", "2026-09-27"
};

static const picker_def_t RESULT_DATE_DEF =
{
    "Filter by date", RESULT_DATES, ARRAY_LEN(RESULT_DATES)
};

/* Build the runtime value list for the "Filter by Test" picker: the test
 * library plus a leading All tests, with no duplicated string table. */
static void result_build_filter(void)
{
    result_filter_values[0] = "All tests";

    for(int i = 0; i < TESTS_COUNT; i++)
    {
        result_filter_values[i + 1] = TESTS[i].name;
    }

    result_filter_def.title = "Filter by test";
    result_filter_def.values = (const char *const *)result_filter_values;
    result_filter_def.count = TESTS_COUNT + 1;
}

/*
 * The tests the RESULT screen shows, after both filters
 * (results.py: the date filter narrows the names, then the test filter picks
 * one out of them).
 */
static void result_compute_shown(void)
{
    result_test_shown_count = 0;

    for(int i = 0; i < TESTS_COUNT; i++)
    {
        if(result_test_filter[0] != '\0' &&
           strcmp(result_test_filter, "All tests") != 0 &&
           strcmp(result_test_filter, TESTS[i].name) != 0)
        {
            continue;
        }

        result_test_shown[result_test_shown_count++] = i;
    }
}

static void result_refresh(void)
{
    open_page(ANALYZER_SCREEN_RESULTS);
}

static void result_test_picked(const char *value)
{
    lv_snprintf(result_test_filter, sizeof(result_test_filter), "%s", value);
    result_page = 1;

    result_refresh();
}

static void result_date_picked(const char *value)
{
    lv_snprintf(result_date_filter, sizeof(result_date_filter), "%s", value);
    result_page = 1;

    result_refresh();
}

static void result_clear_filters_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    lv_snprintf(result_test_filter, sizeof(result_test_filter), "All tests");
    lv_snprintf(result_date_filter, sizeof(result_date_filter), "All dates");
    result_page = 1;

    result_refresh();
}

static void result_filter_test_cb(lv_event_t *e)
{
    lv_obj_t *btn = lv_event_get_target_obj(e);

    picker_pick_hook = result_test_picked;
    picker_open_def(&result_filter_def, lv_obj_get_child(btn, 0));
}

static void result_filter_date_cb(lv_event_t *e)
{
    lv_obj_t *btn = lv_event_get_target_obj(e);

    picker_pick_hook = result_date_picked;
    picker_open_def(&RESULT_DATE_DEF, lv_obj_get_child(btn, 0));
}

static void result_page_cb(lv_event_t *e)
{
    result_page = (int)(intptr_t)lv_event_get_user_data(e);

    result_refresh();
}

static void result_qc_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    result_qc_mode = !result_qc_mode;

    if(verbose_nav)
    {
        printf(
            "[results] QC mode %s\n",
            result_qc_mode ? "ON - pick a test for its QC data" : "OFF"
        );
    }

    result_refresh();
}

static void result_parameter_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    analyzer_ui_open(ANALYZER_SCREEN_PARAMETERS);
}

static void result_log_cb(lv_event_t *e)
{
    /* results.py: handle_result_button - Report / Std. / Com. only raise a
     * notification in the original. Logging is the port's equivalent until
     * those views exist; the button still does what the reference does. */
    printf("[results] %s: not implemented yet\n", (const char *)lv_event_get_user_data(e));
}

static void result_tile_cb(lv_event_t *e)
{
    int index = (int)(intptr_t)lv_event_get_user_data(e);

    if(result_qc_mode)
    {
        printf("[results] QC data for %s\n", TESTS[index].name);
        return;
    }

    measurement_test = index;

    analyzer_ui_open(ANALYZER_SCREEN_RESULT_DETAIL);
}

static lv_obj_t *result_filter_picker(
    lv_obj_t *parent,
    const char *value,
    int32_t width,
    lv_event_cb_t cb
)
{
    lv_obj_t *btn = make_button(
        parent,
        value,
        F_PICKER,
        HEX_SURFACE_SUNKEN,
        HEX_BTN_NEUTRAL_HOVER,
        HEX_TEXT,
        bar_height(F_PICKER, sc(16)),
        cb,
        NULL
    );

    lv_obj_set_width(btn, width);
    lv_obj_set_style_border_color(btn, CLR_BORDER_STRONG, LV_PART_MAIN);

    return btn;
}

static lv_obj_t *create_results_screen(void)
{
    lv_obj_t *card;
    lv_obj_t *page = create_page(
        "RESULTS",
        "Select a test to view its measurement results",
        &card
    );

    card_as_column(card);

    result_build_filter();
    result_compute_shown();


    /* ---------------- filter card ---------------- */

    lv_obj_t *filter_card = lv_obj_create(card);

    lv_obj_set_width(filter_card, lv_pct(100));
    lv_obj_set_height(filter_card, bar_height(F_PICKER, sc(30)));

    lv_obj_set_style_bg_color(filter_card, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(filter_card, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(filter_card, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(filter_card, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(filter_card, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_all(filter_card, sc(6), LV_PART_MAIN);

    lv_obj_set_flex_flow(filter_card, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        filter_card,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(filter_card, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(filter_card, LV_OBJ_FLAG_SCROLLABLE);

    make_label(filter_card, "Filter by Test:", F_ROW_LABEL, HEX_TEXT);

    result_filter_picker(
        filter_card,
        result_test_filter,
        sc(240),
        result_filter_test_cb
    );

    make_label(filter_card, "Filter by Date:", F_ROW_LABEL, HEX_TEXT);

    result_filter_picker(
        filter_card,
        result_date_filter,
        sc(210),
        result_filter_date_cb
    );

    if(strcmp(result_test_filter, "All tests") != 0 ||
       strcmp(result_date_filter, "All dates") != 0)
    {
        lv_obj_t *clear = make_button(
            filter_card,
            "Clear filters",
            F_ACTION,
            HEX_BTN_NEUTRAL,
            HEX_BTN_NEUTRAL_HOVER,
            HEX_BTN_TEXT,
            0,
            result_clear_filters_cb,
            NULL
        );

        lv_obj_set_width(clear, sc(150));
    }


    /* ---------------- the results grid ---------------- */

    lv_obj_t *grid = lv_obj_create(card);

    make_transparent(grid);

    lv_obj_set_width(grid, lv_pct(100));
    lv_obj_set_height(grid, lv_pct(100));
    lv_obj_set_flex_grow(grid, 1);

    lv_obj_set_style_pad_all(grid, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_column(grid, sc(6), LV_PART_MAIN);
    lv_obj_set_style_pad_row(grid, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(grid, LV_OBJ_FLAG_SCROLLABLE);

    static int32_t result_cols[LIST_COLUMNS + 1] =
    {
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_FR(1),
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST
    };

    static int32_t result_row_dsc[LIST_ROWS + 1] =
    {
        LV_GRID_FR(1), LV_GRID_FR(1),
        LV_GRID_FR(1), LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST
    };

    lv_obj_set_grid_dsc_array(grid, result_cols, result_row_dsc);

    int total_pages =
        (result_test_shown_count + LIST_PER_PAGE - 1) / LIST_PER_PAGE;

    if(total_pages < 1)
    {
        total_pages = 1;
    }

    if(result_page > total_pages)
    {
        result_page = total_pages;
    }

    if(result_page < 1)
    {
        result_page = 1;
    }

    int start = (result_page - 1) * LIST_PER_PAGE;
    int shown = result_test_shown_count - start;

    if(shown > LIST_PER_PAGE)
    {
        shown = LIST_PER_PAGE;
    }

    if(shown <= 0)
    {
        /* results.py: the empty state. */
        lv_obj_t *empty = make_label(
            grid,
            "No results found.\nRun measurements and they will appear here.",
            F_TILE,
            HEX_TEXT_MUTED
        );

        lv_obj_set_style_text_align(empty, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        lv_obj_set_grid_cell(
            empty,
            LV_GRID_ALIGN_CENTER, 0, LIST_COLUMNS,
            LV_GRID_ALIGN_CENTER, 0, LIST_ROWS
        );
    }

    for(int i = 0; i < shown; i++)
    {
        int test_index = result_test_shown[start + i];
        int method = TESTS[test_index].method;
        int count = test_result_count(test_index);

        /* One container per cell: the tinted test button over its meta line. */
        lv_obj_t *cell = lv_obj_create(grid);

        lv_obj_set_style_bg_color(cell, CLR_SURFACE, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(cell, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(cell, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(cell, CLR_BORDER, LV_PART_MAIN);
        lv_obj_set_style_radius(cell, sc(12), LV_PART_MAIN);
        lv_obj_set_style_pad_all(cell, sc(5), LV_PART_MAIN);
        lv_obj_set_style_pad_row(cell, sc(2), LV_PART_MAIN);

        lv_obj_set_flex_flow(cell, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            cell,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_clear_flag(cell, LV_OBJ_FLAG_SCROLLABLE);

        lv_obj_set_grid_cell(
            cell,
            LV_GRID_ALIGN_STRETCH, i % LIST_COLUMNS, 1,
            LV_GRID_ALIGN_STRETCH, i / LIST_COLUMNS, 1
        );

        lv_obj_t *btn = make_button(
            cell,
            TESTS[test_index].name,
            F_TILE,
            METHOD_FILL_HEX[method],
            METHOD_BORDER_HEX[method],
            METHOD_TEXT_HEX[method],
            bar_height(F_TILE, sc(16)),
            result_tile_cb,
            (void *)(intptr_t)test_index
        );

        lv_obj_set_width(btn, lv_pct(100));
        lv_obj_set_style_border_width(btn, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(btn, CLR_METHOD_BORDER(method), LV_PART_MAIN);
        lv_obj_set_style_radius(btn, sc(11), LV_PART_MAIN);

        char meta[48];

        lv_snprintf(
            meta,
            sizeof(meta),
            "%s  -  %d result%s",
            METHOD_NAMES[method],
            count,
            count == 1 ? "" : "s"
        );

        lv_obj_t *meta_label = make_label(cell, meta, F_TILE_META, HEX_TEXT_MUTED);

        lv_obj_set_width(meta_label, lv_pct(100));
        lv_label_set_long_mode(meta_label, LV_LABEL_LONG_MODE_WRAP);
        lv_obj_set_style_text_align(meta_label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    }


    /* ---------------- page bar ---------------- */

    build_page_bar(card, result_page, total_pages, result_page_cb);


    /* ---------------- bottom: five actions ---------------- */

    lv_obj_t *bottom = lv_obj_create(card);

    make_transparent(bottom);

    lv_obj_set_width(bottom, lv_pct(100));
    lv_obj_set_height(bottom, bar_height(F_ACTION, sc(20)));
    lv_obj_set_flex_flow(bottom, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        bottom,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(bottom, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(bottom, LV_OBJ_FLAG_SCROLLABLE);

    static const char *const RESULT_ACTIONS[] =
    {
        "Report", "Parameter", "Std.", "QC", "Com."
    };

    for(int i = 0; i < ARRAY_LEN(RESULT_ACTIONS); i++)
    {
        int is_qc = (i == 3);

        lv_obj_t *btn = make_button(
            bottom,
            RESULT_ACTIONS[i],
            F_ACTION,
            (is_qc && result_qc_mode) ? HEX_ACCENT : HEX_BTN_NEUTRAL,
            (is_qc && result_qc_mode) ? HEX_ACCENT_HOVER : HEX_BTN_NEUTRAL_HOVER,
            (is_qc && result_qc_mode) ? HEX_TEXT_ON_ACCENT : HEX_BTN_TEXT,
            0,
            is_qc ? result_qc_cb :
                (i == 1 ? result_parameter_cb : result_log_cb),
            is_qc || i == 1 ? NULL : (void *)RESULT_ACTIONS[i]
        );

        /* Five across: 19% each plus their gutters stays under the bar. */
        lv_obj_set_width(btn, lv_pct(19));
    }

    return page;
}


/* =========================================================
 * RESULT  ->  "RESULTS" detail table
 *                (results.py: show_test_results)
 *
 * One test's measurement results: a method badge, the test
 * name, five summary chips, then the results table
 * (Type | Abs | Result | Unit | Date & Time).
 *
 * The rows are generated from the run types results.py
already labels, so the table has the shape and the rhythm
 * of the reference without a database behind it.
 * ========================================================= */

static const char *const RUN_TYPES[] =
{
    "Water", "Blank", "Std", "Sample", "QC 1", "QC 2", "Sample"
};

static lv_obj_t *create_result_detail_screen(void)
{
    int test_index = measurement_test;
    int method = TESTS[test_index].method;

    lv_obj_t *card;
    lv_obj_t *page = create_page(
        TESTS[test_index].name,
        "Measurement results, unit: -",
        &card
    );

    card_as_column(card);


    /* ---------------- summary chips ---------------- */

    lv_obj_t *chips = lv_obj_create(card);

    make_transparent(chips);

    lv_obj_set_width(chips, lv_pct(100));
    lv_obj_set_height(chips, bar_height(F_VALUE, sc(34)));
    lv_obj_set_flex_flow(chips, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        chips,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(chips, sc(6), LV_PART_MAIN);
    lv_obj_clear_flag(chips, LV_OBJ_FLAG_SCROLLABLE);

    static const char *const CHIP_LABELS[] =
    {
        "Total Results", "Latest", "Average", "Minimum", "Maximum"
    };

    static const char *const CHIP_VALUES[] =
    {
        "12", "1.204", "1.187", "1.020", "1.352"
    };

    for(int i = 0; i < ARRAY_LEN(CHIP_LABELS); i++)
    {
        lv_obj_t *chip = lv_obj_create(chips);

        lv_obj_set_width(chip, lv_pct(19));
        lv_obj_set_height(chip, lv_pct(100));

        lv_obj_set_style_bg_color(chip, CLR_SURFACE_SUNKEN, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(chip, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(chip, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(chip, CLR_BORDER, LV_PART_MAIN);
        lv_obj_set_style_radius(chip, sc(12), LV_PART_MAIN);
        lv_obj_set_style_pad_all(chip, 0, LV_PART_MAIN);

        lv_obj_set_flex_flow(chip, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            chip,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_clear_flag(chip, LV_OBJ_FLAG_SCROLLABLE);

        lv_obj_t *name = make_label(chip, CHIP_LABELS[i], F_CAPTION, HEX_TEXT_MUTED);

        lv_obj_set_style_text_font(name, F_TILE_META, LV_PART_MAIN);

        make_label(chip, CHIP_VALUES[i], F_VALUE, HEX_TEXT);
    }


    /* ---------------- results table ---------------- */

    lv_obj_t *table = lv_obj_create(card);

    lv_obj_set_width(table, lv_pct(100));
    lv_obj_set_height(table, lv_pct(100));
    lv_obj_set_flex_grow(table, 1);

    lv_obj_set_style_bg_color(table, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(table, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(table, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(table, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(table, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_all(table, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_row(table, sc(1), LV_PART_MAIN);

    lv_obj_set_flex_flow(table, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        table,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    /* Scrolls rather than clipping rows that do not fit. */
    lv_obj_add_flag(table, LV_OBJ_FLAG_SCROLLABLE);

    static const char *const COLUMNS[] =
    {
        "Type", "Abs", "Result", "Unit", "Date & Time"
    };

    static const int32_t COLUMN_W[] = { 16, 16, 22, 14, 32 };

    lv_obj_t *head = lv_obj_create(table);

    lv_obj_set_width(head, lv_pct(100));
    lv_obj_set_height(head, bar_height(F_ROW_LABEL, sc(12)));
    lv_obj_set_style_bg_color(head, lv_color_hex(0x1E293B), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(head, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(head, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(head, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(head, 0, LV_PART_MAIN);

    lv_obj_set_flex_flow(head, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        head,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_clear_flag(head, LV_OBJ_FLAG_SCROLLABLE);

    for(int c = 0; c < ARRAY_LEN(COLUMNS); c++)
    {
        lv_obj_t *label = make_label(head, COLUMNS[c], F_ROW_LABEL, 0xFFFFFF);

        lv_obj_set_width(label, lv_pct(COLUMN_W[c]));
        lv_obj_set_style_pad_left(label, sc(10), LV_PART_MAIN);
    }

    static const char *const ROW_RESULTS[] =
    {
        "-", "-", "1.204", "1.187", "0.020", "0.018", "1.204"
    };

    static const char *const ROW_ABS[] =
    {
        "0.412", "0.000", "1.204", "1.187", "0.020", "0.018", "1.187"
    };

    static const char *const ROW_UNITS[] =
    {
        "V", "-", "mmol/L", "mmol/L", "-", "-", "mmol/L"
    };

    static const char *const ROW_DATES[] =
    {
        "30 Sep 2026, 09:12", "30 Sep 2026, 09:20",
        "30 Sep 2026, 09:31", "30 Sep 2026, 09:44",
        "30 Sep 2026, 09:52", "30 Sep 2026, 10:01",
        "30 Sep 2026, 10:15"
    };

    for(int r = 0; r < ARRAY_LEN(RUN_TYPES); r++)
    {
        lv_obj_t *row = lv_obj_create(table);

        lv_obj_set_width(row, lv_pct(100));
        lv_obj_set_height(row, bar_height(F_TILE, sc(12)));
        lv_obj_set_style_bg_color(
            row,
            (r % 2 == 0) ? CLR_SURFACE_SUNKEN : CLR_SURFACE,
            LV_PART_MAIN
        );
        lv_obj_set_style_bg_opa(row, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(row, 0, LV_PART_MAIN);
        lv_obj_set_style_radius(row, 0, LV_PART_MAIN);
        lv_obj_set_style_pad_all(row, 0, LV_PART_MAIN);

        lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(
            row,
            LV_FLEX_ALIGN_START,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

        const char *cells[5] =
        {
            RUN_TYPES[r], ROW_ABS[r], ROW_RESULTS[r],
            ROW_UNITS[r], ROW_DATES[r]
        };

        for(int c = 0; c < 5; c++)
        {
            lv_obj_t *label = make_label(row, cells[c], F_TILE, HEX_TEXT_MUTED);

            lv_obj_set_width(label, lv_pct(COLUMN_W[c]));
            lv_obj_set_style_pad_left(label, sc(10), LV_PART_MAIN);

            if(c == 2)
            {
                /* The measured value is the one the operator reads, so it is
                 * the one that gets the value colour and font. */
                lv_obj_set_style_text_font(label, F_VALUE, LV_PART_MAIN);
                lv_obj_set_style_text_color(label, CLR_TEXT, LV_PART_MAIN);
            }
        }
    }


    /* ---------------- footer ---------------- */

    lv_obj_t *footer = lv_obj_create(card);

    make_transparent(footer);

    lv_obj_set_width(footer, lv_pct(100));
    lv_obj_set_height(footer, bar_height(F_ACTION, sc(20)));
    lv_obj_set_flex_flow(footer, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        footer,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(footer, sc(10), LV_PART_MAIN);
    lv_obj_clear_flag(footer, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *back = make_button(
        footer,
        "Back to results",
        F_ACTION,
        HEX_BTN_NEUTRAL,
        HEX_BTN_NEUTRAL_HOVER,
        HEX_BTN_TEXT,
        0,
        NULL,
        NULL
    );

    lv_obj_set_width(back, lv_pct(49));

    /* The header's BACK and this button do the same thing: one step back. */
    lv_obj_add_event_cb(back, back_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *menu = make_button(
        footer,
        "Back to menu",
        F_ACTION,
        HEX_BTN_NEUTRAL,
        HEX_BTN_NEUTRAL_HOVER,
        HEX_BTN_TEXT,
        0,
        home_event_cb,
        NULL
    );

    lv_obj_set_width(menu, lv_pct(49));

    return page;
}


/* =========================================================
 * TEST  ->  "MEASUREMENT: <test>"  (measurement.py)
 *
 * Header, the live chart ("Absorbance vs Time", x-axis
 * "Time (s)"), the two readout tables - realtime on the
 * left, the Type | Result | Unit results table on the right -
 * and the seven workflow buttons.
 *
 * The chart is a real lv_line over a small static point array:
 * no charting library, no per-frame allocation, and the same
 * draw path as every other widget.
 * ========================================================= */

#define MEASURE_PLOT_W 700      /* design px */
#define MEASURE_PLOT_H 200      /* design px */
#define MEASURE_BUTTON_COUNT 7

static const char *const MEASURE_BUTTONS[MEASURE_BUTTON_COUNT] =
{
    "WATER", "BLANK", "STD", "SAMPLE", "QC1", "QC2", "WASH"
};

static const char *const MEASURE_ROW_RESULT[MEASURE_BUTTON_COUNT] =
{
    "0.412", "0.000", "1.204", "1.187", "0.020", "0.018", "0.000"
};

static const char *const MEASURE_ROW_UNIT[MEASURE_BUTTON_COUNT] =
{
    "V", "-", "mmol/L", "mmol/L", "-", "-", "-"
};

/* 0..512 absorbance, seven samples across the plot. */
static const int MEASURE_CURVE[7] =
{
    160, 250, 205, 320, 285, 400, 360
};

static lv_point_precise_t measure_points[7];

static lv_obj_t *measure_buttons[MEASURE_BUTTON_COUNT];
static lv_obj_t *measure_type_label;
static lv_obj_t *measure_result_label;
static lv_obj_t *measure_unit_label;
static int measure_selected = -1;

static void measurement_button_cb(lv_event_t *e)
{
    int index = (int)(intptr_t)lv_event_get_user_data(e);

    measure_selected = index;

    /* Selecting a button is the visible state change: the chosen step is the
     * accent one, the rest fall back to neutral. */
    for(int i = 0; i < MEASURE_BUTTON_COUNT; i++)
    {
        lv_obj_t *btn = measure_buttons[i];

        if(btn == NULL)
        {
            continue;
        }

        int on = (i == index);

        lv_obj_set_style_bg_color(
            btn,
            on ? CLR_ACCENT : CLR_BTN_NEUTRAL,
            LV_PART_MAIN
        );
        lv_obj_set_style_text_color(
            btn,
            on ? CLR_TEXT_ON_ACCENT : CLR_BTN_TEXT,
            LV_PART_MAIN
        );
    }

    /* The results row follows the selection, as the live readout does in the
     * Tk screen (measurement.py: update_results_display). */
    if(measure_type_label != NULL)
    {
        lv_label_set_text(measure_type_label, MEASURE_BUTTONS[index]);
    }

    if(measure_result_label != NULL)
    {
        lv_label_set_text(measure_result_label, MEASURE_ROW_RESULT[index]);
    }

    if(measure_unit_label != NULL)
    {
        lv_label_set_text(measure_unit_label, MEASURE_ROW_UNIT[index]);
    }

    if(verbose_nav)
    {
        printf("[measure] %s selected\n", MEASURE_BUTTONS[index]);
    }
}

/* One row of the little readout tables: fixed-width cells so the columns line
 * up across rows without a grid, exactly like the Tk tables. */
static lv_obj_t *readout_row(
    lv_obj_t *parent,
    const char *a,
    const char *b,
    const lv_font_t *font,
    uint32_t color
)
{
    lv_obj_t *row = lv_obj_create(parent);

    make_transparent(row);

    lv_obj_set_width(row, lv_pct(100));
    lv_obj_set_height(row, bar_height(font, sc(6)));
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        row,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *left = make_label(row, a, font, color);
    lv_obj_t *right = make_label(row, b, font, color);

    lv_obj_set_width(left, lv_pct(50));
    lv_obj_set_width(right, lv_pct(50));
    lv_obj_set_style_text_align(right, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);

    return row;
}

/*
 * Height of a readout box, SUMMED FROM ITS OWN CONTENT rather than picked by
 * eye: the box title, the column-header row, the four data rows, the gaps
 * between them and the box's own padding. Sizing the box from the rows it
 * actually holds is what makes its last row visible instead of clipped - the
 * same font-derived rule the bars and buttons use.
 */
static int32_t readout_box_height(void)
{
    return line_height(F_ROW_LABEL)                  /* box title       */
         + bar_height(F_TILE_META, sc(6))            /* column headers  */
         + 4 * bar_height(F_TILE, sc(6))             /* four data rows  */
         + 4 * sc(2)                                 /* pad_row gaps    */
         + sc(8) * 2;                                /* box padding     */
}

static lv_obj_t *create_measurement_screen(void)
{
    char title[64];

    lv_snprintf(
        title,
        sizeof(title),
        "MEASUREMENT - %s",
        TESTS[measurement_test].name
    );

    lv_obj_t *card;
    lv_obj_t *page = create_page(
        title,
        "Live readout while the run is in progress",
        &card
    );

    card_as_column(card);

    measure_selected = -1;
    measure_type_label = NULL;
    measure_result_label = NULL;
    measure_unit_label = NULL;

    for(int i = 0; i < MEASURE_BUTTON_COUNT; i++)
    {
        measure_buttons[i] = NULL;
    }


    /* ---------------- graph ---------------- */

    lv_obj_t *graph = lv_obj_create(card);

    lv_obj_set_width(graph, lv_pct(100));
    lv_obj_set_height(graph, lv_pct(100));
    lv_obj_set_flex_grow(graph, 1);

    lv_obj_set_style_bg_color(graph, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(graph, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(graph, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(graph, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_radius(graph, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_all(graph, sc(8), LV_PART_MAIN);
    lv_obj_set_style_pad_row(graph, sc(2), LV_PART_MAIN);

    lv_obj_set_flex_flow(graph, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        graph,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_clear_flag(graph, LV_OBJ_FLAG_SCROLLABLE);

    {    /* Title / axis labels and the plotted line. */
        lv_obj_t *header = lv_obj_create(graph);

        make_transparent(header);

        lv_obj_set_width(header, lv_pct(100));
        lv_obj_set_height(header, bar_height(F_ROW_LABEL, sc(4)));
        lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(
            header,
            LV_FLEX_ALIGN_SPACE_BETWEEN,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

        /* Title centred, as the reference chart has it. */
        lv_obj_t *chart_title = make_label(
            header,
            "Absorbance vs Time",
            F_ROW_LABEL,
            HEX_TEXT
        );

        lv_obj_set_width(chart_title, lv_pct(100));
        lv_obj_set_style_text_align(chart_title, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);

        lv_obj_t *axis = lv_obj_create(graph);

        make_transparent(axis);

        /* The plotted area. The line inside it has an explicit design size,
         * so its points can be computed rather than guessed from a size the
         * object does not report at build time. */
        lv_obj_set_width(axis, lv_pct(100));
        lv_obj_set_height(axis, lv_pct(100));
        lv_obj_set_flex_grow(axis, 1);
        lv_obj_clear_flag(axis, LV_OBJ_FLAG_SCROLLABLE);

        /* The y-axis label, parked in the band above the centred plot so it
         * cannot overlap the curve. */
        lv_obj_t *y_label = make_label(
            axis,
            "Absorbance",
            F_TILE_META,
            HEX_TEXT_MUTED
        );

        lv_obj_align(y_label, LV_ALIGN_TOP_LEFT, 0, 0);

        lv_obj_t *plot = lv_obj_create(axis);

        make_transparent(plot);

        lv_obj_set_size(plot, sc(MEASURE_PLOT_W), sc(MEASURE_PLOT_H));
        lv_obj_center(plot);

        lv_obj_set_style_border_width(plot, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(plot, CLR_BORDER, LV_PART_MAIN);
        lv_obj_set_style_border_side(plot, LV_BORDER_SIDE_BOTTOM | LV_BORDER_SIDE_LEFT, LV_PART_MAIN);
        lv_obj_clear_flag(plot, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_style_pad_all(plot, 0, LV_PART_MAIN);

        for(int i = 0; i < 7; i++)
        {
            measure_points[i].x =
                (int32_t)((int64_t)i * sc(MEASURE_PLOT_W) / 6);
            measure_points[i].y =
                sc(MEASURE_PLOT_H) -
                (int32_t)((int64_t)MEASURE_CURVE[i] * sc(MEASURE_PLOT_H) / 512);
        }

        lv_obj_t *line = lv_line_create(plot);

        lv_line_set_points(line, measure_points, 7);
        lv_obj_set_style_line_width(line, sc(4), LV_PART_MAIN);
        lv_obj_set_style_line_color(line, CLR_ACCENT, LV_PART_MAIN);
        lv_obj_set_style_line_rounded(line, true, LV_PART_MAIN);
        lv_obj_set_size(line, sc(MEASURE_PLOT_W), sc(MEASURE_PLOT_H));
        lv_obj_align(line, LV_ALIGN_TOP_LEFT, 0, 0);
        lv_obj_clear_flag(line, LV_OBJ_FLAG_CLICKABLE);

        lv_obj_t *xlabel = make_label(graph, "Time (s)", F_TILE_META, HEX_TEXT_MUTED);

        lv_obj_set_width(xlabel, lv_pct(100));
        lv_obj_set_style_text_align(xlabel, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
    }


    /* ---------------- readout: realtime | results ---------------- */

    lv_obj_t *readout = lv_obj_create(card);

    make_transparent(readout);

    lv_obj_set_width(readout, lv_pct(100));
    lv_obj_set_height(readout, readout_box_height());
    lv_obj_set_flex_flow(readout, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        readout,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(readout, sc(8), LV_PART_MAIN);
    lv_obj_clear_flag(readout, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *half[2] = { NULL, NULL };

    for(int i = 0; i < 2; i++)
    {
        lv_obj_t *box = lv_obj_create(readout);

        lv_obj_set_width(box, lv_pct(49));
        lv_obj_set_height(box, lv_pct(100));

        lv_obj_set_style_bg_color(box, CLR_SURFACE, LV_PART_MAIN);
        lv_obj_set_style_bg_opa(box, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_set_style_border_width(box, 1, LV_PART_MAIN);
        lv_obj_set_style_border_color(box, CLR_BORDER, LV_PART_MAIN);
        lv_obj_set_style_radius(box, sc(10), LV_PART_MAIN);
        lv_obj_set_style_pad_all(box, sc(8), LV_PART_MAIN);
        lv_obj_set_style_pad_row(box, sc(2), LV_PART_MAIN);

        lv_obj_set_flex_flow(box, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            box,
            LV_FLEX_ALIGN_START,
            LV_FLEX_ALIGN_START,
            LV_FLEX_ALIGN_START
        );
        lv_obj_clear_flag(box, LV_OBJ_FLAG_SCROLLABLE);

        half[i] = box;
    }

    /* Realtime table: time and absorbance, newest reading at the bottom. */
    make_label(half[0], "Realtime data", F_ROW_LABEL, HEX_TEXT);
    readout_row(half[0], "Time (s)", "Absorbance", F_TILE_META, HEX_TEXT_MUTED);
    readout_row(half[0], "2", "0.250", F_TILE, HEX_TEXT);
    readout_row(half[0], "4", "0.500", F_TILE, HEX_TEXT);
    readout_row(half[0], "6", "0.125", F_TILE, HEX_TEXT);

    /* Results table: measurement.py: initialize_results_table headers. */
    make_label(half[1], "Results", F_ROW_LABEL, HEX_TEXT);

    /* readout_row() makes two cells; Type | Result | Unit needs a third, so
     * the header and the value row each get one more label and the three are
     * given shares that add up to 100%% - never overlapping, never clipped. */
    lv_obj_t *rhead = readout_row(half[1], "Type", "Result", F_TILE_META, HEX_TEXT_MUTED);

    lv_obj_t *unit_head = make_label(rhead, "Unit", F_TILE_META, HEX_TEXT_MUTED);

    lv_obj_set_width(unit_head, lv_pct(34));
    lv_obj_set_style_text_align(unit_head, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
    lv_obj_set_width(lv_obj_get_child(rhead, 0), lv_pct(33));
    lv_obj_set_width(lv_obj_get_child(rhead, 1), lv_pct(33));

    lv_obj_t *rrow = readout_row(half[1], "-", "-", F_TILE, HEX_TEXT);
    lv_obj_t *unit_cell = make_label(rrow, "-", F_TILE, HEX_TEXT);

    lv_obj_set_width(unit_cell, lv_pct(34));
    lv_obj_set_style_text_align(unit_cell, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
    lv_obj_set_width(lv_obj_get_child(rrow, 0), lv_pct(42));
    lv_obj_set_width(lv_obj_get_child(rrow, 1), lv_pct(24));

    /* The three cells the selection updates. */
    measure_type_label = lv_obj_get_child(rrow, 0);
    measure_result_label = lv_obj_get_child(rrow, 1);
    measure_unit_label = unit_cell;


    /* ---------------- the seven workflow buttons ---------------- */

    lv_obj_t *controls = lv_obj_create(card);

    make_transparent(controls);

    lv_obj_set_width(controls, lv_pct(100));
    lv_obj_set_height(controls, bar_height(F_TILE, sc(18)));
    lv_obj_set_flex_flow(controls, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        controls,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_set_style_pad_column(controls, sc(4), LV_PART_MAIN);
    lv_obj_clear_flag(controls, LV_OBJ_FLAG_SCROLLABLE);

    for(int i = 0; i < MEASURE_BUTTON_COUNT; i++)
    {
        int on = (measure_selected == i);

        lv_obj_t *btn = make_button(
            controls,
            MEASURE_BUTTONS[i],
            F_TILE,
            on ? HEX_ACCENT : HEX_BTN_NEUTRAL,
            on ? HEX_ACCENT_HOVER : HEX_BTN_NEUTRAL_HOVER,
            on ? HEX_TEXT_ON_ACCENT : HEX_BTN_TEXT,
            bar_height(F_TILE, sc(18)),
            measurement_button_cb,
            (void *)(intptr_t)i
        );

        /* Seven across: 13% each plus their gutters stays under the bar. */
        lv_obj_set_width(btn, lv_pct(13));
        lv_obj_set_style_radius(btn, sc(10), LV_PART_MAIN);

        measure_buttons[i] = btn;
    }

    return page;
}


/* =========================================================
 * SCREENS STILL WAITING FOR A REFERENCE
 *
 * These keep the same shell, the same back button and the
 * same component library, so the app is one consistent UI
 * today and dropping in the ported content later is a local
 * change. They carry no fake controls: only BACK works here,
 * and the card says so rather than pretending.
 * ========================================================= */

static lv_obj_t *create_placeholder_screen(analyzer_screen_t screen)
{
    const menu_entry_t *entry = &menu_entries[screen];

    lv_obj_t *card;
    lv_obj_t *page = create_page(entry->title, entry->subtitle, &card);

    /* One centred column of prose in the card. */
    lv_obj_t *note = lv_label_create(card);

    lv_label_set_text_fmt(
        note,
        "%s\n\nThis screen has no reference image yet, so its content "
        "has not been invented. The ported shell, theme and "
        "navigation around it are already in place.",
        entry->subtitle
    );

    lv_obj_set_style_text_font(note, F_STATUS, LV_PART_MAIN);
    lv_obj_set_style_text_color(note, CLR_TEXT_MUTED, LV_PART_MAIN);
    lv_obj_set_style_text_line_space(note, sc(6), LV_PART_MAIN);

    /* Wrap inside the card rather than running off it on a narrower panel:
     * the note is prose, so it must be allowed to re-flow. */
    lv_obj_set_width(note, lv_pct(100));
    lv_label_set_long_mode(note, LV_LABEL_LONG_MODE_WRAP);

    return page;
}

static lv_obj_t *create_system_screen(void)
{
    return create_placeholder_screen(ANALYZER_SCREEN_SYSTEM);
}

static lv_obj_t *create_maintenance_screen(void)
{
    return create_placeholder_screen(ANALYZER_SCREEN_MAINTENANCE);
}

static lv_obj_t *create_power_screen(void)
{
    return create_placeholder_screen(ANALYZER_SCREEN_POWER);
}

static lv_obj_t *create_about_screen(void)
{
    return create_placeholder_screen(ANALYZER_SCREEN_ABOUT);
}


/* ---------------------------------------------------------
 * DISPATCH
 *
 * One entry point per screen, so adding a ported screen is a
 * new create_*_screen() plus one line here - and nothing else
 * in the app has to change.
 * --------------------------------------------------------- */

static lv_obj_t *create_screen_page(analyzer_screen_t screen)
{
    switch(screen)
    {
        /* The two "pick a list" tabs - the dashboard card and its own sub-
         * screen render the same screen, so a BACK that lands on either is
         * consistent with the card the operator tapped. */
        case ANALYZER_SCREEN_TEST:
        case ANALYZER_SCREEN_TEST_LIST:
            return create_test_list_screen();

        case ANALYZER_SCREEN_RESULT:
        case ANALYZER_SCREEN_RESULTS:
            return create_results_screen();

        case ANALYZER_SCREEN_RESULT_DETAIL:
            return create_result_detail_screen();

        case ANALYZER_SCREEN_PARAMETERS:
            return create_test_screen();

        case ANALYZER_SCREEN_MEASUREMENT:
            return create_measurement_screen();

        case ANALYZER_SCREEN_SYSTEM:
            return create_system_screen();

        case ANALYZER_SCREEN_MAINTENANCE:
            return create_maintenance_screen();

        case ANALYZER_SCREEN_POWER:
            return create_power_screen();

        case ANALYZER_SCREEN_ABOUT:
            return create_about_screen();

        default:
            return create_about_screen();
    }
}


/* =========================================================
 * NAVIGATION
 * ========================================================= */

static size_t open_page(analyzer_screen_t screen)
{
    size_t before = analyzer_ui_heap_used();

    /* An open picker belongs to the page that is about to go: it lives on
     * lv_layer_top(), so deleting the page would not free it. */
    picker_close();

    /* Delete before create: the two pages are never alive together. */
    if(current_page != NULL)
    {
        lv_obj_delete(current_page);
        current_page = NULL;
    }

    size_t after_delete = analyzer_ui_heap_used();

    current_screen = screen;
    page_open = 1;

    current_page = create_screen_page(screen);

    size_t after_build = analyzer_ui_heap_used();

    if(home_layer != NULL)
    {
        lv_obj_add_flag(home_layer, LV_OBJ_FLAG_HIDDEN);
    }

    size_t overhead =
        after_build > before ? after_build - before : 0;

    if(overhead > worst_switch_overhead)
    {
        worst_switch_overhead = overhead;
    }

    if(verbose_nav)
    {
        printf(
            "[nav] %s  before=%u  after_delete=%u  after_build=%u  overhead=%u\n",
            menu_entries[screen].title,
            (unsigned)before,
            (unsigned)after_delete,
            (unsigned)after_build,
            (unsigned)overhead
        );
    }

    return overhead;
}

size_t analyzer_ui_open(analyzer_screen_t screen)
{
    /*
     * Remember where we came from, so BACK returns there instead of always
     * dumping the operator on the dashboard. Home is the root, so opening a
     * tab from the dashboard pushes nothing and BACK from that tab reaches
     * go_home(). Re-opening the screen already on show (a filter rebuild
     * routed through open) is not a step, so it pushes nothing either.
     */
    if(page_open && current_screen != screen)
    {
        if(nav_depth < NAV_STACK_MAX)
        {
            nav_stack[nav_depth++] = current_screen;
        }
        else
        {
            /* Full: drop the oldest step, keep the most recent ones. */
            memmove(
                nav_stack,
                nav_stack + 1,
                sizeof(nav_stack) - sizeof(nav_stack[0])
            );

            nav_stack[NAV_STACK_MAX - 1] = current_screen;
        }
    }

    return open_page(screen);
}

void analyzer_ui_back(void)
{
    if(nav_depth > 0)
    {
        analyzer_screen_t previous = nav_stack[--nav_depth];

        open_page(previous);

        return;
    }

    /* Nothing to go back to: the dashboard is the root of every flow. */
    analyzer_ui_go_home();
}

void analyzer_ui_go_home(void)
{
    picker_close();

    /* Home is the root: coming home ends the flow, so the history restarts
     * here rather than keeping steps the operator can no longer reach. */
    nav_depth = 0;

    page_open = 0;

    if(current_page != NULL)
    {
        lv_obj_delete(current_page);
        current_page = NULL;
    }

    if(home_layer != NULL)
    {
        lv_obj_remove_flag(home_layer, LV_OBJ_FLAG_HIDDEN);
    }

    if(verbose_nav)
    {
        printf(
            "[nav] home  used=%u\n",
            (unsigned)analyzer_ui_heap_used()
        );
    }
}

void analyzer_ui_build(void)
{
    /* One focus group for the app. Setting it as the default lets the SDL
     * keyboard indev type into the focused text field without every call site
     * having to pass the group around. */
    if(ui_group == NULL)
    {
        ui_group = lv_group_create();

        if(ui_group != NULL)
        {
            lv_group_set_default(ui_group);
        }
    }

    build_home();
}

analyzer_screen_t analyzer_ui_current_screen(void)
{
    return page_open ? current_screen : ANALYZER_SCREEN_COUNT;
}

void analyzer_ui_home_key_center(int index, int32_t *x, int32_t *y)
{
    if(index < 0 || index >= ANALYZER_HOME_COUNT)
    {
        return;
    }

    if(home_keys[index] == NULL)
    {
        return;
    }

    /* Ask the widget itself, so the answer follows the layout rather than a
     * second copy of the menu's numbers. */
    lv_area_t area;

    lv_obj_get_coords(home_keys[index], &area);

    *x = (area.x1 + area.x2) / 2;
    *y = (area.y1 + area.y2) / 2;
}
