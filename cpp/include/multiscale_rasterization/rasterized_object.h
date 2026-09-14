#pragma once

#include <cstdint>
#include <vector>

#include "point.h"

namespace multiscale_rasterization {

/// Classification of a square in the rasterized result.
///
/// Only two categories are emitted by the rasterizer: `Boundary` squares are
/// intersected by the polyline (the paper's Gray cells) and `Interior`
/// squares lie inside the geometry (the paper's Black cells). Exterior
/// (White) and undetermined cells are not part of the result.
enum class CellKind : std::uint8_t {
    Boundary = 0,  ///< Intersected by the polyline boundary.
    Interior = 1,  ///< Inside the geometry.
};

/// The result of rasterizing a polyline at multiple scales.
///
/// It stores the coordinates of the squares in the multiscale hierarchy that
/// touch the polyline and its interior. Each square is described by its
/// lower-left corner (`Point`) and its side length (`size`).
///
/// The `level` field is the depth of the square in the quadtree hierarchy:
/// level 0 corresponds to the coarsest squares (the whole bounding box) and
/// larger levels correspond to finer subdivisions.
///
/// The four vectors are parallel: entry `i` of each describes the same square.
struct RasterizedObject {
    /// Lower-left corners of the squares.
    std::vector<Point> corners;
    /// Side length of each square.
    std::vector<double> sizes;
    /// Quadtree depth of each square (0 = coarsest).
    std::vector<int> levels;
    /// Whether each square is a boundary or an interior cell.
    std::vector<CellKind> kinds;
};

}  // namespace multiscale_rasterization