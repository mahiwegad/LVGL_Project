cmake_minimum_required(VERSION 3.20)

project(LVGL_Project C)

set(CMAKE_C_STANDARD 99)

find_package(SDL2 CONFIG REQUIRED)

set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)

# SDL2 include directory
include_directories(
    "C:/Users/91626/vcpkg/installed/x64-windows/include"
)

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
