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

"""Python implementation of persistent base types."""
import persistent
from collections import UserDict as IterableUserDict

class default:

    def __init__(self, func):
        self.func = func

    def __get__(self, inst, class_):
        if inst is None:
            return self
        return self.func(inst)


class PersistentMapping(IterableUserDict, persistent.Persistent):
    """A persistent wrapper for mapping objects.

    This class allows wrapping of mapping objects so that object
    changes are registered.  As a side effect, mapping objects may be
    subclassed.

    A subclass of PersistentMapping or any code that adds new
    attributes should not create an attribute named _container.  This
    is reserved for backwards compatibility reasons.
    """

    # UserDict provides all of the mapping behavior.  The
    # PersistentMapping class is responsible marking the persistent
    # state as changed when a method actually changes the state.  At
    # the mapping API evolves, we may need to add more methods here.

    __super_delitem = IterableUserDict.__delitem__
    __super_setitem = IterableUserDict.__setitem__
    __super_clear = IterableUserDict.clear
    __super_update = IterableUserDict.update
    __super_setdefault = IterableUserDict.setdefault
    __super_pop = IterableUserDict.pop
    __super_popitem = IterableUserDict.popitem


    # Be sure to make a deep copy of our ``data`` (See PersistentList.)
    # See https://github.com/python/cpython/commit/3645d29a1dc2102fdb0f5f0c0129ff2295bcd768
    # This was fixed in CPython 3.7.4, but we can't rely on that because it
    # doesn't handle our old ``_container`` appropriately (it goes directly
    # to ``self.__dict__``, bypassing the descriptor). The code here was initially
    # based on the version found in 3.7.4.
    def __copy__(self):
        inst = self.__class__.__new__(self.__class__)
        inst.__dict__.update(self.__dict__)
        # Create a copy and avoid triggering descriptors
        if '_container' in inst.__dict__:
            # BWC for ZODB < 3.3.
            data = inst.__dict__.pop('_container')
        else:
            data = inst.__dict__['data']
        inst.__dict__["data"] = data.copy()
        return inst

    def __delitem__(self, key):
        self.__super_delitem(key)
        self._p_changed = 1

    def __setitem__(self, key, v):
        self.__super_setitem(key, v)
        self._p_changed = 1

    def clear(self):
        """
        Remove all data from this dictionary.

        .. versionchanged:: 4.5.2
           If there was nothing to remove, this object is no
           longer marked as modified.
        """
        # Historically this method always marked ourself as changed,
        # so if there was a _container it was persisted as data. We want
        # to preserve that, even if we won't make any modifications otherwise.
        needs_changed = '_container' in self.__dict__ or bool(self)
        # Python 2 implements this by directly calling self.data.clear(),
        # but Python 3 does so by repeatedly calling self.popitem()
        self.__super_clear()
        if needs_changed:
            self._p_changed = 1

    def update(self, *args, **kwargs):
        """
        D.update([E, ]**F) -> None.

        .. versionchanged:: 4.5.2
           Now accepts arbitrary keyword arguments. In the special case
           of a keyword argument named ``b`` that is a dictionary,
           the behaviour will change.
        """
        self.__super_update(*args, **kwargs)
        self._p_changed = 1

    def setdefault(self, key, default=None):
        # We could inline all of UserDict's implementation into the
        # method here, but I'd rather not depend at all on the
        # implementation in UserDict (simple as it is).
        if key not in self.data:
            self._p_changed = 1
        return self.__super_setdefault(key, default=default)

    def pop(self, key, *args, **kwargs):
        self._p_changed = 1
        return self.__super_pop(key, *args, **kwargs)

    def popitem(self):
        """
        Remove an item.

        .. versionchanged:: 4.5.2
           No longer marks this object as modified if it was empty
           and an exception raised.
        """
        result = self.__super_popitem()
        self._p_changed = 1
        return result

    # Old implementations (prior to 2001; see
    # https://github.com/zopefoundation/ZODB/commit/c64281cf2830b569eed4f211630a8a61d22a0f0b#diff-b0f568e20f51129c10a096abad27c64a)
    # used ``_container`` rather than ``data``. Use a descriptor to provide
    # ``data`` when we have ``_container`` instead

    @default
    def data(self): # pylint:disable=method-hidden
        # We don't want to cause a write on read, so we're careful not to
        # do anything that would cause us to become marked as changed, however,
        # if we're modified, then the saved record will have data, not
        # _container.
        data = self.__dict__.pop('_container')
        self.__dict__['data'] = data

        return data
