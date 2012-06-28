##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
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
import unittest

try:
    import transaction
    import ZODB
except ImportError:
    pass
else:
    def new_ghost_w_persistent_classes():
        """
        Peristent meta classes work too:

            >>> import persistent
            >>> from persistent.tests.utils import ResettingJar
            >>> jar = ResettingJar()
            >>> cache = persistent.PickleCache(jar, 10, 100)
            >>> import ZODB.persistentclass
            >>> class PC:
            ...     __metaclass__ = ZODB.persistentclass.PersistentMetaClass

            >>> PC._p_oid
            >>> PC._p_jar
            >>> PC._p_serial
            >>> PC._p_changed
            False

            >>> cache.new_ghost('2', PC)
            >>> PC._p_oid
            '2'
            >>> PC._p_jar is jar
            True
            >>> PC._p_serial
            >>> PC._p_changed
            False
        """

    def cache_invalidate_and_minimize_used_to_leak_None_ref():
        """Persistent weak references

        >>> import transaction
        >>> import ZODB.tests.util

        >>> db = ZODB.tests.util.DB()

        >>> conn = db.open()
        >>> conn.root.p = p = conn.root().__class__()
        >>> transaction.commit()

        >>> import sys
        >>> old = sys.getrefcount(None)
        >>> conn._cache.invalidate(p._p_oid)
        >>> sys.getrefcount(None) - old
        0

        >>> _ = conn.root.p.keys()
        >>> old = sys.getrefcount(None)
        >>> conn._cache.minimize()
        >>> sys.getrefcount(None) - old
        0

        >>> db.close()

        """


def test_suite():
    from doctest import DocTestSuite
    return unittest.TestSuite((
        DocTestSuite(),
    ))
