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

# Take care not to shadow the module names
from persistent import interfaces as _interfaces
from persistent import persistence as _persistence
from persistent import picklecache as _picklecache
from persistent import timestamp as _timestamp


IPersistent = _interfaces.IPersistent
Persistent = _persistence.Persistent
GHOST = _interfaces.GHOST
UPTODATE = _interfaces.UPTODATE
CHANGED = _interfaces.CHANGED
STICKY = _interfaces.STICKY
PickleCache = _picklecache.PickleCache

# BWC for TimeStamp.
TimeStamp = _timestamp

sys.modules['persistent.TimeStamp'] = sys.modules['persistent.timestamp']
