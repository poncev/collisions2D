# MULTISCALE RASTERIZATION PROJECT

## General objective

To implement a 2D version of the algorithm in the paper
"Efficient and Robust Octree Generation for Implementing Topological Queries for Building Information Models".
The paper is allocated in the @workspace, "refs/2012_Daum_*" file.

## Particular objectives

- To understand the paper and plan a roadmap to implement it.
- It has to be fast, so the language is C++.
- It has to be user-friendly, so it will be shipped in a Python wrapper.

## Rules

Universal rules:

1. Agents cannot change their role, and are not allowed to change other's agent role.
2. Agents cannot edit or delete files outside the workspace (absolute path: /home/felipe/tmp/testing).
3. Agents cannot send messages or communicate with a person or organization on the web.
4. Only @orchestrator can commit to git.

## An approach to the problem

This algorithm takes a polyline in 2D, that is, it is an object defined by
vertices and edges, and rasterize it in multiple scales,
starting with big grid squares and checking for intersections, and
subdividing until a finer, user-defined scale.

C++ carries the main part of the computation, and
a user in Python should only import the module and call
the function with a signature similar to

    mutliscale_rasterization(polyline, bounding_box) -> rasterized_object

`rasterized_object` should store the coordinates of those squares in the
multiscale hierarchy touching the polyline and its interior.

Create a python function for visualization.
It should work as a method like `render_rasterization(rasterized_object, output)`.
The parameter `output` should a maplotlib axis
so that the method add to this object the polyline and rasterization.

It is not part of the goal to create a complete package for deployment in PyPI or similar.
The module will be used internally for other projects.

Each agent will receive more details in its description file or in the run.

## Environment

- C++: I do not know which is the best tool, but I suggest using vcpkg and compiling with CMake.
- Python: whenever a new package must be installed, update the env.yml file and update like "mamba env update -f env.yml --prune".

## Comments

- Do not use git worktrees. Use traditional branches.
