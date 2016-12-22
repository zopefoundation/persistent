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
import weakref


from zope.interface import implementer

from persistent.interfaces import GHOST
from persistent.interfaces import IPickleCache
from persistent.interfaces import OID_TYPE
from persistent.interfaces import UPTODATE
from persistent.persistence import Persistent
from persistent.persistence import _estimated_size_in_24_bits

# Tests may modify this to add additional types
_CACHEABLE_TYPES = (type, Persistent)
_SWEEPABLE_TYPES = (Persistent,)

# On Jython, we need to explicitly ask it to monitor
# objects if we want a more deterministic GC
if hasattr(gc, 'monitorObject'): # pragma: no cover
    _gc_monitor = gc.monitorObject
else:
    def _gc_monitor(o):
        pass

_OGA = object.__getattribute__

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

from .ring import Ring

@implementer(IPickleCache)
class PickleCache(object):

    total_estimated_size = 0
    cache_size_bytes = 0

    # Set by functions that sweep the entire ring (via _sweeping_ring)
    # Serves as a pseudo-lock
    _is_sweeping_ring = False

    def __init__(self, jar, target_size=0, cache_size_bytes=0):
        # TODO:  forward-port Dieter's bytes stuff
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
        self.data = weakref.WeakValueDictionary()
        self.ring = Ring()
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
        value = self.data.get(oid)
        if value is not None:
            return value
        return self.persistent_classes[oid]

    def __setitem__(self, oid, value):
        """ See IPickleCache.
        """
        # The order of checks matters for C compatibility;
        # the ZODB tests depend on this

        # The C impl requires either a type or a Persistent subclass
        if not isinstance(value, _CACHEABLE_TYPES):
            raise TypeError("Cache values must be persistent objects.")

        value_oid = value._p_oid
        if not isinstance(oid, OID_TYPE) or not isinstance(value_oid, OID_TYPE):
            raise TypeError('OID must be %s: key=%s _p_oid=%s' % (OID_TYPE, oid, value_oid))

        if value_oid != oid:
            raise ValueError("Cache key does not match oid")

        # XXX
        if oid in self.persistent_classes or oid in self.data:
            # Have to be careful here, a GC might have just run
            # and cleaned up the object
            existing_data = self.get(oid)
            if existing_data is not None and existing_data is not value:
                # Raise the same type of exception as the C impl with the same
                # message.
                raise ValueError('A different object already has the same oid')
        # Match the C impl: it requires a jar
        jar = getattr(value, '_p_jar', None)
        if jar is None and not isinstance(value, type):
            raise ValueError("Cached object jar missing")
        # It also requires that it cannot be cached more than one place
        existing_cache = getattr(jar, '_cache', None)
        if (existing_cache is not None
            and existing_cache is not self
            and existing_cache.data.get(oid) is not None):
            raise ValueError("Object already in another cache")

        if isinstance(value, type): # ZODB.persistentclass.PersistentMetaClass
            self.persistent_classes[oid] = value
        else:
            self.data[oid] = value
            _gc_monitor(value)
            if _OGA(value, '_p_state') != GHOST and value not in self.ring:
                self.ring.add(value)
                self.non_ghost_count += 1

    def __delitem__(self, oid):
        """ See IPickleCache.
        """
        if not isinstance(oid, OID_TYPE):
            raise TypeError('OID must be %s: %s' % (OID_TYPE, oid))
        if oid in self.persistent_classes:
            del self.persistent_classes[oid]
        else:
            value = self.data.pop(oid)
            self.ring.delete(value)

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
            return False # marker return for tests

        value = self.data[oid]

        was_in_ring = value in self.ring
        if not was_in_ring:
            if _OGA(value, '_p_state') != GHOST:
                self.ring.add(value)
                self.non_ghost_count += 1
        else:
            self.ring.move_to_head(value)

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
        result = []
        for obj in self.ring:
            result.append((obj._p_oid, obj))
        return result

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
        if isinstance(to_reify, OID_TYPE): #bytes
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
            result.append((oid,
                            len(gc.get_referents(klass)),
                            type(klass).__name__,
                            klass._p_state,
                            ))
        for oid, value in self.data.items():
            result.append((oid,
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

    cache_drain_resistance = property(lambda self: self.drain_resistance)
    cache_non_ghost_count = property(lambda self: self.non_ghost_count)
    cache_data = property(lambda self: dict(self.data.items()))
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
        # To avoid mutating datastructures in place or making a copy,
        # and to work efficiently with both the CFFI ring and the
        # deque-based ring, we collect the objects and their indexes
        # up front and then hand them off for ejection.
        # We don't use enumerate because that's slow under PyPy
        i = -1
        to_eject = []
        for value in self.ring:
            if self.non_ghost_count <= target and (self.total_estimated_size <= target_size_bytes or not target_size_bytes):
                break
            i += 1
            if value._p_state == UPTODATE:
                # The C implementation will only evict things that are specifically
                # in the up-to-date state
                self._persistent_deactivate_ran = False

                # sweeping an object out of the cache should also
                # ghost it---that's what C does. This winds up
                # calling `update_object_size_estimation`.
                # Also in C, if this was the last reference to the object,
                # it removes itself from the `data` dictionary.
                # If we're under PyPy or Jython, we need to run a GC collection
                # to make this happen...this is only noticeable though, when
                # we eject objects. Also, note that we can only take any of these
                # actions if our _p_deactivate ran, in case of buggy subclasses.
                # see _persistent_deactivate_ran

                value._p_deactivate()
                if (self._persistent_deactivate_ran
                    # Test-cases sneak in non-Persistent objects, sigh, so naturally
                    # they don't cooperate (without this check a bunch of test_picklecache
                    # breaks)
                    or not isinstance(value, _SWEEPABLE_TYPES)):
                    to_eject.append((i, value))
                    self.non_ghost_count -= 1

        ejected = len(to_eject)
        if ejected:
            self.ring.delete_all(to_eject)

        return ejected

    @_sweeping_ring
    def _invalidate(self, oid):
        value = self.data.get(oid)
        if value is not None and value._p_state != GHOST:
            value._p_invalidate()
            was_in_ring = self.ring.delete(value)
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
