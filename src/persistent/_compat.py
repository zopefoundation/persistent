##############################################################################
#
# Copyright (c) 2012 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################

import os
import sys
import types

from zope.interface import classImplements
from zope.interface import implementedBy


__all__ = [
    'use_c_impl',
    'PYPY',
]


PYPY = hasattr(sys, 'pypy_version_info')


def _c_optimizations_required():
    """
    Return a true value if the C optimizations are required.

    This uses the ``PURE_PYTHON`` variable as documented in `use_c_impl`.
    """
    pure_env = os.environ.get('PURE_PYTHON')
    require_c = pure_env == "0"
    return require_c


def _c_optimizations_available():
    """
    Return the C optimization modules, if available, otherwise
    a false value.

    If the optimizations are required but not available, this
    raises the ImportError. Either all optimization modules are
    available or none are.

    This does not say whether they should be used or not.
    """
    catch = () if _c_optimizations_required() else (ImportError,)
    try:
        from persistent import _timestamp
        from persistent import cPersistence
        from persistent import cPickleCache
        return {
            'persistent.persistence': cPersistence,
            'persistent.picklecache': cPickleCache,
            'persistent.timestamp': _timestamp,
        }
    except catch:  # pragma: no cover (only Jython doesn't build extensions)
        return {}


def _c_optimizations_ignored():
    """
    The opposite of `_c_optimizations_required`.

    On PyPy, this always returns True.

    Otherwise, if ``$PURE_PYTHON`` is set to any non-empty value
    besides "0", optimizations are ignored. Setting ``$PURE_PYTHON``
    to "1", for example, ignores optimizations. Setting ``$PURE_PYTHON`` to
    an empty value *does not* ignore optimizations.
    """
    pure_env = os.environ.get('PURE_PYTHON')
    # The extensions can be compiled with PyPy 7.3, but they don't work.
    return PYPY or (pure_env and pure_env != "0")


def _should_attempt_c_optimizations():
    """
    Return a true value if we should attempt to use the C optimizations.

    This takes into account whether we're on PyPy and the value of the
    ``PURE_PYTHON`` environment variable, as defined in `use_c_impl`.

    Note that setting ``PURE_PYTHON=0`` forces the use of C optimizations,
    even on PyPy.
    """
    if _c_optimizations_required():
        return True
    if PYPY:  # pragma: no cover
        return False
    return not _c_optimizations_ignored()


def use_c_impl(py_impl, name=None, globs=None, mod_name=None):
    """
    Decorator. Given an object implemented in Python, with a name like
    ``Foo``, import the corresponding C implementation from
    ``persistent.c<NAME>`` with the name ``Foo`` and use it instead
    (where ``NAME`` is the module name).

    This can also be used for constants and other things that do not
    have a name by passing the name as the second argument.

    Example::

        @use_c_impl
        class Foo(object):
            ...

        GHOST = use_c_impl(12, 'GHOST')

    If the ``PURE_PYTHON`` environment variable is set to any value
    other than ``"0"``, or we're on PyPy, ignore the C implementation
    and return the Python version. If the C implementation cannot be
    imported, return the Python version. If ``PURE_PYTHON`` is set to
    0, *require* the C implementation (let the ImportError propagate);
    note that PyPy can import the C implementation in this case (and
    all tests pass).

    In all cases, the Python version is kept available in the module
    globals with the name ``FooPy``.

    If the Python version is a class that implements interfaces, then
    the C version will be declared to also implement those interfaces.

    If the Python version is a class, then each function defined
    directly in that class will be replaced with a new version using
    globals that still use the original name of the class for the
    Python implementation. This lets the function bodies refer to the
    class using the name the class is defined with, as it would
    expect. (Only regular functions and static methods are handled.)
    However, it also means that mutating the module globals later on
    will not be visible to the methods of the class. In this example,
    ``Foo().method()`` will always return 1::

        GLOBAL_OBJECT = 1
        @use_c_impl
        class Foo(object):
            def method(self):
                super(Foo, self).method()
                return GLOBAL_OBJECT
        GLOBAL_OBJECT = 2
    """
    name = name or py_impl.__name__
    globs = globs or sys._getframe(1).f_globals
    mod_name = mod_name or globs['__name__']

    def find_impl():
        if not _should_attempt_c_optimizations():
            return py_impl

        c_opts = _c_optimizations_available()
        # only Jython doesn't build extensions:
        if not c_opts:  # pragma: no cover
            return py_impl

        __traceback_info__ = c_opts
        c_opt = c_opts[mod_name]
        return getattr(c_opt, name)

    c_impl = find_impl()
    # Always make available by the FooPy name
    globs[name + 'Py'] = py_impl

    if c_impl is not py_impl and isinstance(py_impl, type):
        # Rebind the globals of all the functions to still see the
        # object under its original class name, so that references
        # in function bodies work as expected.
        py_attrs = vars(py_impl)
        new_globals = None
        for k, v in list(py_attrs.items()):
            static = isinstance(v, staticmethod)
            if static:
                # Often this is __new__
                v = v.__func__

            if not isinstance(v, types.FunctionType):
                continue

            if new_globals is None:
                new_globals = v.__globals__.copy()
                new_globals[py_impl.__name__] = py_impl
            v = types.FunctionType(
                v.__code__,
                new_globals,
                k,  # name
                v.__defaults__,
                v.__closure__,
            )
            if static:
                v = staticmethod(v)
            setattr(py_impl, k, v)
        # copy the interface declarations.
        implements = list(implementedBy(py_impl))
        if implements:
            classImplements(c_impl, *implements)
    return c_impl
