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
__all__ = ('TimeStamp',)

import datetime
import math
import struct
import sys
import functools
from datetime import timezone

from persistent._compat import use_c_impl

_RAWTYPE = bytes
_MAXINT = sys.maxsize

_ZERO = b'\x00' * 8

__all__ = [
    'TimeStamp',
    'TimeStampPy',
]

try:
    # Make sure to overflow and wraparound just
    # like the C code does.
    from ctypes import c_long
except ImportError: # pragma: no cover
    # XXX: This is broken on 64-bit windows, where
    # sizeof(long) != sizeof(Py_ssize_t)
    # sizeof(long) == 4, sizeof(Py_ssize_t) == 8
    # It can be fixed by setting _MAXINT = 2 ** 31 - 1 on all
    # win32 platforms, but then that breaks PyPy3 64 bit for an unknown
    # reason.
    c_long = None
    def _wraparound(x):
        return int(((x + (_MAXINT + 1)) & ((_MAXINT << 1) + 1)) - (_MAXINT + 1))
else:
    def _wraparound(x):
        return c_long(x).value


def _UTC():
    return timezone.utc


def _makeUTC(y, mo, d, h, mi, s):
    s = round(s, 6) # microsecond precision, to match the C implementation
    usec, sec = math.modf(s)
    sec = int(sec)
    usec = int(usec * 1e6)
    return datetime.datetime(y, mo, d, h, mi, sec, usec, tzinfo=_UTC())

_EPOCH = _makeUTC(1970, 1, 1, 0, 0, 0)

_TS_SECOND_BYTES_BIAS = 60.0 / (1<<16) / (1<<16)

def _makeRaw(year, month, day, hour, minute, second):
    a = (((year - 1900) * 12 + month - 1) * 31 + day - 1)
    a = (a * 24 + hour) * 60 + minute
    b = int(second / _TS_SECOND_BYTES_BIAS) # Don't round() this; the C version just truncates
    return struct.pack('>II', a, b)

def _parseRaw(octets):
    a, b = struct.unpack('>II', octets)
    minute = a % 60
    hour = a // 60 % 24
    day = a // (60 * 24) % 31 + 1
    month = a // (60 * 24 * 31) % 12 + 1
    year = a // (60 * 24 * 31 * 12) + 1900
    second = b * _TS_SECOND_BYTES_BIAS
    return (year, month, day, hour, minute, second)



@use_c_impl
@functools.total_ordering
class TimeStamp:
    __slots__ = ('_raw', '_elements')

    def __init__(self, *args):
        self._elements = None
        if len(args) == 1:
            raw = args[0]
            if not isinstance(raw, _RAWTYPE):
                raise TypeError('Raw octets must be of type: %s' % _RAWTYPE)
            if len(raw) != 8:
                raise TypeError('Raw must be 8 octets')
            self._raw = raw
        elif len(args) == 6:
            self._raw = _makeRaw(*args) # pylint:disable=no-value-for-parameter
            # Note that we don't preserve the incoming arguments in self._elements,
            # we derive them from the raw value. This is because the incoming
            # seconds value could have more precision than would survive
            # in the raw data, so we must be consistent.
        else:
            raise TypeError('Pass either a single 8-octet arg '
                            'or 5 integers and a float')

        self._elements = _parseRaw(self._raw)

    def raw(self):
        return self._raw

    def __repr__(self):
        return repr(self._raw)

    def __str__(self):
        return "%4.4d-%2.2d-%2.2d %2.2d:%2.2d:%09.6f" % (
            self.year(), self.month(), self.day(),
            self.hour(), self.minute(),
            self.second())

    def year(self):
        return self._elements[0]

    def month(self):
        return self._elements[1]

    def day(self):
        return self._elements[2]

    def hour(self):
        return self._elements[3]

    def minute(self):
        return self._elements[4]

    def second(self):
        return self._elements[5]

    def timeTime(self):
        """ -> seconds since epoch, as a float.
        """
        delta = _makeUTC(*self._elements) - _EPOCH
        return delta.days * 86400 + delta.seconds + delta.microseconds / 1e6

    def laterThan(self, other):
        """ Return a timestamp instance which is later than 'other'.

        If self already qualifies, return self.

        Otherwise, return a new instance one moment later than 'other'.
        """
        if not isinstance(other, self.__class__):
            raise ValueError()
        # pylint:disable=protected-access
        if self._raw > other._raw:
            return self
        a, b = struct.unpack('>II', other._raw)
        later = struct.pack('>II', a, b + 1)
        return self.__class__(later)

    def __eq__(self, other):
        try:
            return self.raw() == other.raw()
        except AttributeError:
            return NotImplemented

    def __ne__(self, other):
        try:
            return self.raw() != other.raw()
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        # Match the C implementation
        a = bytearray(self._raw)
        x = a[0] << 7
        for i in a:
            x = (1000003 * x) ^ i
        x ^= 8

        x = _wraparound(x)

        if x == -1: # pragma: no cover
            # The C version has this condition, but it's not clear
            # why; it's also not immediately obvious what bytestring
            # would generate this---hence the no-cover
            x = -2
        return x

    def __lt__(self, other):
        try:
            return self.raw() < other.raw()
        except AttributeError:
            return NotImplemented


# This name is bound by the ``@use_c_impl`` decorator to the class defined above.
# We make sure and list it statically, though, to help out linters.
TimeStampPy = TimeStampPy # pylint:disable=undefined-variable,self-assigning-variable
