##############################################################################
#
# Copyright (c) 2011 Zope Foundation and Contributors.
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

from zope.interface import implementer

from persistent.interfaces import IPersistent
from persistent.interfaces import GHOST
from persistent.interfaces import UPTODATE
from persistent.interfaces import CHANGED
from persistent.interfaces import STICKY
from persistent.interfaces import OID_TYPE
from persistent.interfaces import SERIAL_TYPE
from persistent.timestamp import TimeStamp
from persistent.timestamp import _ZERO
from persistent._compat import copy_reg
from persistent._compat import intern

_INITIAL_SERIAL = _ZERO


# Bitwise flags
_CHANGED = 0x0001
_STICKY = 0x0002

_OGA = object.__getattribute__
_OSA = object.__setattr__

# These names can be used from a ghost without causing it to be activated.
SPECIAL_NAMES = ('__class__',
                 '__del__',
                 '__dict__',
                 '__of__',
                 '__setstate__'
                )


@implementer(IPersistent)
class Persistent(object):
    """ Pure Python implmentation of Persistent base class
    """
    __slots__ = ('__jar', '__oid', '__serial', '__flags', '__size')

    def __new__(cls, *args, **kw):
        inst = super(Persistent, cls).__new__(cls)
        # We bypass the __setattr__ implementation of this object
        # at __new__ time, just like the C implementation does. This
        # makes us compatible with subclasses that want to access
        # properties like _p_changed in their setattr implementation
        _OSA(inst, '_Persistent__jar', None)
        _OSA(inst, '_Persistent__oid', None)
        _OSA(inst, '_Persistent__serial', None)
        _OSA(inst, '_Persistent__flags', None)
        _OSA(inst, '_Persistent__size', 0)
        return inst

    # _p_jar:  see IPersistent.
    def _get_jar(self):
        return self.__jar

    def _set_jar(self, value):
        if self._p_is_in_cache() and value is not None and self.__jar != value:
            # The C implementation only forbids changing the jar
            # if we're already in a cache. Match its error message
            raise ValueError('can not change _p_jar of cached object')

        if self.__jar != value:
            _OSA(self, '_Persistent__jar', value)
            _OSA(self, '_Persistent__flags', 0)

    def _del_jar(self):
        jar = self.__jar
        oid = self.__oid
        if jar is not None:
            if self._p_is_in_cache():
                raise ValueError("can't delete _p_jar of cached object")
            self.__setattr__('_Persistent__jar', None)
            _OSA(self, '_Persistent__flags', None)

    _p_jar = property(_get_jar, _set_jar, _del_jar)

    # _p_oid:  see IPersistent.
    def _get_oid(self):
        return self.__oid

    def _set_oid(self, value):
        if value == self.__oid:
            return
        # The C implementation allows *any* value to be
        # used as the _p_oid.
        #if value is not None:
        #    if not isinstance(value, OID_TYPE):
        #        raise ValueError('Invalid OID type: %s' % value)
        # The C implementation only forbids changing the OID
        # if we're in a cache, regardless of what the current
        # value or jar is
        if self._p_is_in_cache():
            # match the C error message
            raise ValueError('can not change _p_oid of cached object')
        _OSA(self, '_Persistent__oid', value)

    def _del_oid(self):
        jar = self.__jar
        oid = self.__oid
        if jar is not None:
            if oid and jar._cache.get(oid):
                raise ValueError('Cannot delete _p_oid of cached object')
        _OSA(self, '_Persistent__oid', None)

    _p_oid = property(_get_oid, _set_oid, _del_oid)

    # _p_serial:  see IPersistent.
    def _get_serial(self):
        if self.__serial is not None:
            return self.__serial
        return _INITIAL_SERIAL

    def _set_serial(self, value):
        if not isinstance(value, SERIAL_TYPE):
            raise ValueError('Invalid SERIAL type: %s' % value)
        if len(value) != 8:
            raise ValueError('SERIAL must be 8 octets')
        _OSA(self, '_Persistent__serial', value)

    def _del_serial(self):
        self.__serial = None

    _p_serial = property(_get_serial, _set_serial, _del_serial)

    # _p_changed:  see IPersistent.
    def _get_changed(self):
        if self.__jar is None:
            return False
        if self.__flags is None: # ghost
            return None
        return bool(self.__flags & _CHANGED)

    def _set_changed(self, value):
        if self.__flags is None:
            if value:
                self._p_activate()
                self._p_set_changed_flag(value)
        else:
            if value is None: # -> ghost
                self._p_deactivate()
            else:
                self._p_set_changed_flag(value)

    def _del_changed(self):
        self._p_invalidate()

    _p_changed = property(_get_changed, _set_changed, _del_changed)

    # _p_mtime
    def _get_mtime(self):
        if self.__serial is not None:
            ts = TimeStamp(self.__serial)
            return ts.timeTime()

    _p_mtime = property(_get_mtime)

    # _p_state
    def _get_state(self):
        if self.__jar is None:
            return UPTODATE
        if self.__flags is None:
            return GHOST
        if self.__flags & _CHANGED:
            result = CHANGED
        else:
            result = UPTODATE
        if self.__flags & _STICKY:
            return STICKY
        return result

    _p_state = property(_get_state)

    # _p_estimated_size:  XXX don't want to reserve the space?
    def _get_estimated_size(self):
        return self.__size * 64

    def _set_estimated_size(self, value):
        if isinstance(value, int):
            if value < 0:
                raise ValueError('_p_estimated_size must not be negative')
            _OSA(self, '_Persistent__size', _estimated_size_in_24_bits(value))
        else:
            raise TypeError("_p_estimated_size must be an integer")

    def _del_estimated_size(self):
        self.__size = 0

    _p_estimated_size = property(
        _get_estimated_size, _set_estimated_size, _del_estimated_size)

    # The '_p_sticky' property is not (yet) part of the API:  for now,
    # it exists to simplify debugging and testing assertions.
    def _get_sticky(self):
        if self.__flags is None:
            return False
        return bool(self.__flags & _STICKY)
    def _set_sticky(self, value):
        if self.__flags is None:
            raise ValueError('Ghost')
        if value:
            self.__flags |= _STICKY
        else:
            self.__flags &= ~_STICKY
    _p_sticky = property(_get_sticky, _set_sticky)

    # The '_p_status' property is not (yet) part of the API:  for now,
    # it exists to simplify debugging and testing assertions.
    def _get_status(self):
        if self.__jar is None:
            return 'unsaved'
        if self.__flags is None:
            return 'ghost'
        if self.__flags & _STICKY:
            return 'sticky'
        if self.__flags & _CHANGED:
            return 'changed'
        return 'saved'

    _p_status = property(_get_status)

    # Methods from IPersistent.
    def __getattribute__(self, name):
        """ See IPersistent.
        """
        if (not name.startswith('_Persistent__') and
            not name.startswith('_p_') and
            name not in SPECIAL_NAMES):
            if _OGA(self, '_Persistent__flags') is None:
                _OGA(self, '_p_activate')()
            _OGA(self, '_p_accessed')()
        return _OGA(self, name)

    def __setattr__(self, name, value):
        special_name = (name.startswith('_Persistent__') or
                        name.startswith('_p_'))
        volatile = name.startswith('_v_')
        if not special_name:
            if _OGA(self, '_Persistent__flags') is None:
                _OGA(self, '_p_activate')()
            if not volatile:
                _OGA(self, '_p_accessed')()
        _OSA(self, name, value)
        if (_OGA(self, '_Persistent__jar') is not None and
            _OGA(self, '_Persistent__oid') is not None and
            not special_name and
            not volatile):
            before = _OGA(self, '_Persistent__flags')
            after = before | _CHANGED
            if before != after:
                _OSA(self, '_Persistent__flags', after)
                _OGA(self, '_p_register')()

    def __delattr__(self, name):
        special_name = (name.startswith('_Persistent__') or
                        name.startswith('_p_'))
        if not special_name:
            if _OGA(self, '_Persistent__flags') is None:
                _OGA(self, '_p_activate')()
            _OGA(self, '_p_accessed')()
            before = _OGA(self, '_Persistent__flags')
            after = before | _CHANGED
            if before != after:
                _OSA(self, '_Persistent__flags', after)
                if (_OGA(self, '_Persistent__jar') is not None and
                    _OGA(self, '_Persistent__oid') is not None):
                    _OGA(self, '_p_register')()
        object.__delattr__(self, name)

    def _slotnames(self):
        slotnames = copy_reg._slotnames(type(self))
        return [x for x in slotnames
                   if not x.startswith('_p_') and
                      not x.startswith('_v_') and
                      not x.startswith('_Persistent__') and
                      x not in Persistent.__slots__]

    def __getstate__(self):
        """ See IPersistent.
        """
        idict = getattr(self, '__dict__', None)
        slotnames = self._slotnames()
        if idict is not None:
            d = dict([x for x in idict.items()
                         if not x[0].startswith('_p_') and
                            not x[0].startswith('_v_')])
        else:
            d = None
        if slotnames:
            s = {}
            for slotname in slotnames:
                value = getattr(self, slotname, self)
                if value is not self:
                    s[slotname] = value
            return d, s
        return d

    def __setstate__(self, state):
        """ See IPersistent.
        """
        if isinstance(state,tuple):
            inst_dict, slots = state
        else:
            inst_dict, slots = state, ()
        idict = getattr(self, '__dict__', None)
        if inst_dict is not None:
            if idict is None:
                raise TypeError('No instance dict')
            idict.clear()
            for k, v in inst_dict.items():
                idict[intern(k)] = v
        slotnames = self._slotnames()
        if slotnames:
            for k, v in slots.items():
                setattr(self, k, v)

    def __reduce__(self):
        """ See IPersistent.
        """
        gna = getattr(self, '__getnewargs__', lambda: ())
        return (copy_reg.__newobj__,
                (type(self),) + gna(), self.__getstate__())

    def _p_activate(self):
        """ See IPersistent.
        """
        before = self.__flags
        if self.__flags is None or self._p_state < 0: # Only do this if we're a ghost
            _OSA(self, '_Persistent__flags', 0)
            if self.__jar is not None and self.__oid is not None:
                try:
                    self.__jar.setstate(self)
                except:
                    _OSA(self, '_Persistent__flags', before)
                    raise

    # In the C implementation, _p_invalidate winds up calling
    # _p_deactivate. There are ZODB tests that depend on this;
    # it's not documented but there may be code in the wild
    # that does as well

    def _p_deactivate(self):
        """ See IPersistent.
        """
        if self.__flags is not None and not self.__flags:
            self._p_invalidate_deactivate_helper()

    def _p_invalidate(self):
        """ See IPersistent.
        """
        # If we think we have changes, we must pretend
        # like we don't so that deactivate does its job
        _OSA(self, '_Persistent__flags', 0)
        self._p_deactivate()

    def _p_invalidate_deactivate_helper(self):
        if self.__jar is not None:
            if self.__flags is not None:
                _OSA(self, '_Persistent__flags', None)
            idict = getattr(self, '__dict__', None)
            if idict is not None:
                idict.clear()
            # Implementation detail: deactivating/invalidating
            # updates the size of the cache (if we have one)
            # by telling it this object no longer takes any bytes
            # (-1 is a magic number to compensate for the implementation,
            # which always adds one to the size given)
            try:
                cache = self.__jar._cache
            except AttributeError:
                pass
            else:
                cache.update_object_size_estimation(self.__oid, -1)
                # See notes in PickleCache.sweep for why we have to do this
                cache._persistent_deactivate_ran = True

    def _p_getattr(self, name):
        """ See IPersistent.
        """
        if name.startswith('_p_') or name in SPECIAL_NAMES:
            return True
        self._p_activate()
        self._p_accessed()
        return False

    def _p_setattr(self, name, value):
        """ See IPersistent.
        """
        if name.startswith('_p_'):
            setattr(self, name, value)
            return True
        self._p_activate()
        self._p_accessed()
        return False

    def _p_delattr(self, name):
        """ See IPersistent.
        """
        if name.startswith('_p_'):
            delattr(self, name)
            return True
        self._p_activate()
        self._p_accessed()
        return False

    # Helper methods:  not APIs:  we name them with '_p_' to bypass
    # the __getattribute__ bit which bumps the cache.
    def _p_register(self):
        if self.__jar is not None and self.__oid is not None:
            self.__jar.register(self)

    def _p_set_changed_flag(self, value):
        if value:
            before = self.__flags
            after = self.__flags | _CHANGED
            if before != after:
                self._p_register()
            _OSA(self, '_Persistent__flags', after)
        else:
            flags = self.__flags
            flags &= ~_CHANGED
            _OSA(self, '_Persistent__flags', flags)


    def _p_accessed(self):
        # Notify the jar's pickle cache that we have been accessed.
        # This relies on what has been (until now) an implementation
        # detail, the '_cache' attribute of the jar.  We made it a
        # private API to avoid the cycle of keeping a reference to
        # the cache on the persistent object.
        if (self.__jar is not None and
            self.__oid is not None and
            self._p_state >= 0):
            # The KeyError arises in ZODB: ZODB.serialize.ObjectWriter
            # can assign a jar and an oid to newly seen persistent objects,
            # but because they are newly created, they aren't in the
            # pickle cache yet. There doesn't seem to be a way to distinguish
            # that at this level, all we can do is catch it.
            # The AttributeError arises in ZODB test cases
            try:
                cache = self.__jar._cache
            except AttributeError:
                pass
            else:
                try:
                    cache.mru(self.__oid)
                except KeyError:
                    pass

    def _p_is_in_cache(self):
        oid = self.__oid
        if not oid:
            return False

        jar = self.__jar
        cache = getattr(jar, '_cache', None)
        if cache is not None:
            return cache.get(oid) is self

def _estimated_size_in_24_bits(value):
    if value > 1073741696:
        return 16777215
    return (value//64) + 1
