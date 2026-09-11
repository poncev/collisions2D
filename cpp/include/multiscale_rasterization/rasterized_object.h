#pragma once

#include <vector>

#include "point.h"

namespace multiscale_rasterization {

/// The result of rasterizing a polyline at multiple scales.
///
/// It stores the coordinates of the squares in the multiscale hierarchy that
/// touch the polyline and its interior. Each square is described by its
/// lower-left corner (`Point`) and its side length (`size`).
///
/// The `level` field is the depth of the square in the quadtree hierarchy:
/// level 0 corresponds to the coarsest squares (the whole bounding box) and
/// larger levels correspond to finer subdivisions.
struct RasterizedObject {
    /// Lower-left corners of the squares.
    std::vector<Point> corners;
    /// Side length of each square.
    std::vector<double> sizes;
    /// Quadtree depth of each square (0 = coarsest).
    std::vector<int> levels;
};

}  // namespace multiscale_rasterization