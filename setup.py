##############################################################################
#
# Copyright (c) 2008 Zope Foundation and Contributors.
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

import platform

from setuptools import Extension
from setuptools import setup


define_macros = (
    # We currently use macros like PyBytes_AS_STRING
    # and internal functions like _PyObject_GetDictPtr
    # that make it impossible to use the stable (limited) API.
    # ('Py_LIMITED_API', '0x03050000'),
)
ext_modules = [
    Extension(
        name='persistent.cPersistence',
        sources=[
            'src/persistent/cPersistence.c',
            'src/persistent/ring.c',
        ],
        depends=[
            'src/persistent/cPersistence.h',
            'src/persistent/ring.h',
            'src/persistent/ring.c',
        ],
        define_macros=list(define_macros),
    ),
    Extension(
        name='persistent.cPickleCache',
        sources=[
            'src/persistent/cPickleCache.c',
            'src/persistent/ring.c',
        ],
        depends=[
            'src/persistent/cPersistence.h',
            'src/persistent/ring.h',
            'src/persistent/ring.c',
        ],
        define_macros=list(define_macros),
    ),
    Extension(
        name='persistent._timestamp',
        sources=[
            'src/persistent/_timestamp.c',
        ],
        define_macros=list(define_macros),
    ),
]

is_pypy = platform.python_implementation() == 'PyPy'
if is_pypy:
    # Header installation doesn't work on PyPy:
    # https://github.com/zopefoundation/persistent/issues/135
    headers = []
else:
    headers = [
        'src/persistent/cPersistence.h',
        'src/persistent/ring.h',
    ]

# setup_requires must be specified in the setup call, when building CFFI
# modules it's not sufficient to have the requirements in a pyproject.toml
# [build-system] section.
setup(ext_modules=ext_modules,
      cffi_modules=['src/persistent/_ring_build.py:ffi'],
      headers=headers,
      setup_requires=[
          "cffi ; platform_python_implementation == 'CPython'",
          "pycparser",
      ])
