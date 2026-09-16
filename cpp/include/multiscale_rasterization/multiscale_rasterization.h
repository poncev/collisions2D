#pragma once

#include <vector>

#include "bounding_box.h"
#include "point.h"
#include "rasterized_object.h"

namespace multiscale_rasterization {

/// Rasterizes a 2D polyline at multiple scales.
///
/// The polyline is given as a sequence of vertices (`polyline`), which are
/// connected in order by straight edges. The algorithm starts from the
/// coarsest grid (a single square covering `bounding_box`) and recursively
/// subdivides any square that intersects the polyline until the finest
/// user-defined scale (`max_level`) is reached.
///
/// @param polyline     The vertices of the polyline (at least two).
/// @param bounding_box The axis-aligned box that bounds the rasterization.
/// @param max_level    The finest subdivision depth (>= 0).
/// @return The squares in the multiscale hierarchy touching the polyline.
RasterizedObject multiscale_rasterization(
    const std::vector<Point>& polyline,
    const BoundingBox& bounding_box,
    int max_level);

}  // namespace multiscale_rasterization