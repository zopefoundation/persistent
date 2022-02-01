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

"""Python implementation of persistent list.

$Id$"""
import sys
import persistent
from persistent._compat import UserList
from persistent._compat import PYTHON2

# The slice object you get when you write list[:]
_SLICE_ALL = slice(None, None, None)


class PersistentList(UserList, persistent.Persistent):
    """A persistent wrapper for list objects.

    Mutating instances of this class will cause them to be marked
    as changed and automatically persisted.

    .. versionchanged:: 4.5.2
       Using the `clear` method, or deleting a slice (e.g., ``del inst[:]`` or ``del inst[x:x]``)
       now only results in marking the instance as changed if it actually removed
       items.
    .. versionchanged:: 4.5.2
       The `copy` method is available on Python 2.
    """
    __super_getitem = UserList.__getitem__
    __super_setitem = UserList.__setitem__
    __super_delitem = UserList.__delitem__
    __super_iadd = UserList.__iadd__
    __super_imul = UserList.__imul__
    __super_append = UserList.append
    __super_insert = UserList.insert
    __super_pop = UserList.pop
    __super_remove = UserList.remove
    __super_reverse = UserList.reverse
    __super_sort = UserList.sort
    __super_extend = UserList.extend
    __super_clear = (
        UserList.clear
        if hasattr(UserList, 'clear')
        else lambda inst: inst.__delitem__(_SLICE_ALL)
    )

    if not PYTHON2 and sys.version_info[:3] < (3, 7, 4):
        # Prior to 3.7.4, Python 3 (but not Python 2) failed to properly
        # return an instance of the same class.
        # See https://bugs.python.org/issue27639
        # and https://github.com/zopefoundation/persistent/issues/112.
        # We only define the special method on the necessary versions to avoid
        # any speed penalty.
        def __getitem__(self, item):
            result = self.__super_getitem(item)
            if isinstance(item, slice):
                result = self.__class__(result)
            return result

    if sys.version_info[:3] < (3, 7, 4):
        # Likewise for __copy__, except even Python 2 needs it.
        # See https://github.com/python/cpython/commit/3645d29a1dc2102fdb0f5f0c0129ff2295bcd768
        def __copy__(self):
            inst = self.__class__.__new__(self.__class__)
            inst.__dict__.update(self.__dict__)
            # Create a copy and avoid triggering descriptors
            inst.__dict__["data"] = self.__dict__["data"][:]
            return inst

    def __setitem__(self, i, item):
        self.__super_setitem(i, item)
        self._p_changed = 1

    def __delitem__(self, i):
        # If they write del list[:] but we're empty,
        # no need to mark us changed. Likewise with
        # a slice that's empty, like list[1:1].
        len_before = len(self.data)
        self.__super_delitem(i)
        if len(self.data) != len_before:
            self._p_changed = 1

    if PYTHON2:  # pragma: no cover
        __super_setslice = UserList.__setslice__
        __super_delslice = UserList.__delslice__

        def copy(self):
            return self.__class__(self)

        def __setslice__(self, i, j, other):
            self.__super_setslice(i, j, other)
            self._p_changed = 1

        def __delslice__(self, i, j):
            # In the past we just called super, but we want to apply the
            # same _p_changed optimization logic that __delitem__ does. Don't
            # call it as ``self.__delitem__``, though, because user code in subclasses
            # on Python 2 may not be expecting to get a slice.
            PersistentList.__delitem__(self, slice(i, j))

    def __iadd__(self, other):
        L = self.__super_iadd(other)
        self._p_changed = 1
        return L

    def __imul__(self, n):
        L = self.__super_imul(n)
        self._p_changed = 1
        return L

    def append(self, item):
        self.__super_append(item)
        self._p_changed = 1

    def clear(self):
        """
        Remove all items from the list.

        .. versionchanged:: 4.5.2
           Now marks the list as changed, and is available
           on both Python 2 and Python 3.
        """
        needs_changed = bool(self)
        self.__super_clear()
        if needs_changed:
            self._p_changed = 1

    def insert(self, i, item):
        self.__super_insert(i, item)
        self._p_changed = 1

    def pop(self, i=-1):
        rtn = self.__super_pop(i)
        self._p_changed = 1
        return rtn

    def remove(self, item):
        self.__super_remove(item)
        self._p_changed = 1

    def reverse(self):
        self.__super_reverse()
        self._p_changed = 1

    def sort(self, *args, **kwargs):
        self.__super_sort(*args, **kwargs)
        self._p_changed = 1

    def extend(self, other):
        self.__super_extend(other)
        self._p_changed = 1
