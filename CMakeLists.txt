cmake_minimum_required(VERSION 3.20)

project(LVGL_Project C)

set(CMAKE_C_STANDARD 99)

#
# SDL2 supplies its own include directories through the imported SDL2::SDL2
# target, so there is deliberately NO hardcoded install path here: point CMake
# at your SDL2 with a toolchain file (vcpkg: -DCMAKE_TOOLCHAIN_FILE=...) or a
# system package, and this file works unchanged on any machine.
#
find_package(SDL2 CONFIG REQUIRED)

#
# LVGL's own SDL driver (lvgl/src/drivers/sdl) is compiled as part of the lvgl
# subdirectory and needs SDL2's headers as well. Taking them off the imported
# target - instead of spelling out an install path - is what keeps this file
# portable across machines.
#
get_target_property(SDL2_INCLUDE_DIRS SDL2::SDL2 INTERFACE_INCLUDE_DIRECTORIES)

if(SDL2_INCLUDE_DIRS)
    include_directories(${SDL2_INCLUDE_DIRS})
endif()

set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)

add_subdirectory(lvgl)

add_executable(LVGL_Project
    main.c
    analyzer_ui.c
)

target_include_directories(LVGL_Project PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/lvgl
)

target_link_libraries(LVGL_Project PRIVATE
    lvgl
    SDL2::SDL2
)

#
# LVGL's SDL driver in the submodule references lv_sdl_* symbols, so the lvgl
# target has to see SDL2's headers when it is built. Attaching the imported
# target to lvgl (rather than relying on the directory-level include above)
# keeps that true no matter where this project is added from.
#
target_link_libraries(lvgl PRIVATE SDL2::SDL2)

