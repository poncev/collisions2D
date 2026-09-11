#pragma once

#include <cmath>
#include <cstdlib>
#include <iostream>

#include "multiscale_rasterization/multiscale_rasterization.h"

namespace {

int failures = 0;

void check(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << "\n";
        ++failures;
    }
}

}  // namespace

int main() {
    // A horizontal segment from (0, 0) to (10, 0) inside a 10x10 box.
    const std::vector<multiscale_rasterization::Point> polyline = {
        {0.0, 0.0}, {10.0, 0.0}};
    const multiscale_rasterization::BoundingBox box = {
        {0.0, 0.0}, {10.0, 10.0}};

    // Level 0: the whole box intersects the segment, so exactly one square.
    {
        const auto result =
            multiscale_rasterization::multiscale_rasterization(polyline, box, 0);
        check(result.corners.size() == 1, "level 0 yields a single square");
        check(result.sizes[0] == 10.0, "level 0 square spans the box");
        check(result.levels[0] == 0, "level 0 square is at depth 0");
    }

    // Level 1: the segment lies on the bottom edge, so the two bottom
    // children intersect it.
    {
        const auto result =
            multiscale_rasterization::multiscale_rasterization(polyline, box, 1);
        check(result.corners.size() == 2, "level 1 yields two squares");
        check(result.sizes[0] == 5.0 && result.sizes[1] == 5.0,
              "level 1 squares are half the box");
        check(result.levels[0] == 1 && result.levels[1] == 1,
              "level 1 squares are at depth 1");
    }

    // A degenerate polyline (fewer than two vertices) yields no squares.
    {
        const std::vector<multiscale_rasterization::Point> empty = {{1.0, 1.0}};
        const auto result =
            multiscale_rasterization::multiscale_rasterization(empty, box, 2);
        check(result.corners.empty(), "degenerate polyline yields nothing");
    }

    if (failures == 0) {
        std::cout << "All tests passed.\n";
        return EXIT_SUCCESS;
    }
    std::cout << failures << " test(s) failed.\n";
    return EXIT_FAILURE;
}