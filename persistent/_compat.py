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
import os

PURE_PYTHON = os.environ.get('PURE_PYTHON')

if sys.version_info[0] > 2:
    import copyreg as copy_reg
    from collections import UserDict as IterableUserDict
    from collections import UserList
    from sys import intern

    PYTHON3 = True
    PYTHON2 = False

else: # pragma: no cover
    import copy_reg
    from UserDict import IterableUserDict
    from UserList import UserList

    PYTHON3 = False
    PYTHON2 = True

    intern = intern
