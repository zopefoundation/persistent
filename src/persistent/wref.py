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
"""ZODB-based persistent weakrefs
"""

from persistent import Persistent

WeakRefMarker = object()

class WeakRef:
    """Persistent weak references

    Persistent weak references are used much like Python weak
    references.  The major difference is that you can't specify an
    object to be called when the object is removed from the database.
    """
    # We set _p_oid to a marker so that the serialization system can
    # provide special handling of weakrefs.
    _p_oid = WeakRefMarker

    def __init__(self, ob):
        self._v_ob = ob
        self.oid = ob._p_oid
        self.dm = ob._p_jar
        if self.dm is not None:
            self.database_name = self.dm.db().database_name

    def __call__(self):
        try:
            return self._v_ob
        except AttributeError:
            try:
                self._v_ob = self.dm[self.oid]
            except (KeyError, AttributeError):
                return None
            return self._v_ob

    def __hash__(self):
        self = self()
        if self is None:
            raise TypeError('Weakly-referenced object has gone away')
        return hash(self)

    def __eq__(self, other):
        if not isinstance(other, WeakRef):
            return False
        self = self()
        if self is None:
            raise TypeError('Weakly-referenced object has gone away')
        other = other()
        if other is None:
            raise TypeError('Weakly-referenced object has gone away')

        return self == other


class PersistentWeakKeyDictionary(Persistent):
    """Persistent weak key dictionary

    This is akin to WeakKeyDictionaries. Note, however, that removal
    of items is extremely lazy.
    """
    # TODO:  It's expensive trying to load dead objects from the database.
    # It would be helpful if the data manager/connection cached these.

    def __init__(self, adict=None, **kwargs):
        self.data = {}
        if adict is not None:
            keys = getattr(adict, "keys", None)
            if keys is None:
                adict = dict(adict)
            self.update(adict)
        # XXX 'kwargs' is pointless, because keys must be strings, but we
        #     are going to try (and fail) to wrap a WeakRef around them.
        if kwargs: # pragma: no cover
            self.update(kwargs)

    def __getstate__(self):
        state = Persistent.__getstate__(self)
        state['data'] = list(state['data'].items())
        return state

    def __setstate__(self, state):
        state['data'] = {
            k: v for (k, v) in state['data']
            if k() is not None
            }
        Persistent.__setstate__(self, state)

    def __setitem__(self, key, value):
        self.data[WeakRef(key)] = value

    def __getitem__(self, key):
        return self.data[WeakRef(key)]

    def __delitem__(self, key):
        del self.data[WeakRef(key)]

    def get(self, key, default=None):
        """D.get(k[, d]) -> D[k] if k in D, else d.
        """
        return self.data.get(WeakRef(key), default)

    def __contains__(self, key):
        return WeakRef(key) in self.data

    def __iter__(self):
        for k in self.data:
            yield k()

    def update(self, adict):
        if isinstance(adict, PersistentWeakKeyDictionary):
            self.data.update(adict.data)
        else:
            for k, v in adict.items():
                self.data[WeakRef(k)] = v

    # TODO:  May need more methods and tests.
