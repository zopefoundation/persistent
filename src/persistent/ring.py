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

from collections import deque

from zope.interface import Interface
from zope.interface import implementer


_OGA = object.__getattribute__
_OSA = object.__setattr__


class IRing(Interface):
    """Conceptually, a doubly-linked list for efficiently keeping track of
    least- and most-recently used :class:`persistent.interfaces.IPersistent`
    objects.

    This is meant to be used by the :class:`persistent.picklecache.PickleCache`
    and should not be considered a public API. This interface documentation
    exists to assist development of the picklecache and alternate
    implementations by explaining assumptions and performance requirements.
    """

    def __len__():
        """Return the number of persistent objects stored in the ring.

        Should be constant time.
        """

    def __contains__(object):
        """Answer whether the given persistent object is found in the ring.

        Must not rely on object equality or object hashing, but only
        identity or the `_p_oid`. Should be constant time.
        """

    def add(object):
        """Add the persistent object to the ring as most-recently used.

        When an object is in the ring, the ring holds a strong
        reference to it so it can be deactivated later by the pickle
        cache. Should be constant time.

        The object should not already be in the ring, but this is not
        necessarily enforced.
        """

    def delete(object):
        """Remove the object from the ring if it is present.

        Returns a true value if it was present and a false value
        otherwise. An ideal implementation should be constant time,
        but linear time is allowed.
        """

    def move_to_head(object):
        """Place the object as the most recently used object in the ring.

        The object should already be in the ring, but this is not
        necessarily enforced, and attempting to move an object that is
        not in the ring has undefined consequences. An ideal
        implementation should be constant time, but linear time is
        allowed.
        """

    def __iter__():
        """Iterate over each persistent object in the ring, in the order of
        least recently used to most recently used.

        Mutating the ring while an iteration is in progress has
        undefined consequences.
        """


@implementer(IRing)
class _DequeRing:
    """A ring backed by the :class:`collections.deque` class.

    Operations are a mix of constant and linear time.

    It is available on all platforms.
    """

    __slots__ = ('ring', 'ring_oids', 'cleanup_func')

    def __init__(self, cleanup_func=None):

        self.ring = deque()
        self.ring_oids = set()

        self.cleanup_func = cleanup_func

    def __len__(self):
        return len(self.ring)

    def __contains__(self, pobj):
        return pobj._p_oid in self.ring_oids

    def add(self, pobj):
        self.ring.append(pobj)
        self.ring_oids.add(pobj._p_oid)

    def delete(self, pobj):
        # Note that we do not use self.ring.remove() because that
        # uses equality semantics and we don't want to call the persistent
        # object's __eq__ method (which might wake it up just after we
        # tried to ghost it)
        for i, o in enumerate(self.ring):
            if o is pobj:
                del self.ring[i]
                self.ring_oids.discard(pobj._p_oid)
                return 1

    def move_to_head(self, pobj):
        self.delete(pobj)
        self.add(pobj)

    def delete_all(self, indexes_and_values):
        for ix, value in reversed(indexes_and_values):
            del self.ring[ix]
            self.ring_oids.discard(value._p_oid)

    def __iter__(self):
        return iter(self.ring)

#    def iteritems(self):
#        return [(obj._p_oid, obj) for obj in self.ring]
#
#    def delete_node(self, node):
#        pass
#
#    def ring_node_for(self, persistent_object, create=True):
#        ring_data = _OGA(persistent_object, '_Persistent__ring')
#        if ring_data is None:
#            if not create:
#                return None
#
#            node =
#            gc_ptr = None
#            _data = (
#            node,
#            gc_ptr,
#            )
#            _OSA(persistent_object, '_Persistent__ring', ring_data)
#
#        return ring_data[0]


try:
    from persistent import _ring
except ImportError:  # pragma: no cover
    _CFFIRing = None
else:
    ffi = _ring.ffi
    _FFI_RING = _ring.lib

    _handles = set()

    @implementer(IRing)
    class _CFFIRing:
        """A ring backed by a C implementation.

        All operations are constant time.

        It is only available on platforms with ``cffi`` installed.
        """

        __slots__ = ('ring_home', 'ring_to_obj', 'cleanup_func')

        def __init__(self, cleanup_func=None):
            node = self.ring_home = ffi.new("CPersistentRing*")
            node.r_next = node
            node.r_prev = node

            self.cleanup_func = cleanup_func

            # The Persistent objects themselves are responsible for keeping
            # the CFFI nodes alive, but we need to be able to detect whether
            # or not any given object is in our ring, plus know how many
            # there are.
            # In addition, once an object enters the ring, it must be kept
            # alive so that it can be deactivated.
            # Note that because this is a strong reference to the persistent
            # object, its cleanup function --- triggered by the ``ffi.gc``
            # object it owns --- will never be fired while it is in this dict.
            self.ring_to_obj = {}

        def ring_node_for(self, persistent_object, create=True):
            ring_data = _OGA(persistent_object, '_Persistent__ring')
            if ring_data is None:
                if not create:
                    return None

                if self.cleanup_func:
                    node = ffi.new('CPersistentRingCFFI*')
                    node.pobj_id = ffi.cast('uintptr_t', id(persistent_object))
                    gc_ptr = ffi.gc(node, self.cleanup_func)
                else:
                    node = ffi.new("CPersistentRing*")
                    gc_ptr = None
                ring_data = (
                    node,
                    gc_ptr,
                )
                _OSA(persistent_object, '_Persistent__ring', ring_data)

            return ring_data[0]

        def __len__(self):
            return len(self.ring_to_obj)

        def __contains__(self, pobj):
            node = self.ring_node_for(pobj, False)
            return node and node in self.ring_to_obj

        def add(self, pobj):
            node = self.ring_node_for(pobj)
            _FFI_RING.cffi_ring_add(self.ring_home, node)
            self.ring_to_obj[node] = pobj

        def delete(self, pobj):
            its_node = self.ring_node_for(pobj, False)
            our_obj = self.ring_to_obj.pop(its_node, self)
            if its_node is not None and \
               our_obj is not self and \
               its_node.r_next:
                _FFI_RING.cffi_ring_del(its_node)
                return 1
            return None

        def delete_node(self, node):
            # Minimal sanity checking, assumes we're called from iter.
            self.ring_to_obj.pop(node)
            _FFI_RING.cffi_ring_del(node)

        def move_to_head(self, pobj):
            node = self.ring_node_for(pobj, False)
            _FFI_RING.cffi_ring_move_to_head(self.ring_home, node)

        def iteritems(self):
            head = self.ring_home
            here = head.r_next
            ring_to_obj = self.ring_to_obj
            while here != head:
                # We allow mutation during iteration, which means
                # we must get the next ``here`` value before
                # yielding, just in case the current value is
                # removed.
                current = here
                here = here.r_next
                pobj = ring_to_obj[current]
                yield current, pobj

        def __iter__(self):
            for _, v in self.iteritems():
                yield v


# Export the best available implementation
Ring = _CFFIRing if _CFFIRing else _DequeRing
