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

from zope.interface import Interface
from zope.interface import implementer

from persistent import _ring


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


ffi = _ring.ffi
_FFI_RING = _ring.lib

_OGA = object.__getattribute__
_OSA = object.__setattr__

_handles = set()


@implementer(IRing)
class _CFFIRing:
    """A ring backed by a C implementation. All operations are constant time.

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
        # or not any given object is in our ring, plus know how many there are.
        # In addition, once an object enters the ring, it must be kept alive
        # so that it can be deactivated.
        # Note that because this is a strong reference to the persistent
        # object, its cleanup function --- triggered by the ``ffi.gc`` object
        # it owns --- will never be fired while it is in this dict.
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
        if its_node is not None and our_obj is not self and its_node.r_next:
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
Ring = _CFFIRing
