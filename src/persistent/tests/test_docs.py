##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
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
"""
Tests for the documentation.
"""


import doctest
import os.path
import unittest

import manuel.capture
import manuel.codeblock
import manuel.doctest
import manuel.ignore
import manuel.testing


def test_suite():
    here = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(here, 'setup.py')):
        prev, here = here, os.path.dirname(here)
        if here == prev:
            # Let's avoid infinite loops at root
            raise AssertionError('could not find my setup.py')

    docs = os.path.join(here, 'docs', 'api')

    files_to_test = (
        'cache.rst',
        'attributes.rst',
        'pickling.rst',
    )
    paths = [os.path.join(docs, f) for f in files_to_test]

    m = manuel.ignore.Manuel()
    m += manuel.doctest.Manuel(optionflags=(
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.IGNORE_EXCEPTION_DETAIL
    ))
    m += manuel.codeblock.Manuel()
    m += manuel.capture.Manuel()

    suite = unittest.TestSuite()
    suite.addTest(
        manuel.testing.TestSuite(
            m,
            *paths
        )
    )

    return suite
