cmake_minimum_required(VERSION 3.16)

project(
    multiscale_rasterization
    VERSION 0.1.0
    DESCRIPTION "2D multiscale rasterization of polylines (quadtree-based)"
    LANGUAGES CXX
)

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
option(MR_BUILD_TESTS "Build the C++ unit tests" OFF)

# ---------------------------------------------------------------------------
# The core library
# ---------------------------------------------------------------------------
add_library(multiscale_rasterization_core
    src/multiscale_rasterization.cpp
    src/quadtree.cpp
)

target_include_directories(multiscale_rasterization_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

# The library is self-contained (no external dependencies yet), but we keep
# the vcpkg toolchain integration in place so that future dependencies can be
# added through the vcpkg manifest (see vcpkg.json).
find_package(Python3 COMPONENTS Interpreter Development)

# ---------------------------------------------------------------------------
# The CPython extension module (built by scikit-build-core)
# ---------------------------------------------------------------------------
if(Python3_Development_FOUND)
    add_library(_core MODULE src/python_module.cpp)
    target_link_libraries(_core PRIVATE multiscale_rasterization_core)
    target_include_directories(_core PRIVATE ${Python3_INCLUDE_DIRS})
    target_link_libraries(_core PRIVATE ${Python3_LINK_LIBRARIES})
    set_target_properties(_core PROPERTIES
        PREFIX ""
        OUTPUT_NAME "_core"
    )
    # Install the extension into the Python package so scikit-build-core can
    # place it inside the wheel.
    install(TARGETS _core LIBRARY DESTINATION multiscale_rasterization)
endif()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if(MR_BUILD_TESTS)
    enable_testing()
    add_executable(multiscale_rasterization_tests
        tests/test_multiscale_rasterization.cpp
    )
    target_link_libraries(multiscale_rasterization_tests
        PRIVATE multiscale_rasterization_core
    )
    add_test(NAME multiscale_rasterization_tests
             COMMAND multiscale_rasterization_tests)
endif()