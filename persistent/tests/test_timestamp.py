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
import unittest

class Test__UTC(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.timestamp import _UTC
        return _UTC

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_tzname(self):
        utc = self._makeOne()
        self.assertEqual(utc.tzname(), 'UTC')

    def test_utcoffset(self):
        from datetime import timedelta
        utc = self._makeOne()
        self.assertEqual(utc.utcoffset(object()), timedelta(0))

    def test_dst(self):
        utc = self._makeOne()
        self.assertEqual(utc.dst(), 0)

    def test_fromutc(self):
        source = object()
        utc = self._makeOne()
        self.assertTrue(utc.fromutc(source) is source)


class pyTimeStampTests(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.timestamp import pyTimeStamp
        return pyTimeStamp

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_ctor_invalid_arglist(self):
        BAD_ARGS = [(),
                    (1,),
                    (1, 2),
                    (1, 2, 3),
                    (1, 2, 3, 4),
                    (1, 2, 3, 4, 5),
                    ('1', '2', '3', '4', '5', '6'),
                    (1, 2, 3, 4, 5, 6, 7),
                   ]
        for args in BAD_ARGS:
            self.assertRaises((TypeError, ValueError), self._makeOne, *args)

    def test_ctor_from_invalid_strings(self):
        BAD_ARGS = [''
                    '\x00',
                    '\x00' * 2,
                    '\x00' * 3,
                    '\x00' * 4,
                    '\x00' * 5,
                    '\x00' * 7,
                   ]
        for args in BAD_ARGS:
            self.assertRaises((TypeError, ValueError), self._makeOne, *args)

    def test_ctor_from_string(self):
        from persistent.timestamp import _makeOctets
        from persistent.timestamp import _makeUTC
        ZERO = _makeUTC(1900, 1, 1, 0, 0, 0)
        EPOCH = _makeUTC(1970, 1, 1, 0, 0, 0)
        DELTA = ZERO - EPOCH
        DELTA_SECS = DELTA.days * 86400 + DELTA.seconds
        SERIAL = _makeOctets('\x00' * 8)
        ts = self._makeOne(SERIAL)
        self.assertEqual(ts.raw(), SERIAL)
        self.assertEqual(ts.year(), 1900)
        self.assertEqual(ts.month(), 1)
        self.assertEqual(ts.day(), 1)
        self.assertEqual(ts.hour(), 0)
        self.assertEqual(ts.minute(), 0)
        self.assertEqual(ts.second(), 0.0)
        self.assertEqual(ts.timeTime(), DELTA_SECS)

    def test_ctor_from_string_non_zero(self):
        before = self._makeOne(2011, 2, 16, 14, 37, 22.0)
        after = self._makeOne(before.raw())
        self.assertEqual(before.raw(), after.raw())

    def test_ctor_from_elements(self):
        from persistent.timestamp import _makeOctets
        from persistent.timestamp import _makeUTC
        ZERO = _makeUTC(1900, 1, 1, 0, 0, 0)
        EPOCH = _makeUTC(1970, 1, 1, 0, 0, 0)
        DELTA = ZERO - EPOCH
        DELTA_SECS = DELTA.days * 86400 + DELTA.seconds
        SERIAL = _makeOctets('\x00' * 8)
        ts = self._makeOne(1900, 1, 1, 0, 0, 0.0)
        self.assertEqual(ts.raw(), SERIAL)
        self.assertEqual(ts.year(), 1900)
        self.assertEqual(ts.month(), 1)
        self.assertEqual(ts.day(), 1)
        self.assertEqual(ts.hour(), 0)
        self.assertEqual(ts.minute(), 0)
        self.assertEqual(ts.second(), 0.0)
        self.assertEqual(ts.timeTime(), DELTA_SECS)

    def test_laterThan_invalid(self):
        from persistent.timestamp import _makeOctets
        SERIAL = _makeOctets('\x01' * 8)
        ts = self._makeOne(SERIAL)
        self.assertRaises(ValueError, ts.laterThan, None)
        self.assertRaises(ValueError, ts.laterThan, '')
        self.assertRaises(ValueError, ts.laterThan, ())
        self.assertRaises(ValueError, ts.laterThan, [])
        self.assertRaises(ValueError, ts.laterThan, {})
        self.assertRaises(ValueError, ts.laterThan, object())

    def test_laterThan_self_is_earlier(self):
        from persistent.timestamp import _makeOctets
        SERIAL1 = _makeOctets('\x01' * 8)
        SERIAL2 = _makeOctets('\x02' * 8)
        ts1 = self._makeOne(SERIAL1)
        ts2 = self._makeOne(SERIAL2)
        later = ts1.laterThan(ts2)
        self.assertEqual(later.raw(), _makeOctets('\x02' * 7 + '\x03'))

    def test_laterThan_self_is_later(self):
        from persistent.timestamp import _makeOctets
        SERIAL1 = _makeOctets('\x01' * 8)
        SERIAL2 = _makeOctets('\x02' * 8)
        ts1 = self._makeOne(SERIAL1)
        ts2 = self._makeOne(SERIAL2)
        later = ts2.laterThan(ts1)
        self.failUnless(later is ts2)

    def test_repr(self):
        from persistent.timestamp import _makeOctets
        from persistent._compat import _native
        SERIAL = _makeOctets('\x01' * 8)
        ts = self._makeOne(SERIAL)
        self.assertEqual(repr(ts), _native(SERIAL))

class TimeStampTests(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.timestamp import TimeStamp
        return TimeStamp


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(Test__UTC),
        unittest.makeSuite(pyTimeStampTests),
        unittest.makeSuite(TimeStampTests),
    ))
