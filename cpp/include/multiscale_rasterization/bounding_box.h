#pragma once

#include "point.h"

namespace multiscale_rasterization {

/// An axis-aligned bounding box in 2D.
///
/// The box is defined by its lower-left corner (`min`) and upper-right
/// corner (`max`). It is assumed that `min.x <= max.x` and `min.y <= max.y`.
struct BoundingBox {
    Point min;
    Point max;
};

}  // namespace multiscale_rasterization