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
from persistent._compat import PURE_PYTHON
from persistent.interfaces import IPersistent
from persistent.interfaces import IPickleCache

import persistent.timestamp as TimeStamp

from persistent import persistence as pyPersistence
from persistent import picklecache as pyPickleCache

try:
    # Be careful not to shadow the modules
    from persistent import cPersistence as _cPersistence
    from persistent import cPickleCache as _cPickleCache
except ImportError: # pragma: no cover
    _cPersistence = None
    _cPickleCache = None
else:
    # Make an interface declaration for Persistent
    # Note that the Python version already does this.
    from zope.interface import classImplements
    classImplements(_cPersistence.Persistent, IPersistent)
    classImplements(_cPickleCache.PickleCache, IPickleCache)


_persistence = pyPersistence if PURE_PYTHON or _cPersistence is None else _cPersistence
_picklecache = pyPickleCache if PURE_PYTHON or _cPickleCache is None else _cPickleCache

Persistent = _persistence.Persistent
GHOST = _persistence.GHOST
UPTODATE = _persistence.UPTODATE
CHANGED = _persistence.CHANGED
STICKY = _persistence.STICKY
PickleCache = _picklecache.PickleCache

sys.modules['persistent.TimeStamp'] = sys.modules['persistent.timestamp']
