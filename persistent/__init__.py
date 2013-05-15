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
import os

PURE_PYTHON = os.environ.get('PURE_PYTHON')
if not PURE_PYTHON:
    try:
        from persistent.cPersistence import Persistent
        from persistent.cPersistence import GHOST
        from persistent.cPersistence import UPTODATE
        from persistent.cPersistence import CHANGED
        from persistent.cPersistence import STICKY
        from persistent.cPersistence import simple_new
    except ImportError: #pragma NO COVER
        from persistent.persistence import Persistent
        from persistent.persistence import GHOST
        from persistent.persistence import UPTODATE
        from persistent.persistence import CHANGED
        from persistent.persistence import STICKY
    else:
        from persistent._compat import copy_reg
        copy_reg.constructor(simple_new)
        # Make an interface declaration for Persistent, if zope.interface
        # is available.  Note that the Python version already does this.
        try:
            from zope.interface import classImplements
        except ImportError: #pragma NO COVER
            pass
        else:
            from persistent.interfaces import IPersistent
            classImplements(Persistent, IPersistent)

    try:
        from persistent.cPickleCache import PickleCache
    except ImportError: #pragma NO COVER
        from persistent.picklecache import PickleCache

    try:
        import persistent.TimeStamp
    except ImportError: #pragma NO COVER
        import persistent.timestamp as TimeStamp
        import sys
        sys.modules['persistent.TimeStamp'
                   ] = sys.modules['persistent.timestamp']
else: #pragma NO COVER
    from persistent.persistence import Persistent
    from persistent.persistence import GHOST
    from persistent.persistence import UPTODATE
    from persistent.persistence import CHANGED
    from persistent.persistence import STICKY
    from persistent.picklecache import PickleCache
    import persistent.timestamp as TimeStamp
    import sys
    sys.modules['persistent.TimeStamp'] = sys.modules['persistent.timestamp']
