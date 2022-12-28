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
import unittest


from persistent.tests.utils import TrivialJar
from persistent.tests.utils import copy_test

# pylint:disable=blacklisted-name, protected-access

class Test_default(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.mapping import default
        return default

    def _makeOne(self, func):
        return self._getTargetClass()(func)

    def test___get___from_class(self):
        def _test(inst):
            raise AssertionError("Must not be caled")

        descr = self._makeOne(_test)
        class Foo:
            testing = descr
        self.assertIs(Foo.testing, descr)


    def test___get___from_instance(self):
        _called_with = []
        def _test(inst):
            _called_with.append(inst)
            return 'TESTING'
        descr = self._makeOne(_test)
        class Foo:
            testing = descr
        foo = Foo()
        self.assertEqual(foo.testing, 'TESTING')
        self.assertEqual(_called_with, [foo])


class PersistentMappingTests(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.mapping import PersistentMapping
        return PersistentMapping

    def _makeJar(self):
        return TrivialJar()

    def _makeOne(self, *args, **kwargs):
        inst = self._getTargetClass()(*args, **kwargs)
        inst._p_jar = self._makeJar()
        return inst

    def test_volatile_attributes_not_persisted(self):
        # http://www.zope.org/Collectors/Zope/2052
        m = self._makeOne()
        m.foo = 'bar'
        m._v_baz = 'qux'
        state = m.__getstate__()
        self.assertTrue('foo' in state)
        self.assertFalse('_v_baz' in state)

    def testTheWorld(self):
        # Test constructors
        l0 = {}
        l1 = {0:0}
        l2 = {0:0, 1:1}
        u = self._makeOne()
        u0 = self._makeOne(l0)
        u1 = self._makeOne(l1)
        u2 = self._makeOne(l2)

        uu = self._makeOne(u)
        uu0 = self._makeOne(u0)
        uu1 = self._makeOne(u1)
        uu2 = self._makeOne(u2)

        class OtherMapping(dict):
            def __init__(self, initmapping):
                dict.__init__(self)
                self.__data = initmapping
            def items(self):
                raise AssertionError("Not called")
        self._makeOne(OtherMapping(u0))
        self._makeOne([(0, 0), (1, 1)])

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
                if hasattr(a, 'items'):
                    a = sorted(a.items())
                    b = sorted(b.items())
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

        # Test get

        for i in range(len(u2)):
            eq(u2.get(i), i, "u2.get(i) == i")
            eq(u2.get(i, 5), i, "u2.get(i, 5) == i")

        for i in min(u2)-1, max(u2)+1:
            eq(u2.get(i), None, "u2.get(i) == None")
            eq(u2.get(i, 5), 5, "u2.get(i, 5) == 5")

        # Test __setitem__

        uu2[0] = 0
        uu2[1] = 100
        uu2[2] = 200

        # Test __delitem__

        del uu2[1]
        del uu2[0]
        with self.assertRaises(KeyError):
            del uu2[0]

        # Test __contains__
        for i in u2:
            self.assertTrue(i in u2, "i in u2")
        for i in min(u2)-1, max(u2)+1:
            self.assertTrue(i not in u2, "i not in u2")

        # Test update

        l = {"a":"b"}
        u = self._makeOne(l)
        u.update(u2)
        for i in u:
            self.assertTrue(i in l or i in u2, "i in l or i in u2")
        for i in l:
            self.assertTrue(i in u, "i in u")
        for i in u2:
            self.assertTrue(i in u, "i in u")

        # Test setdefault

        x = u2.setdefault(0, 5)
        eq(x, 0, "u2.setdefault(0, 5) == 0")

        x = u2.setdefault(5, 5)
        eq(x, 5, "u2.setdefault(5, 5) == 5")
        self.assertTrue(5 in u2, "5 in u2")

        # Test pop

        x = u2.pop(1)
        eq(x, 1, "u2.pop(1) == 1")
        self.assertTrue(1 not in u2, "1 not in u2")

        with self.assertRaises(KeyError):
            u2.pop(1)

        x = u2.pop(1, 7)
        eq(x, 7, "u2.pop(1, 7) == 7")

        # Test popitem

        items = list(u2.items())
        key, value = u2.popitem()
        self.assertTrue((key, value) in items, "key, value in items")
        self.assertTrue(key not in u2, "key not in u2")

        # Test clear

        u2.clear()
        eq(u2, {}, "u2 == {}")

    def test___repr___converts_legacy_container_attr(self):
        # In the past, PM used a _container attribute. For some time, the
        # implementation continued to use a _container attribute in pickles
        # (__get/setstate__) to be compatible with older releases.  This isn't
        # really necessary any more. In fact, releases for which this might
        # matter can no longer share databases with current releases.  Because
        # releases as recent as 3.9.0b5 still use _container in saved state, we
        # need to accept such state, but we stop producing it.
        pm = self._makeOne()
        self.assertEqual(pm.__dict__, {'data': {}})
        # Make it look like an older instance
        pm.__dict__.clear()
        pm.__dict__['_container'] = {'a': 1}
        self.assertEqual(pm.__dict__, {'_container': {'a': 1}})
        pm._p_changed = 0
        self.assertEqual(repr(pm), "{'a': 1}")
        self.assertEqual(pm.__dict__, {'data': {'a': 1}})
        self.assertEqual(pm.__getstate__(), {'data': {'a': 1}})

    def test_update_keywords(self):
        # Prior to https://github.com/zopefoundation/persistent/issues/126,
        # PersistentMapping didn't accept keyword arguments to update as
        # the builtin dict and the UserDict do.
        # Here we make sure it does. We use some names that have been
        # seen to be special in signatures as well to make sure that
        # we don't interpret them incorrectly.
        pm = self._makeOne()
        # Our older implementation was ``def update(self, b)``, so ``b``
        # is potentially a keyword argument in the wild; the behaviour in that
        # corner case has changed.
        pm.update(b={'a': 42})
        self.assertEqual(pm, {'b': {'a': 42}})

        pm = self._makeOne()
        # Our previous implementation would explode with a TypeError
        pm.update(b=42)
        self.assertEqual(pm, {'b': 42})

        pm = self._makeOne()
        # ``other`` shows up in a Python 3 signature.
        pm.update(other=42)
        self.assertEqual(pm, {'other': 42})
        pm = self._makeOne()
        pm.update(other={'a': 42})
        self.assertEqual(pm, {'other': {'a': 42}})

        pm = self._makeOne()
        pm.update(a=1, b=2)
        self.assertEqual(pm, {'a': 1, 'b': 2})

    def test_clear_nonempty(self):
        pm = self._makeOne({'a': 42})
        self.assertFalse(pm._p_changed)
        pm.clear()
        self.assertTrue(pm._p_changed)

    def test_clear_empty(self):
        pm = self._makeOne()
        self.assertFalse(pm._p_changed)
        pm.clear()
        self.assertFalse(pm._p_changed)

    def test_clear_no_jar(self):
        # https://github.com/zopefoundation/persistent/issues/139
        self._makeOne = self._getTargetClass()
        self.test_clear_empty()

        pm = self._makeOne(a=42)
        pm.clear()
        self.assertFalse(pm._p_changed)

    def test_clear_empty_legacy_container(self):
        pm = self._makeOne()
        pm.__dict__['_container'] = pm.__dict__.pop('data')
        self.assertFalse(pm._p_changed)
        pm.clear()
        # Migration happened
        self.assertIn('data', pm.__dict__)
        # and we are marked as changed.
        self.assertTrue(pm._p_changed)

    def test_copy(self):
        pm = self._makeOne()
        pm['key'] = 42
        copy = copy_test(self, pm)
        self.assertEqual(42, copy['key'])

    def test_copy_legacy_container(self):
        pm = self._makeOne()
        pm['key'] = 42
        pm.__dict__['_container'] = pm.__dict__.pop('data')

        self.assertNotIn('data', pm.__dict__)
        self.assertIn('_container', pm.__dict__)

        copy = copy_test(self, pm)
        self.assertNotIn('_container', copy.__dict__)
        self.assertIn('data', copy.__dict__)
        self.assertEqual(42, copy['key'])


class Test_legacy_PersistentDict(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.dict import PersistentDict
        return PersistentDict

    def test_PD_is_alias_to_PM(self):
        from persistent.mapping import PersistentMapping
        self.assertIs(self._getTargetClass(), PersistentMapping)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
