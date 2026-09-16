#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "bounding_box.h"
#include "point.h"

namespace multiscale_rasterization {

/// A polyline: an ordered sequence of vertices connected by straight edges.
using Polyline = std::vector<Point>;

/// Number of axis-aligned neighbor directions (see `Direction` in quadtree.cpp).
///
/// The flood fill only steps along shared edges, never diagonally, so the four
/// cardinal directions suffice and no diagonal leak is possible.
constexpr int kNumDirections = 4;

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

    /// Cross-links to the distinct adjacent leaf cells, in direction order
    /// (Right, Left, Up, Down). An empty list means there is no leaf neighbor
    /// in that direction.
    ///
    /// Filled once by `cross_link_leaves` after the boundary phase (paper,
    /// Section 4.2: "adjacent cells can be stored in a list structure in each
    /// cell"). The flood fill reads these links instead of re-running the
    /// hierarchical `find_neighbors` traversal at every step, which turns the
    /// fill into O(number of cells) neighbour lookups.
    ///
    /// A list — rather than a single index — is required because the octree is
    /// deliberately *not* smoothed (the paper drops Crouse's smoothing step).
    /// An adjacent cell can therefore be finer than this one, in which case
    /// several of its leaves touch this cell's edge along the same direction
    /// and all of them are neighbours. Conversely a coarser adjacent leaf
    /// appears as the single entry of the list.
    std::array<std::vector<int>, kNumDirections> neighbors;
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

/// Cross-links every leaf cell with its distinct axis-aligned leaf neighbors.
///
/// This is the paper's Section 4.2 optimization ("Cross-linking of leaf cells"):
/// each leaf stores the indices of the leaves adjacent to it in the four
/// cardinal directions, so the flooding algorithm can transfer information
/// between neighbors in O(1) per link instead of re-traversing the tree.
///
/// Each direction stores a *list* because the octree is not level-smoothed: a
/// leaf may be adjacent to several finer leaves along one edge (or to a single
/// coarser leaf). `find_neighbors` collects every leaf whose footprint shares
/// an edge with the queried cell.
void cross_link_leaves(Quadtree& tree);
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