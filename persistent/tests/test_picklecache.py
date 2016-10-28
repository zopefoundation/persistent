##############################################################################
#
# Copyright (c) 2009 Zope Foundation and Contributors.
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
import gc
import os
import platform
import sys
import unittest

_py_impl = getattr(platform, 'python_implementation', lambda: None)
_is_pypy = _py_impl() == 'PyPy'
_is_jython = 'java' in sys.platform

_marker = object()

class PickleCacheTests(unittest.TestCase):

    def setUp(self):
        import persistent.picklecache
        self.orig_types = persistent.picklecache._CACHEABLE_TYPES
        persistent.picklecache._CACHEABLE_TYPES += (DummyPersistent,)

    def tearDown(self):
        import persistent.picklecache
        persistent.picklecache._CACHEABLE_TYPES = self.orig_types

    def _getTargetClass(self):
        from persistent.picklecache import PickleCache
        return PickleCache

    def _makeOne(self, jar=None, target_size=10):
        if jar is None:
            jar = DummyConnection()
        return self._getTargetClass()(jar, target_size)

    def _makePersist(self, state=None, oid='foo', jar=_marker):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        if state is None:
            state = GHOST
        if jar is _marker:
            jar = DummyConnection()
        persist = DummyPersistent()
        persist._p_state = state
        persist._p_oid = _b(oid)
        persist._p_jar = jar
        return persist

    def test_class_conforms_to_IPickleCache(self):
        from zope.interface.verify import verifyClass
        from persistent.interfaces import IPickleCache
        verifyClass(IPickleCache, self._getTargetClass())

    def test_instance_conforms_to_IPickleCache(self):
        from zope.interface.verify import verifyObject
        from persistent.interfaces import IPickleCache
        verifyObject(IPickleCache, self._makeOne())

    def test_empty(self):
        cache = self._makeOne()

        self.assertEqual(len(cache), 0)
        self.assertEqual(_len(cache.items()), 0)
        self.assertEqual(_len(cache.klass_items()), 0)
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(len(cache.lru_items()), 0)
        self.assertEqual(cache.cache_size, 10)
        self.assertEqual(cache.cache_drain_resistance, 0)
        self.assertEqual(cache.cache_non_ghost_count, 0)
        self.assertEqual(dict(cache.cache_data), {})
        self.assertEqual(cache.cache_klass_count, 0)

    def test___getitem___nonesuch_raises_KeyError(self):
        cache = self._makeOne()

        self.assertRaises(KeyError, lambda: cache['nonesuch'])

    def test_get_nonesuch_no_default(self):
        cache = self._makeOne()

        self.assertEqual(cache.get('nonesuch'), None)

    def test_get_nonesuch_w_default(self):
        cache = self._makeOne()
        default = object

        self.assertTrue(cache.get('nonesuch', default) is default)

    def test___setitem___non_string_oid_raises_TypeError(self):
        cache = self._makeOne()

        try:
            cache[object()] = self._makePersist()
        except TypeError:
            pass
        else:
            self.fail("Didn't raise ValueError with non-string OID.")

    def test___setitem___duplicate_oid_same_obj(self):
        from persistent._compat import _b
        KEY = _b('original')
        cache = self._makeOne()
        original = self._makePersist(oid=KEY)
        cache[KEY] = original
        cache[KEY] = original

    def test___setitem___duplicate_oid_raises_ValueError(self):
        from persistent._compat import _b
        KEY = _b('original')
        cache = self._makeOne()
        original = self._makePersist(oid=KEY)
        cache[KEY] = original
        duplicate = self._makePersist(oid=KEY)

        try:
            cache[KEY] = duplicate
        except ValueError:
            pass
        else:
            self.fail("Didn't raise KeyError with duplicate OID.")

    def test___setitem___ghost(self):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('ghost')
        cache = self._makeOne()
        ghost = self._makePersist(state=GHOST, oid=KEY)

        cache[KEY] = ghost

        self.assertEqual(len(cache), 1)
        items = list(cache.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(_len(cache.klass_items()), 0)
        self.assertEqual(items[0][0], KEY)
        self.assertEqual(cache.ringlen(), 0)
        self.assertTrue(items[0][1] is ghost)
        self.assertTrue(cache[KEY] is ghost)

    def test___setitem___mismatch_key_oid(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('uptodate')
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE)

        try:
            cache[KEY] = uptodate
        except ValueError:
            pass
        else:
            self.fail("Didn't raise ValueError when the key didn't match the OID")


    def test___setitem___non_ghost(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('uptodate')
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE, oid=KEY)

        cache[KEY] = uptodate

        self.assertEqual(len(cache), 1)
        items = list(cache.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(_len(cache.klass_items()), 0)
        self.assertEqual(items[0][0], KEY)
        self.assertEqual(cache.ringlen(), 1)
        self.assertTrue(items[0][1] is uptodate)
        self.assertTrue(cache[KEY] is uptodate)
        self.assertTrue(cache.get(KEY) is uptodate)

    def test___setitem___persistent_class(self):
        from persistent._compat import _b
        KEY = _b('pclass')
        class pclass(object):
            _p_oid = KEY
        cache = self._makeOne()

        cache[KEY] = pclass

        kitems = list(cache.klass_items())
        self.assertEqual(len(cache), 1)
        self.assertEqual(_len(cache.items()), 0)
        self.assertEqual(len(kitems), 1)
        self.assertEqual(kitems[0][0], KEY)
        self.assertTrue(kitems[0][1] is pclass)
        self.assertTrue(cache[KEY] is pclass)
        self.assertTrue(cache.get(KEY) is pclass)

    def test___delitem___non_string_oid_raises_TypeError(self):
        cache = self._makeOne()

        try:
            del cache[object()]
        except TypeError:
            pass
        else:
            self.fail("Didn't raise ValueError with non-string OID.")

    def test___delitem___nonesuch_raises_KeyError(self):
        from persistent._compat import _b
        cache = self._makeOne()
        original = self._makePersist()

        try:
            del cache[_b('nonesuch')]
        except KeyError:
            pass
        else:
            self.fail("Didn't raise KeyError with nonesuch OID.")

    def test___delitem___w_persistent_class(self):
        from persistent._compat import _b
        KEY = _b('pclass')
        cache = self._makeOne()
        class pclass(object):
            _p_oid = KEY
        cache = self._makeOne()

        cache[KEY] = pclass
        del cache[KEY]
        self.assertTrue(cache.get(KEY, self) is self)
        self.assertFalse(KEY in cache.persistent_classes)
        self.assertEqual(cache.ringlen(), 0)

    def test___delitem___w_normal_object(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('uptodate')
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE, oid=KEY)

        cache[KEY] = uptodate

        del cache[KEY]
        self.assertTrue(cache.get(KEY, self) is self)

    def test___delitem___w_ghost(self):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        cache = self._makeOne()
        KEY = _b('ghost')
        ghost = self._makePersist(state=GHOST, oid=KEY)

        cache[KEY] = ghost

        del cache[KEY]
        self.assertTrue(cache.get(KEY, self) is self)

    def test___delitem___w_remaining_object(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        REMAINS = _b('remains')
        UPTODATE = _b('uptodate')
        remains = self._makePersist(state=UPTODATE, oid=REMAINS)
        uptodate = self._makePersist(state=UPTODATE, oid=UPTODATE)

        cache[REMAINS] = remains
        cache[UPTODATE] = uptodate

        del cache[UPTODATE]
        self.assertTrue(cache.get(UPTODATE, self) is self)
        self.assertTrue(cache.get(REMAINS, self) is remains)

    def test_lruitems(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid='two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], TWO)
        self.assertEqual(items[2][0], THREE)

    def test_mru_nonesuch_raises_KeyError(self):
        cache = self._makeOne()
        from persistent._compat import _b
        self.assertRaises(KeyError, cache.mru, _b('nonesuch'))

    def test_mru_normal(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid='two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], TWO)

    def test_mru_ghost(self):
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        two = cache[TWO] = self._makePersist(oid='two', state=GHOST)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 2)
        items = cache.lru_items()
        self.assertEqual(_len(items), 2)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)

    def test_mru_was_ghost_now_active(self):
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        two = cache[TWO] = self._makePersist(oid='two', state=GHOST)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        two._p_state = UPTODATE
        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], TWO)

    def test_mru_first(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid='two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        cache.mru(ONE)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], TWO)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], ONE)

    def test_mru_last(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        ONE = _b('one')
        TWO = _b('two')
        THREE = _b('three')
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid='one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid='two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid='three', state=UPTODATE)

        cache.mru(THREE)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], TWO)
        self.assertEqual(items[2][0], THREE)

    def test_incrgc_simple(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 10)
        items = cache.lru_items()
        self.assertEqual(_len(items), 10)
        self.assertEqual(items[0][0], _b('oid_0090'))
        self.assertEqual(items[1][0], _b('oid_0091'))
        self.assertEqual(items[2][0], _b('oid_0092'))
        self.assertEqual(items[3][0], _b('oid_0093'))
        self.assertEqual(items[4][0], _b('oid_0094'))
        self.assertEqual(items[5][0], _b('oid_0095'))
        self.assertEqual(items[6][0], _b('oid_0096'))
        self.assertEqual(items[7][0], _b('oid_0097'))
        self.assertEqual(items[8][0], _b('oid_0098'))
        self.assertEqual(items[9][0], _b('oid_0099'))

        for oid in oids[:90]:
            self.assertTrue(cache.get(oid) is None)

        for oid in oids[90:]:
            self.assertFalse(cache.get(oid) is None)

    def test_incrgc_w_smaller_drain_resistance(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        cache.drain_resistance = 2
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()

        self.assertEqual(cache.cache_non_ghost_count, 10)

    def test_incrgc_w_larger_drain_resistance(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        cache.drain_resistance = 2
        cache.cache_size = 90
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()

        self.assertEqual(cache.cache_non_ghost_count, 49)

    def test_full_sweep(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        for oid in oids:
            self.assertTrue(cache.get(oid) is None)

    def test_full_sweep_w_sticky(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import STICKY
        from persistent._compat import _b
        cache = self._makeOne()
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            state = UPTODATE if i > 0 else STICKY
            cache[oid] = self._makePersist(oid=oid, state=state)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 1)

        self.assertTrue(cache.get(oids[0]) is not None)
        for oid in oids[1:]:
            self.assertTrue(cache.get(oid) is None)

    def test_full_sweep_w_changed(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import CHANGED
        from persistent._compat import _b
        cache = self._makeOne()
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            state = UPTODATE if i > 0 else CHANGED
            cache[oid] = self._makePersist(oid=oid, state=state)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 1)

        self.assertTrue(cache.get(oids[0]) is not None)
        for oid in oids[1:]:
            self.assertTrue(cache.get(oid) is None)

    def test_minimize(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.minimize()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        for oid in oids:
            self.assertTrue(cache.get(oid) is None)

    def test_minimize_turns_into_ghosts(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        cache = self._makeOne()
        oid = _b('oid_%04d' % 1)
        obj = cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 1)

        cache.minimize()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        self.assertEqual(obj._p_state, GHOST)

    def test_new_ghost_non_persistent_object(self):
        from persistent._compat import _b
        cache = self._makeOne()
        self.assertRaises(AttributeError, cache.new_ghost, _b('123'), object())

    def test_new_ghost_obj_already_has_oid(self):
        from persistent._compat import _b
        from persistent.interfaces import GHOST
        candidate = self._makePersist(oid=_b('123'), state=GHOST)
        cache = self._makeOne()
        self.assertRaises(ValueError, cache.new_ghost, _b('123'), candidate)

    def test_new_ghost_obj_already_has_jar(self):
        from persistent._compat import _b
        class Dummy(object):
            _p_oid = None
            _p_jar = object()
        cache = self._makeOne()
        candidate = self._makePersist(oid=None, jar=object())
        self.assertRaises(ValueError, cache.new_ghost, _b('123'), candidate)

    def test_new_ghost_obj_already_in_cache(self):
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid=KEY)
        cache[KEY] = candidate
        # Now, normally we can't get in the cache without an oid and jar
        # (the C implementation doesn't allow it), so if we try to create
        # a ghost, we get the value error
        self.assertRaises(ValueError, cache.new_ghost, KEY, candidate)
        candidate._p_oid = None
        self.assertRaises(ValueError, cache.new_ghost, KEY, candidate)
        # if we're sneaky and remove the OID and jar, then we get the duplicate
        # key error
        candidate._p_jar = None
        self.assertRaises(KeyError, cache.new_ghost, KEY, candidate)

    def test_new_ghost_success_already_ghost(self):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid=None, jar=None)
        cache.new_ghost(KEY, candidate)
        self.assertTrue(cache.get(KEY) is candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_jar, cache.jar)
        self.assertEqual(candidate._p_state, GHOST)

    def test_new_ghost_success_not_already_ghost(self):
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid=None, jar=None, state=UPTODATE)
        cache.new_ghost(KEY, candidate)
        self.assertTrue(cache.get(KEY) is candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_jar, cache.jar)
        self.assertEqual(candidate._p_state, GHOST)

    def test_new_ghost_w_pclass_non_ghost(self):
        from persistent._compat import _b
        KEY = _b('123')
        class Pclass(object):
            _p_oid = None
            _p_jar = None
        cache = self._makeOne()
        cache.new_ghost(KEY, Pclass)
        self.assertTrue(cache.get(KEY) is Pclass)
        self.assertTrue(cache.persistent_classes[KEY] is Pclass)
        self.assertEqual(Pclass._p_oid, KEY)
        self.assertEqual(Pclass._p_jar, cache.jar)

    def test_new_ghost_w_pclass_ghost(self):
        from persistent._compat import _b
        KEY = _b('123')
        class Pclass(object):
            _p_oid = None
            _p_jar = None
        cache = self._makeOne()
        cache.new_ghost(KEY, Pclass)
        self.assertTrue(cache.get(KEY) is Pclass)
        self.assertTrue(cache.persistent_classes[KEY] is Pclass)
        self.assertEqual(Pclass._p_oid, KEY)
        self.assertEqual(Pclass._p_jar, cache.jar)

    def test_reify_miss_single(self):
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        self.assertRaises(KeyError, cache.reify, KEY)

    def test_reify_miss_multiple(self):
        from persistent._compat import _b
        KEY = _b('123')
        KEY2 = _b('456')
        cache = self._makeOne()
        self.assertRaises(KeyError, cache.reify, [KEY, KEY2])

    def test_reify_hit_single_ghost(self):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('123')
        from persistent.interfaces import UPTODATE
        cache = self._makeOne()
        candidate = self._makePersist(oid=KEY, jar=cache.jar, state=GHOST)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 0)
        cache.reify(KEY)
        self.assertEqual(cache.ringlen(), 1)
        items = cache.lru_items()
        self.assertEqual(items[0][0], KEY)
        self.assertTrue(items[0][1] is candidate)
        self.assertEqual(candidate._p_state, UPTODATE)

    def test_reify_hit_single_non_ghost(self):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid=KEY, jar=cache.jar, state=UPTODATE)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 1)
        cache.reify(KEY)
        self.assertEqual(cache.ringlen(), 1)
        self.assertEqual(candidate._p_state, UPTODATE)

    def test_reify_hit_multiple_mixed(self):
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('123')
        KEY2 = _b('456')
        cache = self._makeOne()
        c1 = self._makePersist(oid=KEY, jar=cache.jar, state=GHOST)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=cache.jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 1)
        cache.reify([KEY, KEY2])
        self.assertEqual(cache.ringlen(), 2)
        self.assertEqual(c1._p_state, UPTODATE)
        self.assertEqual(c2._p_state, UPTODATE)

    def test_invalidate_miss_single(self):
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        cache.invalidate(KEY) # doesn't raise

    def test_invalidate_miss_multiple(self):
        from persistent._compat import _b
        KEY = _b('123')
        KEY2 = _b('456')
        cache = self._makeOne()
        cache.invalidate([KEY, KEY2]) # doesn't raise

    def test_invalidate_hit_single_ghost(self):
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid='123', jar=cache.jar, state=GHOST)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 0)
        cache.invalidate(KEY)
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(candidate._p_state, GHOST)

    def test_invalidate_hit_single_non_ghost(self):
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('123')
        cache = self._makeOne()
        candidate = self._makePersist(oid='123', jar=cache.jar, state=UPTODATE)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 1)
        cache.invalidate(KEY)
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(candidate._p_state, GHOST)

    def test_invalidate_hit_multiple_mixed(self):
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('123')
        KEY2 = _b('456')
        cache = self._makeOne()
        c1 = self._makePersist(oid=KEY, jar=cache.jar, state=GHOST)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=cache.jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 1)
        cache.invalidate([KEY, KEY2])
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(c1._p_state, GHOST)
        self.assertEqual(c2._p_state, GHOST)

    def test_invalidate_hit_multiple_non_ghost(self):
        from persistent.interfaces import UPTODATE
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('123')
        KEY2 = _b('456')
        cache = self._makeOne()
        c1 = self._makePersist(oid=KEY, jar=cache.jar, state=UPTODATE)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=cache.jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 2)
        # These should be in the opposite order of how they were
        # added to the ring to ensure ring traversal works
        cache.invalidate([KEY2, KEY])
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(c1._p_state, GHOST)
        self.assertEqual(c2._p_state, GHOST)

    def test_invalidate_hit_pclass(self):
        from persistent._compat import _b
        KEY = _b('123')
        class Pclass(object):
            _p_oid = KEY
            _p_jar = None
        cache = self._makeOne()
        cache[KEY] = Pclass
        self.assertTrue(cache.persistent_classes[KEY] is Pclass)
        cache.invalidate(KEY)
        self.assertFalse(KEY in cache.persistent_classes)

    def test_debug_info_w_persistent_class(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('pclass')
        class pclass(object):
            _p_oid = KEY
        cache = self._makeOne()
        pclass._p_state = UPTODATE
        cache[KEY] = pclass

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        oid, refc, typ, state = info[0]
        self.assertEqual(oid, KEY)
        self.assertEqual(refc, len(gc.get_referents(pclass)))
        self.assertEqual(typ, 'type')
        self.assertEqual(state, UPTODATE)

    def test_debug_info_w_normal_object(self):
        import gc
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        KEY = _b('uptodate')
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE, oid=KEY)
        cache[KEY] = uptodate

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        oid, refc, typ, state = info[0]
        self.assertEqual(oid, KEY)
        self.assertEqual(refc, len(gc.get_referents(uptodate)))
        self.assertEqual(typ, 'DummyPersistent')
        self.assertEqual(state, UPTODATE)


    def test_debug_info_w_ghost(self):
        import gc
        from persistent.interfaces import GHOST
        from persistent._compat import _b
        KEY = _b('ghost')
        cache = self._makeOne()
        ghost = self._makePersist(state=GHOST, oid=KEY)
        cache[KEY] = ghost

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        oid, refc, typ, state = info[0]
        self.assertEqual(oid, KEY)
        self.assertEqual(refc, len(gc.get_referents(ghost)))
        self.assertEqual(typ, 'DummyPersistent')
        self.assertEqual(state, GHOST)

    def test_init_with_cacheless_jar(self):
        # Sometimes ZODB tests pass objects that don't
        # have a _cache
        class Jar(object):
            was_set = False
            def __setattr__(self, name, value):
                if name == '_cache':
                    object.__setattr__(self, 'was_set', True)
                raise AttributeError(name)

        jar = Jar()
        self._makeOne(jar)
        self.assertTrue(jar.was_set)

    def test_setting_non_persistent_item(self):
        cache = self._makeOne()
        try:
            cache[None] = object()
        except TypeError as e:
            self.assertEqual(str(e), "Cache values must be persistent objects.")
        else:
            self.fail("Should raise TypeError")

    def test_setting_without_jar(self):
        cache = self._makeOne()
        p = self._makePersist(jar=None)
        try:
            cache[p._p_oid] = p
        except ValueError as e:
            self.assertEqual(str(e), "Cached object jar missing")
        else:
            self.fail("Should raise ValueError")

    def test_setting_already_cached(self):
        cache1 = self._makeOne()
        p = self._makePersist(jar=cache1.jar)

        cache1[p._p_oid] = p

        cache2 = self._makeOne()
        try:
            cache2[p._p_oid] = p
        except ValueError as e:
            self.assertEqual(str(e), "Object already in another cache")
        else:
            self.fail("Should raise value error")

    def test_cannot_update_mru_while_already_locked(self):
        cache = self._makeOne()
        cache._is_sweeping_ring = True

        updated = cache.mru(None)
        self.assertFalse(updated)

    def test_update_object_size_estimation_simple(self):
        cache = self._makeOne()
        p = self._makePersist(jar=cache.jar)

        cache[p._p_oid] = p
        # The cache accesses the private attribute directly to bypass
        # the bit conversion.
        # Note that the _p_estimated_size is set *after*
        # the update call is made in ZODB's serialize
        p._Persistent__size = 0

        cache.update_object_size_estimation(p._p_oid, 2)

        self.assertEqual(cache.total_estimated_size, 64)

        # A missing object does nothing
        cache.update_object_size_estimation(None, 2)
        self.assertEqual(cache.total_estimated_size, 64)

    def test_cache_size(self):
        size = 42
        cache = self._makeOne(target_size=size)
        self.assertEqual(cache.cache_size, size)

        cache.cache_size = 64
        self.assertEqual(cache.cache_size, 64)

    def test_sweep_empty(self):
        cache = self._makeOne()
        self.assertEqual(cache.incrgc(), 0)

    def test_sweep_of_non_deactivating_object(self):
        cache = self._makeOne()
        p = self._makePersist(jar=cache.jar)

        p._p_state = 0 # non-ghost, get in the ring
        cache[p._p_oid] = p


        def bad_deactivate():
            "Doesn't call super, for it's own reasons, so can't be ejected"
            return

        p._p_deactivate = bad_deactivate

        import persistent.picklecache
        sweep_types = persistent.picklecache._SWEEPABLE_TYPES
        persistent.picklecache._SWEEPABLE_TYPES = DummyPersistent
        try:
            self.assertEqual(cache.full_sweep(), 0)
        finally:
            persistent.picklecache._SWEEPABLE_TYPES = sweep_types

        del p._p_deactivate
        self.assertEqual(cache.full_sweep(), 1)

    if _is_jython:
        def with_deterministic_gc(f):
            def test(self):
                old_flags = gc.getMonitorGlobal()
                gc.setMonitorGlobal(True)
                try:
                    f(self, force_collect=True)
                finally:
                    gc.setMonitorGlobal(old_flags)
            return test
    else:
        def with_deterministic_gc(f):
            return f

    @with_deterministic_gc
    def test_cache_garbage_collection_bytes_also_deactivates_object(self, force_collect=_is_pypy or _is_jython):
        from persistent.interfaces import UPTODATE
        from persistent._compat import _b
        cache = self._makeOne()
        cache.cache_size = 1000
        oids = []
        for i in range(100):
            oid = _b('oid_%04d' % i)
            oids.append(oid)
            o = cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
            o._Persistent__size = 0 # must start 0, ZODB sets it AFTER updating the size
            cache.update_object_size_estimation(oid, 64)
            o._Persistent__size = 2

            # mimic what the real persistent object does to update the cache
            # size; if we don't get deactivated by sweeping, the cache size
            # won't shrink so this also validates that _p_deactivate gets
            # called when ejecting an object.
            o._p_deactivate = lambda: cache.update_object_size_estimation(oid, -1)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        # A GC at this point does nothing
        cache.incrgc()
        self.assertEqual(cache.cache_non_ghost_count, 100)
        self.assertEqual(len(cache), 100)

        # Now if we set a byte target:

        cache.cache_size_bytes = 1
        # verify the change worked as expected
        self.assertEqual(cache.cache_size_bytes, 1)
        # verify our entrance assumption is fulfilled
        self.assertTrue(cache.cache_size > 100)
        self.assertTrue(cache.total_estimated_size > 1)
        # A gc shrinks the bytes
        cache.incrgc()
        self.assertEqual(cache.total_estimated_size, 0)

        # It also shrank the measured size of the cache;
        # this would fail under PyPy if _SWEEP_NEEDS_GC was False
        if force_collect:
            gc.collect()
        self.assertEqual(len(cache), 1)

    def test_invalidate_persistent_class_calls_p_invalidate(self):
        from persistent._compat import _b
        KEY = _b('pclass')
        class pclass(object):
            _p_oid = KEY
            invalidated = False
            @classmethod
            def _p_invalidate(cls):
                cls.invalidated = True


        cache = self._makeOne()

        cache[KEY] = pclass

        cache.invalidate(KEY)

        self.assertTrue(pclass.invalidated)

    def test_ring_impl(self):
        from .. import ring

        if _is_pypy or os.getenv('USING_CFFI'):
            self.assertTrue(ring.Ring is ring._CFFIRing)
        else:
            self.assertTrue(ring.Ring is ring._DequeRing)

class DummyPersistent(object):

    def _p_invalidate(self):
        from persistent.interfaces import GHOST
        self._p_state = GHOST

    _p_deactivate = _p_invalidate

    def _p_invalidate_deactivate_helper(self, clear=True):
        self._p_invalidate()

    def _p_activate(self):
        from persistent.interfaces import UPTODATE
        self._p_state = UPTODATE


class DummyConnection:
    pass


def _len(seq):
    return len(list(seq))

def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(PickleCacheTests),
        ))

if __name__ == '__main__':
    unittest.main()
