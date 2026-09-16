#include <cmath>
#include <cstdio>
#include <vector>

#include "multiscale_rasterization/quadtree.h"

using namespace multiscale_rasterization;

static bool is_leaf(const Quadtree& t, int i) {
    return t.nodes[i].children[0] == -1;
}

static bool pip(const Point& p, const Polyline& poly) {
    bool inside = false;
    const size_t n = poly.size();
    for (size_t i = 0, j = n - 1; i < n; j = i++) {
        const Point& a = poly[i];
        const Point& b = poly[j];
        if (a.x == b.x && a.y == b.y) continue;
        if (((a.y > p.y) != (b.y > p.y)) &&
            (p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)) {
            inside = !inside;
        }
    }
    return inside;
}

int main() {
    const int n = 400;
    const double r = 4.5;
    Polyline poly;
    for (int i = 0; i < n; ++i) {
        const double a = 2 * M_PI * i / n;
        poly.push_back({5 + r * std::cos(a), 5 + r * std::sin(a)});
    }
    poly.push_back(poly[0]);
    const BoundingBox box = {{0, 0}, {10, 10}};

    Quadtree tree = initialize_quadtree(box, 9);
    for (size_t i = 0; i + 1 < poly.size(); ++i) {
        tree.nodes[0].candidate_edges.push_back(static_cast<int>(i));
    }

    std::vector<int> stack{0};
    while (!stack.empty()) {
        int index = stack.back();
        stack.pop_back();
        QuadtreeNode& node = tree.nodes[index];
        std::vector<int> kept;
        for (int e : node.candidate_edges) {
            if (liang_barsky_intersect(poly[e], poly[e + 1], node.bounds)) {
                kept.push_back(e);
            }
        }
        node.candidate_edges = std::move(kept);
        if (node.candidate_edges.empty()) continue;
        node.color = CellColor::Gray;
        if (node.level < tree.max_level) {
            subdivide_node(tree, index, poly);
            for (int c : tree.nodes[index].children) stack.push_back(c);
        }
    }

    cross_link_leaves(tree);

    // Replicate the seed selection.
    int seed = -1;
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        if (!is_leaf(tree, static_cast<int>(i))) continue;
        if (tree.nodes[i].color != CellColor::Undetermined) continue;
        seed = static_cast<int>(i);
        break;
    }
    const BoundingBox& sb = tree.nodes[seed].bounds;
    const Point c = {(sb.min.x + sb.max.x) / 2, (sb.min.y + sb.max.y) / 2};
    printf("seed=%d level=%d bounds=[%.4f,%.4f]-[%.4f,%.4f] center=(%.4f,%.4f) inside=%d\n",
           seed, tree.nodes[seed].level, sb.min.x, sb.min.y, sb.max.x, sb.max.y,
           c.x, c.y, pip(c, poly) ? 1 : 0);

    // Count free leaves and gray leaves.
    size_t free_leaves = 0, gray_leaves = 0;
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        if (!is_leaf(tree, static_cast<int>(i))) continue;
        if (tree.nodes[i].color == CellColor::Gray) ++gray_leaves;
        else ++free_leaves;
    }
    printf("free_leaves=%zu gray_leaves=%zu total_nodes=%zu\n", free_leaves,
           gray_leaves, tree.nodes.size());

    // Flood from the seed and report the reached count.
    flood_fill(tree, poly);
    size_t black = 0, white = 0, undet = 0;
    for (size_t i = 0; i < tree.nodes.size(); ++i) {
        if (!is_leaf(tree, static_cast<int>(i))) continue;
        if (tree.nodes[i].color == CellColor::Black) ++black;
        else if (tree.nodes[i].color == CellColor::White) ++white;
        else if (tree.nodes[i].color == CellColor::Undetermined) ++undet;
    }
    printf("after flood: black=%zu white=%zu undet=%zu\n", black, white, undet);
    return 0;
}
