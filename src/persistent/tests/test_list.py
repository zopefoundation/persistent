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
"""Tests for PersistentList
"""

import unittest


from persistent.tests.utils import TrivialJar
from persistent.tests.utils import copy_test


l0 = []
l1 = [0]
l2 = [0, 1]

# pylint:disable=protected-access

class OtherList:
    def __init__(self, initlist):
        self.__data = initlist
    def __len__(self):
        return len(self.__data)
    def __getitem__(self, i):
        return self.__data[i]


class TestPList(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.list import PersistentList
        return PersistentList

    def _makeJar(self):
        return TrivialJar()

    def _makeOne(self, *args):
        inst = self._getTargetClass()(*args)
        inst._p_jar = self._makeJar()
        return inst

    def test_volatile_attributes_not_persisted(self):
        # http://www.zope.org/Collectors/Zope/2052
        m = self._getTargetClass()()
        m.foo = 'bar'
        m._v_baz = 'qux'
        state = m.__getstate__()
        self.assertTrue('foo' in state)
        self.assertFalse('_v_baz' in state)

    def testTheWorld(self):
        # Test constructors
        pl = self._getTargetClass()
        u = pl()
        u0 = pl(l0)
        u1 = pl(l1)
        u2 = pl(l2)

        uu = pl(u)
        uu0 = pl(u0)
        uu1 = pl(u1)
        uu2 = pl(u2)

        pl(tuple(u))
        pl(OtherList(u0))
        pl("this is also a sequence")

        # Test __repr__
        eq = self.assertEqual

        eq(str(u0), str(l0), "str(u0) == str(l0)")
        eq(repr(u1), repr(l1), "repr(u1) == repr(l1)")

        # Test __cmp__ and __len__
        try:
            cmp
        except NameError:
            def cmp(a, b):
                if a == b:
                    return 0
                if a < b:
                    return -1
                return 1

        def mycmp(a, b):
            r = cmp(a, b)
            if r < 0:
                return -1
            if r > 0:
                return 1
            return r

        to_test = [l0, l1, l2, u, u0, u1, u2, uu, uu0, uu1, uu2]
        for a in to_test:
            for b in to_test:
                eq(mycmp(a, b), mycmp(len(a), len(b)),
                   "mycmp(a, b) == mycmp(len(a), len(b))")

        # Test __getitem__

        for i, val in enumerate(u2):
            eq(val, i, "u2[i] == i")

        # Test __setitem__

        uu2[0] = 0
        uu2[1] = 100
        with self.assertRaises(IndexError):
            uu2[2] = 200

        # Test __delitem__

        del uu2[1]
        del uu2[0]
        with self.assertRaises(IndexError):
            del uu2[0]

        # Test __getslice__

        for i in range(-3, 4):
            eq(u2[:i], l2[:i], "u2[:i] == l2[:i]")
            eq(u2[i:], l2[i:], "u2[i:] == l2[i:]")
            for j in range(-3, 4):
                eq(u2[i:j], l2[i:j], "u2[i:j] == l2[i:j]")

        # Test __setslice__

        for i in range(-3, 4):
            u2[:i] = l2[:i]
            eq(u2, l2, "u2 == l2")
            u2[i:] = l2[i:]
            eq(u2, l2, "u2 == l2")
            for j in range(-3, 4):
                u2[i:j] = l2[i:j]
                eq(u2, l2, "u2 == l2")

        uu2 = u2[:]
        uu2[:0] = [-2, -1]
        eq(uu2, [-2, -1, 0, 1], "uu2 == [-2, -1, 0, 1]")
        uu2[0:] = []
        eq(uu2, [], "uu2 == []")

        # Test __contains__
        for i in u2:
            self.assertTrue(i in u2, "i in u2")
        for i in min(u2)-1, max(u2)+1:
            self.assertTrue(i not in u2, "i not in u2")

        # Test __delslice__

        uu2 = u2[:]
        del uu2[1:2]
        del uu2[0:1]
        eq(uu2, [], "uu2 == []")

        uu2 = u2[:]
        del uu2[1:]
        del uu2[:1]
        eq(uu2, [], "uu2 == []")

        # Test __add__, __radd__, __mul__ and __rmul__

        #self.assertTrue(u1 + [] == [] + u1 == u1, "u1 + [] == [] + u1 == u1")
        self.assertTrue(u1 + [1] == u2, "u1 + [1] == u2")
        #self.assertTrue([-1] + u1 == [-1, 0], "[-1] + u1 == [-1, 0]")
        self.assertTrue(u2 == u2*1 == 1*u2, "u2 == u2*1 == 1*u2")
        self.assertTrue(u2+u2 == u2*2 == 2*u2, "u2+u2 == u2*2 == 2*u2")
        self.assertTrue(u2+u2+u2 == u2*3 == 3*u2, "u2+u2+u2 == u2*3 == 3*u2")

        # Test append

        u = u1[:]
        u.append(1)
        eq(u, u2, "u == u2")

        # Test insert

        u = u2[:]
        u.insert(0, -1)
        eq(u, [-1, 0, 1], "u == [-1, 0, 1]")

        # Test pop

        u = pl([0, -1, 1])
        u.pop()
        eq(u, [0, -1], "u == [0, -1]")
        u.pop(0)
        eq(u, [-1], "u == [-1]")

        # Test remove

        u = u2[:]
        u.remove(1)
        eq(u, u1, "u == u1")

        # Test count
        u = u2*3
        eq(u.count(0), 3, "u.count(0) == 3")
        eq(u.count(1), 3, "u.count(1) == 3")
        eq(u.count(2), 0, "u.count(2) == 0")


        # Test index

        eq(u2.index(0), 0, "u2.index(0) == 0")
        eq(u2.index(1), 1, "u2.index(1) == 1")
        with self.assertRaises(ValueError):
            u2.index(2)

        # Test reverse

        u = u2[:]
        u.reverse()
        eq(u, [1, 0], "u == [1, 0]")
        u.reverse()
        eq(u, u2, "u == u2")

        # Test sort

        u = pl([1, 0])
        u.sort()
        eq(u, u2, "u == u2")

        # Test keyword arguments to sort
        u.sort(key=lambda x: -x)
        eq(u, [1, 0], "u == [1, 0]")

        u.sort(reverse=True)
        eq(u, [1, 0], "u == [1, 0]")

        # Passing any other keyword arguments results in a TypeError
        with self.assertRaises(TypeError):
            u.sort(blah=True)

        # Test extend

        u = u1[:]
        u.extend(u2)
        eq(u, u1 + u2, "u == u1 + u2")

        # Test iadd
        u = u1[:]
        u += u2
        eq(u, u1 + u2, "u == u1 + u2")

        # Test imul
        u = u1[:]
        u *= 3
        eq(u, u1 + u1 + u1, "u == u1 + u1 + u1")

    def test_setslice(self):
        inst = self._makeOne()
        self.assertFalse(inst._p_changed)
        inst[:] = [1, 2, 3]
        self.assertEqual(inst, [1, 2, 3])
        self.assertTrue(inst._p_changed)

    def test_delslice_all_nonempty_list(self):
        # Delete everything from a non-empty list
        inst = self._makeOne([1, 2, 3])
        self.assertFalse(inst._p_changed)
        self.assertEqual(inst, [1, 2, 3])
        del inst[:]
        self.assertEqual(inst, [])
        self.assertTrue(inst._p_changed)

    def test_delslice_sub_nonempty_list(self):
        # delete a sub-list from a non-empty list
        inst = self._makeOne([0, 1, 2, 3])
        self.assertFalse(inst._p_changed)
        del inst[1:2]
        self.assertEqual(inst, [0, 2, 3])
        self.assertTrue(inst._p_changed)

    def test_delslice_empty_nonempty_list(self):
        # delete an empty sub-list from a non-empty list
        inst = self._makeOne([0, 1, 2, 3])
        self.assertFalse(inst._p_changed)
        del inst[1:1]
        self.assertEqual(inst, [0, 1, 2, 3])
        self.assertFalse(inst._p_changed)

    def test_delslice_all_empty_list(self):
        inst = self._makeOne([])
        self.assertFalse(inst._p_changed)
        self.assertEqual(inst, [])
        del inst[:]
        self.assertEqual(inst, [])
        self.assertFalse(inst._p_changed)

    def test_iadd(self):
        inst = self._makeOne()
        self.assertFalse(inst._p_changed)
        inst += [1, 2, 3]
        self.assertEqual(inst, [1, 2, 3])
        self.assertTrue(inst._p_changed)

    def test_extend(self):
        inst = self._makeOne()
        self.assertFalse(inst._p_changed)
        inst.extend([1, 2, 3])
        self.assertEqual(inst, [1, 2, 3])
        self.assertTrue(inst._p_changed)

    def test_imul(self):
        inst = self._makeOne([1])
        self.assertFalse(inst._p_changed)
        inst *= 2
        self.assertEqual(inst, [1, 1])
        self.assertTrue(inst._p_changed)

    def test_append(self):
        inst = self._makeOne()
        self.assertFalse(inst._p_changed)
        inst.append(1)
        self.assertEqual(inst, [1])
        self.assertTrue(inst._p_changed)

    def test_clear_nonempty(self):
        inst = self._makeOne([1, 2, 3, 4])
        self.assertFalse(inst._p_changed)
        inst.clear()
        self.assertEqual(inst, [])
        self.assertTrue(inst._p_changed)

    def test_clear_empty(self):
        inst = self._makeOne([])
        self.assertFalse(inst._p_changed)
        inst.clear()
        self.assertEqual(inst, [])
        self.assertFalse(inst._p_changed)

    def test_insert(self):
        inst = self._makeOne()
        self.assertFalse(inst._p_changed)
        inst.insert(0, 1)
        self.assertEqual(inst, [1])
        self.assertTrue(inst._p_changed)

    def test_remove(self):
        inst = self._makeOne([1])
        self.assertFalse(inst._p_changed)
        inst.remove(1)
        self.assertEqual(inst, [])
        self.assertTrue(inst._p_changed)

    def test_reverse(self):
        inst = self._makeOne([2, 1])
        self.assertFalse(inst._p_changed)
        inst.reverse()
        self.assertEqual(inst, [1, 2])
        self.assertTrue(inst._p_changed)

    def test_getslice_same_class(self):
        class MyList(self._getTargetClass()):
            pass

        inst = MyList()
        inst._p_jar = self._makeJar()
        # Entire thing, empty.
        inst2 = inst[:]
        self.assertIsNot(inst, inst2)
        self.assertEqual(inst, inst2)
        self.assertIsInstance(inst2, MyList)
        # The _p_jar is *not* propagated.
        self.assertIsNotNone(inst._p_jar)
        self.assertIsNone(inst2._p_jar)

        # Partial
        inst.extend((1, 2, 3))
        inst2 = inst[1:2]
        self.assertEqual(inst2, [2])
        self.assertIsInstance(inst2, MyList)
        self.assertIsNone(inst2._p_jar)

    def test_copy(self):
        inst = self._makeOne()
        inst.append(42)
        copy_test(self, inst)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main()
