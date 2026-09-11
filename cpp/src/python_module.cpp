// CPython extension module that exposes the C++ core to Python.
//
// This module is built by scikit-build-core from the C++ sources. It converts
// Python sequences into the C++ data structures, calls the core algorithm,
// and converts the result back into Python objects.

#include <Python.h>

#include <vector>

#include "multiscale_rasterization/multiscale_rasterization.h"

namespace mr = multiscale_rasterization;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Parses a Python sequence of (x, y) pairs into a vector of C++ points.
/// Returns false (and sets a Python exception) on failure.
static bool parse_polyline(PyObject* obj, std::vector<mr::Point>* out) {
    PyObject* seq = PySequence_Fast(obj, "polyline must be a sequence");
    if (seq == nullptr) {
        return false;
    }

    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out->reserve(static_cast<size_t>(n));

    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        PyObject* pair = PySequence_Fast(item, "each vertex must be a pair");
        if (pair == nullptr) {
            Py_DECREF(seq);
            return false;
        }
        if (PySequence_Fast_GET_SIZE(pair) != 2) {
            PyErr_SetString(PyExc_ValueError,
                            "each vertex must be a (x, y) pair");
            Py_DECREF(pair);
            Py_DECREF(seq);
            return false;
        }
        PyObject* x = PySequence_Fast_GET_ITEM(pair, 0);
        PyObject* y = PySequence_Fast_GET_ITEM(pair, 1);
        out->push_back(mr::Point{PyFloat_AsDouble(x), PyFloat_AsDouble(y)});
        Py_DECREF(pair);
    }

    Py_DECREF(seq);
    return true;
}

/// Parses a Python sequence of four numbers into a C++ bounding box.
static bool parse_bounding_box(PyObject* obj, mr::BoundingBox* out) {
    PyObject* seq = PySequence_Fast(obj, "bounding_box must be a sequence");
    if (seq == nullptr) {
        return false;
    }
    if (PySequence_Fast_GET_SIZE(seq) != 4) {
        PyErr_SetString(PyExc_ValueError,
                        "bounding_box must have exactly four values");
        Py_DECREF(seq);
        return false;
    }
    const double min_x = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 0));
    const double min_y = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 1));
    const double max_x = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 2));
    const double max_y = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 3));
    Py_DECREF(seq);

    if (min_x > max_x || min_y > max_y) {
        PyErr_SetString(PyExc_ValueError,
                        "bounding_box min must not exceed max");
        return false;
    }
    *out = mr::BoundingBox{{min_x, min_y}, {max_x, max_y}};
    return true;
}

// ---------------------------------------------------------------------------
// The exposed function
// ---------------------------------------------------------------------------

static PyObject* py_multiscale_rasterization(PyObject* /* self */,
                                             PyObject* args,
                                             PyObject* kwargs) {
    static const char* kwlist[] = {"polyline", "bounding_box", "max_level",
                                   nullptr};

    PyObject* polyline_obj = nullptr;
    PyObject* bbox_obj = nullptr;
    int max_level = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOi:multiscale_rasterization",
                                     const_cast<char**>(kwlist),
                                     &polyline_obj, &bbox_obj, &max_level)) {
        return nullptr;
    }

    std::vector<mr::Point> polyline;
    if (!parse_polyline(polyline_obj, &polyline)) {
        return nullptr;
    }

    mr::BoundingBox bbox;
    if (!parse_bounding_box(bbox_obj, &bbox)) {
        return nullptr;
    }

    const mr::RasterizedObject result =
        mr::multiscale_rasterization(polyline, bbox, max_level);

    // Build the three parallel lists.
    PyObject* corners = PyList_New(static_cast<Py_ssize_t>(result.corners.size()));
    PyObject* sizes = PyList_New(static_cast<Py_ssize_t>(result.sizes.size()));
    PyObject* levels = PyList_New(static_cast<Py_ssize_t>(result.levels.size()));
    if (corners == nullptr || sizes == nullptr || levels == nullptr) {
        Py_XDECREF(corners);
        Py_XDECREF(sizes);
        Py_XDECREF(levels);
        return nullptr;
    }

    for (size_t i = 0; i < result.corners.size(); ++i) {
        PyObject* corner = Py_BuildValue("(dd)", result.corners[i].x,
                                         result.corners[i].y);
        PyList_SET_ITEM(corners, static_cast<Py_ssize_t>(i), corner);
        PyList_SET_ITEM(sizes, static_cast<Py_ssize_t>(i),
                        PyFloat_FromDouble(result.sizes[i]));
        PyList_SET_ITEM(levels, static_cast<Py_ssize_t>(i),
                        PyLong_FromLong(result.levels[i]));
    }

    PyObject* tuple = Py_BuildValue("(OOO)", corners, sizes, levels);
    Py_DECREF(corners);
    Py_DECREF(sizes);
    Py_DECREF(levels);
    return tuple;
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

static PyObject* py_version(PyObject* /* self */, PyObject* /* args */) {
    return PyUnicode_FromString("0.1.0");
}

static PyMethodDef module_methods[] = {
    {"multiscale_rasterization", (PyCFunction)py_multiscale_rasterization,
     METH_VARARGS | METH_KEYWORDS,
     "Rasterize a 2D polyline at multiple scales."},
    {"version", py_version, METH_NOARGS, "Return the module version."},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_core",
    "C++ core for multiscale rasterization.",
    -1,
    module_methods,
};

PyMODINIT_FUNC PyInit__core(void) {
    return PyModule_Create(&module_def);
}