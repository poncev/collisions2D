#include "multiscale_rasterization/quadtree.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <utility>

namespace multiscale_rasterization {

namespace {

/// Returns the index of the child of `node` that lies in the direction
/// `(dx, dy)` (each of `dx`, `dy` is -1, 0 or +1).
int child_in_direction(int dx, int dy) {
    const int xbit = (dx > 0) ? 1 : 0;
    const int ybit = (dy > 0) ? 1 : 0;
    return child_index(xbit, ybit);
}

/// Returns true if the node at `index` is a leaf (has no children).
bool is_leaf(const Quadtree& tree, int index) {
    return tree.nodes[static_cast<size_t>(index)].children[0] == -1;
}

/// Returns the index of the neighbor of the node at `index` in the direction
/// `(dx, dy)`, or -1 if there is no such neighbor.
///
/// This follows the paper's bit-encoding traversal. We climb towards the root
/// while the node's location bit in the queried axis equals the "far" bit
/// (i.e. the node is on the boundary of its parent in that direction),
/// recording each location. When we reach a node whose bit equals the "near"
/// bit, its sibling in the queried direction is the neighbor's ancestor; we
/// then descend from that sibling, mirroring the recorded locations.
int find_neighbor(const Quadtree& tree, int index, int dx, int dy) {
    if (dx == 0 && dy == 0) {
        return -1;
    }

    // Only axis-aligned directions are used by the flood fill.
    const int axis = (dx != 0) ? 0 : 1;  // 0 = x, 1 = y
    const int dir = (dx != 0) ? dx : dy; // +1 or -1
    const int far_bit = (dir > 0) ? 1 : 0;
    const int near_bit = (dir > 0) ? 0 : 1;

    // Climb, recording each node's location in its parent, until the location
    // bit in the queried axis equals the near bit.
    std::vector<int> path;
    int current = index;
    while (current != -1) {
        const QuadtreeNode& node = tree.nodes[static_cast<size_t>(current)];
        const int bit = (axis == 0) ? node.xbit : node.ybit;
        if (bit != far_bit) {
            break;  // Found the stopping node (bit == near_bit).
        }
        path.push_back(child_index(node.xbit, node.ybit));
        current = node.parent;
    }

    if (current == -1) {
        return -1;  // Reached the root without finding a neighbor.
    }

    // `current` is the stopping node; its sibling in the queried direction is
    // the ancestor of the neighbor.
    const QuadtreeNode& stopping = tree.nodes[static_cast<size_t>(current)];
    const int parent = stopping.parent;
    if (parent == -1) {
        return -1;  // The stopping node is the root; no sibling exists.
    }
    const int sibling = child_in_direction(dx, dy);
    if (sibling == -1) {
        return -1;
    }

    // Descend from the sibling, mirroring the recorded locations. The path is
    // bottom-up (leaf first), so iterate it in reverse (top-down). At each
    // step the child adjacent to the direction has the near bit on the queried
    // axis and the recorded bits on the other axes.
    int result = sibling;
    for (auto it = path.rbegin(); it != path.rend(); ++it) {
        const QuadtreeNode& r = tree.nodes[static_cast<size_t>(result)];
        if (r.children[0] == -1) {
            break;
        }
        const int entry = *it;
        const int entry_xbit = entry & 1;
        const int entry_ybit = (entry >> 1) & 1;
        const int child_xbit = (axis == 0) ? near_bit : entry_xbit;
        const int child_ybit = (axis == 1) ? near_bit : entry_ybit;
        result = r.children[child_index(child_xbit, child_ybit)];
    }
    return result;
}

/// Returns true if the point `p` is strictly inside the closed polygon
/// `polyline` (whose first and last vertices coincide).
///
/// Uses the even-odd rule with a horizontal ray cast to the right. Points on
/// the boundary are treated as inside.
bool point_in_polygon(const Point& p, const Polyline& polyline) {
    bool inside = false;
    const size_t n = polyline.size();
    for (size_t i = 0, j = n - 1; i < n; j = i++) {
        const Point& a = polyline[i];
        const Point& b = polyline[j];
        // Skip degenerate edges.
        if (a.x == b.x && a.y == b.y) {
            continue;
        }
        // Boundary test: is p on the segment a-b?
        const double cross = (b.x - a.x) * (p.y - a.y) -
                             (b.y - a.y) * (p.x - a.x);
        const double dot = (p.x - a.x) * (b.x - a.x) +
                           (p.y - a.y) * (b.y - a.y);
        const double len2 = (b.x - a.x) * (b.x - a.x) +
                            (b.y - a.y) * (b.y - a.y);
        if (std::abs(cross) <= 1e-12 * std::sqrt(len2) &&
            dot >= 0.0 && dot <= len2) {
            return true;
        }
        // Standard even-odd crossing test.
        if (((a.y > p.y) != (b.y > p.y)) &&
            (p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)) {
            inside = !inside;
        }
    }
    return inside;
}

}  // namespace

Quadtree initialize_quadtree(const BoundingBox& box, int max_level) {
    Quadtree tree;
    tree.max_level = max_level;
    QuadtreeNode root;
    root.bounds = box;
    root.level = 0;
    root.parent = -1;
    root.xbit = 0;
    root.ybit = 0;
    tree.nodes.push_back(root);
    return tree;
}

bool liang_barsky_intersect(const Point& a, const Point& b,
                            const BoundingBox& box) {
    const double xmin = box.min.x;
    const double xmax = box.max.x;
    const double ymin = box.min.y;
    const double ymax = box.max.y;

    const double dx = b.x - a.x;
    const double dy = b.y - a.y;

    double tmin = 0.0;
    double tmax = 1.0;

    const double p[4] = {-dx, dx, -dy, dy};
    const double q[4] = {a.x - xmin, xmax - a.x, a.y - ymin, ymax - a.y};

    for (int i = 0; i < 4; ++i) {
        if (p[i] == 0.0) {
            // Segment is parallel to this boundary; it must lie inside.
            if (q[i] < 0.0) {
                return false;
            }
        } else {
            const double r = q[i] / p[i];
            if (p[i] < 0.0) {
                // Entering the region.
                if (r > tmax) {
                    return false;
                }
                if (r > tmin) {
                    tmin = r;
                }
            } else {
                // Leaving the region.
                if (r < tmin) {
                    return false;
                }
                if (r < tmax) {
                    tmax = r;
                }
            }
        }
    }

    return true;
}

void subdivide_node(Quadtree& tree, int node_index, const Polyline& polyline) {
    const QuadtreeNode& node = tree.nodes[static_cast<size_t>(node_index)];
    if (node.level >= tree.max_level) {
        return;
    }

    // Copy the parent's data up front: pushing children below may reallocate
    // the node pool and invalidate `node`.
    const double min_x = node.bounds.min.x;
    const double min_y = node.bounds.min.y;
    const double max_x = node.bounds.max.x;
    const double max_y = node.bounds.max.y;
    const int child_level = node.level + 1;
    const std::vector<int> parent_edges = node.candidate_edges;

    const double mid_x = (min_x + max_x) / 2.0;
    const double mid_y = (min_y + max_y) / 2.0;

    // Create the four children. The parent's children indices are recorded
    // after all pushes so that no reference into the node pool is held across
    // a reallocation.
    std::array<int, 4> child_indices = {-1, -1, -1, -1};
    for (int xbit = 0; xbit < 2; ++xbit) {
        for (int ybit = 0; ybit < 2; ++ybit) {
            QuadtreeNode child;
            child.bounds.min.x = (xbit == 0) ? min_x : mid_x;
            child.bounds.max.x = (xbit == 0) ? mid_x : max_x;
            child.bounds.min.y = (ybit == 0) ? min_y : mid_y;
            child.bounds.max.y = (ybit == 0) ? mid_y : max_y;
            child.level = child_level;
            child.parent = node_index;
            child.xbit = xbit;
            child.ybit = ybit;
            // Inherit the parent's candidate edges and keep only those that
            // still intersect this child.
            child.candidate_edges.reserve(parent_edges.size());
            for (const int edge : parent_edges) {
                const Point& a = polyline[static_cast<size_t>(edge)];
                const Point& b = polyline[static_cast<size_t>(edge) + 1];
                if (liang_barsky_intersect(a, b, child.bounds)) {
                    child.candidate_edges.push_back(edge);
                }
            }
            tree.nodes.push_back(child);
            child_indices[child_index(xbit, ybit)] =
                static_cast<int>(tree.nodes.size()) - 1;
        }
    }

    // Record the children on the parent (re-fetched by index).
    tree.nodes[static_cast<size_t>(node_index)].children = child_indices;
}

void flood_fill(Quadtree& tree, const Polyline& polyline) {
    if (tree.nodes.empty()) {
        return;
    }

    // Collect the leaf cells.
    std::vector<int> leaves;
    leaves.reserve(tree.nodes.size());
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        if (is_leaf(tree, static_cast<int>(i))) {
            leaves.push_back(static_cast<int>(i));
        }
    }

    // Find a seed: an undetermined leaf that is inside the polygon. If none
    // exists, there is nothing to flood.
    int seed = -1;
    for (const int leaf : leaves) {
        const QuadtreeNode& node = tree.nodes[static_cast<size_t>(leaf)];
        if (node.color == CellColor::Undetermined) {
            const Point center = {(node.bounds.min.x + node.bounds.max.x) / 2.0,
                                  (node.bounds.min.y + node.bounds.max.y) / 2.0};
            if (point_in_polygon(center, polyline)) {
                seed = leaf;
                break;
            }
        }
    }
    if (seed == -1) {
        return;
    }

    // Flood the interior (Black) from the seed, using Gray cells as a barrier.
    std::queue<int> queue;
    queue.push(seed);
    tree.nodes[static_cast<size_t>(seed)].color = CellColor::Black;

    const int directions[4][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

    while (!queue.empty()) {
        const int current = queue.front();
        queue.pop();
        for (const auto& dir : directions) {
            const int neighbor = find_neighbor(tree, current, dir[0], dir[1]);
            if (neighbor == -1) {
                continue;
            }
            QuadtreeNode& n = tree.nodes[static_cast<size_t>(neighbor)];
            if (n.color == CellColor::Undetermined) {
                n.color = CellColor::Black;
                queue.push(neighbor);
            }
        }
    }

    // Everything still undetermined is exterior (White).
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        QuadtreeNode& node = tree.nodes[i];
        if (node.color == CellColor::Undetermined) {
            node.color = CellColor::White;
        }
    }
}

}  // namespace multiscale_rasterization