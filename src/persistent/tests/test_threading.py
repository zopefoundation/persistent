"""Tests for concurrent access to persistent objects and the pickle cache.

These tests exercise the C extensions under multi-threaded conditions,
particularly to verify the free-threaded Python (3.14t+) fixes:

- Per_dealloc refcount resurrection to prevent infinite recursion
  when PyDict_GetItem INCREFs/DECREFs stolen-reference objects
- Cache dict operations that internally INCREF/DECREF values

The tests are also valuable on standard (GIL) Python to catch
concurrency issues with greenlets or signal handlers.
"""

import gc
import struct
import threading
from unittest import TestCase

from persistent.tests.utils import skipIfNoCExtension


def _make_oid(n):
    return struct.pack(">Q", n)


@skipIfNoCExtension
class ConcurrentCacheTests(TestCase):
    """Test concurrent access to the C PickleCache."""

    def _getTargetClass(self):
        from persistent.cPickleCache import PickleCache
        return PickleCache

    def _makePersistentClass(self):
        from persistent import Persistent

        class P(Persistent):
            pass

        return P

    def _makeJar(self):
        jar = _DummyJar()
        jar._cache = self._getTargetClass()(jar, 100)
        jar.cache = jar._cache
        return jar

    def _addObjects(self, jar, start, count):
        """Add `count` persistent objects to jar, starting at oid `start`."""
        P = self._makePersistentClass()
        objects = []
        for i in range(start, start + count):
            obj = P()
            obj._p_oid = _make_oid(i)
            obj._p_jar = jar
            jar._cache[obj._p_oid] = obj
            objects.append(obj)
        return objects

    def test_concurrent_object_creation_and_deletion(self):
        """Multiple threads creating and deleting objects in the cache."""
        jar = self._makeJar()
        errors = []
        n_threads = 4
        n_objects = 200

        def worker(thread_id):
            try:
                start = thread_id * n_objects
                objs = self._addObjects(jar, start, n_objects)
                # Drop references so GC can collect them
                del objs
                gc.collect()
            except Exception as e:
                errors.append((thread_id, e))

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")

    def test_concurrent_ghost_creation_and_gc(self):
        """Threads create ghost objects while GC runs concurrently.

        This is the scenario that triggered the infinite recursion in
        Per_dealloc on free-threaded Python: ghost objects have stolen
        (uncounted) references in the cache dict, and GC triggers
        deallocation that calls cc_oid_unreferenced -> PyDict_GetItem,
        which INCREFs/DECREFs the value internally.
        """
        jar = self._makeJar()
        errors = []
        barrier = threading.Barrier(3)

        def creator(thread_id):
            try:
                barrier.wait(timeout=5)
                for cycle in range(50):
                    start = thread_id * 10000 + cycle * 100
                    objs = self._addObjects(jar, start, 100)
                    # Make them all ghosts by deactivating
                    for obj in objs:
                        obj._p_deactivate()
                    del objs
            except Exception as e:
                errors.append((thread_id, e))

        def collector():
            try:
                barrier.wait(timeout=5)
                for _ in range(100):
                    gc.collect()
            except Exception as e:
                errors.append(("gc", e))

        threads = [
            threading.Thread(target=creator, args=(0,)),
            threading.Thread(target=creator, args=(1,)),
            threading.Thread(target=collector),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")

    def test_concurrent_incrgc(self):
        """Cache.incrgc() running while objects are added/removed."""
        jar = self._makeJar()
        errors = []
        stop = threading.Event()

        def adder():
            try:
                i = 0
                while not stop.is_set():
                    objs = self._addObjects(jar, i, 50)
                    for obj in objs:
                        obj._p_deactivate()
                    del objs
                    i += 50
            except Exception as e:
                errors.append(("adder", e))

        def gc_runner():
            try:
                for _ in range(200):
                    jar._cache.incrgc()
            except Exception as e:
                errors.append(("gc_runner", e))
            finally:
                stop.set()

        threads = [
            threading.Thread(target=adder),
            threading.Thread(target=gc_runner),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")

    def test_concurrent_minimize(self):
        """Cache.minimize() running concurrently with object access."""
        jar = self._makeJar()
        errors = []
        # Pre-populate
        objs = self._addObjects(jar, 0, 500)
        for obj in objs:
            obj._p_changed = True  # activate
            obj._p_changed = False  # mark as clean/uptodate
        del objs

        stop = threading.Event()

        def accessor():
            try:
                while not stop.is_set():
                    for oid_num in range(500):
                        oid = _make_oid(oid_num)
                        obj = jar._cache.get(oid)
                        if obj is not None:
                            # Touch to simulate access
                            try:
                                obj._p_activate()
                            except Exception:
                                pass  # object may have been evicted
            except Exception as e:
                errors.append(("accessor", e))

        def minimizer():
            try:
                for _ in range(50):
                    jar._cache.minimize()
            except Exception as e:
                errors.append(("minimizer", e))
            finally:
                stop.set()

        threads = [
            threading.Thread(target=accessor),
            threading.Thread(target=minimizer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")

    def test_concurrent_cache_clear_during_access(self):
        """Clearing the entire cache while threads access objects."""
        jar = self._makeJar()
        errors = []

        def populate_and_clear(cycle):
            try:
                start = cycle * 200
                objs = self._addObjects(jar, start, 200)
                for obj in objs:
                    obj._p_changed = True
                    obj._p_changed = False
                del objs
                jar._cache.full_sweep()
            except Exception as e:
                errors.append((cycle, e))

        threads = [
            threading.Thread(target=populate_and_clear, args=(i,))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")

    def test_rapid_create_destroy_cycle(self):
        """Rapidly create and destroy objects to stress refcount handling.

        On free-threaded Python, this exercises the Py_SET_REFCNT
        resurrection in Per_dealloc that prevents recursive deallocation
        during cache dict cleanup.
        """
        jar = self._makeJar()
        errors = []
        n_threads = 4
        n_cycles = 100

        def worker(thread_id):
            try:
                P = self._makePersistentClass()
                for cycle in range(n_cycles):
                    oid = _make_oid(thread_id * n_cycles + cycle)
                    obj = P()
                    obj._p_oid = oid
                    obj._p_jar = jar
                    jar._cache[oid] = obj
                    # Immediately drop and collect
                    del obj
                    gc.collect()
            except Exception as e:
                errors.append((thread_id, e))

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive(), "Thread hung")
        self.assertEqual(errors, [], f"Errors in threads: {errors}")


class _DummyJar:
    """Minimal jar for threading tests.

    Implements just enough for PickleCache and Persistent to work.
    """

    def __init__(self):
        self._registered = []

    def register(self, obj):
        self._registered.append(obj)

    def setstate(self, obj):
        # Trivial: just mark as up-to-date
        pass
