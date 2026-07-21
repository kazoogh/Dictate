cmake_minimum_required(VERSION 3.20)
project(dictate_native LANGUAGES CXX)

add_library(dictate_native SHARED
    src/dictate_native.cpp
    src/hotkey_win.cpp
    src/paste_win.cpp
    src/audio_win.cpp
)
target_include_directories(dictate_native PUBLIC include)
target_compile_definitions(dictate_native PRIVATE DICTATE_NATIVE_EXPORTS UNICODE _UNICODE)
target_link_libraries(dictate_native PRIVATE user32 ole32 winmm)
set_target_properties(dictate_native PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
