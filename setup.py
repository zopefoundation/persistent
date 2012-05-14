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

__version__ = '4.0dev'

import os

from ez_setup import use_setuptools
use_setuptools()

from setuptools import Extension
from setuptools import find_packages
from setuptools import setup

TESTS_REQUIRE = [
]

here = os.path.abspath(os.path.dirname(__file__))
README = (open(os.path.join(here, 'README.txt')).read()
          + '\n\n' +
          open(os.path.join(here, 'CHANGES.txt')).read())

setup(name='persistent',
      version=__version__,
      description='Translucent persistent objects',
      long_description=README,
      classifiers=[
        "Development Status :: 6 - Mature",
        "License :: OSI Approved :: Zope Public License",
        "Programming Language :: Python",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Unix",
        ],
      author="Zope Corporation",
      author_email="zodb-dev@zope.org",
      url="http://www.zope.org/Products/ZODB",
      license="ZPL 2.1",
      platforms=["any"],
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      ext_modules = [Extension(name = 'persistent.cPersistence',
                               sources= ['persistent/cPersistence.c',
                                         'persistent/ring.c',
                                        ],
                               depends = ['persistent/cPersistence.h',
                                          'persistent/ring.h',
                                          'persistent/ring.c',
                                         ]
                              ),
                     Extension(name = 'persistent.cPickleCache',
                               sources= ['persistent/cPickleCache.c',
                                         'persistent/ring.c'
                                        ],
                               depends = ['persistent/cPersistence.h',
                                          'persistent/ring.h',
                                          'persistent/ring.c',
                                         ]
                              ),
                     Extension(name = 'persistent.TimeStamp',
                               sources= ['persistent/TimeStamp.c',
                                        ],
                              ),
                    ],
      headers = ['persistent/cPersistence.h',
                 'persistent/ring.h'],
      tests_require = TESTS_REQUIRE,
      extras_require = {
        'test': TESTS_REQUIRE,
        'testing': TESTS_REQUIRE + ['nose', 'coverage'],
        'docs': ['Sphinx', 'repoze.sphinx.autointerface'],
      },
      test_suite="persistent.tests",
      install_requires=[
        'zope.interface',
      ],
      entry_points = """\
      """
      )

