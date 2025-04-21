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
import copyreg
import struct
from sys import intern

from zope.interface import implementer

from persistent import interfaces
from persistent._compat import use_c_impl
from persistent.interfaces import SERIAL_TYPE
from persistent.timestamp import _ZERO
from persistent.timestamp import TimeStamp


__all__ = [
    'Persistent',
    'PersistentPy',
]

_INITIAL_SERIAL = _ZERO


# Bitwise flags
_CHANGED = 0x0001
_STICKY = 0x0002

_OGA = object.__getattribute__
_OSA = object.__setattr__
_ODA = object.__delattr__

# These names can be read from a ghost without causing it to be
# activated. These are standardized with the C implementation
SPECIAL_NAMES = ('__class__',
                 '__del__',
                 '__dict__',
                 '__of__',
                 '__setstate__',)

# And this is an implementation detail of this class; it holds
# the standard names plus the slot names, allowing for just one
# check in __getattribute__
_SPECIAL_NAMES = set(SPECIAL_NAMES)

# __ring is for use by PickleCachePy and is opaque to us.
_SLOTS = ('__jar', '__oid', '__serial', '__flags', '__size', '__ring',)
_SPECIAL_NAMES.update([intern('_Persistent' + x) for x in _SLOTS])

# These are names that can be written to a ghost without
# causing it to be activated. The C code only makes the exception for
# _p_* names; in practice, only __class__ and __dict__ are actually
# going to be set on instances, as the rest of the exceptions are
# methods called on the type
_SPECIAL_WRITE_NAMES = set(_SPECIAL_NAMES) - {'__class__', '__dict__'}

# Represent 8-byte OIDs as hex integer, just like
# ZODB does.
_OID_STRUCT = struct.Struct('>Q')


def oid_repr(oid):
    _repr = f'{_OID_STRUCT.unpack(oid)[0]:x}'
    len_repr = len(_repr)
    if len_repr < 8 and len_repr % 2 == 1:
        _repr = '0' + _repr
    return _repr


@use_c_impl
@implementer(interfaces.IPersistent)
class Persistent:
    """ Pure Python implmentation of Persistent base class
    """
    __slots__ = _SLOTS

    def __new__(cls, *args, **kw):
        inst = super().__new__(cls)
        # We bypass the __setattr__ implementation of this object
        # at __new__ time, just like the C implementation does. This
        # makes us compatible with subclasses that want to access
        # properties like _p_changed in their setattr implementation
        _OSA(inst, '_Persistent__jar', None)
        _OSA(inst, '_Persistent__oid', None)
        _OSA(inst, '_Persistent__serial', None)
        _OSA(inst, '_Persistent__flags', None)
        _OSA(inst, '_Persistent__size', 0)
        _OSA(inst, '_Persistent__ring', None)
        return inst

    # _p_jar:  see IPersistent.
    def _get_jar(self):
        return _OGA(self, '_Persistent__jar')

    def _set_jar(self, value):
        jar = _OGA(self, '_Persistent__jar')
        if self._p_is_in_cache(jar) and value is not None and jar != value:
            # The C implementation only forbids changing the jar
            # if we're already in a cache. Match its error message
            raise ValueError('can not change _p_jar of cached object')

        if _OGA(self, '_Persistent__jar') != value:
            _OSA(self, '_Persistent__jar', value)
            _OSA(self, '_Persistent__flags', 0)

    def _del_jar(self):
        jar = _OGA(self, '_Persistent__jar')
        if jar is not None:
            if self._p_is_in_cache(jar):
                raise ValueError("can't delete _p_jar of cached object")
            _OSA(self, '_Persistent__jar', None)
            _OSA(self, '_Persistent__flags', None)

    _p_jar = property(_get_jar, _set_jar, _del_jar)

    # _p_oid:  see IPersistent.
    def _get_oid(self):
        return _OGA(self, '_Persistent__oid')

    def _set_oid(self, value):
        if value == _OGA(self, '_Persistent__oid'):
            return
        # The C implementation allows *any* value to be
        # used as the _p_oid.
        # if value is not None:
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
        jar = _OGA(self, '_Persistent__jar')
        oid = _OGA(self, '_Persistent__oid')
        if jar is not None:
            if oid and jar._cache.get(oid):
                raise ValueError('Cannot delete _p_oid of cached object')
        _OSA(self, '_Persistent__oid', None)

    _p_oid = property(_get_oid, _set_oid, _del_oid)

    # _p_serial:  see IPersistent.
    def _get_serial(self):
        serial = _OGA(self, '_Persistent__serial')
        if serial is not None:
            return serial
        return _INITIAL_SERIAL

    def _set_serial(self, value):
        if not isinstance(value, SERIAL_TYPE):
            raise ValueError('Invalid SERIAL type: %s' % value)
        if len(value) != 8:
            raise ValueError('SERIAL must be 8 octets')
        _OSA(self, '_Persistent__serial', value)

    def _del_serial(self):
        _OSA(self, '_Persistent__serial', None)

    _p_serial = property(_get_serial, _set_serial, _del_serial)

    # _p_changed:  see IPersistent.
    def _get_changed(self):
        if _OGA(self, '_Persistent__jar') is None:
            return False
        flags = _OGA(self, '_Persistent__flags')
        if flags is None:  # ghost
            return None
        return bool(flags & _CHANGED)

    def _set_changed(self, value):
        if _OGA(self, '_Persistent__flags') is None:
            if value:
                self._p_activate()
                self._p_set_changed_flag(value)
        else:
            if value is None:  # -> ghost
                self._p_deactivate()
            else:
                self._p_set_changed_flag(value)

    def _del_changed(self):
        self._p_invalidate()

    _p_changed = property(_get_changed, _set_changed, _del_changed)

    # _p_mtime
    def _get_mtime(self):
        # The C implementation automatically unghostifies the object
        # when _p_mtime is accessed.
        self._p_activate()
        self._p_accessed()
        serial = _OGA(self, '_Persistent__serial')
        return TimeStamp(serial).timeTime() if serial is not None else None

    _p_mtime = property(_get_mtime)

    # _p_state
    def _get_state(self):
        # Note the use of OGA and caching to avoid recursive calls to
        # __getattribute__: __getattribute__ calls _p_accessed calls
        # cache.mru() calls _p_state
        if _OGA(self, '_Persistent__jar') is None:
            return interfaces.UPTODATE
        flags = _OGA(self, '_Persistent__flags')
        if flags is None:
            return interfaces.GHOST
        if flags & _CHANGED:
            result = interfaces.CHANGED
        else:
            result = interfaces.UPTODATE
        if flags & _STICKY:
            return interfaces.STICKY
        return result

    _p_state = property(_get_state)

    # _p_estimated_size:  XXX don't want to reserve the space?
    def _get_estimated_size(self):
        return _OGA(self, '_Persistent__size') * 64

    def _set_estimated_size(self, value):
        if isinstance(value, int):
            if value < 0:
                raise ValueError('_p_estimated_size must not be negative')
            _OSA(self, '_Persistent__size', _estimated_size_in_24_bits(value))
        else:
            raise TypeError("_p_estimated_size must be an integer")

    def _del_estimated_size(self):
        _OSA(self, '_Persistent__size', 0)

    _p_estimated_size = property(
        _get_estimated_size, _set_estimated_size, _del_estimated_size)

    # The '_p_sticky' property is not (yet) part of the API:  for now,
    # it exists to simplify debugging and testing assertions.
    def _get_sticky(self):
        flags = _OGA(self, '_Persistent__flags')
        if flags is None:
            return False
        return bool(flags & _STICKY)

    def _set_sticky(self, value):
        flags = _OGA(self, '_Persistent__flags')
        if flags is None:
            raise ValueError('Ghost')
        if value:
            flags |= _STICKY
        else:
            flags &= ~_STICKY
        _OSA(self, '_Persistent__flags', flags)
    _p_sticky = property(_get_sticky, _set_sticky)

    # The '_p_status' property is not (yet) part of the API:  for now,
    # it exists to simplify debugging and testing assertions.
    def _get_status(self):
        if _OGA(self, '_Persistent__jar') is None:
            return 'unsaved'
        flags = _OGA(self, '_Persistent__flags')
        if flags is None:
            return 'ghost'
        if flags & _STICKY:
            return 'sticky'
        if flags & _CHANGED:
            return 'changed'
        return 'saved'

    _p_status = property(_get_status)

    # Methods from IPersistent.
    def __getattribute__(self, name):
        """ See IPersistent.
        """
        oga = _OGA
        if (not name.startswith('_p_') and
                name not in _SPECIAL_NAMES):
            if oga(self, '_Persistent__flags') is None:
                oga(self, '_p_activate')()
            oga(self, '_p_accessed')()
        return oga(self, name)

    def __setattr__(self, name, value):
        special_name = (name in _SPECIAL_WRITE_NAMES or
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
        special_name = (name in _SPECIAL_NAMES or
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
        _ODA(self, name)

    def _slotnames(self, _v_exclude=True):
        slotnames = copyreg._slotnames(type(self))
        return [x for x in slotnames
                if not x.startswith('_p_') and
                not (x.startswith('_v_') and _v_exclude) and
                not x.startswith('_Persistent__') and
                x not in _SLOTS]

    def __getstate__(self):
        """ See IPersistent.
        """
        idict = getattr(self, '__dict__', None)
        slotnames = self._slotnames()
        if idict is not None:
            # TODO: Convert to a dictionary comprehension, avoid the
            # intermediate list.
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
        if isinstance(state, tuple):
            inst_dict, slots = state
        else:
            inst_dict, slots = state, ()
        idict = getattr(self, '__dict__', None)
        if inst_dict is not None:
            if idict is None:
                raise TypeError('No instance dict')
            idict.clear()
            for k, v in inst_dict.items():
                # Normally the keys for instance attributes are interned.
                # Do that here, but only if it is possible to do so.
                idict[intern(k) if k.__class__ is str else k] = v
        slotnames = self._slotnames()
        if slotnames:
            for k, v in slots.items():
                setattr(self, k, v)

    def __reduce__(self):
        """ See IPersistent.
        """
        gna = getattr(self, '__getnewargs__', lambda: ())
        return (copyreg.__newobj__,
                (type(self),) + gna(), self.__getstate__())

    def _p_activate(self):
        """ See IPersistent.
        """
        oga = _OGA
        before = oga(self, '_Persistent__flags')
        if before is None:  # Only do this if we're a ghost
            # Begin by marking up-to-date in case we bail early
            _OSA(self, '_Persistent__flags', 0)
            jar = oga(self, '_Persistent__jar')
            if jar is None:
                return
            oid = oga(self, '_Persistent__oid')
            if oid is None:
                return

            # If we're actually going to execute a set-state,
            # mark as changed to prevent any recursive call
            # (actually, our earlier check that we're a ghost should
            # prevent this, but the C implementation sets it to changed
            # while calling jar.setstate, and this is observable to clients).
            # The main point of this is to prevent changes made during
            # setstate from registering the object with the jar.
            _OSA(self, '_Persistent__flags', interfaces.CHANGED)
            try:
                jar.setstate(self)
            except BaseException:
                _OSA(self, '_Persistent__flags', before)
                raise
            else:
                # If we succeed, no matter what the implementation
                # of setstate did, mark ourself as up-to-date. The
                # C implementation unconditionally does this.
                _OSA(self, '_Persistent__flags', 0)  # up-to-date

    # In the C implementation, _p_invalidate winds up calling
    # _p_deactivate. There are ZODB tests that depend on this;
    # it's not documented but there may be code in the wild
    # that does as well

    def _p_deactivate(self):
        """ See IPersistent.
        """
        flags = _OGA(self, '_Persistent__flags')
        if flags is not None and not flags:
            self._p_invalidate_deactivate_helper()

    def _p_invalidate(self):
        """ See IPersistent.
        """
        # If we think we have changes, we must pretend
        # like we don't so that deactivate does its job
        _OSA(self, '_Persistent__flags', 0)
        self._p_deactivate()

    def _p_invalidate_deactivate_helper(self, clear=True):
        jar = _OGA(self, '_Persistent__jar')
        if jar is None:
            return

        if _OGA(self, '_Persistent__flags') is not None:
            _OSA(self, '_Persistent__flags', None)

        if clear:
            try:
                idict = _OGA(self, '__dict__')
            except AttributeError:
                pass
            else:
                idict.clear()
            type_ = type(self)
            # for backward-compatibility reason we release __slots__ only if
            # class does not override __new__
            if type_.__new__ is Persistent.__new__:
                for slotname in Persistent._slotnames(self, _v_exclude=False):
                    try:
                        getattr(type_, slotname).__delete__(self)
                    except AttributeError:
                        # AttributeError means slot variable was not
                        # initialized at all - we can simply skip its deletion.
                        pass

        # Implementation detail: deactivating/invalidating
        # updates the size of the cache (if we have one)
        # by telling it this object no longer takes any bytes
        # (-1 is a magic number to compensate for the implementation,
        # which always adds one to the size given)
        try:
            cache = jar._cache
        except AttributeError:
            pass
        else:
            cache.update_object_size_estimation(
                _OGA(self, '_Persistent__oid'), -1)
            # See notes in PickleCache.sweep for why we have to do this
            cache._persistent_deactivate_ran = True

    def _p_getattr(self, name):
        """ See IPersistent.
        """
        if name.startswith('_p_') or name in _SPECIAL_NAMES:
            return True
        self._p_activate()
        self._p_accessed()
        return False

    def _p_setattr(self, name, value):
        """ See IPersistent.
        """
        if name.startswith('_p_'):
            _OSA(self, name, value)
            return True
        self._p_activate()
        self._p_accessed()
        return False

    def _p_delattr(self, name):
        """ See IPersistent.
        """
        if name.startswith('_p_'):
            if name == '_p_oid' and self._p_is_in_cache(
                    _OGA(self, '_Persistent__jar')):
                # The C implementation forbids deleting the oid
                # if we're already in a cache. Match its error message
                raise ValueError('can not change _p_jar of cached object')

            _ODA(self, name)
            return True
        self._p_activate()
        self._p_accessed()
        return False

    # Helper methods:  not APIs:  we name them with '_p_' to bypass
    # the __getattribute__ bit which bumps the cache.
    def _p_register(self):
        jar = _OGA(self, '_Persistent__jar')
        if jar is not None and _OGA(self, '_Persistent__oid') is not None:
            jar.register(self)

    def _p_set_changed_flag(self, value):
        if value:
            before = _OGA(self, '_Persistent__flags')
            after = before | _CHANGED
            if before != after:
                self._p_register()
            _OSA(self, '_Persistent__flags', after)
        else:
            flags = _OGA(self, '_Persistent__flags')
            flags &= ~_CHANGED
            _OSA(self, '_Persistent__flags', flags)

    def _p_accessed(self):
        # Notify the jar's pickle cache that we have been accessed.
        # This relies on what has been (until now) an implementation
        # detail, the '_cache' attribute of the jar.  We made it a
        # private API to avoid the cycle of keeping a reference to
        # the cache on the persistent object.

        # The below is the equivalent of this, but avoids
        # several recursive through __getattribute__, especially for _p_state,
        # and benchmarks much faster
        #
        # if(self.__jar is  None or
        #    self.__oid is None or
        #    self._p_state < 0 ): return

        oga = _OGA
        jar = oga(self, '_Persistent__jar')
        if jar is None:
            return
        oid = oga(self, '_Persistent__oid')
        if oid is None:
            return
        flags = oga(self, '_Persistent__flags')
        if flags is None:  # ghost
            return

        # The KeyError arises in ZODB: ZODB.serialize.ObjectWriter
        # can assign a jar and an oid to newly seen persistent objects,
        # but because they are newly created, they aren't in the
        # pickle cache yet. There doesn't seem to be a way to distinguish
        # that at this level, all we can do is catch it.
        # The AttributeError arises in ZODB test cases
        try:
            jar._cache.mru(oid)
        except (AttributeError, KeyError):
            pass

    def _p_is_in_cache(self, jar=None):
        oid = _OGA(self, '_Persistent__oid')
        if not oid:
            return False

        jar = jar or _OGA(self, '_Persistent__jar')
        cache = getattr(jar, '_cache', None)
        if cache is not None:
            return cache.get(oid) is self
        return None

    def __repr__(self):
        p_repr_str = ''
        p_repr = getattr(type(self), '_p_repr', None)
        if p_repr is not None:
            try:
                return p_repr(self)
            except Exception as e:
                p_repr_str = f' _p_repr {e!r}'

        oid = _OGA(self, '_Persistent__oid')
        jar = _OGA(self, '_Persistent__jar')

        oid_str = ''
        jar_str = ''

        if oid is not None:
            try:
                if isinstance(oid, bytes) and len(oid) == 8:
                    oid_str = f' oid 0x{oid_repr(oid)}'
                else:
                    oid_str = f' oid {oid!r}'
            except Exception as e:
                oid_str = f' oid {e!r}'

        if jar is not None:
            try:
                jar_str = f' in {jar!r}'
            except Exception as e:
                jar_str = f' in {e!r}'

        cls = self.__class__
        return '<{}.{} object at 0x{:x}{}{}{}>'.format(
            # Match the C name for this exact class
            'persistent' if cls is Persistent else cls.__module__,
            'Persistent' if cls is Persistent else cls.__name__,
            id(self),
            oid_str, jar_str, p_repr_str
        )


def _estimated_size_in_24_bits(value):
    if value > 1073741696:
        return 16777215
    return (value // 64) + 1


# This name is bound by the ``@use_c_impl`` decorator to the class defined
# above. We make sure and list it statically, though, to help out linters.
PersistentPy = PersistentPy  # noqa: F821 undefined name 'PersistentPy'
