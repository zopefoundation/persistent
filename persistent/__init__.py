##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""Prefer C implementations of Persistent / PickleCache / TimeStamp.

Fall back to pure Python implementations.
"""

import sys

__all__ = [
    'IPersistent',
    'Persistent',
    'GHOST',
    'UPTODATE',
    'CHANGED',
    'STICKY',
    'PickleCache',
    'TimeStamp',
]

from persistent.interfaces import IPersistent

import persistent.timestamp as TimeStamp

from persistent import persistence as _persistence
from persistent import picklecache as _picklecache

Persistent = _persistence.Persistent
PersistentPy = _persistence.PersistentPy
GHOST = _persistence.GHOST
UPTODATE = _persistence.UPTODATE
CHANGED = _persistence.CHANGED
STICKY = _persistence.STICKY
PickleCache = _picklecache.PickleCache
PickleCachePy = _picklecache.PickleCachePy

sys.modules['persistent.TimeStamp'] = sys.modules['persistent.timestamp']
