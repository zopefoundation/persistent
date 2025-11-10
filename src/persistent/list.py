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

"""Python implementation of persistent list."""
from collections import UserList

import persistent


# The slice object you get when you write list[:]
_SLICE_ALL = slice(None, None, None)


class PersistentList(UserList, persistent.Persistent):
    """A persistent wrapper for list objects.

    Mutating instances of this class will cause them to be marked
    as changed and automatically persisted.

    .. versionchanged:: 4.5.2
       Using the `clear` method, or deleting a slice (e.g., ``del inst[:]`` or
       ``del inst[x:x]``) now only results in marking the instance as changed
       if it actually removed items.
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
           Now marks the list as changed.
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
