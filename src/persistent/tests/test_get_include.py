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
Tests for ``persistent.get_include``
"""
import pathlib
import unittest

import persistent


PERSISTENT_FILE = pathlib.Path(persistent.__file__)


class Test_get_include(unittest.TestCase):

    @staticmethod
    def test_bare_path():
        found = persistent.get_include()

        assert found == str(PERSISTENT_FILE.parent.parent)

    @staticmethod
    def test_cPersistence_h():
        found = persistent.get_include()

        found_path = pathlib.Path(found)
        cPersistence_h = found_path / "persistent" / "cPersistence.h"

        assert cPersistence_h.is_file()

    @staticmethod
    def test_ring_h():
        found = persistent.get_include()

        found_path = pathlib.Path(found)
        ring_h = found_path / "persistent" / "ring.h"

        assert ring_h.is_file()
