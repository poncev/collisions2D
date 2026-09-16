#include "multiscale_rasterization/quadtree.h"

#include <cmath>
#include <utility>

namespace multiscale_rasterization {

namespace {

/// Returns true if the node at `index` is a leaf (has no children).
bool is_leaf(const Quadtree& tree, int index) {
    return tree.nodes[static_cast<size_t>(index)].children[0] == -1;
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

/// Cardinal direction of an axis-aligned neighbor lookup.
enum class Direction { Right = 0, Left = 1, Up = 2, Down = 3 };

/// Location bits of a node within its parent, used to replay a traversal.
using LocationBits = std::pair<int, int>;

/// Returns the leaf cell(s) adjacent to `index` in direction `dir`.
///
/// The traversal uses only the parent pointers and the stored `xbit`/`ybit`
/// location bits, so it is O(depth) and needs no extra spatial index. It
/// climbs from `index` until the current node has a sibling in `dir`, steps
/// into that sibling, then descends replaying (and mirroring) the climb to
/// find the cell at `index`'s level that shares the edge.
///
/// Unlike a smoothed octree, the neighbour is not necessarily a single cell:
/// the paper deliberately drops Crouse's level-smoothing step, so an adjacent
/// footprint can be subdivided into many smaller leaves touching this cell's
/// edge. The results are appended to `out`, which the caller owns and which is
/// cleared here. Three cases arise:
///
///  * the descent lands on a leaf at the same level -> one neighbour;
///  * the descent reaches a *coarser* leaf covering the whole adjacent
///    footprint -> one neighbour;
///  * the same-level cell is subdivided -> the leaves of its subtree that
///    touch the shared edge are neighbours, so all of them are collected.
///
/// Gray cells are included like any other leaf; the flood fill simply refuses
/// to enter or expand from them, so they act as barriers.
///
/// `path` is a caller-owned scratch buffer: it is cleared and reused on every
/// call so that repeated lookups (the cross-linking pass) do not allocate a
/// fresh vector per neighbour query.
void find_neighbors(const Quadtree& tree, int index, Direction dir,
                    std::vector<LocationBits>& path, std::vector<int>& out) {
    out.clear();
    if (index < 0) {
        return;
    }
    const int target_level = tree.nodes[static_cast<size_t>(index)].level;

    // Location bits of the nodes traversed while climbing, from `index`
    // upwards. They are replayed, mirrored, when descending into the sibling.
    path.clear();
    int current = index;

    int sibling = -1;
    while (true) {
        const QuadtreeNode& node = tree.nodes[static_cast<size_t>(current)];
        const int parent = node.parent;
        if (parent == -1) {
            return;  // Reached the root without finding a sibling.
        }

        int sibling_xbit = node.xbit;
        int sibling_ybit = node.ybit;
        bool can_move = false;
        switch (dir) {
            case Direction::Right:
                can_move = (node.xbit == 0);
                sibling_xbit = 1;
                break;
            case Direction::Left:
                can_move = (node.xbit == 1);
                sibling_xbit = 0;
                break;
            case Direction::Up:
                can_move = (node.ybit == 0);
                sibling_ybit = 1;
                break;
            case Direction::Down:
                can_move = (node.ybit == 1);
                sibling_ybit = 0;
                break;
        }

        if (!can_move) {
            // The node sits on the `dir` side of its parent: climb.
            path.emplace_back(node.xbit, node.ybit);
            current = parent;
            continue;
        }

        sibling = tree.nodes[static_cast<size_t>(parent)]
                      .children[child_index(sibling_xbit, sibling_ybit)];
        break;
    }

    if (sibling == -1) {
        return;
    }

    // Descend into the sibling, mirroring the climb across the shared edge.
    // Mirroring flips the location bit along the movement axis.
    int cell = sibling;
    for (auto it = path.rbegin(); it != path.rend(); ++it) {
        if (tree.nodes[static_cast<size_t>(cell)].level == target_level) {
            break;
        }
        if (is_leaf(tree, cell)) {
            out.push_back(cell);  // Coarser neighbour covering the footprint.
            return;
        }
        int xbit = it->first;
        int ybit = it->second;
        if (dir == Direction::Right || dir == Direction::Left) {
            xbit = 1 - xbit;
        } else {
            ybit = 1 - ybit;
        }
        cell = tree.nodes[static_cast<size_t>(cell)]
                   .children[child_index(xbit, ybit)];
        if (cell == -1) {
            return;
        }
    }

    if (is_leaf(tree, cell)) {
        out.push_back(cell);  // Same-level leaf neighbour.
        return;
    }

    // The same-level adjacent cell is subdivided: its leaves tile the shared
    // edge. Only the leaves that actually touch that edge are neighbours, so
    // the descent keeps the child on the near side of the movement axis (all
    // children along the perpendicular axis are kept) at every level.
    const int near_xbit = (dir == Direction::Left) ? 1 : 0;
    const int near_ybit = (dir == Direction::Down) ? 1 : 0;
    std::vector<int> todo;
    todo.push_back(cell);
    while (!todo.empty()) {
        const int node_index = todo.back();
        todo.pop_back();
        if (is_leaf(tree, node_index)) {
            out.push_back(node_index);
            continue;
        }
        const QuadtreeNode& parent = tree.nodes[static_cast<size_t>(node_index)];
        for (int xbit = 0; xbit < 2; ++xbit) {
            if ((dir == Direction::Right || dir == Direction::Left) &&
                xbit != near_xbit) {
                continue;
            }
            for (int ybit = 0; ybit < 2; ++ybit) {
                if ((dir == Direction::Up || dir == Direction::Down) &&
                    ybit != near_ybit) {
                    continue;
                }
                const int child = parent.children[child_index(xbit, ybit)];
                if (child != -1) {
                    todo.push_back(child);
                }
            }
        }
    }
}

}  // namespace

void cross_link_leaves(Quadtree& tree) {
    // Reusable scratch buffers shared by every lookup, so the whole
    // cross-linking pass performs no per-neighbour heap allocation.
    std::vector<LocationBits> path;
    std::vector<int> neighbors;

    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        QuadtreeNode& node = tree.nodes[i];
        if (node.children[0] != -1) {
            continue;  // Only leaf cells are cross-linked.
        }
        if (node.color == CellColor::Gray) {
            // Gray cells are barriers: the flood fill never enters them and
            // never expands from them, so their links are never read. Skipping
            // them avoids a large amount of useless traversal work, since the
            // boundary cells are exactly the finely subdivided leaves.
            continue;
        }
        for (int d = 0; d < kNumDirections; ++d) {
            const Direction dir = static_cast<Direction>(d);
            find_neighbors(tree, static_cast<int>(i), dir, path, neighbors);
            node.neighbors[static_cast<size_t>(d)] = neighbors;
        }
    }
}

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

    // Phase 1: pick a single undetermined leaf as the seed. Only this one
    // leaf is tested against the polygon: its center is classified with an
    // even-odd ray cast, and that single test decides whether the free region
    // reachable from the seed is the interior or the exterior. Gray boundary
    // cells are skipped so the seed always comes from the free region.
    int seed = -1;
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        const int index = static_cast<int>(i);
        if (!is_leaf(tree, index)) {
            continue;
        }
        if (tree.nodes[i].color != CellColor::Undetermined) {
            continue;
        }
        seed = index;
        break;
    }

    if (seed == -1) {
        return;  // No free cell to classify.
    }

    const BoundingBox& seed_bounds = tree.nodes[static_cast<size_t>(seed)].bounds;
    const Point seed_center = {(seed_bounds.min.x + seed_bounds.max.x) / 2.0,
                               (seed_bounds.min.y + seed_bounds.max.y) / 2.0};
    const bool seed_inside = point_in_polygon(seed_center, polyline);

    // Phase 2: flood fill the connected free region reachable from the seed,
    // colouring it with the seed's classification: Black if the seed center is
    // inside the polygon, White otherwise. The traversal is a stack-based
    // flood fill that reads the cross-links built by `cross_link_leaves`, so
    // each neighbor is reached in O(1) instead of re-running the hierarchical
    // traversal. Gray cells are barriers: they are never entered nor coloured.
    const CellColor seed_color =
        seed_inside ? CellColor::Black : CellColor::White;
    tree.nodes[static_cast<size_t>(seed)].color = seed_color;

    std::vector<int> stack;
    stack.push_back(seed);

    while (!stack.empty()) {
        const int index = stack.back();
        stack.pop_back();
        const QuadtreeNode& node = tree.nodes[static_cast<size_t>(index)];
        for (int d = 0; d < kNumDirections; ++d) {
            for (const int neighbor : node.neighbors[static_cast<size_t>(d)]) {
                QuadtreeNode& cell = tree.nodes[static_cast<size_t>(neighbor)];
                if (cell.color != CellColor::Undetermined) {
                    continue;  // Already classified, or a Gray barrier.
                }
                cell.color = seed_color;
                stack.push_back(neighbor);
            }
        }
    }

    // Phase 3: every cell not reached by the flood fill lies on the other side
    // of the boundary, so it receives the opposite classification. The seed's
    // own region was coloured `seed_color`, hence the remaining free cells are
    // White when the seed was interior and Black when it was exterior. Gray
    // boundary cells are preserved.
    const CellColor opposite_color =
        seed_inside ? CellColor::White : CellColor::Black;
    for (QuadtreeNode& node : tree.nodes) {
        if (node.children[0] != -1) {
            continue;  // Not a leaf.
        }
        if (node.color == CellColor::Undetermined) {
            node.color = opposite_color;
        }
    }
}

}  // namespace multiscale_rasterization