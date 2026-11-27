/***************************************************************************

  Copyright (c) 2026 Zope Foundation and Contributors.
  All Rights Reserved.

  This software is subject to the provisions of the Zope Public License,
  Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
  THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
  WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
  WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
  FOR A PARTICULAR PURPOSE

 **************************************************************************/

/* Test-only helpers.

   Provides heap-allocated subtypes of the C 'persistent.Persistent'
   heap type whose 'tp_new' slots mimic what downstream C extensions
   do.  Not part of the public API.
 */

#include "Python.h"

/* Distinct from PyType_GenericNew, but behaviorally identical; stands
   in for what a consumer extension's own generic 'tp_new' looks like
   to persistent's ghostify() (i.e. *not* the shared sentinel). */
static PyObject *
custom_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    return PyType_GenericNew(type, args, kwds);
}

/* 'tp_new' is assigned at run time (in 'testtypes_exec') rather than via
   a static initializer: MSVC binds imported functions referenced from
   static data initializers differently than from code, so only the
   run-time-loaded value is guaranteed to match the sentinel used by
   'ghostify' in cPersistence.c. */

static PyType_Slot empty_slots[] = {
    {0,                     NULL},
};

static PyType_Spec generic_new_spec = {
    "persistent.tests._testtypes.GenericNew",
    0,                          /* basicsize: inherit from base */
    0,                          /* itemsize */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    empty_slots,
};

static PyType_Spec custom_new_spec = {
    "persistent.tests._testtypes.CustomNew",
    0,                          /* basicsize: inherit from base */
    0,                          /* itemsize */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    empty_slots,
};

static int
testtypes_exec(PyObject *module)
{
    PyObject *cmodule = NULL;
    PyObject *pertype = NULL;
    PyObject *bases = NULL;
    PyObject *type = NULL;

    cmodule = PyImport_ImportModule("persistent.cPersistence");
    if (cmodule == NULL)
        goto error;
    pertype = PyObject_GetAttrString(cmodule, "Persistent");
    if (pertype == NULL)
        goto error;
    bases = PyTuple_Pack(1, pertype);
    if (bases == NULL)
        goto error;

    type = PyType_FromModuleAndSpec(module, &generic_new_spec, bases);
    if (type == NULL)
        goto error;
    ((PyTypeObject *)type)->tp_new = PyType_GenericNew;
    if (PyModule_AddObject(module, "GenericNew", type) < 0) {
        Py_DECREF(type);
        goto error;
    }

    type = PyType_FromModuleAndSpec(module, &custom_new_spec, bases);
    if (type == NULL)
        goto error;
    ((PyTypeObject *)type)->tp_new = custom_new;
    if (PyModule_AddObject(module, "CustomNew", type) < 0) {
        Py_DECREF(type);
        goto error;
    }

    Py_XDECREF(bases);
    Py_XDECREF(pertype);
    Py_XDECREF(cmodule);
    return 0;

error:
    Py_XDECREF(bases);
    Py_XDECREF(pertype);
    Py_XDECREF(cmodule);
    return -1;
}

static PyModuleDef_Slot testtypes_slots[] = {
    {Py_mod_exec,           testtypes_exec},
    {0,                     NULL},
};

static PyModuleDef testtypes_module = {
    PyModuleDef_HEAD_INIT,
    .m_name     = "persistent.tests._testtypes",
    .m_size     = 0,
    .m_slots    = testtypes_slots,
};

PyMODINIT_FUNC
PyInit__testtypes(void)
{
    return PyModuleDef_Init(&testtypes_module);
}
