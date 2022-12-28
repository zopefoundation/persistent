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
import unittest

from persistent.interfaces import UPTODATE
from persistent._compat import PYPY
from persistent.tests.utils import skipIfNoCExtension


# pylint:disable=protected-access,too-many-lines,too-many-public-methods
# pylint:disable=attribute-defined-outside-init,redefined-outer-name

_marker = object()

class DummyPersistent:
    _Persistent__ring = None

    def _p_invalidate(self):
        from persistent.interfaces import GHOST
        self._p_state = GHOST

    _p_deactivate = _p_invalidate

    def _p_invalidate_deactivate_helper(self, clear=True):
        self._p_invalidate()

    def _p_activate(self):
        self._p_state = UPTODATE


class DummyConnection:
    pass


class ClosedConnection(DummyConnection):
    def __init__(self, test):
        self.test = test

    def setstate(self, obj): # pragma: no cover
        self.test.fail("Connection is closed")

    def register(self, obj):
        """Does nothing."""

def _len(seq):
    return len(list(seq))


class PickleCacheTestMixin:

    # py2/3 compat
    assertRaisesRegex = getattr(unittest.TestCase,
                                'assertRaisesRegex',
                                unittest.TestCase.assertRaisesRegexp)

    def _getTargetClass(self):
        from persistent.picklecache import PickleCachePy as BasePickleCache
        class PickleCache(BasePickleCache):
            _CACHEABLE_TYPES = BasePickleCache._CACHEABLE_TYPES + (DummyPersistent,)
        return PickleCache

    def _getTargetInterface(self):
        from persistent.interfaces import IPickleCache
        return IPickleCache

    def _makeOne(self, jar=None, target_size=10):
        if jar is None:
            jar = DummyConnection()
        return self._getTargetClass()(jar, target_size)

    def _getDummyPersistentClass(self):
        return DummyPersistent

    def _getRealPersistentClass(self):
        from persistent.persistence import PersistentPy
        return PersistentPy

    def _makePersist(self, state=None, oid=b'foo', jar=_marker, kind=_marker):
        from persistent.interfaces import GHOST

        if state is None:
            state = GHOST
        if jar is _marker:
            jar = DummyConnection()
        kind = self._getDummyPersistentClass() if kind is _marker else kind
        persist = kind()
        try:
            persist._p_state = state
        except AttributeError:
            pass
        persist._p_oid = oid
        persist._p_jar = jar
        return persist

    def test_class_conforms_to_IPickleCache(self):
        from zope.interface.verify import verifyClass
        verifyClass(self._getTargetInterface(), self._getTargetClass())

    def test_instance_conforms_to_IPickleCache(self):
        from zope.interface.verify import verifyObject
        verifyObject(self._getTargetInterface(), self._makeOne())

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

        self.assertIs(cache.get('nonesuch', default), default)

    def test___setitem___non_string_oid_raises_TypeError(self):
        cache = self._makeOne()

        with self.assertRaises(TypeError):
            cache[object()] = self._makePersist()

    def test___setitem___duplicate_oid_same_obj(self):

        KEY = b'original'
        cache = self._makeOne()
        original = self._makePersist(oid=KEY)
        cache[KEY] = original
        cache[KEY] = original

    def test___setitem___duplicate_oid_raises_ValueError(self):

        KEY = b'original'
        cache = self._makeOne()
        original = self._makePersist(oid=KEY)
        cache[KEY] = original
        duplicate = self._makePersist(oid=KEY)

        with self.assertRaises(ValueError):
            cache[KEY] = duplicate

    def test___setitem___ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'ghost'
        cache = self._makeOne()
        ghost = self._makePersist(state=GHOST, oid=KEY)

        cache[KEY] = ghost

        self.assertEqual(len(cache), 1)
        items = list(cache.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(_len(cache.klass_items()), 0)
        self.assertEqual(items[0][0], KEY)
        self.assertIs(items[0][1], ghost)
        self.assertIs(cache[KEY], ghost)
        return cache

    def test___setitem___mismatch_key_oid(self):
        KEY = b'uptodate'
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE)

        with self.assertRaises(ValueError):
            cache[KEY] = uptodate


    def test___setitem___non_ghost(self):
        KEY = b'uptodate'
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

        KEY = b'pclass'
        class pclass:
            _p_oid = KEY
            _p_jar = DummyConnection()
        cache = self._makeOne(pclass._p_jar)

        cache[KEY] = pclass

        kitems = list(cache.klass_items())
        self.assertEqual(len(cache), 1)
        self.assertEqual(len(kitems), 1)
        self.assertEqual(kitems[0][0], KEY)
        self.assertIs(kitems[0][1], pclass)
        self.assertIs(cache[KEY], pclass)
        self.assertIs(cache.get(KEY), pclass)
        return cache

    def test___delitem___non_string_oid_raises_TypeError(self):
        cache = self._makeOne()

        with self.assertRaises(TypeError):
            del cache[object()]

    def test___delitem___nonesuch_raises_KeyError(self):

        cache = self._makeOne()

        with self.assertRaises(KeyError):
            del cache[b'nonesuch']

    def test___delitem___w_persistent_class(self):

        KEY = b'pclass'
        cache = self._makeOne()
        class pclass:
            _p_oid = KEY
            _p_jar = DummyConnection()
        cache = self._makeOne()

        cache[KEY] = pclass
        del cache[KEY]
        self.assertIs(cache.get(KEY, self), self)
        self.assertEqual(cache.ringlen(), 0)
        return cache, KEY

    def test___delitem___w_normal_object(self):
        KEY = b'uptodate'
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE, oid=KEY)

        cache[KEY] = uptodate

        del cache[KEY]
        self.assertTrue(cache.get(KEY, self) is self)

    def test___delitem___w_ghost(self):
        from persistent.interfaces import GHOST

        cache = self._makeOne()
        KEY = b'ghost'
        ghost = self._makePersist(state=GHOST, oid=KEY)

        cache[KEY] = ghost

        del cache[KEY]
        self.assertTrue(cache.get(KEY, self) is self)

    def test___delitem___w_remaining_object(self):
        cache = self._makeOne()
        REMAINS = b'remains'
        UPTODATE = b'uptodate'
        remains = self._makePersist(state=UPTODATE, oid=REMAINS)
        uptodate = self._makePersist(state=UPTODATE, oid=UPTODATE)

        cache[REMAINS] = remains
        cache[UPTODATE] = uptodate

        del cache[UPTODATE]
        self.assertTrue(cache.get(UPTODATE, self) is self)
        self.assertTrue(cache.get(REMAINS, self) is remains)

    def test_lruitems(self):
        cache = self._makeOne()
        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid=b'two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], TWO)
        self.assertEqual(items[2][0], THREE)


    def _numbered_oid(self, i):
        return b'oid_%04d' % i

    def _populate_cache(self, cache, count=100,
                        state_0=UPTODATE,
                        state_rest=UPTODATE):

        oids = []
        for i in range(100):
            oid = self._numbered_oid(i)
            oids.append(oid)
            state = state_0 if i == 0 else state_rest
            cache[oid] = self._makePersist(oid=oid, state=state)
        return oids

    def test_incrgc_simple(self):
        cache = self._makeOne()
        oids = self._populate_cache(cache)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 10)
        items = cache.lru_items()
        self.assertEqual(_len(items), 10)
        self.assertEqual(items[0][0], b'oid_0090')
        self.assertEqual(items[1][0], b'oid_0091')
        self.assertEqual(items[2][0], b'oid_0092')
        self.assertEqual(items[3][0], b'oid_0093')
        self.assertEqual(items[4][0], b'oid_0094')
        self.assertEqual(items[5][0], b'oid_0095')
        self.assertEqual(items[6][0], b'oid_0096')
        self.assertEqual(items[7][0], b'oid_0097')
        self.assertEqual(items[8][0], b'oid_0098')
        self.assertEqual(items[9][0], b'oid_0099')

        for oid in oids[:90]:
            self.assertIsNone(cache.get(oid))

        for oid in oids[90:]:
            self.assertIsNotNone(cache.get(oid))

    def test_incrgc_w_smaller_drain_resistance(self):
        cache = self._makeOne()
        cache.cache_drain_resistance = 2
        self._populate_cache(cache)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()

        self.assertEqual(cache.cache_non_ghost_count, 10)

    def test_incrgc_w_larger_drain_resistance(self):
        cache = self._makeOne()
        cache.cache_drain_resistance = 2
        cache.cache_size = 90
        self._populate_cache(cache)

        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.incrgc()

        self.assertEqual(cache.cache_non_ghost_count, 49)

    def test_full_sweep(self):
        cache = self._makeOne()
        oids = self._populate_cache(cache)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        for oid in oids:
            self.assertTrue(cache.get(oid) is None)

    def test_full_sweep_clears_weakrefs_in_interface(self, sweep_method='full_sweep'):
        # https://github.com/zopefoundation/persistent/issues/149
        # Sweeping the cache clears weak refs (for PyPy especially)
        # In the real world, this shows up in the interaction with
        # persistent objects and zope.interface/zope.component,
        # so we use an Interface to demonstrate. This helps find issues
        # like needing to run GC more than once, etc, because of how the
        # object is referenced.
        from zope.interface import Interface

        gc.disable()
        self.addCleanup(gc.enable)

        jar = ClosedConnection(self)
        cache = self._makeOne(jar, 0)

        # Make a persistent object, put it in the cache as saved
        class P(self._getRealPersistentClass()):
            "A real persistent object that can be weak referenced"

        p = P()
        p._p_jar = jar
        p._p_oid = b'\x01' * 8
        cache[p._p_oid] = p
        p._p_changed = False

        # Now, take a weak reference to it from somewhere far away.
        Interface.subscribe(p)

        # Remove the original object
        del p

        # Sweep the cache.
        getattr(cache, sweep_method)()

        # Now, try to use that weak reference. If the weak reference is
        # still around, this will raise the error about the connection
        # being closed.
        Interface.changed(None)

    def test_incrgc_clears_weakrefs_in_interface(self):
        self.test_full_sweep_clears_weakrefs_in_interface(sweep_method='incrgc')

    def test_full_sweep_clears_weakrefs(self, sweep_method='incrgc'):
        # like test_full_sweep_clears_weakrefs_in_interface,
        # but directly using a weakref. This is the simplest version of the test.
        from weakref import ref as WeakRef
        gc.disable()
        self.addCleanup(gc.enable)

        jar = ClosedConnection(self)
        cache = self._makeOne(jar, 0)

        # Make a persistent object, put it in the cache as saved
        class P(self._getRealPersistentClass()):
            """A real persistent object that can be weak referenced."""

        p = P()
        p._p_jar = jar
        p._p_oid = b'\x01' * 8
        cache[p._p_oid] = p
        p._p_changed = False

        # Now, take a weak reference to it
        ref = WeakRef(p)

        # Remove the original object
        del p

        # Sweep the cache.
        getattr(cache, sweep_method)()

        # Now, try to use that weak reference; it should be gone.
        p = ref()
        self.assertIsNone(p)

    def test_incrgc_clears_weakrefs(self):
        self.test_full_sweep_clears_weakrefs(sweep_method='incrgc')

    def test_minimize(self):
        cache = self._makeOne()
        oids = self._populate_cache(cache)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.minimize()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        for oid in oids:
            self.assertTrue(cache.get(oid) is None)

    def test_minimize_turns_into_ghosts(self):
        from persistent.interfaces import GHOST

        cache = self._makeOne()
        oid = self._numbered_oid(1)
        obj = cache[oid] = self._makePersist(oid=oid, state=UPTODATE)
        self.assertEqual(cache.cache_non_ghost_count, 1)

        cache.minimize()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 0)

        self.assertEqual(obj._p_state, GHOST)

    def test_new_ghost_non_persistent_object(self):

        cache = self._makeOne()
        with self.assertRaises((AttributeError, TypeError)):
            cache.new_ghost(b'123', object())

    def test_new_ghost_obj_already_has_oid(self):

        from persistent.interfaces import GHOST
        candidate = self._makePersist(oid=b'123', state=GHOST)
        cache = self._makeOne()
        with self.assertRaises(ValueError):
            cache.new_ghost(b'123', candidate)

    def test_new_ghost_obj_already_has_jar(self):
        cache = self._makeOne()
        candidate = self._makePersist(oid=None, jar=object())
        with self.assertRaises(ValueError):
            cache.new_ghost(b'123', candidate)

    def test_new_ghost_obj_already_in_cache(self):
        KEY = b'123'
        cache = self._makeOne()
        candidate = self._makePersist(oid=KEY)
        cache[KEY] = candidate
        # Now, normally we can't get in the cache without an oid and jar
        # (the C implementation doesn't allow it), so if we try to create
        # a ghost, we get the value error
        self.assertRaises(ValueError, cache.new_ghost, KEY, candidate)
        return cache, KEY, candidate

    def test_new_ghost_success_already_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        candidate = self._makePersist(oid=None, jar=None)
        cache.new_ghost(KEY, candidate)
        self.assertTrue(cache.get(KEY) is candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_jar, jar)
        self.assertEqual(candidate._p_state, GHOST)

    def test_new_ghost_success_not_already_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        candidate = self._makePersist(oid=None, jar=None, state=UPTODATE)
        cache.new_ghost(KEY, candidate)
        self.assertTrue(cache.get(KEY) is candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_jar, jar)
        self.assertEqual(candidate._p_state, GHOST)

    def test_new_ghost_w_pclass_non_ghost(self):
        KEY = b'123'
        class Pclass:
            _p_oid = None
            _p_jar = None
        cache = self._makeOne()
        cache.new_ghost(KEY, Pclass)
        self.assertTrue(cache.get(KEY) is Pclass)
        self.assertEqual(Pclass._p_oid, KEY)
        return cache, Pclass, KEY

    def test_new_ghost_w_pclass_ghost(self):
        KEY = b'123'
        class Pclass:
            _p_oid = None
            _p_jar = None
        cache = self._makeOne()
        cache.new_ghost(KEY, Pclass)
        self.assertTrue(cache.get(KEY) is Pclass)
        self.assertEqual(Pclass._p_oid, KEY)
        return cache, Pclass, KEY

    def test_invalidate_miss_single(self):
        KEY = b'123'
        cache = self._makeOne()
        cache.invalidate(KEY) # doesn't raise

    def test_invalidate_miss_multiple(self):
        KEY = b'123'
        KEY2 = b'456'
        cache = self._makeOne()
        cache.invalidate([KEY, KEY2]) # doesn't raise

    def test_invalidate_hit_single_non_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        candidate = self._makePersist(oid=b'123', jar=jar, state=UPTODATE)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 1)
        cache.invalidate(KEY)
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(candidate._p_state, GHOST)

    def test_invalidate_hit_multiple_non_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        KEY2 = b'456'
        jar = DummyConnection()
        cache = self._makeOne()
        c1 = self._makePersist(oid=KEY, jar=jar, state=UPTODATE)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 2)
        # These should be in the opposite order of how they were
        # added to the ring to ensure ring traversal works
        cache.invalidate([KEY2, KEY])
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(c1._p_state, GHOST)
        self.assertEqual(c2._p_state, GHOST)

    def test_debug_info_w_persistent_class(self):
        KEY = b'pclass'
        class pclass:
            _p_oid = KEY
            _p_jar = DummyConnection()
        cache = self._makeOne(pclass._p_jar)
        pclass._p_state = UPTODATE
        cache[KEY] = pclass

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        # C and Python return different length tuples,
        # and the refcounts are off by one.
        oid = info[0][0]
        typ = info[0][2]

        self.assertEqual(oid, KEY)
        self.assertEqual(typ, 'type')

        return pclass, info[0]

    def test_debug_info_w_normal_object(self):
        KEY = b'uptodate'
        cache = self._makeOne()
        uptodate = self._makePersist(state=UPTODATE, oid=KEY)
        cache[KEY] = uptodate

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        # C and Python return different length tuples,
        # and the refcounts are off by one.
        oid = info[0][0]
        typ = info[0][2]
        self.assertEqual(oid, KEY)
        self.assertEqual(typ, type(uptodate).__name__)
        return uptodate, info[0]


    def test_debug_info_w_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'ghost'
        cache = self._makeOne()
        ghost = self._makePersist(state=GHOST, oid=KEY)
        cache[KEY] = ghost

        gc.collect() # pypy vs. refcounting
        info = cache.debug_info()

        self.assertEqual(len(info), 1)
        oid, _refc, typ, state = info[0]
        self.assertEqual(oid, KEY)
        self.assertEqual(typ, type(ghost).__name__)
        # In the C implementation, we couldn't actually set the _p_state
        # directly.
        self.assertEqual(state, ghost._p_state)
        return ghost, info[0]

    def test_setting_non_persistent_item(self):
        cache = self._makeOne()
        with self.assertRaisesRegex(TypeError,
                                    "Cache values must be persistent objects."):
            cache[b'12345678'] = object()

    def test_setting_without_jar(self):
        cache = self._makeOne()
        p = self._makePersist(jar=None)
        with self.assertRaisesRegex(ValueError,
                                    "Cached object jar missing"):
            cache[p._p_oid] = p

    def test_setting_already_cached(self):
        jar = DummyConnection()
        cache1 = self._makeOne(jar)
        p = self._makePersist(jar=jar)

        cache1[p._p_oid] = p

        cache2 = self._makeOne()
        with self.assertRaisesRegex(ValueError,
                                    "Cache values may only be in one cache"):
            cache2[p._p_oid] = p

    def test_cache_size(self):
        size = 42
        cache = self._makeOne(target_size=size)
        self.assertEqual(cache.cache_size, size)

        cache.cache_size = 64
        self.assertEqual(cache.cache_size, 64)

    def test_sweep_empty(self):
        cache = self._makeOne()
        # Python returns 0, C returns None
        self.assertFalse(cache.incrgc())

    def test_invalidate_persistent_class_calls_p_invalidate(self):
        KEY = b'pclass'
        class pclass:
            _p_oid = KEY
            _p_jar = DummyConnection()
            invalidated = False
            @classmethod
            def _p_invalidate(cls):
                cls.invalidated = True


        cache = self._makeOne(pclass._p_jar)

        cache[KEY] = pclass

        cache.invalidate(KEY)

        self.assertTrue(pclass.invalidated)

    def test_cache_raw(self):
        raw = self._makePersist(kind=self._getRealPersistentClass())
        cache = self._makeOne(raw._p_jar)

        cache[raw._p_oid] = raw
        self.assertEqual(1, len(cache))
        self.assertIs(cache.get(raw._p_oid), raw)

        del raw
        self.assertEqual(1, len(cache))


class PythonPickleCacheTests(PickleCacheTestMixin, unittest.TestCase):
    # Tests that depend on the implementation details of the
    # Python PickleCache and the Python persistent object.
    # Anything that involves directly setting the _p_state of a persistent
    # object has to be here, we can't do that in the C implementation.

    def _getTargetInterface(self):
        from persistent.interfaces import IExtendedPickleCache
        return IExtendedPickleCache

    def test_sweep_of_non_deactivating_object(self):
        jar = DummyConnection()
        cache = self._makeOne(jar)
        p = self._makePersist(jar=jar)

        p._p_state = 0 # non-ghost, get in the ring
        cache[p._p_oid] = p

        def bad_deactivate():
            "Doesn't call super, for it's own reasons, so can't be ejected"


        p._p_deactivate = bad_deactivate

        cache._SWEEPABLE_TYPES = DummyPersistent
        self.assertEqual(cache.full_sweep(), 0)
        del cache._SWEEPABLE_TYPES

        del p._p_deactivate
        self.assertEqual(cache.full_sweep(), 1)

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

    def test_reify_miss_single(self):
        KEY = b'123'
        cache = self._makeOne()
        self.assertRaises(KeyError, cache.reify, KEY)

    def test_reify_miss_multiple(self):
        KEY = b'123'
        KEY2 = b'456'
        cache = self._makeOne()
        self.assertRaises(KeyError, cache.reify, [KEY, KEY2])

    def test_reify_hit_single_non_ghost(self):
        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        candidate = self._makePersist(oid=KEY, jar=jar, state=UPTODATE)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 1)
        cache.reify(KEY)
        self.assertEqual(cache.ringlen(), 1)
        self.assertEqual(candidate._p_state, UPTODATE)

    def test_cannot_update_mru_while_already_locked(self):
        cache = self._makeOne()
        cache._is_sweeping_ring = True

        updated = cache.mru(None)
        self.assertFalse(updated)

    def test___delitem___w_persistent_class(self):
        cache, key = super().test___delitem___w_persistent_class()
        self.assertNotIn(key, cache.persistent_classes)

    def test___setitem___ghost(self):
        cache = super().test___setitem___ghost()
        self.assertEqual(cache.ringlen(), 0)

    def test___setitem___persistent_class(self):
        cache = super().test___setitem___persistent_class()
        self.assertEqual(_len(cache.items()), 0)

    def test_new_ghost_w_pclass_non_ghost(self):
        cache, Pclass, key = super().test_new_ghost_w_pclass_non_ghost()
        self.assertEqual(Pclass._p_jar, cache.jar)
        self.assertIs(cache.persistent_classes[key], Pclass)

    def test_new_ghost_w_pclass_ghost(self):
        cache, Pclass, key = super().test_new_ghost_w_pclass_ghost()
        self.assertEqual(Pclass._p_jar, cache.jar)
        self.assertIs(cache.persistent_classes[key], Pclass)

    def test_mru_nonesuch_raises_KeyError(self):
        cache = self._makeOne()

        self.assertRaises(KeyError, cache.mru, b'nonesuch')

    def test_mru_normal(self):
        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid=b'two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], TWO)

    def test_mru_ghost(self):
        from persistent.interfaces import GHOST

        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        two = cache[TWO] = self._makePersist(oid=b'two', state=GHOST)
        # two must live to survive gc
        self.assertIsNotNone(two)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 2)
        items = cache.lru_items()
        self.assertEqual(_len(items), 2)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)

    def test_mru_was_ghost_now_active(self):
        from persistent.interfaces import GHOST

        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        two = cache[TWO] = self._makePersist(oid=b'two', state=GHOST)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        two._p_state = UPTODATE
        cache.mru(TWO)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], TWO)

    def test_mru_first(self):
        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid=b'two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        cache.mru(ONE)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], TWO)
        self.assertEqual(items[1][0], THREE)
        self.assertEqual(items[2][0], ONE)

    def test_mru_last(self):
        ONE = b'one'
        TWO = b'two'
        THREE = b'three'
        cache = self._makeOne()
        cache[ONE] = self._makePersist(oid=b'one', state=UPTODATE)
        cache[TWO] = self._makePersist(oid=b'two', state=UPTODATE)
        cache[THREE] = self._makePersist(oid=b'three', state=UPTODATE)

        cache.mru(THREE)

        self.assertEqual(cache.ringlen(), 3)
        items = cache.lru_items()
        self.assertEqual(_len(items), 3)
        self.assertEqual(items[0][0], ONE)
        self.assertEqual(items[1][0], TWO)
        self.assertEqual(items[2][0], THREE)

    def test_invalidate_hit_pclass(self):
        KEY = b'123'
        class Pclass:
            _p_oid = KEY
            _p_jar = DummyConnection()
        cache = self._makeOne(Pclass._p_jar)
        cache[KEY] = Pclass
        self.assertIs(cache.persistent_classes[KEY], Pclass)
        cache.invalidate(KEY)
        self.assertNotIn(KEY, cache.persistent_classes)

    def test_debug_info_w_normal_object(self):
        obj, info = super().test_debug_info_w_normal_object()
        self.assertEqual(info[1], len(gc.get_referents(obj)))
        self.assertEqual(info[3], UPTODATE)

    def test_debug_info_w_ghost(self):
        ghost, info = super().test_debug_info_w_ghost()
        self.assertEqual(info[1], len(gc.get_referents(ghost)))

    def test_debug_info_w_persistent_class(self):
        pclass, info = super().test_debug_info_w_persistent_class()
        self.assertEqual(info[3], UPTODATE)
        self.assertEqual(info[1], len(gc.get_referents(pclass)))

    def test_full_sweep_w_sticky(self):
        from persistent.interfaces import STICKY

        cache = self._makeOne()
        oids = self._populate_cache(cache, state_0=STICKY)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 1)

        self.assertTrue(cache.get(oids[0]) is not None)
        for oid in oids[1:]:
            self.assertTrue(cache.get(oid) is None)

    def test_full_sweep_w_changed(self):
        from persistent.interfaces import CHANGED

        cache = self._makeOne()
        oids = self._populate_cache(cache, state_0=CHANGED)
        self.assertEqual(cache.cache_non_ghost_count, 100)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring

        self.assertEqual(cache.cache_non_ghost_count, 1)

        self.assertTrue(cache.get(oids[0]) is not None)
        for oid in oids[1:]:
            self.assertTrue(cache.get(oid) is None)

    def test_init_with_cacheless_jar(self):
        # Sometimes ZODB tests pass objects that don't
        # have a _cache
        class Jar:
            was_set = False
            def __setattr__(self, name, value):
                if name == '_cache':
                    object.__setattr__(self, 'was_set', True)
                raise AttributeError(name)

        jar = Jar()
        self._makeOne(jar)
        self.assertTrue(jar.was_set)

    def test_invalidate_hit_multiple_mixed(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        KEY2 = b'456'
        jar = DummyConnection()
        cache = self._makeOne()
        c1 = self._makePersist(oid=KEY, jar=jar, state=GHOST)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 1)
        cache.invalidate([KEY, KEY2])
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(c1._p_state, GHOST)
        self.assertEqual(c2._p_state, GHOST)

    def test_invalidate_hit_single_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        candidate = self._makePersist(oid=b'123', jar=jar, state=GHOST)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 0)
        cache.invalidate(KEY)
        self.assertEqual(cache.ringlen(), 0)
        self.assertEqual(candidate._p_state, GHOST)

    def test_reify_hit_multiple_mixed(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        KEY2 = b'456'
        jar = DummyConnection()
        cache = self._makeOne(jar)
        c1 = self._makePersist(oid=KEY, jar=jar, state=GHOST)
        cache[KEY] = c1
        c2 = self._makePersist(oid=KEY2, jar=jar, state=UPTODATE)
        cache[KEY2] = c2
        self.assertEqual(cache.ringlen(), 1)
        cache.reify([KEY, KEY2])
        self.assertEqual(cache.ringlen(), 2)
        self.assertEqual(c1._p_state, UPTODATE)
        self.assertEqual(c2._p_state, UPTODATE)

    def test_reify_hit_single_ghost(self):
        from persistent.interfaces import GHOST

        KEY = b'123'
        jar = DummyConnection()
        cache = self._makeOne()
        candidate = self._makePersist(oid=KEY, jar=jar, state=GHOST)
        cache[KEY] = candidate
        self.assertEqual(cache.ringlen(), 0)
        cache.reify(KEY)
        self.assertEqual(cache.ringlen(), 1)
        items = cache.lru_items()
        self.assertEqual(items[0][0], KEY)
        self.assertTrue(items[0][1] is candidate)
        self.assertEqual(candidate._p_state, UPTODATE)

    def test_cache_garbage_collection_bytes_also_deactivates_object(self):

        class MyPersistent(self._getDummyPersistentClass()):
            def _p_deactivate(self):
                # mimic what the real persistent object does to update the cache
                # size; if we don't get deactivated by sweeping, the cache size
                # won't shrink so this also validates that _p_deactivate gets
                # called when ejecting an object.
                cache.update_object_size_estimation(self._p_oid, -1)

        cache = self._makeOne()
        cache.cache_size = 1000
        oids = []
        for i in range(100):
            oid = self._numbered_oid(i)
            oids.append(oid)
            o = cache[oid] = self._makePersist(oid=oid, kind=MyPersistent, state=UPTODATE)

            o._Persistent__size = 0 # must start 0, ZODB sets it AFTER updating the size

            cache.update_object_size_estimation(oid, 64)
            o._Persistent__size = 2

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

        # It also shrank the measured size of the cache,
        # though this may require a GC to be visible.
        if PYPY: # pragma: no cover
            gc.collect()
        self.assertEqual(len(cache), 1)


    def test_new_ghost_obj_already_in_cache(self):
        base_result = super().test_new_ghost_obj_already_in_cache()
        cache, key, candidate = base_result
        # If we're sneaky and remove the OID and jar, then we get the duplicate
        # key error. Removing them only works because we're not using a real
        # persistent object.
        candidate._p_oid = None
        self.assertRaises(ValueError, cache.new_ghost, key, candidate)

        candidate._p_jar = None
        self.assertRaises(KeyError, cache.new_ghost, key, candidate)

    def test_cache_garbage_collection_bytes_with_cache_size_0(self):

        class MyPersistent(self._getDummyPersistentClass()):
            def _p_deactivate(self):
                # mimic what the real persistent object does to update
                # the cache size; if we don't get deactivated by
                # sweeping, the cache size won't shrink so this also
                # validates that _p_deactivate gets called when
                # ejecting an object.
                cache.update_object_size_estimation(self._p_oid, -1)

        cache = self._makeOne()
        cache.cache_size = 0
        cache.cache_size_bytes = 400
        oids = []
        for i in range(100):
            oid = self._numbered_oid(i)
            oids.append(oid)
            o = cache[oid] = self._makePersist(oid=oid,
                                               kind=MyPersistent,
                                               state=UPTODATE)
            # must start 0, ZODB sets it AFTER updating the size
            o._Persistent__size = 0
            cache.update_object_size_estimation(oid, 1)
            o._Persistent__size = 1
            del o # leave it only in the cache

        self.assertEqual(cache.cache_non_ghost_count, 100)
        self.assertEqual(cache.total_estimated_size, 64 * 100)

        cache.incrgc()
        gc.collect() # banish the ghosts who are no longer in the ring
        self.assertEqual(cache.total_estimated_size, 64 * 6)
        self.assertEqual(cache.cache_non_ghost_count, 6)
        self.assertEqual(len(cache), 6)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring
        self.assertEqual(cache.total_estimated_size, 0)
        self.assertEqual(cache.cache_non_ghost_count, 0)
        self.assertEqual(len(cache), 0)

    def test_interpreter_finalization_ffi_cleanup(self):
        # When the interpreter is busy garbage collecting old objects
        # and clearing their __dict__ in random orders, the CFFI cleanup
        # ``ffi.gc()`` cleanup hooks we use on CPython don't
        # raise errors.
        #
        # Prior to Python 3.8, when ``sys.unraisablehook`` was added,
        # the only way to know if this test fails is to look for AttributeError
        # on stderr.
        #
        # But wait, it gets worse. Prior to https://foss.heptapod.net/pypy/cffi/-/issues/492
        # (CFFI > 1.14.5, unreleased at this writing), CFFI ignores
        # ``sys.unraisablehook``, so even on 3.8 the only way to know
        # a failure is to watch stderr.
        #
        # See https://github.com/zopefoundation/persistent/issues/150

        import sys
        unraised = []
        try:
            old_hook = sys.unraisablehook
        except AttributeError:
            pass
        else: # pragma: no cover
            sys.unraisablehook = unraised.append
            self.addCleanup(setattr, sys, 'unraisablehook', old_hook)

        cache = self._makeOne()
        oid = self._numbered_oid(42)
        o = cache[oid] = self._makePersist(oid=oid)
        # Clear the dict, or at least part of it.
        # This is coupled to ``cleanup_hook``
        if cache.data.cleanup_hook:
            del cache.data._addr_to_oid
        del cache[oid]

        self.assertEqual(unraised, [])


@skipIfNoCExtension
class CPickleCacheTests(PickleCacheTestMixin, unittest.TestCase):

    def _getTargetClass(self):
        from persistent._compat import _c_optimizations_available as get_c
        return get_c()['persistent.picklecache'].PickleCache

    def _getRealPersistentClass(self):
        from persistent._compat import _c_optimizations_available as get_c
        return get_c()['persistent.persistence'].Persistent

    def _getDummyPersistentClass(self):
        class DummyPersistent(self._getRealPersistentClass()):
            __slots__ = ()
        return DummyPersistent

    def test_inst_does_not_conform_to_IExtendedPickleCache(self):
        # Test that ``@use_c_impl`` is only applying the correct
        # interface declaration to the C implementation.
        from persistent.interfaces import IExtendedPickleCache
        from zope.interface.verify import verifyObject
        from zope.interface.exceptions import Invalid
        # We don't claim to implement it.
        self.assertFalse(IExtendedPickleCache.providedBy(self._makeOne()))
        # And we don't even provide everything it asks for.
        # (Exact error depends on version of zope.interface and what we
        # fail to implement. 5.0 probably raises MultipleInvalid).
        with self.assertRaises(Invalid):
            verifyObject(IExtendedPickleCache, self._makeOne(), tentative=True)

    def test___setitem___persistent_class(self):
        cache = super().test___setitem___persistent_class()
        self.assertEqual(_len(cache.items()), 1)

    def test_cache_garbage_collection_bytes_with_cache_size_0(self):

        class DummyConnection:
            def register(self, obj):
                pass

        dummy_connection = DummyConnection()
        dummy_connection.register(1) # for coveralls

        def makePersistent(oid):
            persist = self._getDummyPersistentClass()()
            persist._p_oid = oid
            persist._p_jar = dummy_connection
            return persist

        cache = self._getTargetClass()(dummy_connection)
        dummy_connection._cache = cache

        cache.cache_size = 0
        cache.cache_size_bytes = 400

        oids = []
        for i in range(100):
            oid = self._numbered_oid(i)
            oids.append(oid)
            o = cache[oid] = makePersistent(oid)
            cache.update_object_size_estimation(oid, 1)
            o._p_estimated_size = 1
            del o # leave it only in the cache

        self.assertEqual(cache.cache_non_ghost_count, 100)
        self.assertEqual(cache.total_estimated_size, 64 * 100)

        cache.incrgc()
        self.assertEqual(cache.total_estimated_size, 64 * 6)
        self.assertEqual(cache.cache_non_ghost_count, 6)
        self.assertEqual(len(cache), 6)

        cache.full_sweep()
        gc.collect() # banish the ghosts who are no longer in the ring
        self.assertEqual(cache.total_estimated_size, 0)
        self.assertEqual(cache.cache_non_ghost_count, 0)
        self.assertEqual(len(cache), 0)


class TestWeakValueDictionary(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.picklecache import _WeakValueDictionary
        return _WeakValueDictionary

    def _makeOne(self):
        return self._getTargetClass()()

    @unittest.skipIf(PYPY, "PyPy doesn't have the cleanup_hook")
    def test_cleanup_hook_gc(self):
        # A more targeted test than ``test_interpreter_finalization_ffi_cleanup``
        # See https://github.com/zopefoundation/persistent/issues/150
        wvd = self._makeOne()

        class cdata:
            o = object()
            pobj_id = id(o)
        wvd['key'] = cdata.o

        wvd.__dict__.clear()
        wvd.cleanup_hook(cdata)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main()
