cmake_minimum_required(VERSION 3.16)
project(VNPSP-RE LANGUAGES C CXX)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "build type" FORCE)
    message(STATUS "No CMAKE_BUILD_TYPE given, defaulting to Release")
endif()

set(VNPSP-RE_SOURCES
        src/main.cpp
        src/app.cpp
        src/bppFormat.cpp
        src/debug.cpp
        src/gameSelect.cpp
        src/graphics.cpp
        src/input.cpp
        src/interpreter.cpp
        src/parser.cpp
        src/pspGraphics.cpp
        src/pspMemory.cpp
        src/textbox.cpp
        src/ui.cpp
)

set(VNPSP-RE_LIBS
        pspdebug
        pspdisplay
        pspge
        pspctrl
        pspgu
        pspaudio
        tinyfont
        pthread
        psppower
        pspmp3
        psputility
)

add_executable(${PROJECT_NAME} ${VNPSP-RE_SOURCES})

target_include_directories(${PROJECT_NAME} PRIVATE src)
target_link_libraries(${PROJECT_NAME} PRIVATE ${VNPSP-RE_LIBS})

target_compile_options(${PROJECT_NAME} PRIVATE -Wall -Wextra)

# enables debug::log output (Debug builds only, Release compiles it out)
target_compile_definitions(${PROJECT_NAME} PRIVATE $<$<CONFIG:Debug>:VNPSP_DEBUG>)

create_pbp_file(
        TARGET ${PROJECT_NAME}
        ICON_PATH NULL
        BACKGROUND_PATH NULL
        PREVIEW_PATH NULL
        TITLE ${PROJECT_NAME}
        VERSION 01.00
)