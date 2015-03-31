##############################################################################
#
# Copyright (c) 2012 Zope Foundation and Contributors.
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

import sys

if sys.version_info[0] > 2: #pragma NO COVER
    import copyreg as copy_reg
    from collections import UserDict as IterableUserDict
    from collections import UserList
    from sys import intern

    def _u(s):
        return s

    def _b(s):
        if isinstance(s, str):
            return s.encode('unicode_escape')
        return s

    def _native(s):
        if isinstance(s, bytes):
            return s.decode('unicode_escape')
        return s

    PYTHON3 = True
    PYTHON2 = False

else: #pragma NO COVER
    import copy_reg
    from UserDict import IterableUserDict
    from UserList import UserList

    def _u(s):
        return unicode(s, 'unicode_escape')

    def _native(s):
        if isinstance(s, unicode):
            return s.encode('unicode_escape')
        return s

    _b = _native

    PYTHON3 = False
    PYTHON2 = True

    intern = intern
