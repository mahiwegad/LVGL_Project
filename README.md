# Analyzer UI — LVGL port

An LVGL re-implementation of a CustomTkinter lab-analyzer UI, targeting an
**800x480 RGB565** panel.

## What is in here

| Path                 | What it is                                                     |
| -------------------- | -------------------------------------------------------------- |
| `analyzer_ui.c/.h`   | The LVGL port: palette, home screen, navigation                |
| `main.c`             | Display setup, SDL window, `--memtest` and `--shot` modes      |
| `lv_conf.h`          | LVGL configuration (`LV_COLOR_DEPTH 16` = RGB565)              |
| `ui/`                | The original CustomTkinter application (the design reference)  |
| `tools/bmp2png.py`   | Converts a `--shot` BMP into a PNG + viewable HTML             |
| `MEMORY_BUDGET.md`   | Measured memory numbers and the page-switch budget             |
| `shots/`             | Rendered screenshots                                           |
| `lvgl/`              | **Git submodule** — LVGL itself (see below)                    |

## Getting the code

LVGL is a submodule, so clone recursively:

```bash
git clone --recursive <repo-url>
```

If you already cloned without `--recursive`:

```bash
git submodule update --init --recursive
```

The pinned LVGL version is commit `274c7e692` (`lvgl/lvgl`, branch `master`).

## Building

Requires CMake >= 3.20, a C compiler, SDL2 and (on Windows) vcpkg.

```bash
cmake -S . -B build -G "Visual Studio 18 2026" \
  -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Debug --target LVGL_Project
```

## Running

```bash
# the app window (800x480)
./build/Debug/LVGL_Project.exe

# page-switch memory check, headless (no window)
./build/Debug/LVGL_Project.exe --memtest 300

# render the UI to an image, headless
./build/Debug/LVGL_Project.exe --shot shots/home.bmp
./build/Debug/LVGL_Project.exe --shot shots/test.bmp 0   # 0 = TEST screen
python tools/bmp2png.py shots/home.bmp
```

`--memtest` prints a `verdict` line. Note that the process always exits `0`, so
read the verdict line rather than the exit code.

## Memory

| Budget                                   | Measured                       |
| ---------------------------------------- | ------------------------------ |
| Page switch (transient)                  | 2,048 B worst case, 0 B drift  |
| Resident heap (whole UI, before a page)  | ~30 KB                         |

The 2 KB limit applies to **page switching**, which is met by deleting the
outgoing page before building the incoming one. The resident footprint is far
larger, so this UI needs a device with LVGL's heap available — a 2 KB MCU would
need an external-GRAM display controller and direct drawing instead of LVGL.
Details in [MEMORY_BUDGET.md](MEMORY_BUDGET.md).

## Status

Ported: the **home screen** (top bar, warm-up status card, six menu cards,
navigation).

Not yet ported: the destination screens — TEST, RESULT, SYSTEM, MAINTENANCE,
POWER, ABOUT — currently render as placeholders. The originals live in `ui/`
(`test_parameters.py`, `measurement.py`, `qc.py`, `results.py`,
`system_screens.py`, `controls.py`, `dilution.py`).
