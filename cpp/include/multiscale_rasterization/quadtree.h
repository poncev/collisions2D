#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "bounding_box.h"
#include "point.h"

namespace multiscale_rasterization {

/// A polyline: an ordered sequence of vertices connected by straight edges.
using Polyline = std::vector<Point>;

/// Color of a quadtree cell, following the paper's tri-color scheme.
///
/// The boundary of the geometry is rasterized first (Gray cells). The
/// remaining undetermined cells are then classified as interior (Black) or
/// exterior (White) by a flood fill that uses the Gray cells as a barrier.
enum class CellColor : std::uint8_t {
    Undetermined = 0,  ///< Not yet classified (interior or exterior).
    Gray = 1,          ///< Intersected by the polyline boundary.
    Black = 2,         ///< Interior of the geometry.
    White = 3,         ///< Exterior of the geometry.
};

/// A node of the quadtree.
///
/// Nodes are stored in a contiguous pool (`Quadtree::nodes`) and referenced by
/// index. This keeps the structure cache-friendly and avoids pointer chasing
/// during the recursive subdivision and the flood fill.
struct QuadtreeNode {
    /// Axis-aligned square covered by this node.
    BoundingBox bounds;
    /// Depth in the tree (0 = root).
    int level = 0;
    /// Classification of the cell.
    CellColor color = CellColor::Undetermined;
    /// Index of the parent node, -1 for the root.
    int parent = -1;
    /// Indices of the four children, -1 if the node is a leaf.
    std::array<int, 4> children = {-1, -1, -1, -1};
    /// 0/1 location of this node within its parent (x axis).
    int xbit = 0;
    /// 0/1 location of this node within its parent (y axis).
    int ybit = 0;
    /// Indices of polyline edges that may intersect this node (boundary phase).
    ///
    /// Each child inherits its parent's list and keeps only the edges that
    /// still intersect it, so only potentially intersecting edges are tested
    /// against a node (as in the paper's triangle-index list).
    std::vector<int> candidate_edges;
};

/// A quadtree over a bounding box.
struct Quadtree {
    /// Contiguous pool of nodes; the root is always at index 0.
    std::vector<QuadtreeNode> nodes;
    /// Finest subdivision depth.
    int max_level = 0;
};

/// Child index for a given (xbit, ybit) location within a parent.
///
/// Layout: 0 = bottom-left, 1 = bottom-right, 2 = top-left, 3 = top-right.
constexpr int child_index(int xbit, int ybit) { return xbit + 2 * ybit; }

/// Creates a quadtree whose root covers `box`.
///
/// The root is created with no candidate edges; the caller is responsible for
/// seeding them (see `multiscale_rasterization`).
Quadtree initialize_quadtree(const BoundingBox& box, int max_level);

/// Liang--Barsky clip test: does the segment `a`--`b` intersect the square
/// `box`?
///
/// The segment is parameterised as `p(t) = a + t * (b - a)` with `t` in
/// [0, 1] and the parameter interval is clipped against the four half-planes
/// that define the square. A non-empty interval means an intersection.
bool liang_barsky_intersect(const Point& a, const Point& b,
                            const BoundingBox& box);

/// Subdivides the node at `node_index` into four children.
///
/// Each child inherits the parent's candidate edges and keeps only those that
/// intersect it. The parent's `children` array is updated in place.
void subdivide_node(Quadtree& tree, int node_index, const Polyline& polyline);

/// Classifies interior (Black) and exterior (White) leaf cells by flooding,
/// using the Gray boundary cells as a barrier.
///
/// The polyline must be a closed polygon (first vertex equals the last) for
/// the interior to be well defined. The algorithm assumes caveless geometry,
/// as in the paper.
void flood_fill(Quadtree& tree, const Polyline& polyline);

}  // namespace multiscale_rasterization