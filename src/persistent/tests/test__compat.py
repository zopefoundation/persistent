##############################################################################
#
# Copyright (c) Zope Foundation and Contributors.
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
Tests for ``persistent._compat``

"""

import unittest
import os

from persistent import _compat as compat

class TestCOptimizationsFuncs(unittest.TestCase):
    # pylint:disable=protected-access
    def setUp(self):
        self.env_val = os.environ.get('PURE_PYTHON', self)
        self.orig_pypy = compat.PYPY
        compat.PYPY = False

    def tearDown(self):
        compat.PYPY = self.orig_pypy
        if self.env_val is not self:
            # Reset to what it was to begin with.
            os.environ['PURE_PYTHON'] = self.env_val
        else: # pragma: no cover
            # It wasn't present before, make sure it's not present now.
            os.environ.pop('PURE_PYTHON', None)

        self.env_val = None

    def _set_env(self, val):
        if val is not None:
            os.environ['PURE_PYTHON'] = val
        else:
            os.environ.pop('PURE_PYTHON', None)

    def test_ignored_no_env_val(self):
        self._set_env(None)
        self.assertFalse(compat._c_optimizations_ignored())

    def test_ignored_zero(self):
        self._set_env('0')
        self.assertFalse(compat._c_optimizations_ignored())

    def test_ignored_empty(self):
        self._set_env('')
        self.assertFalse(compat._c_optimizations_ignored())

    def test_ignored_other_values(self):
        for val in "1", "yes", "hi":
            self._set_env(val)
            self.assertTrue(compat._c_optimizations_ignored())

    def test_ignored_pypy(self):
        # No matter what the environment variable is, PyPy always ignores
        compat.PYPY = True
        for val in None, "", "0", "1", "yes":
            __traceback_info__ = val
            self._set_env(val)
            self.assertTrue(compat._c_optimizations_ignored())

    def test_required(self):
        for val, expected in (
                ('', False),
                ('0', True),
                ('1', False),
                ('Yes', False)
        ):
            self._set_env(val)
            self.assertEqual(expected, compat._c_optimizations_required())

    def test_should_attempt(self):
        for val, expected in (
                (None, True),
                ('', True),
                ('0', True),
                ('1', False),
                ('Yes', False)
        ):
            self._set_env(val)
            self.assertEqual(expected, compat._should_attempt_c_optimizations())

    def test_should_attempt_pypy(self):
        compat.PYPY = True
        for val, expected in (
                (None, False),
                ('', False),
                ('0', True),
                ('1', False),
                ('Yes', False)
        ):
            __traceback_info__ = val
            self._set_env(val)
            self.assertEqual(expected, compat._should_attempt_c_optimizations())
