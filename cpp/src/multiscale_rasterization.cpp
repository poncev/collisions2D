#include "multiscale_rasterization/multiscale_rasterization.h"

#include <vector>

#include "multiscale_rasterization/quadtree.h"

namespace multiscale_rasterization {

namespace {

/// Seeds the root node with all polyline edges as candidate edges.
void seed_root(Quadtree& tree, const Polyline& polyline) {
    QuadtreeNode& root = tree.nodes[0];
    root.candidate_edges.reserve(polyline.size() - 1);
    for (size_t i = 0; i + 1 < polyline.size(); ++i) {
        root.candidate_edges.push_back(static_cast<int>(i));
    }
}

/// Recursively subdivides every node that intersects the polyline until the
/// finest level is reached, marking intersected nodes as Gray.
///
/// This mirrors the paper's boundary phase: a node is refined if it contains
/// intersecting edges and the maximum level has not been reached. Nodes with
/// no intersecting edges are left undetermined for the subsequent flood fill.
void build_boundary(Quadtree& tree, const Polyline& polyline) {
    std::vector<int> stack;
    stack.push_back(0);

    while (!stack.empty()) {
        const int index = stack.back();
        stack.pop_back();
        QuadtreeNode& node = tree.nodes[static_cast<size_t>(index)];

        // Keep only the candidate edges that actually intersect this node.
        std::vector<int> kept;
        kept.reserve(node.candidate_edges.size());
        for (const int edge : node.candidate_edges) {
            const Point& a = polyline[static_cast<size_t>(edge)];
            const Point& b = polyline[static_cast<size_t>(edge) + 1];
            if (liang_barsky_intersect(a, b, node.bounds)) {
                kept.push_back(edge);
            }
        }
        node.candidate_edges = std::move(kept);

        if (node.candidate_edges.empty()) {
            // No boundary passes through this node; leave it undetermined.
            continue;
        }

        node.color = CellColor::Gray;

        if (node.level < tree.max_level) {
            subdivide_node(tree, index, polyline);
            // subdivide_node may have reallocated the node pool, so re-fetch
            // the node before reading its children.
            const QuadtreeNode& subdivided = tree.nodes[static_cast<size_t>(index)];
            for (const int child : subdivided.children) {
                stack.push_back(child);
            }
        }
    }
}

/// Collects the leaf cells that touch the polyline or its interior into a
/// `RasterizedObject`.
///
/// Only Gray (boundary) and Black (interior) cells are emitted; exterior
/// (White) and undetermined cells are excluded.
RasterizedObject collect_leaves(const Quadtree& tree) {
    RasterizedObject result;
    for (const QuadtreeNode& node : tree.nodes) {
        if (node.children[0] != -1) {
            continue;  // Not a leaf.
        }
        if (node.color != CellColor::Gray && node.color != CellColor::Black) {
            continue;  // Exterior or undetermined.
        }
        result.corners.push_back(node.bounds.min);
        result.sizes.push_back(node.bounds.max.x - node.bounds.min.x);
        result.levels.push_back(node.level);
    }
    return result;
}

}  // namespace

RasterizedObject multiscale_rasterization(
    const std::vector<Point>& polyline,
    const BoundingBox& bounding_box,
    int max_level) {
    if (polyline.size() < 2 || max_level < 0) {
        return RasterizedObject{};
    }

    Quadtree tree = initialize_quadtree(bounding_box, max_level);
    seed_root(tree, polyline);
    build_boundary(tree, polyline);
    flood_fill(tree, polyline);
    return collect_leaves(tree);
}

}  // namespace multiscale_rasterization