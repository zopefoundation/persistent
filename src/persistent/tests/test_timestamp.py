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
from contextlib import contextmanager

from persistent.tests.utils import skipIfNoCExtension


class Test__UTC(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.timestamp import _UTC
        return _UTC

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_tzname(self):
        utc = self._makeOne()
        self.assertEqual(utc.tzname(None), 'UTC')

    def test_utcoffset(self):
        from datetime import timedelta
        utc = self._makeOne()
        self.assertEqual(utc.utcoffset(None), timedelta(0))

    def test_dst(self):
        utc = self._makeOne()
        self.assertEqual(utc.dst(None), None)

    def test_fromutc(self):
        import datetime
        source = datetime.datetime.now(self._getTargetClass()())
        utc = self._makeOne()
        self.assertEqual(utc.fromutc(source), source)


class TimeStampTestsMixin:
    # Tests that work for either implementation.

    def _getTargetClass(self):
        raise NotImplementedError

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
                    (b'123',),
                    ]
        for args in BAD_ARGS:
            with self.assertRaises((TypeError, ValueError)):
                self._makeOne(*args)

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
        from persistent.timestamp import _makeUTC
        ZERO = _makeUTC(1900, 1, 1, 0, 0, 0)
        EPOCH = _makeUTC(1970, 1, 1, 0, 0, 0)
        DELTA = ZERO - EPOCH
        DELTA_SECS = DELTA.days * 86400 + DELTA.seconds
        SERIAL = b'\x00' * 8
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
        before = self._makeOne(2011, 2, 16, 14, 37, 22.80544)
        after = self._makeOne(before.raw())
        self.assertEqual(before.raw(), after.raw())
        self.assertEqual(before.timeTime(), 1297867042.80544)

    def test_ctor_from_elements(self):
        from persistent.timestamp import _makeUTC
        ZERO = _makeUTC(1900, 1, 1, 0, 0, 0)
        EPOCH = _makeUTC(1970, 1, 1, 0, 0, 0)
        DELTA = ZERO - EPOCH
        DELTA_SECS = DELTA.days * 86400 + DELTA.seconds
        SERIAL = b'\x00' * 8
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
        ERRORS = (ValueError, TypeError)
        SERIAL = b'\x01' * 8
        ts = self._makeOne(SERIAL)
        self.assertRaises(ERRORS, ts.laterThan, None)
        self.assertRaises(ERRORS, ts.laterThan, '')
        self.assertRaises(ERRORS, ts.laterThan, ())
        self.assertRaises(ERRORS, ts.laterThan, [])
        self.assertRaises(ERRORS, ts.laterThan, {})
        self.assertRaises(ERRORS, ts.laterThan, object())

    def test_laterThan_self_is_earlier(self):
        SERIAL1 = b'\x01' * 8
        SERIAL2 = b'\x02' * 8
        ts1 = self._makeOne(SERIAL1)
        ts2 = self._makeOne(SERIAL2)
        later = ts1.laterThan(ts2)
        self.assertEqual(later.raw(), b'\x02' * 7 + b'\x03')

    def test_laterThan_self_is_later(self):
        SERIAL1 = b'\x01' * 8
        SERIAL2 = b'\x02' * 8
        ts1 = self._makeOne(SERIAL1)
        ts2 = self._makeOne(SERIAL2)
        later = ts2.laterThan(ts1)
        self.assertIs(later, ts2)

    def test_repr(self):
        SERIAL = b'\x01' * 8
        ts = self._makeOne(SERIAL)
        self.assertEqual(repr(ts), repr(SERIAL))

    def test_comparisons_to_non_timestamps(self):
        import operator

        # Check the corner cases when comparing non-comparable types
        ts = self._makeOne(2011, 2, 16, 14, 37, 22.0)

        def check_common(op, passes):
            if passes == 'neither':
                self.assertFalse(op(ts, None))
                self.assertFalse(op(None, ts))
                return True

            if passes == 'both':
                self.assertTrue(op(ts, None))
                self.assertTrue(op(None, ts))
                return True
            return False

        def check(op, passes):
            self.assertRaises(TypeError, op, ts, None)
            self.assertRaises(TypeError, op, None, ts)

        for op_name, passes in (('lt', 'second'),
                                ('gt', 'first'),
                                ('le', 'second'),
                                ('ge', 'first'),
                                ('eq', 'neither'),
                                ('ne', 'both')):
            op = getattr(operator, op_name)
            if not check_common(op, passes):
                check(op, passes)


class Instant:
    # Namespace to hold some constants.

    # A particular instant in time.
    now = 1229959248.3

    # That instant in time split as the result of this expression:
    #    (time.gmtime(now)[:5] + (now % 60,))
    now_ts_args = (2008, 12, 22, 15, 20, 48.299999952316284)

    # We happen to know that on a 32-bit platform, the hashcode
    # of a TimeStamp at that instant should be exactly
    # -1419374591
    # and the 64-bit should be exactly:
    # -3850693964765720575
    bit_32_hash = -1419374591
    bit_64_hash = -3850693964765720575

    MAX_32_BITS = 2 ** 31 - 1
    MAX_64_BITS = 2 ** 63 - 1

    def __init__(self):
        from persistent import timestamp as MUT
        self.MUT = MUT
        self.orig_maxint = MUT._MAXINT

        self.is_32_bit_hash = self.orig_maxint == self.MAX_32_BITS

        self.orig_c_long = None
        self.c_int64 = None
        self.c_int32 = None
        if MUT.c_long is not None:
            import ctypes
            self.orig_c_long = MUT.c_long
            self.c_int32 = ctypes.c_int32
            self.c_int64 = ctypes.c_int64
            # win32, even on 64-bit long, has funny sizes
            self.is_32_bit_hash = self.c_int32 == ctypes.c_long
        self.expected_hash = (
            self.bit_32_hash if self.is_32_bit_hash else self.bit_64_hash)

    @contextmanager
    def _use_hash(self, maxint, c_long):
        try:
            self.MUT._MAXINT = maxint
            self.MUT.c_long = c_long
            yield
        finally:
            self.MUT._MAXINT = self.orig_maxint
            self.MUT.c_long = self.orig_c_long

    def use_32bit(self):
        return self._use_hash(self.MAX_32_BITS, self.c_int32)

    def use_64bit(self):
        return self._use_hash(self.MAX_64_BITS, self.c_int64)


class pyTimeStampTests(TimeStampTestsMixin, unittest.TestCase):
    # Tests specific to the Python implementation

    def _getTargetClass(self):
        from persistent.timestamp import TimeStampPy
        return TimeStampPy

    def test_py_hash_32_64_bit(self):
        # Fake out the python version to think it's on a 32-bit
        # platform and test the same; also verify 64 bit
        instant = Instant()

        with instant.use_32bit():
            py = self._makeOne(*Instant.now_ts_args)
            self.assertEqual(hash(py), Instant.bit_32_hash)

        with instant.use_64bit():
            # call __hash__ directly to avoid interpreter truncation
            # in hash() on 32-bit platforms
            self.assertEqual(py.__hash__(), Instant.bit_64_hash)

        self.assertEqual(py.__hash__(), instant.expected_hash)


class CTimeStampTests(TimeStampTestsMixin, unittest.TestCase):

    def _getTargetClass(self):
        from persistent.timestamp import TimeStamp
        return TimeStamp

    def test_hash_32_or_64_bit(self):
        ts = self._makeOne(*Instant.now_ts_args)
        self.assertIn(hash(ts), (Instant.bit_32_hash, Instant.bit_64_hash))


@skipIfNoCExtension
class PyAndCComparisonTests(unittest.TestCase):
    """
    Compares C and Python implementations.
    """

    def _make_many_instants(self):
        # Given the above data, return many slight variations on
        # it to test matching
        yield Instant.now_ts_args
        for i in range(2000):
            yield Instant.now_ts_args[:-1] + (
                Instant.now_ts_args[-1] + (i % 60.0) / 100.0, )

    def _makeC(self, *args, **kwargs):
        from persistent._compat import _c_optimizations_available as get_c
        return get_c()['persistent.timestamp'].TimeStamp(*args, **kwargs)

    def _makePy(self, *args, **kwargs):
        from persistent.timestamp import TimeStampPy
        return TimeStampPy(*args, **kwargs)

    def _make_C_and_Py(self, *args, **kwargs):
        return self._makeC(*args, **kwargs), self._makePy(*args, **kwargs)

    def test_reprs_equal(self):
        for args in self._make_many_instants():
            c, py = self._make_C_and_Py(*args)
            self.assertEqual(repr(c), repr(py))

    def test_strs_equal(self):
        for args in self._make_many_instants():
            c, py = self._make_C_and_Py(*args)
            self.assertEqual(str(c), str(py))

    def test_raw_equal(self):
        c, py = self._make_C_and_Py(*Instant.now_ts_args)
        self.assertEqual(c.raw(), py.raw())

    def test_equal(self):
        c, py = self._make_C_and_Py(*Instant.now_ts_args)
        self.assertEqual(c, py)

    def test_hash_equal(self):
        c, py = self._make_C_and_Py(*Instant.now_ts_args)
        self.assertEqual(hash(c), hash(py))

    def test_hash_equal_constants(self):
        # The simple constants make it easier to diagnose
        # a difference in algorithms
        is_32_bit = Instant().is_32_bit_hash

        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x00\x00\x00\x00')
        self.assertEqual(hash(c), 8)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x00\x00\x00\x01')
        self.assertEqual(hash(c), 9)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x00\x00\x01\x00')
        self.assertEqual(hash(c), 1000011)
        self.assertEqual(hash(c), hash(py))

        # overflow kicks in here on 32-bit platforms
        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x00\x01\x00\x00')
        expected = -721379967 if is_32_bit else 1000006000001
        self.assertEqual(hash(c), expected)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x01\x00\x00\x00')
        expected = 583896275 if is_32_bit else 1000009000027000019
        self.assertEqual(hash(c), expected)
        self.assertEqual(hash(c), hash(py))

        # Overflow kicks in at this point on 64-bit platforms
        c, py = self._make_C_and_Py(b'\x00\x00\x00\x01\x00\x00\x00\x00')
        expected = 1525764953 if is_32_bit else -4442925868394654887
        self.assertEqual(hash(c), expected)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x01\x00\x00\x00\x00\x00')
        expected = -429739973 if is_32_bit else -3993531167153147845
        self.assertEqual(hash(c), expected)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x01\x00\x00\x00\x00\x00\x00\x00')
        expected = 263152323 if is_32_bit else -3099646879006235965
        self.assertEqual(hash(c), expected)
        self.assertEqual(hash(c), hash(py))

    def test_ordering(self):
        small_c = self._makeC(b'\x00\x00\x00\x00\x00\x00\x00\x01')
        small_py = self._makePy(b'\x00\x00\x00\x00\x00\x00\x00\x01')

        big_c = self._makeC(b'\x01\x00\x00\x00\x00\x00\x00\x00')
        big_py = self._makePy(b'\x01\x00\x00\x00\x00\x00\x00\x00')

        self.assertLess(small_py, big_py)
        self.assertLessEqual(small_py, big_py)

        self.assertLess(small_py, big_c)
        self.assertLessEqual(small_py, big_c)
        self.assertLessEqual(small_py, small_c)

        self.assertLess(small_c, big_c)
        self.assertLessEqual(small_c, big_c)

        self.assertLessEqual(small_c, big_py)
        self.assertGreater(big_c, small_py)
        self.assertGreaterEqual(big_c, big_py)

        self.assertNotEqual(big_c, small_py)
        self.assertNotEqual(small_py, big_c)

        self.assertNotEqual(big_c, small_py)
        self.assertNotEqual(small_py, big_c)

    def test_seconds_precision(self, seconds=6.123456789):
        # https://github.com/zopefoundation/persistent/issues/41
        args = (2001, 2, 3, 4, 5, seconds)
        c = self._makeC(*args)
        py = self._makePy(*args)

        self.assertEqual(c, py)
        self.assertEqual(c.second(), py.second())

        py2 = self._makePy(c.raw())
        self.assertEqual(py2, c)

        c2 = self._makeC(c.raw())
        self.assertEqual(c2, c)

    def test_seconds_precision_half(self):
        # make sure our rounding matches
        self.test_seconds_precision(seconds=6.5)
        self.test_seconds_precision(seconds=6.55)
        self.test_seconds_precision(seconds=6.555)
        self.test_seconds_precision(seconds=6.5555)
        self.test_seconds_precision(seconds=6.55555)
        self.test_seconds_precision(seconds=6.555555)
        self.test_seconds_precision(seconds=6.5555555)
        self.test_seconds_precision(seconds=6.55555555)
        self.test_seconds_precision(seconds=6.555555555)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
