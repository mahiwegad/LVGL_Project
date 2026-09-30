#include "lvgl.h"
#include "lvgl/drivers/sdl/lv_sdl_window.h"
#include "lvgl/drivers/sdl/lv_sdl_mouse.h"

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
 * MEMORY-TEST DISPLAY (no window)
 *
 * A small partial buffer and a no-op flush is all the memory
 * test needs: it measures object/style allocation, not
 * pixels.
 * ========================================================= */

static uint8_t memtest_buf[PANEL_W * 20 * PANEL_BPP];

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
 * SCREENSHOT DISPLAY
 *
 * Renders the whole screen into one buffer and keeps a copy
 * of the pixels, so the UI can be written out as an image
 * and looked at without a window.
 * ========================================================= */

static uint8_t shot_buf[PANEL_W * PANEL_H * PANEL_BPP];
static uint16_t shot_frame[PANEL_W * PANEL_H];

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
 * MEMORY TEST
 * ========================================================= */

static void run_memtest(unsigned cycles)
{
    printf("\n");
    printf("=========================================\n");
    printf(" PAGE SWITCH MEMORY TEST\n");
    printf("=========================================\n");
    printf("starting heap used : %u bytes\n",
           (unsigned)analyzer_ui_heap_used());

    printf("\nfirst open of every screen from home:\n");

    for(int i = 0; i < (int)ANALYZER_SCREEN_COUNT; i++)
    {
        analyzer_ui_go_home();

        size_t overhead =
            analyzer_ui_open((analyzer_screen_t)i);

        printf(
            "  %-12s footprint=%u bytes\n",
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

    printf("\n");
    printf("=========================================\n");
    printf(" RESULT\n");
    printf("=========================================\n");
    printf("worst switch overhead : %u bytes\n", (unsigned)worst);
    printf("steady-state drift    : %u bytes over %u switches\n",
           (unsigned)drift,
           (unsigned)(cycles * ANALYZER_SCREEN_COUNT));
    printf("peak heap ever used   : %u bytes\n",
           (unsigned)analyzer_ui_heap_peak());
    printf("budget                : %d bytes\n", ANALYZER_SWITCH_BUDGET);
    printf("verdict               : %s\n",
           worst <= (size_t)ANALYZER_SWITCH_BUDGET ? "PASS" : "FAIL");
    printf("=========================================\n");
}


/* =========================================================
 * SCREENSHOT MODE
 * ========================================================= */

static int run_shot(const char *path, int screen)
{
    lv_init();

    lv_tick_set_cb(headless_tick_cb);

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
        (uint32_t)sizeof(shot_buf),
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

    lv_refr_now(NULL);

    if(!write_bmp(path, shot_frame, PANEL_W, PANEL_H))
    {
        printf("failed to write %s\n", path);
        return 1;
    }

    printf("wrote %s (%dx%d)\n", path, PANEL_W, PANEL_H);
    printf("heap used: %u bytes\n",
           (unsigned)analyzer_ui_heap_used());

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
        int screen = argc > 3 ? atoi(argv[3]) : -1;

        return run_shot(argv[2], screen);
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
        "Biochemistry Analyzer"
    );

    lv_sdl_window_set_zoom(display, 1.0f);

    print_pixel_format(display);


    /* -----------------------------------------------------
     * BUILD
     * ----------------------------------------------------- */

    analyzer_ui_build();

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
