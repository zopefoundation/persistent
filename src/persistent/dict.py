##############################################################################
#
# Copyright Zope Foundation and Contributors.
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
from zope.deferredimport import deprecated


deprecated(
    "`persistent.dict.PersistentDict` is deprecated. Use"
    " `persistent.mapping.PersistentMapping` instead."
    " This backward compatibility shim will be removed in persistent"
    " version 7.",
    PersistentDict='persistent.mapping:PersistentMapping',
)
