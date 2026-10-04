# Analyzer UI — LVGL port

An LVGL re-implementation of a CustomTkinter lab-analyzer UI, targeting an
**800x480 RGB565** panel.

The application is **light theme only**. There is one palette, no dark variant
of any screen, and no theme switch — that is a hard requirement of the project,
not a default that can be flipped back.

## What is in here

| Path                 | What it is                                                     |
| -------------------- | -------------------------------------------------------------- |
| `analyzer_ui.c/.h`   | The whole LVGL UI: colours, home menu, every screen, navigation |
| `home_icons.h`       | The six home menu icons, RGB565 (generated — see `tools/`)      |
| `main.c`             | Display setup, SDL window, `--memtest` / `--shot` / `--clicktest` |
| `lv_conf.h`          | LVGL configuration (`LV_COLOR_DEPTH 16` = RGB565)               |
| `ui/`                | The original CustomTkinter application (the design reference)   |
| `ui pics/`           | The reference screenshots the UI was matched against            |
| `tools/`             | Stdlib-only Python helpers (see below)                          |
| `MEMORY_BUDGET.md`   | Measured memory numbers and the page-switch budget              |
| `shots/`             | Rendered screenshots                                            |
| `lvgl/`              | **Git submodule** — LVGL itself (see below)                     |

## Getting the code

LVGL is a submodule, so clone recursively:

```bash
git clone --recursive <repo-url>
```

If you already cloned without `--recursive`:

```bash
git submodule update --init --recursive
```

There is only one LVGL source tree in the project: the submodule. Nothing is
copied into the repository root.

## Building

Requires CMake >= 3.20, a C compiler, and SDL2. On Windows the easiest source of
SDL2 is vcpkg.

```bash
cmake -S . -B build -G "Visual Studio 18 2026" \
  -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Debug --target LVGL_Project
```

`CMakeLists.txt` deliberately contains **no absolute paths**. SDL2's include
directories are read off the imported `SDL2::SDL2` target and handed to LVGL's
own SDL driver, so any toolchain that provides SDL2 through `find_package(SDL2
CONFIG REQUIRED)` — vcpkg or a system package — works unchanged.

### Visual Studio Code

1. **Clone with the submodule.** Either `git clone --recursive <repo-url>`, or
   run `git submodule update --init --recursive` in an existing checkout. VS
   Code's own clone does not fetch submodules.
2. **Install the extensions** *C/C++* and *CMake Tools*.
3. **Point CMake Tools at the toolchain.** Add to `.vscode/settings.json`
   (git-ignored, so it is yours to edit):

   ```json
   {
     "cmake.buildDirectory": "${workspaceFolder}/build",
     "cmake.configureArgs": [
       "-DCMAKE_TOOLCHAIN_FILE=C:/path/to/vcpkg/scripts/buildsystems/vcpkg.cmake"
     ]
   }
   ```

4. **Configure and build** with *CMake: Configure*, then *CMake: Build*, or
   *CMake: Select a Kit* first if it asks for a compiler.
5. **Run** `build/Debug/LVGL_Project.exe`. On Windows, `SDL2d.dll` must sit next
   to the executable — vcpkg copies it there during the build.

Nothing in the repository assumes a particular machine: `build/` is
git-ignored, and no file contains an absolute path.

> **Rebuilding while the app is running fails** on Windows with `LNK1168` —
> the `.exe` is locked. Close the window first.

## Running

```bash
# the app window (800x480)
./build/Debug/LVGL_Project.exe

# page-switch memory check, headless (no window)
./build/Debug/LVGL_Project.exe --memtest 20

# drive the home menu with synthetic input and report which screen each key opens
./build/Debug/LVGL_Project.exe --clicktest

# render a screen to an image, headless
./build/Debug/LVGL_Project.exe --shot shots/home.bmp        # home menu
./build/Debug/LVGL_Project.exe --shot shots/test.bmp 6      # 6 = TEST PARAMETERS
python tools/bmp2png.py shots/home.bmp                      # -> PNG + HTML to view
```

`--memtest` and `--clicktest` print a `verdict` line and always exit `0`, so
read the verdict rather than the exit code.

The `--shot`/`--memtest`/`--clicktest` modes are host diagnostics: they run the
same UI code with no window, so they work over a remote shell.

## Tools

All Python helpers are **standard library only** — Pillow is not required.

| Tool                   | What it does                                                  |
| ---------------------- | ------------------------------------------------------------- |
| `bmp2png.py`           | `--shot` BMP → PNG plus a viewable HTML page                   |
| `pngread.py`           | Minimal PNG reader (the reference artwork is a PNG)            |
| `makeicons.py`         | Cuts the six home icons out of the reference render → `home_icons.h` |
| `checkhome.py`         | Checks a home render: six keys, names in-cell, hairlines, nothing clipped |
| `iconsheet.py`         | Dumps `home_icons.h` back to PNGs for review                   |
| `zoomshot.py`          | Crops and magnifies part of a `--shot` for close inspection     |
| `refview.py` / `refzoom.py` / `shotview.py` | Contact sheets for the references and the renders |

Regenerating the icons (only needed if the artwork or the target size changes):

```bash
python tools/makeicons.py "<reference render>.png" 130
```

## Screens

All of these are implemented and reachable from the home menu; none are
placeholders.

| Home key   | Opens                                          |
| ---------- | ---------------------------------------------- |
| TEST       | LIST OF TESTS → TEST PARAMETERS → MEASUREMENT   |
| RESULT     | RESULTS → MEASUREMENT RESULTS                   |
| SYSTEM     | instrument status and diagnostics               |
| MAINTENANCE| pump and fluid controls                         |
| POWER      | shut down, reboot or sleep                      |
| ABOUT      | manufacturer and software build                 |

The originals live in `ui/` (`test_parameters.py`, `test_screen.py`,
`measurement.py`, `qc.py`, `results.py`, `system_screens.py`, `controls.py`).

## Memory

| Budget                                   | Measured                        |
| ---------------------------------------- | ------------------------------- |
| Partial draw buffer (the 2 KB budget)    | 1,600 B                         |
| Screen-switch drift over 165 switches    | 0 B                             |
| Resident heap (whole UI, before a page)  | ~18 KB                          |
| Largest single page's widget tree        | ~53 KB                          |

The 2 KB limit applies to the **draw buffer** and to **page switching**. The
draw buffer is `1 line x 800 px x 2 B = 1,600 B`, so the panel's 768,000-byte
frame never exists in RAM. Switching is free because the outgoing page is
deleted *before* the incoming one is built, so the two are never resident
together. Details in [MEMORY_BUDGET.md](MEMORY_BUDGET.md).
