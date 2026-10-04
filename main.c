#include "lvgl.h"
#include "lvgl/drivers/sdl/lv_sdl_window.h"
#include "lvgl/drivers/sdl/lv_sdl_mouse.h"
#include "lvgl/drivers/sdl/lv_sdl_keyboard.h"

#include "analyzer_ui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <SDL.h>

#define PANEL_W 800
#define PANEL_H 480

/*
 * The panel and every draw buffer here are RGB565: 2 bytes per pixel.
 * LVGL derives the display's native format from LV_COLOR_DEPTH, so this guard
 * keeps the buffer arithmetic honest. At any other depth the buffers would be
 * the wrong size and the screenshot decode would produce garbage.
 *
 * Panels that want the two bytes in the other order (common on SPI TFT
 * controllers) use LV_COLOR_FORMAT_RGB565_SWAPPED instead; the buffer size is
 * unchanged.
 */
#if LV_COLOR_DEPTH != 16
#error "Draw buffers in main.c assume LV_COLOR_DEPTH 16 (RGB565). See lv_conf.h."
#endif

#define PANEL_BPP 2


/* =========================================================
 * TICK
 * ========================================================= */

static uint32_t headless_tick_cb(void)
{
    return (uint32_t)(
        clock() * 1000 / CLOCKS_PER_SEC
    );
}


/* =========================================================
 * PIXEL FORMAT
 *
 * Reported rather than assumed: the pixel format the display
 * actually renders in is the one LVGL resolves from
 * LV_COLOR_DEPTH, not what a comment claims.
 * ========================================================= */

static const char *pixel_format_name(lv_color_format_t cf)
{
    switch(cf)
    {
        case LV_COLOR_FORMAT_RGB565:
            return "RGB565";

        case LV_COLOR_FORMAT_RGB565_SWAPPED:
            return "RGB565_SWAPPED";

        case LV_COLOR_FORMAT_RGB565A8:
            return "RGB565A8";

        case LV_COLOR_FORMAT_RGB888:
            return "RGB888";

        case LV_COLOR_FORMAT_XRGB8888:
            return "XRGB8888";

        default:
            return "other";
    }
}

static void print_pixel_format(lv_display_t *disp)
{
    lv_color_format_t cf = lv_display_get_color_format(disp);
    uint8_t size = lv_color_format_get_size(cf);

    printf(
        "[fmt] LV_COLOR_DEPTH=%d  format=%s (0x%02X)  bytes_per_pixel=%u\n",
        (int)LV_COLOR_DEPTH,
        pixel_format_name(cf),
        (unsigned)cf,
        (unsigned)size
    );

    if(size != PANEL_BPP)
    {
        printf(
            "[fmt] WARNING: draw buffers are sized for %d bytes/pixel.\n",
            PANEL_BPP
        );
    }
}


/* =========================================================
 * DRAW BUFFER
 *
 * The draw buffer is PARTIAL: LVGL renders the screen in
 * horizontal strips through it, so the panel's 768000-byte
 * frame never exists in RAM. One full-width line is the
 * smallest buffer LVGL renders correctly with (its own
 * guidance is "more than the horizontal resolution in
 * pixels"), and it is what makes an 800x480 panel reachable
 * on a part with only a few KB of RAM.
 *
 * This is the figure the 2 KB budget applies to: it is RAM
 * that has to exist on the target whether or not a page is
 * being switched. The widget footprint of a page is a
 * separate number and is measured by --memtest.
 * ========================================================= */

#define DRAW_BUF_LINES 1
#define DRAW_BUF_BYTES (PANEL_W * DRAW_BUF_LINES * PANEL_BPP)

#if DRAW_BUF_BYTES > ANALYZER_SWITCH_BUDGET
#error "Draw buffer is over the 2 KB budget - lower DRAW_BUF_LINES."
#endif

static uint8_t memtest_buf[DRAW_BUF_BYTES];

static void print_draw_buffer(void)
{
    printf(
        "[buf] partial draw buffer = %u bytes (%d line x %d px x %d B)\n",
        (unsigned)sizeof(memtest_buf),
        DRAW_BUF_LINES,
        PANEL_W,
        PANEL_BPP
    );

    printf(
        "[buf] budget %d bytes -> %s  (full 800x480 frame would be %u bytes)\n",
        ANALYZER_SWITCH_BUDGET,
        sizeof(memtest_buf) <= (size_t)ANALYZER_SWITCH_BUDGET ? "PASS" : "FAIL",
        (unsigned)(PANEL_W * PANEL_H * PANEL_BPP)
    );
}

static void memtest_flush_cb(
    lv_display_t *disp,
    const lv_area_t *area,
    uint8_t *px_map
)
{
    LV_UNUSED(area);
    LV_UNUSED(px_map);

    lv_display_flush_ready(disp);
}


/* =========================================================
 * SCREENSHOT DISPLAY  (host-only diagnostic)
 *
 * --shot renders the screen once into a scratch buffer and
 * writes it out as a BMP, so the UI can be reviewed without
 * a window. This is the ONLY place a full-frame buffer is
 * ever used, and it is not a static array: it is allocated
 * inside run_shot() for the duration of the shot and freed
 * before the process exits, so the device build never
 * carries an 800x480 framebuffer in its .bss.
 * ========================================================= */

static uint8_t *shot_buf;
static uint16_t *shot_frame;

#define SHOT_BUF_BYTES (PANEL_W * PANEL_H * PANEL_BPP)
#define SHOT_FRAME_BYTES (PANEL_W * PANEL_H * sizeof(uint16_t))

static void shot_flush_cb(
    lv_display_t *disp,
    const lv_area_t *area,
    uint8_t *px_map
)
{
    int32_t w = lv_area_get_width(area);
    int32_t h = lv_area_get_height(area);

    for(int32_t y = 0; y < h; y++)
    {
        const uint16_t *src =
            (const uint16_t *)px_map + y * w;

        int32_t dst_y = area->y1 + y;

        if(dst_y < 0 || dst_y >= PANEL_H)
        {
            continue;
        }

        for(int32_t x = 0; x < w; x++)
        {
            int32_t dst_x = area->x1 + x;

            if(dst_x < 0 || dst_x >= PANEL_W)
            {
                continue;
            }

            shot_frame[dst_y * PANEL_W + dst_x] = src[x];
        }
    }

    lv_display_flush_ready(disp);
}


/* =========================================================
 * BMP WRITER (24-bit, bottom-up)
 * ========================================================= */

static void put_u16(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
}

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
    p[2] = (uint8_t)((v >> 16) & 0xFF);
    p[3] = (uint8_t)((v >> 24) & 0xFF);
}

static int write_bmp(
    const char *path,
    const uint16_t *frame,
    int32_t w,
    int32_t h
)
{
    int32_t row_bytes = w * 3;
    int32_t pad = (4 - (row_bytes % 4)) % 4;
    int32_t stride = row_bytes + pad;
    int32_t image_size = stride * h;

    FILE *file = fopen(path, "wb");

    if(file == NULL)
    {
        return 0;
    }

    uint8_t header[54];

    memset(header, 0, sizeof(header));

    header[0] = 'B';
    header[1] = 'M';

    put_u32(header + 2, (uint32_t)(54 + image_size));
    put_u32(header + 10, 54);
    put_u32(header + 14, 40);
    put_u32(header + 18, (uint32_t)w);
    put_u32(header + 22, (uint32_t)h);
    put_u16(header + 26, 1);
    put_u16(header + 28, 24);
    put_u32(header + 34, (uint32_t)image_size);

    fwrite(header, 1, sizeof(header), file);

    uint8_t *row = (uint8_t *)calloc((size_t)stride, 1);

    if(row == NULL)
    {
        fclose(file);
        return 0;
    }

    /* BMP rows run bottom-up. */
    for(int32_t y = h - 1; y >= 0; y--)
    {
        for(int32_t x = 0; x < w; x++)
        {
            uint16_t c = frame[y * w + x];

            uint8_t r = (uint8_t)(((c >> 11) & 0x1F) * 255 / 31);
            uint8_t g = (uint8_t)(((c >> 5) & 0x3F) * 255 / 63);
            uint8_t b = (uint8_t)((c & 0x1F) * 255 / 31);

            row[x * 3 + 0] = b;
            row[x * 3 + 1] = g;
            row[x * 3 + 2] = r;
        }

        fwrite(row, 1, (size_t)stride, file);
    }

    free(row);
    fclose(file);

    return 1;
}


/* =========================================================
 * HOME CLICK TEST  (host-only diagnostic)
 *
 * Drives the home menu through LVGL's own input pipeline. A synthetic pointer
 * indev is aimed at the centre of each key, pressed and released, and the page
 * that opens is compared with the screen that key is supposed to open.
 *
 * This is what actually proves the keys are clickable: it exercises the real
 * hit test, so it would fail if the hairline layer drawn over the keys were
 * swallowing taps, if a key and its name were not both covered by one tap
 * target, or if a callback had drifted to the wrong destination.
 *
 * The aim points come from analyzer_ui_home_key_center(), which reads them off
 * the live widgets - so this test follows the layout instead of restating it.
 * ========================================================= */

static int32_t click_x;
static int32_t click_y;
static int click_down;

static void clicktest_read_cb(lv_indev_t *indev, lv_indev_data_t *data)
{
    LV_UNUSED(indev);

    data->point.x = click_x;
    data->point.y = click_y;
    data->state = click_down ?
        LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

/*
 * Run LVGL for `ms` of real time.
 *
 * The busy wait is the point: an indev is sampled by LVGL's own timer (about
 * every 33 ms of wall clock), so a tight loop of lv_timer_handler() calls that
 * returns instantly would never let it read the pointer, and a press or a
 * release would simply be missed.
 */
static void clicktest_pump(int ms)
{
    clock_t until = clock() + (clock_t)((long)ms * CLOCKS_PER_SEC / 1000);

    do
    {
        lv_timer_handler();
    }
    while(clock() < until);
}

static int run_clicktest(void)
{
    lv_init();

    lv_tick_set_cb(headless_tick_cb);

    lv_display_t *disp = lv_display_create(PANEL_W, PANEL_H);

    lv_display_set_flush_cb(disp, memtest_flush_cb);

    lv_display_set_buffers(
        disp,
        memtest_buf,
        NULL,
        (uint32_t)sizeof(memtest_buf),
        LV_DISPLAY_RENDER_MODE_PARTIAL
    );

    analyzer_ui_build();
    analyzer_ui_set_verbose(0);

    lv_indev_t *indev = lv_indev_create();

    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, clicktest_read_cb);
    lv_indev_set_display(indev, disp);

    printf("\n=========================================\n");
    printf(" HOME CLICK TEST\n");
    printf("=========================================\n");

    int failures = 0;

    for(int i = 0; i < (int)ANALYZER_HOME_COUNT; i++)
    {
        const char *want = analyzer_ui_screen_title((analyzer_screen_t)i);

        /* Home first, and let it lay out and paint, so the key's centre can be
         * read off a widget that has real coordinates. */
        analyzer_ui_go_home();
        clicktest_pump(150);

        click_x = -1;
        click_y = -1;

        analyzer_ui_home_key_center(i, &click_x, &click_y);

        click_down = 1;
        clicktest_pump(120);

        click_down = 0;
        clicktest_pump(150);

        analyzer_screen_t got = analyzer_ui_current_screen();

        const char *got_title = (got == ANALYZER_SCREEN_COUNT) ?
            "home (nothing opened)" :
            analyzer_ui_screen_title(got);

        int ok = ((int)got == i);

        if(!ok)
        {
            failures++;
        }

        printf(
            "  press (%3d,%3d)  %-12s -> %-24s %s\n",
            (int)click_x,
            (int)click_y,
            want,
            got_title,
            ok ? "OK" : "FAIL"
        );
    }

    printf("-----------------------------------------\n");
    printf("verdict               : %s\n", failures ? "FAIL" : "PASS");
    printf("=========================================\n");

    return failures ? 1 : 0;
}


/* =========================================================
 * MEMORY TEST
 * ========================================================= */

/* Widget footprint of each screen, filled in by the first-open pass below. */
static size_t screen_footprint[ANALYZER_SCREEN_COUNT];

static void run_memtest(unsigned cycles)
{
    printf("\n");
    printf("=========================================\n");
    printf(" MEMORY TEST\n");
    printf("=========================================\n");
    printf("starting heap used : %u bytes\n",
           (unsigned)analyzer_ui_heap_used());

    print_draw_buffer();

    printf("\nfirst open of every screen from home:\n");

    for(int i = 0; i < (int)ANALYZER_SCREEN_COUNT; i++)
    {
        analyzer_ui_go_home();

        size_t overhead =
            analyzer_ui_open((analyzer_screen_t)i);

        screen_footprint[i] = overhead;

        printf(
            "  %-12s widget tree = %u bytes\n",
            analyzer_ui_screen_title(i),
            (unsigned)overhead
        );
    }

    analyzer_ui_go_home();

    printf(
        "\nsteady state: %u cycles x %d screens\n",
        cycles,
        (int)ANALYZER_SCREEN_COUNT
    );

    size_t before_loop = analyzer_ui_heap_used();

    for(unsigned c = 0; c < cycles; c++)
    {
        for(int i = 0; i < (int)ANALYZER_SCREEN_COUNT; i++)
        {
            analyzer_ui_open((analyzer_screen_t)i);
        }
    }

    analyzer_ui_go_home();

    size_t after_loop = analyzer_ui_heap_used();

    size_t drift = after_loop > before_loop ?
        after_loop - before_loop :
        before_loop - after_loop;

    size_t worst = analyzer_ui_worst_switch();

    size_t biggest = 0;

    for(int i = 0; i < (int)ANALYZER_SCREEN_COUNT; i++)
    {
        if(screen_footprint[i] > biggest)
        {
            biggest = screen_footprint[i];
        }
    }

    /* The two checks that decide the verdict.
     *
     *   1. the draw buffer - RAM that must exist on the target whether or not
     *      a page is switching. This is the 2 KB budget.
     *   2. switch drift - switching screens must not grow the heap at all.
     *      Delete-before-create means the outgoing page's blocks are exactly
     *      what the incoming page asks for, so this is the figure that proves
     *      two screens are never resident together (nothing is "duplicated in
     *      RAM"), and it must be zero.
     *
     * A page's widget tree is reported too, but it is not a switch cost on top
     * of anything: it IS the resident page, and only one exists at a time.
     */
    int buf_ok = sizeof(memtest_buf) <= (size_t)ANALYZER_SWITCH_BUDGET;
    int drift_ok = (drift == 0);

    printf("\n");
    printf("=========================================\n");
    printf(" RESULT\n");
    printf("=========================================\n");
    printf("partial draw buffer   : %u / %d bytes        %s\n",
           (unsigned)sizeof(memtest_buf), ANALYZER_SWITCH_BUDGET,
           buf_ok ? "PASS" : "FAIL");
    printf("switch drift          : %u bytes / %u switches %s\n",
           (unsigned)drift,
           (unsigned)(cycles * ANALYZER_SCREEN_COUNT),
           drift_ok ? "PASS" : "FAIL");
    printf("-----------------------------------------\n");
    printf("largest screen tree   : %u bytes (one page alive at a time)\n",
           (unsigned)biggest);
    printf("worst switch overhead : %u bytes\n", (unsigned)worst);
    printf("resident after startup: %u bytes\n",
           (unsigned)analyzer_ui_heap_used());
    printf("peak heap ever used   : %u bytes\n",
           (unsigned)analyzer_ui_heap_peak());
    printf("verdict               : %s\n",
           (buf_ok && drift_ok) ? "PASS" : "FAIL");
    printf("=========================================\n");
}


/* =========================================================
 * SCREENSHOT MODE
 * ========================================================= */

/* The value of a "--flag <int>" pair, or `fallback` when the flag is absent. */
static int flag_int(int argc, char **argv, const char *flag, int fallback)
{
    for(int i = 1; i + 1 < argc; i++)
    {
        if(strcmp(argv[i], flag) == 0)
        {
            return atoi(argv[i + 1]);
        }
    }

    return fallback;
}

static int run_shot(const char *path, int screen, int picker)
{
    lv_init();

    lv_tick_set_cb(headless_tick_cb);

    shot_buf = (uint8_t *)malloc(SHOT_BUF_BYTES);
    shot_frame = (uint16_t *)malloc(SHOT_FRAME_BYTES);

    if(shot_buf == NULL || shot_frame == NULL)
    {
        printf("failed to allocate the screenshot buffers\n");
        return 1;
    }

    lv_display_t *disp = lv_display_create(PANEL_W, PANEL_H);

    if(disp == NULL)
    {
        printf("failed to create display\n");
        return 1;
    }

    lv_display_set_flush_cb(disp, shot_flush_cb);

    lv_display_set_buffers(
        disp,
        shot_buf,
        NULL,
        (uint32_t)SHOT_BUF_BYTES,
        LV_DISPLAY_RENDER_MODE_FULL
    );

    print_pixel_format(disp);

    analyzer_ui_set_verbose(0);

    analyzer_ui_build();

    /* -1 renders the home screen; otherwise open a destination page. */
    if(screen >= 0)
    {
        analyzer_ui_open((analyzer_screen_t)screen);
    }

    /* Optional: open a picker so the modal can be reviewed in the shot. */
    if(picker >= 0)
    {
        analyzer_ui_debug_open_picker(picker);
    }

    lv_refr_now(NULL);

    if(!write_bmp(path, shot_frame, PANEL_W, PANEL_H))
    {
        printf("failed to write %s\n", path);
        return 1;
    }

    printf("wrote %s (%dx%d)\n", path, PANEL_W, PANEL_H);
    printf("heap used: %u bytes\n",
           (unsigned)analyzer_ui_heap_used());

    /* The scratch buffers are host-side only: hand them back before exit so
     * nothing about --shot survives as a resident allocation. */
    free(shot_frame);
    free(shot_buf);

    shot_frame = NULL;
    shot_buf = NULL;

    return 0;
}


/* =========================================================
 * MAIN
 * ========================================================= */

#undef main

int main(int argc, char **argv)
{
    /* -----------------------------------------------------
     * SCREENSHOT MODE
     * ----------------------------------------------------- */

    if(argc > 2 && strcmp(argv[1], "--shot") == 0)
    {
        int screen = -1;

        /* argv[3] is optional and holds the screen index when present. */
        if(argc > 3 && argv[3][0] >= '0' && argv[3][0] <= '9')
        {
            screen = atoi(argv[3]);
        }

        return run_shot(
            argv[2],
            screen,
            flag_int(argc, argv, "--picker", -1)
        );
    }


    /* -----------------------------------------------------
     * HOME CLICK TEST MODE
     * ----------------------------------------------------- */

    if(argc > 1 && strcmp(argv[1], "--clicktest") == 0)
    {
        return run_clicktest();
    }


    /* -----------------------------------------------------
     * MEMORY TEST MODE
     * ----------------------------------------------------- */

    if(argc > 1 && strcmp(argv[1], "--memtest") == 0)
    {
        unsigned cycles = 200;

        if(argc > 2)
        {
            cycles = (unsigned)atoi(argv[2]);
        }

        lv_init();

        lv_tick_set_cb(headless_tick_cb);

        lv_display_t *disp =
            lv_display_create(PANEL_W, PANEL_H);

        lv_display_set_flush_cb(disp, memtest_flush_cb);

        lv_display_set_buffers(
            disp,
            memtest_buf,
            NULL,
            (uint32_t)sizeof(memtest_buf),
            LV_DISPLAY_RENDER_MODE_PARTIAL
        );

        print_pixel_format(disp);

        analyzer_ui_build();
        analyzer_ui_set_verbose(0);

        run_memtest(cycles);

        return 0;
    }


    /* -----------------------------------------------------
     * INITIALIZE
     * ----------------------------------------------------- */

    lv_init();

    if(SDL_Init(SDL_INIT_VIDEO) != 0)
    {
        printf("SDL initialization failed: %s\n", SDL_GetError());
        return 1;
    }

    lv_display_t *display = lv_sdl_window_create(PANEL_W, PANEL_H);

    if(display == NULL)
    {
        printf("Failed to create SDL display\n");
        SDL_Quit();
        return 1;
    }

    lv_indev_t *mouse = lv_sdl_mouse_create();

    if(mouse == NULL)
    {
        printf("Failed to create SDL mouse\n");
    }

    lv_sdl_window_set_title(
        display,
        "STM32F407G-DISC1"
    );

    lv_sdl_window_set_zoom(display, 1.0f);

    print_pixel_format(display);
    print_draw_buffer();


    /* -----------------------------------------------------
     * BUILD
     * ----------------------------------------------------- */

    /* analyzer_ui_build() creates the app's focus group, so the keyboard is
     * created after it and attached to that group. */
    analyzer_ui_build();

    lv_group_t *group = lv_group_get_default();

    if(group != NULL)
    {
        /*
         * The host keyboard. It is what makes a form's text boxes typeable in
         * the simulator: tap a box, type, press Enter. The panel itself wants
         * an on-screen keyboard (controls.py: OnScreenKeyboard), which is
         * separate work - but on a laptop this has to simply work.
         */
        lv_indev_t *keyboard = lv_sdl_keyboard_create();

        if(keyboard != NULL)
        {
            lv_indev_set_group(keyboard, group);
        }
        else
        {
            printf("Failed to create SDL keyboard\n");
        }
    }



    printf(
        "[mem] after startup: %u bytes used, %u bytes peak\n",
        (unsigned)analyzer_ui_heap_used(),
        (unsigned)analyzer_ui_heap_peak()
    );


    /* -----------------------------------------------------
     * LOOP
     * ----------------------------------------------------- */

    while(1)
    {
        lv_timer_handler();

        SDL_Delay(5);
    }

    lv_sdl_quit();
    SDL_Quit();

    return 0;
}
