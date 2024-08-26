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
from weakref import WeakValueDictionary

from zope.interface import classImplements
from zope.interface import implementer

from persistent._compat import PYPY
from persistent._compat import use_c_impl
from persistent.interfaces import GHOST
from persistent.interfaces import OID_TYPE
from persistent.interfaces import UPTODATE
from persistent.interfaces import IExtendedPickleCache
from persistent.interfaces import IPickleCache
from persistent.persistence import PersistentPy
from persistent.persistence import _estimated_size_in_24_bits
from persistent.ring import Ring


__all__ = [
    'PickleCache',
    'PickleCachePy',
]

_OGA = object.__getattribute__
_OSA = object.__setattr__


def _sweeping_ring(f):
    # A decorator for functions in the PickleCache
    # that are sweeping the entire ring (mutating it);
    # serves as a pseudo-lock to not mutate the ring further
    # in other functions
    def locked(self, *args, **kwargs):
        self._is_sweeping_ring = True
        try:
            return f(self, *args, **kwargs)
        finally:
            self._is_sweeping_ring = False
    return locked


class _WeakValueDictionary:
    # Maps from OID -> Persistent object, but only weakly references the
    # Persistent object. This is similar to ``weakref.WeakValueDictionary``,
    # but is customized depending on the platform. On PyPy, all objects can
    # cheaply use a WeakRef, so that's what we actually use. On CPython,
    # though, ``PersistentPy`` cannot be weakly referenced, so we rely on the
    # fact that the ``id()`` of an object is its memory location, and we use
    # ``ctypes`` to cast that integer back to the object.
    #
    # To remove stale addresses, we rely on the ``ffi.gc()`` object with the
    # exact same lifetime as the ``PersistentPy`` object. It calls us, we get
    # the ``id`` back out of the CData, and clean up.
    if PYPY:  # pragma: no cover
        def __init__(self):
            self._data = WeakValueDictionary()

        def _from_addr(self, addr):
            return addr

        def _save_addr(self, oid, obj):
            return obj

        cleanup_hook = None
    else:
        def __init__(self):
            # careful not to require ctypes at import time; most likely the
            # C implementation is in use.
            import ctypes

            self._data = {}
            self._addr_to_oid = {}
            self._cast = ctypes.cast
            self._py_object = ctypes.py_object

        def _save_addr(self, oid, obj):
            i = id(obj)
            self._addr_to_oid[i] = oid
            return i

        def _from_addr(self, addr):
            return self._cast(addr, self._py_object).value

        def cleanup_hook(self, cdata):
            # This is called during GC, possibly at interpreter shutdown
            # when the __dict__ of this object may have already been cleared.
            try:
                addr_to_oid = self._addr_to_oid
            except AttributeError:
                return
            oid = addr_to_oid.pop(cdata.pobj_id, None)
            self._data.pop(oid, None)

    def __contains__(self, oid):
        return oid in self._data

    def __len__(self):
        return len(self._data)

    def __setitem__(self, key, value):
        addr = self._save_addr(key, value)
        self._data[key] = addr

    def pop(self, oid):
        return self._from_addr(self._data.pop(oid))

    def items(self):
        from_addr = self._from_addr
        for oid, addr in self._data.items():
            yield oid, from_addr(addr)

    def get(self, oid, default=None):
        addr = self._data.get(oid, self)
        if addr is self:
            return default
        return self._from_addr(addr)

    def __getitem__(self, oid):
        addr = self._data[oid]
        return self._from_addr(addr)


@use_c_impl
# We actually implement IExtendedPickleCache, but
# the C version does not, and our interface declarations are
# copied over by the decorator. So we make the declaration
# of IExtendedPickleCache later.
@implementer(IPickleCache)
class PickleCache:

    # Tests may modify this to add additional types
    _CACHEABLE_TYPES = (type, PersistentPy)
    _SWEEPABLE_TYPES = (PersistentPy,)

    total_estimated_size = 0
    cache_size_bytes = 0

    # Set by functions that sweep the entire ring (via _sweeping_ring)
    # Serves as a pseudo-lock
    _is_sweeping_ring = False

    def __init__(self, jar, target_size=0, cache_size_bytes=0):
        # TODO: forward-port Dieter's bytes stuff
        self.jar = jar
        # We expect the jars to be able to have a pointer to
        # us; this is a reference cycle, but certain
        # aspects of invalidation and accessing depend on it.
        # The actual Connection objects we're used with do set this
        # automatically, but many test objects don't.
        # TODO: track this on the persistent objects themself?
        try:
            jar._cache = self
        except AttributeError:
            # Some ZODB tests pass in an object that cannot have an _cache
            pass
        self.cache_size = target_size
        self.drain_resistance = 0
        self.non_ghost_count = 0
        self.persistent_classes = {}
        self.data = _WeakValueDictionary()
        self.ring = Ring(self.data.cleanup_hook)
        self.cache_size_bytes = cache_size_bytes

    # IPickleCache API
    def __len__(self):
        """ See IPickleCache.
        """
        return (len(self.persistent_classes) +
                len(self.data))

    def __getitem__(self, oid):
        """ See IPickleCache.
        """
        value = self.data.get(oid, self)
        if value is not self:
            return value
        return self.persistent_classes[oid]

    def __setitem__(self, oid, value):
        """ See IPickleCache.
        """
        # The order of checks matters for C compatibility;
        # the ZODB tests depend on this

        # The C impl requires either a type or a Persistent subclass
        if not isinstance(value, self._CACHEABLE_TYPES):
            raise TypeError("Cache values must be persistent objects.")

        value_oid = value._p_oid
        if not isinstance(
                oid,
                OID_TYPE) or not isinstance(
                value_oid,
                OID_TYPE):
            raise TypeError(
                'OID must be {}: key={} _p_oid={}'.format(
                    OID_TYPE, oid, value_oid))

        if value_oid != oid:
            raise ValueError("Cache key does not match oid")

        if oid in self.persistent_classes or oid in self.data:
            # Have to be careful here, a GC might have just run
            # and cleaned up the object
            existing_data = self.get(oid)
            if existing_data is not None and existing_data is not value:
                # Raise the same type of exception as the C impl with the same
                # message.
                raise ValueError('A different object already has the same oid')
        # Match the C impl: it requires a jar. Let this raise AttributeError
        # if no jar is found.
        jar = value._p_jar
        if jar is None:
            raise ValueError("Cached object jar missing")
        # It also requires that it cannot be cached more than one place
        existing_cache = getattr(jar, '_cache', None)  # type: PickleCache
        if (existing_cache is not None
                and existing_cache is not self
                and oid in existing_cache.data):
            raise ValueError("Cache values may only be in one cache.")

        if isinstance(value, type):  # ZODB.persistentclass.PersistentMetaClass
            self.persistent_classes[oid] = value
        else:
            self.data[oid] = value
            if _OGA(value, '_p_state') != GHOST and value not in self.ring:
                self.ring.add(value)
                self.non_ghost_count += 1
            elif self.data.cleanup_hook:
                # Ensure we begin monitoring for ``value`` to
                # be deallocated.
                self.ring.ring_node_for(value)

    def __delitem__(self, oid):
        """ See IPickleCache.
        """
        if not isinstance(oid, OID_TYPE):
            raise TypeError(f'OID must be {OID_TYPE}: {oid}')
        if oid in self.persistent_classes:
            del self.persistent_classes[oid]
        else:
            pobj = self.data.pop(oid)
            self.ring.delete(pobj)

    def get(self, oid, default=None):
        """ See IPickleCache.
        """
        value = self.data.get(oid, self)
        if value is not self:
            return value
        return self.persistent_classes.get(oid, default)

    def mru(self, oid):
        """ See IPickleCache.
        """
        if self._is_sweeping_ring:
            # accessess during sweeping, such as with an
            # overridden _p_deactivate, don't mutate the ring
            # because that could leave it inconsistent
            return False  # marker return for tests

        value = self.data[oid]

        was_in_ring = value in self.ring
        if not was_in_ring:
            if _OGA(value, '_p_state') != GHOST:
                self.ring.add(value)
                self.non_ghost_count += 1
        else:
            self.ring.move_to_head(value)
        return None

    def ringlen(self):
        """ See IPickleCache.
        """
        return len(self.ring)

    def items(self):
        """ See IPickleCache.
        """
        return self.data.items()

    def lru_items(self):
        """ See IPickleCache.
        """
        return [
            (obj._p_oid, obj)
            for obj in self.ring
        ]

    def klass_items(self):
        """ See IPickleCache.
        """
        return self.persistent_classes.items()

    def incrgc(self, ignored=None):
        """ See IPickleCache.
        """
        target = self.cache_size
        if self.drain_resistance >= 1:
            size = self.non_ghost_count
            target2 = size - 1 - (size // self.drain_resistance)
            if target2 < target:
                target = target2
        # return value for testing
        return self._sweep(target, self.cache_size_bytes)

    def full_sweep(self, target=None):
        """ See IPickleCache.
        """
        # return value for testing
        return self._sweep(0)

    minimize = full_sweep

    def new_ghost(self, oid, obj):
        """ See IPickleCache.
        """
        if obj._p_oid is not None:
            raise ValueError('Object already has oid')
        if obj._p_jar is not None:
            raise ValueError('Object already has jar')
        if oid in self.persistent_classes or oid in self.data:
            raise KeyError('Duplicate OID: %s' % oid)
        obj._p_oid = oid
        obj._p_jar = self.jar
        if not isinstance(obj, type):
            if obj._p_state != GHOST:
                # The C implementation sets this stuff directly,
                # but we delegate to the class. However, we must be
                # careful to avoid broken _p_invalidate and _p_deactivate
                # that don't call the super class. See ZODB's
                # testConnection.doctest_proper_ghost_initialization_with_empty__p_deactivate
                obj._p_invalidate_deactivate_helper(False)
        self[oid] = obj

    def reify(self, to_reify):
        """ See IPickleCache.
        """
        if isinstance(to_reify, OID_TYPE):  # bytes
            to_reify = [to_reify]
        for oid in to_reify:
            value = self[oid]
            if value._p_state == GHOST:
                value._p_activate()
                self.non_ghost_count += 1
                self.mru(oid)

    def invalidate(self, to_invalidate):
        """ See IPickleCache.
        """
        if isinstance(to_invalidate, OID_TYPE):
            self._invalidate(to_invalidate)
        else:
            for oid in to_invalidate:
                self._invalidate(oid)

    def debug_info(self):
        result = []
        for oid, klass in self.persistent_classes.items():
            result.append((
                oid,
                len(gc.get_referents(klass)),
                type(klass).__name__,
                klass._p_state,
            ))
        for oid, value in self.data.items():
            result.append((
                oid,
                len(gc.get_referents(value)),
                type(value).__name__,
                value._p_state,
            ))
        return result

    def update_object_size_estimation(self, oid, new_size):
        """ See IPickleCache.
        """
        value = self.data.get(oid)

        if value is not None:
            # Recall that while the argument is given in bytes,
            # we have to work with 64-block chunks (plus one)
            # to match the C implementation. Hence the convoluted
            # arithmetic
            new_size_in_24 = _estimated_size_in_24_bits(new_size)
            p_est_size_in_24 = value._Persistent__size
            new_est_size_in_bytes = (new_size_in_24 - p_est_size_in_24) * 64

            self.total_estimated_size += new_est_size_in_bytes

    cache_drain_resistance = property(
        lambda self: self.drain_resistance,
        lambda self, nv: setattr(self, 'drain_resistance', nv)
    )
    cache_non_ghost_count = property(lambda self: self.non_ghost_count)
    cache_data = property(lambda self: dict(self.items()))
    cache_klass_count = property(lambda self: len(self.persistent_classes))

    # Helpers

    # Set to true when a deactivation happens in our code. For
    # compatibility with the C implementation, we can only remove the
    # node and decrement our non-ghost count if our implementation
    # actually runs (broken subclasses can forget to call super; ZODB
    # has tests for this). This gets set to false everytime we examine
    # a node and checked afterwards. The C implementation has a very
    # incestuous relationship between cPickleCache and cPersistence:
    # the pickle cache calls _p_deactivate, which is responsible for
    # both decrementing the non-ghost count and removing its node from
    # the cache ring (and, if it gets deallocated, from the pickle
    # cache's dictionary). We're trying to keep that to a minimum, but
    # there's no way around it if we want full compatibility.
    _persistent_deactivate_ran = False

    @_sweeping_ring
    def _sweep(self, target, target_size_bytes=0):
        ejected = 0
        # If we find and eject objects that may have been weak referenced, we
        # need to run a garbage collection to try to clear those references.
        # Otherwise, it's highly likely that accessing those objects through
        # those references will try to ``_p_activate()`` them, and since the
        # jar they came from is probably closed, that will lead to an error.
        # See https://github.com/zopefoundation/persistent/issues/149
        had_weak_refs = False
        ring = self.ring
        for node, value in ring.iteritems():
            if ((target or target_size_bytes)
                    and (not target or self.non_ghost_count <= target)
                    and (self.total_estimated_size <= target_size_bytes
                         or not target_size_bytes)):
                break

            if value._p_state == UPTODATE:
                # The C implementation will only evict things that are
                # specifically in the up-to-date state
                self._persistent_deactivate_ran = False

                # sweeping an object out of the cache should also
                # ghost it---that's what C does. This winds up
                # calling `update_object_size_estimation`.
                # Also in C, if this was the last reference to the object,
                # it removes itself from the `data` dictionary.
                # If we're under PyPy or Jython, we need to run a GC collection
                # to make this happen...this is only noticeable though, when we
                # eject objects. Also, note that we can only take any of these
                # actions if our _p_deactivate ran, in case of buggy
                # subclasses. see _persistent_deactivate_ran.

                if not had_weak_refs:
                    had_weak_refs |= getattr(
                        value, '__weakref__', None) is not None

                value._p_deactivate()
                if (self._persistent_deactivate_ran
                        # Test-cases sneak in non-Persistent objects, sigh, so
                        # naturally they don't cooperate (without this check a
                        # bunch of test_picklecache breaks)
                        or not isinstance(value, self._SWEEPABLE_TYPES)):
                    ring.delete_node(node)
                    ejected += 1
                    self.non_ghost_count -= 1

        if ejected and had_weak_refs:
            # Clear the iteration variables, so the objects they point to
            # are subject to GC.
            node = None
            value = None
            gc.collect()
        return ejected

    @_sweeping_ring
    def _invalidate(self, oid):
        value = self.data.get(oid)
        if value is not None and value._p_state != GHOST:
            value._p_invalidate()
            self.ring.delete(value)
            self.non_ghost_count -= 1
        elif oid in self.persistent_classes:
            persistent_class = self.persistent_classes.pop(oid)
            try:
                # ZODB.persistentclass.PersistentMetaClass objects
                # have this method and it must be called for transaction abort
                # and other forms of invalidation to work
                persistent_class._p_invalidate()
            except AttributeError:
                pass


# This name is bound by the ``@use_c_impl`` decorator to the class defined
# above. We make sure and list it statically, though, to help out linters.
PickleCachePy = PickleCachePy  # noqa: F821 undefined name 'PickleCachePy'
classImplements(PickleCachePy, IExtendedPickleCache)
