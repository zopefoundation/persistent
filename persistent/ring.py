# -*- coding: utf-8 -*-
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

#pylint: disable=W0212

try:
    from cffi import FFI
    import os

    this_dir = os.path.dirname(os.path.abspath(__file__))

    ffi = FFI()
    with open(os.path.join(this_dir, 'ring.h')) as f:
        ffi.cdef(f.read())

    ring = ffi.verify("""
    #include "ring.c"
    """, include_dirs=[os.path.dirname(os.path.abspath(__file__))])

    _OGA = object.__getattribute__
    _OSA = object.__setattr__

    #pylint: disable=E1101
    class _CFFIRing(object):

        __slots__ = ('ring_home', 'ring_to_obj')

        def __init__(self):
            node = self.ring_home = ffi.new("CPersistentRing*")
            node.r_next = node
            node.r_prev = node

            self.ring_to_obj = dict()

        def __len__(self):
            return len(self.ring_to_obj)

        def __contains__(self, pobj):
            return getattr(pobj, '_Persistent__ring', self) in self.ring_to_obj

        def add(self, pobj):
            node = ffi.new("CPersistentRing*")
            ring.ring_add(self.ring_home, node)
            self.ring_to_obj[node] = pobj
            object.__setattr__(pobj, '_Persistent__ring', node)

        def delete(self, pobj):
            node = getattr(pobj, '_Persistent__ring', None)
            if node is not None and node.r_next:
                ring.ring_del(node)
            self.ring_to_obj.pop(node, None)

        def move_to_head(self, pobj):
            node = pobj._Persistent__ring
            ring.ring_move_to_head(self.ring_home, node)

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

    Ring = _CFFIRing

except ImportError:

    from collections import deque

    class _DequeRing(object):

        __slots__ = ('ring', 'ring_oids')

        def __init__(self):

            self.ring = deque()
            self.ring_oids = set()

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
            i = 0 # Using a manual numeric counter instead of enumerate() is much faster on PyPy
            for o in self.ring:
                if o is pobj:
                    del self.ring[i]
                    self.ring_oids.discard(pobj._p_oid)
                    return 1
                i += 1

        def move_to_head(self, pobj):
            self.delete(pobj)
            self.add(pobj)

        def delete_all(self, indexes_and_values):
            for ix, value in reversed(indexes_and_values):
                del self.ring[ix]
                self.ring_oids.discard(value._p_oid)

        def __iter__(self):
            return iter(self.ring)

    Ring = _DequeRing
