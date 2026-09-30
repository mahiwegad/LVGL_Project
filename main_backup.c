#include "lvgl.h"
#include "lvgl/drivers/sdl/lv_sdl_window.h"
#include "lvgl/drivers/sdl/lv_sdl_mouse.h"

#include <stdio.h>
#include <SDL.h>

static int counter = 0;
static lv_obj_t *counter_label;
static lv_obj_t *status_label;


/* ---------------- BUTTON ---------------- */

static void button_event_cb(lv_event_t *e)
{
    counter++;

    char text[32];
    sprintf(text, "Counter: %d", counter);

    lv_label_set_text(counter_label, text);
    lv_label_set_text(status_label, "Button Pressed!");
}


/* ---------------- SLIDER ---------------- */

static void slider_event_cb(lv_event_t *e)
{
    lv_obj_t *slider = lv_event_get_target(e);

    int value = lv_slider_get_value(slider);

    char text[32];
    sprintf(text, "Brightness: %d%%", value);

    lv_label_set_text(status_label, text);
}


/* ---------------- GUI ---------------- */

static void create_gui(void)
{
    lv_obj_t *screen = lv_screen_active();

    /* Background */
    lv_obj_set_style_bg_color(
        screen,
        lv_color_hex(0x202020),
        LV_PART_MAIN
    );


    /* Title */
    lv_obj_t *title = lv_label_create(screen);

    lv_label_set_text(
        title,
        "STM32 LVGL Demo"
    );

    lv_obj_align(
        title,
        LV_ALIGN_TOP_MID,
        0,
        30
    );


    /* Counter */
    counter_label = lv_label_create(screen);

    lv_label_set_text(
        counter_label,
        "Counter: 0"
    );

    lv_obj_align(
        counter_label,
        LV_ALIGN_CENTER,
        0,
        -80
    );


    /* Button */
    lv_obj_t *button = lv_button_create(screen);

    lv_obj_set_size(
        button,
        180,
        60
    );

    lv_obj_align(
        button,
        LV_ALIGN_CENTER,
        0,
        -10
    );

    lv_obj_add_event_cb(
        button,
        button_event_cb,
        LV_EVENT_CLICKED,
        NULL
    );


    /* Button text */
    lv_obj_t *button_label = lv_label_create(button);

    lv_label_set_text(
        button_label,
        "PRESS ME"
    );

    lv_obj_center(button_label);


    /* Slider */
    lv_obj_t *slider = lv_slider_create(screen);

    lv_obj_set_width(
        slider,
        250
    );

    lv_slider_set_value(
        slider,
        50,
        LV_ANIM_OFF
    );

    lv_obj_align(
        slider,
        LV_ALIGN_CENTER,
        0,
        80
    );

    lv_obj_add_event_cb(
        slider,
        slider_event_cb,
        LV_EVENT_VALUE_CHANGED,
        NULL
    );


    /* Status */
    status_label = lv_label_create(screen);

    lv_label_set_text(
        status_label,
        "Ready"
    );

    lv_obj_align(
        status_label,
        LV_ALIGN_BOTTOM_MID,
        0,
        -30
    );
}


/* ---------------- MAIN ---------------- */
#undef main
int main()
{
    /* Initialize LVGL */
    lv_init();

    /* Initialize SDL */
    if(SDL_Init(SDL_INIT_VIDEO) != 0)
    {
        printf("SDL initialization failed: %s\n", SDL_GetError());
        return 1;
    }


    /* Create LVGL SDL window */
    lv_display_t *display =
        lv_sdl_window_create(800, 480);

    if(display == NULL)
    {
        printf("Failed to create SDL display\n");
        SDL_Quit();
        return 1;
    }


    /* Create mouse input */
    lv_indev_t *mouse =
        lv_sdl_mouse_create();

    if(mouse == NULL)
    {
        printf("Failed to create SDL mouse\n");
    }


    /* Window settings */
    lv_sdl_window_set_title(
        display,
        "LVGL - STM32F0 Test"
    );

    lv_sdl_window_set_zoom(
        display,
        1.0f
    );


    /* Create our GUI */
    create_gui();


    /* Main LVGL loop */
    while(1)
    {
        lv_timer_handler();

        SDL_Delay(5);
    }


    /* Cleanup */
    lv_sdl_quit();
    SDL_Quit();

    return 0;
}
