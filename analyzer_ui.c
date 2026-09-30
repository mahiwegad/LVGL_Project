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

#include <stdio.h>
#include <string.h>

/* =========================================================
 * PALETTE
 *
 * LIGHT palette from ui/ui/theme.py. Keys are named after the
 * semantic palette keys so the two stay comparable side by side.
 * ========================================================= */

#define CLR_WINDOW_BG       lv_color_hex(0xEEF2F7)
#define CLR_SURFACE         lv_color_hex(0xFFFFFF)
#define CLR_SURFACE_SUNKEN  lv_color_hex(0xF1F5F9)
#define CLR_BORDER          lv_color_hex(0xE2E8F0)
#define CLR_TEXT            lv_color_hex(0x0F172A)
#define CLR_TEXT_MUTED      lv_color_hex(0x64748B)
#define CLR_TEXT_ON_ACCENT  lv_color_hex(0xFFFFFF)
#define CLR_ACCENT          lv_color_hex(0x0F766E)
#define CLR_ACCENT_TEXT     lv_color_hex(0x0F766E)
#define CLR_SUCCESS         lv_color_hex(0x15803D)
#define CLR_WARNING         lv_color_hex(0xF59E0B)
#define CLR_BTN_NEUTRAL     lv_color_hex(0xE2E8F0)

/* =========================================================
 * TYPE SCALE
 *
 * Design font size -> the nearest Montserrat face compiled in.
 *   22 -> 14   (card icon)
 *   17 -> 12   (card title)   19 -> 12  (card arrow)
 *   16 -> 10   (status line)
 *   20 -> 12   (countdown value)
 *   11 ->  8   (unit caption) 12 ->  8  (progress caption)
 * ========================================================= */

#define F_CARD_ICON   (&lv_font_montserrat_14)
#define F_CARD_TITLE  (&lv_font_montserrat_12)
#define F_CARD_SUB    (&lv_font_montserrat_8)
#define F_CARD_ARROW  (&lv_font_montserrat_12)
#define F_STATUS      (&lv_font_montserrat_10)
#define F_VALUE       (&lv_font_montserrat_12)
#define F_CAPTION     (&lv_font_montserrat_8)
#define F_PAGE_TITLE  (&lv_font_montserrat_14)

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
    }
};


/* =========================================================
 * STATE
 * ========================================================= */

static lv_obj_t *home_layer;
static lv_obj_t *current_page;
static size_t worst_switch_overhead;
static int verbose_nav = 1;


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


/* =========================================================
 * MENU CARD  (main_menu.py: _menu_card)
 *
 * A large card that is clickable anywhere. Icon, title and
 * subtitle are stacked on the left; the arrow sits at the
 * right edge. Hover lifts the fill and turns the border to
 * the accent colour, exactly as _enter() does in Tkinter.
 * ========================================================= */

static void card_event_cb(lv_event_t *e)
{
    analyzer_screen_t screen =
        (analyzer_screen_t)(intptr_t)lv_event_get_user_data(e);

    analyzer_ui_open(screen);
}

static lv_obj_t *create_menu_card(
    lv_obj_t *parent,
    const menu_entry_t *entry,
    size_t index
)
{
    lv_obj_t *card = lv_button_create(parent);

    lv_obj_set_style_bg_color(card, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_set_style_bg_color(card, CLR_SURFACE, LV_STATE_HOVERED);
    lv_obj_set_style_bg_color(card, CLR_SURFACE_SUNKEN, LV_STATE_PRESSED);

    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(card, CLR_BORDER, LV_PART_MAIN);
    lv_obj_set_style_border_color(card, CLR_ACCENT, LV_STATE_HOVERED);

    lv_obj_set_style_radius(card, sc(16), LV_PART_MAIN);
    lv_obj_set_style_pad_all(card, sc(12), LV_PART_MAIN);

    lv_obj_set_style_shadow_width(card, 0, LV_PART_MAIN);

    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        card,
        LV_FLEX_ALIGN_SPACE_BETWEEN,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_add_event_cb(
        card,
        card_event_cb,
        LV_EVENT_CLICKED,
        (void *)(intptr_t)index
    );


    /* ---------------- text block ---------------- */

    lv_obj_t *block = lv_obj_create(card);

    make_transparent(block);

    lv_obj_set_width(block, lv_pct(76));
    lv_obj_set_height(block, LV_SIZE_CONTENT);

    lv_obj_set_flex_flow(block, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        block,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_set_style_pad_row(block, sc(2), LV_PART_MAIN);

    lv_obj_clear_flag(block, LV_OBJ_FLAG_SCROLLABLE);


    lv_obj_t *icon = lv_label_create(block);

    lv_label_set_text(icon, entry->icon);

    lv_obj_set_style_text_font(
        icon,
        F_CARD_ICON,
        LV_PART_MAIN
    );

    lv_obj_set_style_text_color(
        icon,
        entry->accent ? CLR_ACCENT : CLR_ACCENT_TEXT,
        LV_PART_MAIN
    );


    lv_obj_t *title = lv_label_create(block);

    lv_label_set_text(title, entry->title);

    lv_obj_set_style_text_font(
        title,
        F_CARD_TITLE,
        LV_PART_MAIN
    );

    lv_obj_set_style_text_color(
        title,
        CLR_TEXT,
        LV_PART_MAIN
    );


    lv_obj_t *subtitle = lv_label_create(block);

    lv_label_set_text(subtitle, entry->subtitle);

    lv_obj_set_style_text_font(
        subtitle,
        F_CARD_SUB,
        LV_PART_MAIN
    );

    lv_obj_set_style_text_color(
        subtitle,
        CLR_TEXT_MUTED,
        LV_PART_MAIN
    );

    lv_obj_set_width(subtitle, lv_pct(100));

    lv_label_set_long_mode(
        subtitle,
        LV_LABEL_LONG_MODE_WRAP
    );


    /* ---------------- arrow ---------------- */

    lv_obj_t *arrow = lv_label_create(card);

    lv_label_set_text(arrow, LV_SYMBOL_RIGHT);

    lv_obj_set_style_text_font(
        arrow,
        F_CARD_ARROW,
        LV_PART_MAIN
    );

    lv_obj_set_style_text_color(
        arrow,
        CLR_ACCENT,
        LV_PART_MAIN
    );

    return card;
}


/* =========================================================
 * THEME SWITCH  (top-right of the top bar)
 *
 * Visual port of the CustomTkinter segmented button. The
 * light/dark repaint itself is not wired yet: the analyzer
 * always opens in light mode, and this shows that state.
 * ========================================================= */

static void create_theme_switch(lv_obj_t *parent)
{
    lv_obj_t *seg = lv_obj_create(parent);

    lv_obj_set_size(seg, sc(146), sc(30));

    lv_obj_set_style_bg_color(seg, CLR_BTN_NEUTRAL, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(seg, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_set_style_radius(seg, sc(10), LV_PART_MAIN);
    lv_obj_set_style_border_width(seg, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(seg, sc(2), LV_PART_MAIN);

    lv_obj_set_flex_flow(seg, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        seg,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_clear_flag(seg, LV_OBJ_FLAG_SCROLLABLE);


    /* Selected segment: "Light". */
    lv_obj_t *light = lv_label_create(seg);

    lv_label_set_text(light, "Light");

    lv_obj_set_style_text_font(light, F_CAPTION, LV_PART_MAIN);
    lv_obj_set_style_text_color(light, CLR_TEXT_ON_ACCENT, LV_PART_MAIN);

    lv_obj_set_style_bg_color(light, CLR_ACCENT, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(light, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_set_style_radius(light, sc(8), LV_PART_MAIN);

    lv_obj_set_style_pad_hor(light, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_ver(light, sc(4), LV_PART_MAIN);

    lv_obj_set_flex_grow(light, 1);
    lv_obj_set_style_text_align(light, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);


    /* Unselected segment: "Dark". */
    lv_obj_t *dark = lv_label_create(seg);

    lv_label_set_text(dark, "Dark");

    lv_obj_set_style_text_font(dark, F_CAPTION, LV_PART_MAIN);
    lv_obj_set_style_text_color(dark, CLR_TEXT, LV_PART_MAIN);

    lv_obj_set_style_pad_hor(dark, sc(12), LV_PART_MAIN);
    lv_obj_set_style_pad_ver(dark, sc(4), LV_PART_MAIN);

    lv_obj_set_flex_grow(dark, 1);
    lv_obj_set_style_text_align(dark, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
}


/* =========================================================
 * STATUS CARD  (warm-up progress + temperature)
 *
 * Rendered as a mid-warm-up snapshot: the countdown, the
 * partly filled bar and the "ready in N minute(s)" caption
 * are the state the Tkinter screen shows a few minutes in.
 * There is no hardware model behind it yet.
 * ========================================================= */

static lv_obj_t *create_status_card(lv_obj_t *parent)
{
    lv_obj_t *card = lv_obj_create(parent);

    lv_obj_set_width(card, lv_pct(100));
    lv_obj_set_height(card, LV_SIZE_CONTENT);

    lv_obj_set_style_bg_color(card, CLR_SURFACE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
    lv_obj_set_style_border_color(card, CLR_BORDER, LV_PART_MAIN);

    lv_obj_set_style_radius(card, sc(16), LV_PART_MAIN);

    lv_obj_set_style_pad_all(card, sc(16), LV_PART_MAIN);

    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        card,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_set_style_pad_row(card, sc(8), LV_PART_MAIN);

    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- heading row ---------------- */

    lv_obj_t *row = lv_obj_create(card);

    make_transparent(row);

    lv_obj_set_width(row, lv_pct(100));
    lv_obj_set_height(row, LV_SIZE_CONTENT);

    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        row,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_set_style_pad_column(row, sc(8), LV_PART_MAIN);

    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);


    /* status dot: amber while stabilizing (theme.py: warning) */
    lv_obj_t *dot = lv_obj_create(row);

    lv_obj_set_size(dot, sc(12), sc(12));

    lv_obj_set_style_bg_color(dot, CLR_WARNING, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
    lv_obj_set_style_border_width(dot, 0, LV_PART_MAIN);

    lv_obj_clear_flag(dot, LV_OBJ_FLAG_SCROLLABLE);


    lv_obj_t *status = lv_label_create(row);

    lv_label_set_text(
        status,
        "Temperature Stabilization in progress"
    );

    lv_obj_set_style_text_font(status, F_STATUS, LV_PART_MAIN);
    lv_obj_set_style_text_color(status, CLR_TEXT, LV_PART_MAIN);

    lv_obj_set_flex_grow(status, 1);


    /* ---------------- right-hand readout ---------------- */

    lv_obj_t *temp_box = lv_obj_create(row);

    make_transparent(temp_box);

    lv_obj_set_size(temp_box, LV_SIZE_CONTENT, LV_SIZE_CONTENT);

    lv_obj_set_flex_flow(temp_box, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        temp_box,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_END,
        LV_FLEX_ALIGN_END
    );

    lv_obj_clear_flag(temp_box, LV_OBJ_FLAG_SCROLLABLE);


    lv_obj_t *value = lv_label_create(temp_box);

    lv_label_set_text(value, "07:00");

    lv_obj_set_style_text_font(value, F_VALUE, LV_PART_MAIN);
    lv_obj_set_style_text_color(value, CLR_TEXT_MUTED, LV_PART_MAIN);


    lv_obj_t *unit = lv_label_create(temp_box);

    lv_label_set_text(unit, "time remaining");

    lv_obj_set_style_text_font(unit, F_CAPTION, LV_PART_MAIN);
    lv_obj_set_style_text_color(unit, CLR_TEXT_MUTED, LV_PART_MAIN);


    /* ---------------- progress bar ---------------- */

    lv_obj_t *bar = lv_bar_create(card);

    lv_obj_set_width(bar, lv_pct(100));
    lv_obj_set_height(bar, sc(10));

    lv_obj_set_style_radius(bar, sc(6), LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar, CLR_SURFACE_SUNKEN, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_set_style_radius(bar, sc(6), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(bar, CLR_ACCENT, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_INDICATOR);

    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, 30, LV_ANIM_OFF);


    /* ---------------- caption ---------------- */

    lv_obj_t *caption = lv_label_create(card);

    lv_label_set_text(
        caption,
        "Keep the instrument switched on - ready to measure in 7 minute(s)."
    );

    lv_obj_set_style_text_font(caption, F_CAPTION, LV_PART_MAIN);
    lv_obj_set_style_text_color(caption, CLR_TEXT_MUTED, LV_PART_MAIN);

    lv_obj_set_width(caption, lv_pct(100));
    lv_label_set_long_mode(caption, LV_LABEL_LONG_MODE_WRAP);

    return card;
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

    lv_obj_set_style_pad_all(home_layer, sc(18), LV_PART_MAIN);

    lv_obj_set_flex_flow(home_layer, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        home_layer,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_set_style_pad_row(home_layer, sc(8), LV_PART_MAIN);

    lv_obj_clear_flag(home_layer, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- top bar ---------------- */

    lv_obj_t *top_bar = lv_obj_create(home_layer);

    make_transparent(top_bar);

    lv_obj_set_width(top_bar, lv_pct(100));
    lv_obj_set_height(top_bar, LV_SIZE_CONTENT);

    lv_obj_set_flex_flow(top_bar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        top_bar,
        LV_FLEX_ALIGN_END,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_clear_flag(top_bar, LV_OBJ_FLAG_SCROLLABLE);

    create_theme_switch(top_bar);


    /* ---------------- status card ---------------- */

    create_status_card(home_layer);


    /* ---------------- six menu cards ---------------- */

    lv_obj_t *cards = lv_obj_create(home_layer);

    make_transparent(cards);

    lv_obj_set_width(cards, lv_pct(100));
    lv_obj_set_flex_grow(cards, 1);

    lv_obj_clear_flag(cards, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_set_style_pad_row(cards, sc(6), LV_PART_MAIN);
    lv_obj_set_style_pad_column(cards, sc(6), LV_PART_MAIN);

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

    lv_obj_set_grid_dsc_array(cards, columns, rows);

    for(size_t i = 0; i < ANALYZER_SCREEN_COUNT; i++)
    {
        lv_obj_t *card = create_menu_card(
            cards,
            &menu_entries[i],
            i
        );

        lv_obj_set_grid_cell(
            card,
            LV_GRID_ALIGN_STRETCH,
            (int32_t)(i % 3),
            1,
            LV_GRID_ALIGN_STRETCH,
            (int32_t)(i / 3),
            1
        );
    }
}


/* =========================================================
 * DESTINATION PAGE
 *
 * Placeholder for the screens that are not ported yet. One
 * uniform template keeps the delete-before-create switch
 * inside the memory budget, exactly as the memory test
 * requires: the blocks freed by the outgoing page are the
 * sizes the incoming page asks for.
 * ========================================================= */

static void back_event_cb(lv_event_t *e)
{
    LV_UNUSED(e);

    analyzer_ui_go_home();
}

static lv_obj_t *create_screen_page(analyzer_screen_t screen)
{
    const menu_entry_t *entry = &menu_entries[screen];

    lv_obj_t *page = lv_obj_create(lv_screen_active());

    lv_obj_set_size(page, lv_pct(100), lv_pct(100));
    lv_obj_align(page, LV_ALIGN_CENTER, 0, 0);

    lv_obj_set_style_bg_color(page, CLR_WINDOW_BG, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(page, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(page, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(page, 0, LV_PART_MAIN);

    lv_obj_set_style_pad_all(page, sc(18), LV_PART_MAIN);

    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        page,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    lv_obj_set_style_pad_row(page, sc(10), LV_PART_MAIN);

    lv_obj_clear_flag(page, LV_OBJ_FLAG_SCROLLABLE);


    /* ---------------- back button ---------------- */

    lv_obj_t *back = lv_button_create(page);

    lv_obj_set_size(back, sc(110), sc(48));

    lv_obj_set_style_bg_color(back, CLR_ACCENT, LV_PART_MAIN);
    lv_obj_set_style_radius(back, sc(10), LV_PART_MAIN);
    lv_obj_set_style_text_color(back, CLR_TEXT_ON_ACCENT, LV_PART_MAIN);
    lv_obj_set_style_text_font(back, F_STATUS, LV_PART_MAIN);
    lv_obj_set_style_shadow_width(back, 0, LV_PART_MAIN);

    lv_obj_add_event_cb(
        back,
        back_event_cb,
        LV_EVENT_CLICKED,
        NULL
    );

    lv_obj_t *back_label = lv_label_create(back);

    lv_label_set_text(back_label, LV_SYMBOL_LEFT "  BACK");

    lv_obj_center(back_label);


    /* ---------------- title ---------------- */

    lv_obj_t *title = lv_label_create(page);

    lv_label_set_text(title, entry->title);

    lv_obj_set_style_text_font(title, F_PAGE_TITLE, LV_PART_MAIN);
    lv_obj_set_style_text_color(title, CLR_TEXT, LV_PART_MAIN);


    /* ---------------- body ---------------- */

    lv_obj_t *body = lv_label_create(page);

    lv_label_set_text(
        body,
        "This screen is not ported yet.\n"
        "The CustomTkinter original is in ui/ui/."
    );

    lv_obj_set_style_text_font(body, F_STATUS, LV_PART_MAIN);
    lv_obj_set_style_text_color(body, CLR_TEXT_MUTED, LV_PART_MAIN);

    lv_obj_set_width(body, lv_pct(100));
    lv_label_set_long_mode(body, LV_LABEL_LONG_MODE_WRAP);

    return page;
}


/* =========================================================
 * NAVIGATION
 * ========================================================= */

size_t analyzer_ui_open(analyzer_screen_t screen)
{
    size_t before = analyzer_ui_heap_used();

    /* Delete before create: the two pages are never alive together. */
    if(current_page != NULL)
    {
        lv_obj_delete(current_page);
        current_page = NULL;
    }

    size_t after_delete = analyzer_ui_heap_used();

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

void analyzer_ui_go_home(void)
{
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
    build_home();
}
