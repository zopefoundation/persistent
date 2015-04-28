#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""



"""
from cffi import FFI
import pkg_resources
import os

ffi = FFI()

ffi.cdef("""
typedef struct CPersistentRingEx_struct
{
    struct CPersistentRingEx_struct *r_prev;
    struct CPersistentRingEx_struct *r_next;
    void* object;
} CPersistentRingEx;
""")

ffi.cdef(pkg_resources.resource_string('persistent', 'ring.h'))

ring = ffi.verify("""
typedef struct CPersistentRingEx_struct
{
    struct CPersistentRingEx_struct *r_prev;
    struct CPersistentRingEx_struct *r_next;
    void* object;
} CPersistentRingEx;
#include "ring.c"
""", include_dirs=[os.path.dirname(os.path.abspath(__file__))])


class CPersistentRing(object):

    def __init__(self, obj=None):
        self.handle = None
        self.node = ffi.new("CPersistentRingEx*")
        if obj is not None:
            self.handle = self.node.object = ffi.new_handle(obj)
            self._object = obj # Circular reference

    def __getattr__(self, name):
        return getattr(self.node, name)

    def get_object(self):
        return get_object(self.node)

def CPersistentRingHead():
    head = CPersistentRing()
    head.node.r_next = head.node
    head.node.r_prev = head.node
    return head

def _c(node):
    return ffi.cast("CPersistentRing*", node.node)

def add(head, elt):
    ring.ring_add(_c(head), _c(elt))

def del_(elt):
    ring.ring_del(_c(elt))

def move_to_head(head, elt):
    ring.ring_move_to_head(_c(head), _c(elt))

def iteritems(head):
    here = head.r_next
    while here != head.node:
        yield here
        here = here.r_next

def ringlen(head):
    count = 0
    for _ in iteritems(head):
        count += 1
    return count

def get_object(node):
    return ffi.from_handle(node.object)

print CPersistentRing()
