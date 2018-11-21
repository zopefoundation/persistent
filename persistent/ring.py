# -*- coding: utf-8 -*-
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

# pylint:disable=inherit-non-class,no-self-argument,redefined-builtin,c-extension-no-member

from zope.interface import Interface
from zope.interface import implementer

from persistent import _ring

class IRing(Interface):
    """Conceptually, a doubly-linked list for efficiently keeping track of least-
    and most-recently used :class:`persistent.interfaces.IPersistent` objects.

    This is meant to be used by the :class:`persistent.picklecache.PickleCache`
    and should not be considered a public API. This interface documentation exists
    to assist development of the picklecache and alternate implementations by
    explaining assumptions and performance requirements.
    """

    def __len__(): # pylint:disable=no-method-argument
        """Return the number of persistent objects stored in the ring.

        Should be constant time.
        """

    def __contains__(object): # pylint:disable=unexpected-special-method-signature
        """Answer whether the given persistent object is found in the ring.

        Must not rely on object equality or object hashing, but only
        identity or the `_p_oid`. Should be constant time.
        """

    def add(object):
        """Add the persistent object to the ring as most-recently used.

        When an object is in the ring, the ring holds a strong
        reference to it so it can be deactivated later by the pickle
        cache. Should be constant time.

        The object should not already be in the ring, but this is not necessarily
        enforced.
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

    def delete_all(indexes_and_values):
        """Given a sequence of pairs (index, object), remove all of them from
        the ring.

        This should be equivalent to calling :meth:`delete` for each
        value, but allows for a more efficient bulk deletion process.

        If the index and object pairs do not match with the actual state of the
        ring, this operation is undefined.

        Should be at least linear time (not quadratic).
        """

    def __iter__(): # pylint:disable=no-method-argument
        """Iterate over each persistent object in the ring, in the order of least
        recently used to most recently used.

        Mutating the ring while an iteration is in progress has
        undefined consequences.
        """


ffi = _ring.ffi
_FFI_RING = _ring.lib

_OGA = object.__getattribute__
_OSA = object.__setattr__


@implementer(IRing)
class _CFFIRing(object):
    """A ring backed by a C implementation. All operations are constant time.

    It is only available on platforms with ``cffi`` installed.
    """

    __slots__ = ('ring_home', 'ring_to_obj')

    def __init__(self):
        node = self.ring_home = ffi.new("CPersistentRing*")
        node.r_next = node
        node.r_prev = node

        # In order for the CFFI objects to stay alive, we must keep
        # a strong reference to them, otherwise they get freed. We must
        # also keep strong references to the objects so they can be deactivated
        self.ring_to_obj = dict()

    def __len__(self):
        return len(self.ring_to_obj)

    def __contains__(self, pobj):
        return getattr(pobj, '_Persistent__ring', self) in self.ring_to_obj

    def add(self, pobj):
        node = ffi.new("CPersistentRing*")
        _FFI_RING.ring_add(self.ring_home, node)
        self.ring_to_obj[node] = pobj
        _OSA(pobj, '_Persistent__ring', node)

    def delete(self, pobj):
        its_node = getattr(pobj, '_Persistent__ring', None)
        our_obj = self.ring_to_obj.pop(its_node, None)
        if its_node is not None and our_obj is not None and its_node.r_next:
            _FFI_RING.ring_del(its_node)
            return 1
        return None

    def move_to_head(self, pobj):
        node = _OGA(pobj, '_Persistent__ring')
        _FFI_RING.ring_move_to_head(self.ring_home, node)

    def delete_all(self, indexes_and_values):
        for _, value in indexes_and_values:
            self.delete(value)

    def iteritems(self):
        head = self.ring_home
        here = head.r_next
        while here != head:
            yield here
            here = here.r_next

    def __iter__(self):
        ring_to_obj = self.ring_to_obj
        for node in self.iteritems():
            yield ring_to_obj[node]

# Export the best available implementation
Ring = _CFFIRing
