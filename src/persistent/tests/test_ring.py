##############################################################################
#
# Copyright (c) 2015 Zope Foundation and Contributors.
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
import unittest

from .. import ring


class DummyPersistent:
    _p_oid = None
    _Persistent__ring = None
    __next_oid = 0

    @classmethod
    def _next_oid(cls):
        cls.__next_oid += 1
        return cls.__next_oid

    def __init__(self):
        self._p_oid = self._next_oid()

    def __repr__(self):  # pragma: no cover
        return f"<Dummy {self._p_oid!r} at 0x{id(self):x}>"


class CFFIRingTests(unittest.TestCase):

    def _getTargetClass(self):
        return ring._CFFIRing

    def _makeOne(self):
        return self._getTargetClass()()

    def test_empty_len(self):
        self.assertEqual(0, len(self._makeOne()))

    def test_empty_contains(self):
        r = self._makeOne()
        self.assertNotIn(DummyPersistent(), r)

    def test_empty_iter(self):
        self.assertEqual([], list(self._makeOne()))

    def test_add_one_len1(self):
        r = self._makeOne()
        p = DummyPersistent()
        r.add(p)
        self.assertEqual(1, len(r))

    def test_add_one_contains(self):
        r = self._makeOne()
        p = DummyPersistent()
        r.add(p)
        self.assertIn(p, r)

    def test_delete_one_len0(self):
        r = self._makeOne()
        p = DummyPersistent()
        r.add(p)
        r.delete(p)
        self.assertEqual(0, len(r))

    def test_delete_one_multiple(self):
        r = self._makeOne()
        p = DummyPersistent()
        r.add(p)
        r.delete(p)
        self.assertEqual(0, len(r))
        self.assertNotIn(p, r)

        r.delete(p)
        self.assertEqual(0, len(r))
        self.assertNotIn(p, r)

    def test_delete_from_wrong_ring(self):
        r1 = self._makeOne()
        r2 = self._makeOne()
        p1 = DummyPersistent()
        p2 = DummyPersistent()

        r1.add(p1)
        r2.add(p2)

        r2.delete(p1)

        self.assertEqual(1, len(r1))
        self.assertEqual(1, len(r2))

        self.assertEqual([p1], list(r1))
        self.assertEqual([p2], list(r2))

    def test_move_to_head(self):
        r = self._makeOne()
        p1 = DummyPersistent()
        p2 = DummyPersistent()
        p3 = DummyPersistent()

        r.add(p1)
        r.add(p2)
        r.add(p3)
        __traceback_info__ = [
            p1._Persistent__ring,
            p2._Persistent__ring,
            p3._Persistent__ring,
        ]
        self.assertEqual(3, len(r))
        self.assertEqual([p1, p2, p3], list(r))

        r.move_to_head(p1)
        self.assertEqual([p2, p3, p1], list(r))

        r.move_to_head(p3)
        self.assertEqual([p2, p1, p3], list(r))

        r.move_to_head(p3)
        self.assertEqual([p2, p1, p3], list(r))
