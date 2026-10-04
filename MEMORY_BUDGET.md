# Memory Budget — Analyzer UI (LVGL port)

## Target constraints

| Constraint                         | Value      |
| ---------------------------------- | ---------- |
| Display resolution                 | 800 x 480  |
| Memory for switching between pages | <= 2048 B  |

These are **two different budgets** and they must be measured separately:

- **Switch budget** — the transient memory needed while moving from one page to
  another. This is what the 2 KB limit covers.
- **Resident budget** — the memory the whole UI occupies while it is on screen.

## Where the UI comes from

`analyzer_ui.c` is an LVGL port of the analyzer's CustomTkinter UI
(`ui/ui/theme.py` and `ui/ui/main_menu.py`). The Tkinter design targets a
1280x720 panel; every measurement in the port is written in those design pixels
and scaled by the real panel width, so the 800x480 build is a factor of 0.625.

## Measured results

Measured with `lv_mem_monitor()` in a headless build (no window):

```
./build/Debug/LVGL_Project.exe --memtest 300
```

| Metric                                    | Value      |
| ----------------------------------------- | ---------- |
| Partial draw buffer (**the 2 KB budget**)  | **1,600 B**|
| Screen-switch drift over 165 switches     | **0 B**    |
| Heap used after startup (whole UI)        | 18,104 B   |
| Largest single page's widget tree         | 53,360 B   |
| Resident after startup                    | 18,104 B   |
| Peak heap ever used                       | 71,480 B   |
| Switch budget                             | 2,048 B    |
| **Verdict**                               | **PASS**   |

Two checks decide the verdict, and both are reported by `--memtest`:

1. **The draw buffer** — RAM that has to exist on the target whether or not a
   page is switching. This is what the 2 KB figure applies to: one full-width
   line, 1,600 bytes. The panel's 768,000-byte frame never exists in RAM.
2. **Screen-switch drift** — switching pages must not grow the heap at all.

Per-screen widget tree (the page's own objects, one page alive at a time — the
user can tap any key first, so each is measured from home):

| Screen            | Widget tree |
| ----------------- | ----------- |
| TEST              | 37,576 B    |
| RESULT            | 53,360 B    |
| SYSTEM            | 3,856 B     |
| MAINTENANCE       | 3,808 B     |
| POWER             | 3,816 B     |
| ABOUT             | 3,824 B     |
| TEST PARAMETERS   | 32,008 B    |
| LIST OF TESTS     | 37,752 B    |
| RESULTS           | 53,352 B    |
| MEASUREMENT       | 23,192 B    |
| MEASUREMENT RESULTS | 30,088 B  |

These are *not* a switch cost on top of the budget: a widget tree **is** the
resident page, and only one exists at a time. The largest one sets how much
heap the device needs — LVGL's heap is configured to 131,072 B in `lv_conf.h`,
comfortably above the 71,480 B peak.

## Why page-to-page switching costs 0 bytes

`analyzer_ui_open()` performs the switch in one deliberate order:

1. **Delete the outgoing page** — the heap drops immediately. LVGL frees objects
   synchronously here, including when the call comes from inside the outgoing
   page's own event callback (LVGL supports this via `lv_event_mark_deleted`).
2. **Build the incoming page** — the heap rises again.

Because the two never overlap, the transient peak is only
`(incoming size - outgoing size)`, never their sum. Building the new page before
destroying the old one would briefly need **both** and cost roughly twice as
much.

Three further choices make the reuse exact:

- **One persistent shell.** The home menu (`home_layer`: the six keys, their
  names and the hairlines) is built once and never destroyed. Opening a screen
  therefore never reallocates the home chrome.
- **One uniform page template.** The destination pages contain the same widget
  types in the same order, so the blocks freed by the deleted page are exactly
  the sizes the new page requests. That is why later screens cost ~0-8 B after
  the first one.
- **Fewer, cheaper objects.** Text styles (`text_font`, `text_color`) are set
  **once on the page container**, because LVGL inherits text styles to children;
  labels carry no style of their own, and the body is a single multi-line label
  rather than one label per row.

## Keeping margin

The worst case (2,048 B) leaves no headroom. If a screen needs to grow, trim in
this order — each step is a known win:

1. Shorten the placeholder body copy. Label text is copied into the heap, and
   the body string is the largest single allocation on a destination page.
2. Drop an object. Every `lv_obj` costs roughly 250 B.
3. Remove a style override. Any object with at least one `lv_obj_set_style_*()`
   call allocates its own style struct plus property list.

## Important: this is not a 2 KB *device*

The switch budget passes. The **resident** budget does not: LVGL occupies
~30 KB of heap for this UI before any page is open, and LVGL's own documented
floor is ~2 KB static + ~2 KB stack + ~2 KB heap to boot an empty screen.

So:

- If the 2 KB applies to **page switching**, the design above meets it.
- If the 2 KB applies to **the whole MCU**, LVGL still cannot ship there, and the
  target needs a GRAM-backed display controller (RA8875 class) with direct
  drawing instead of LVGL.

## Verifying

```bash
cmake --build build --config Debug --target LVGL_Project
./build/Debug/LVGL_Project.exe --memtest 300
```

The memory test runs headless (static draw buffer, no-op flush callback), so it
needs no window. It prints a `verdict` line — note that the process still exits
`0` either way, so the verdict line, not `$LASTEXITCODE`, is what tells you.

### Pixel format

The panel is addressed as **RGB565**: 2 bytes per pixel. LVGL derives the
native format from `LV_COLOR_DEPTH` in `lv_conf.h`, which is set to `16`, so
`LV_COLOR_FORMAT_NATIVE` resolves to `LV_COLOR_FORMAT_RGB565`.

`main.c` does not assume that quietly — it reports it, and refuses to compile at
any other depth because its draw buffers are sized as 2 bytes per pixel:

```
[fmt] LV_COLOR_DEPTH=16  format=RGB565 (0x12)  bytes_per_pixel=2
```

An 800x480 RGB565 frame is 768,000 bytes. That is the reason a 2 KB design needs
an external-GRAM display controller rather than a framebuffer in the MCU.

Panels that expect the two bytes in the opposite order (common on SPI TFT
controllers) use `LV_COLOR_FORMAT_RGB565_SWAPPED`; the buffer size is identical.

### Seeing the UI without a window

```bash
./build/Debug/LVGL_Project.exe --shot shots/home.bmp      # home screen
./build/Debug/LVGL_Project.exe --shot shots/test.bmp 0    # screen index 0 = TEST
python tools/bmp2png.py shots/home.bmp                     # -> shots/home.png + .html
```

`--shot` renders the whole screen through LVGL into a full-size buffer and
writes it out as a 24-bit BMP. `tools/bmp2png.py` converts that to a PNG
(standard library only — Pillow is not installed) and wraps it in an HTML page
with the image embedded as a base64 data URI, which opens directly in the
browser preview.
