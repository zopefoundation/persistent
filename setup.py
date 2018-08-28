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

import os
import platform
import sys

from setuptools import Extension
from setuptools import find_packages
from setuptools import setup

version = '4.4.2'

here = os.path.abspath(os.path.dirname(__file__))


def _read_file(filename):
    with open(os.path.join(here, filename)) as f:
        return f.read()


README = (_read_file('README.rst') + '\n\n' + _read_file('CHANGES.rst'))

is_pypy = platform.python_implementation() == 'PyPy'
is_jython = 'java' in sys.platform

# Jython cannot build the C optimizations, while on PyPy they are
# anti-optimizations (the C extension compatibility layer is known-slow,
# and defeats JIT opportunities).
if is_pypy or is_jython:
    # Note that all the lists we pass to setuptools must be distinct
    # objects, or bad things happen. See https://github.com/zopefoundation/persistent/issues/88
    ext_modules = []
    headers = []
else:
    ext_modules = [
        Extension(
            name='persistent.cPersistence',
            sources=[
                'persistent/cPersistence.c',
                'persistent/ring.c',
            ],
            depends=[
                'persistent/cPersistence.h',
                'persistent/ring.h',
                'persistent/ring.c',
            ]
        ),
        Extension(
            name='persistent.cPickleCache',
            sources=[
                'persistent/cPickleCache.c',
                'persistent/ring.c',
            ],
            depends=[
                'persistent/cPersistence.h',
                'persistent/ring.h',
                'persistent/ring.c',
            ]
        ),
        Extension(
            name='persistent._timestamp',
            sources=[
                'persistent/_timestamp.c',
            ],
        ),
    ]
    headers = [
        'persistent/cPersistence.h',
        'persistent/ring.h',
    ]

setup(name='persistent',
      version=version,
      description='Translucent persistent objects',
      long_description=README,
      classifiers=[
          "Development Status :: 6 - Mature",
          "License :: OSI Approved :: Zope Public License",
          "Programming Language :: Python",
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          "Programming Language :: Python :: Implementation :: CPython",
          "Programming Language :: Python :: Implementation :: PyPy",
          "Framework :: ZODB",
          "Topic :: Database",
          "Topic :: Software Development :: Libraries :: Python Modules",
          "Operating System :: Microsoft :: Windows",
          "Operating System :: Unix",
      ],
      author="Zope Corporation",
      author_email="zodb-dev@zope.org",
      url="https://github.com/zopefoundation/persistent/",
      license="ZPL 2.1",
      platforms=["any"],
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      ext_modules=ext_modules,
      cffi_modules=['persistent/_ring_build.py:ffi'],
      headers=headers,
      extras_require={
          'test': [
              'zope.testrunner',
              "cffi ; platform_python_implementation == 'CPython'",
              'manuel',
          ],
          'testing': (),
          'docs': [
              'Sphinx',
              'repoze.sphinx.autointerface',
          ],
      },
      install_requires=[
          'zope.interface',
      ],
      entry_points={},
)
