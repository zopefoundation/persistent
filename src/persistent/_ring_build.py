##############################################################################
#
# Copyright (c) 2018 Zope Foundation and Contributors.
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

import os
from cffi import FFI

this_dir = os.path.dirname(os.path.abspath(__file__))

ffi = FFI()
with open(os.path.join(this_dir, 'ring.h')) as f:
    cdefs = f.read()

# Define a structure with the same layout as CPersistentRing,
# and an extra member. We'll cast between them to reuse the
# existing functions.
struct_def = """
typedef struct CPersistentRingCFFI_struct
{
    struct CPersistentRing_struct *r_prev;
    struct CPersistentRing_struct *r_next;
    uintptr_t pobj_id; /* The id(PersistentPy object) */
} CPersistentRingCFFI;
"""

cdefs += struct_def + """
void cffi_ring_add(CPersistentRing* ring, void* elt);
void cffi_ring_del(void* elt);
void cffi_ring_move_to_head(CPersistentRing* ring, void* elt);
"""

ffi.cdef(cdefs)

source = """
#include "ring.c"
""" + struct_def + """

/* Like the other functions, but taking the CFFI version of the struct. This
 * saves casting at runtime in Python.
 */
#define cffi_ring_add(ring, elt) ring_add((CPersistentRing*)ring, (CPersistentRing*)elt)
#define cffi_ring_del(elt) ring_del((CPersistentRing*)elt)
#define cffi_ring_move_to_head(ring, elt) ring_move_to_head((CPersistentRing*)ring, (CPersistentRing*)elt)
"""

ffi.set_source('persistent._ring',
               source,
               include_dirs=[this_dir])

if __name__ == '__main__':
    ffi.compile()
