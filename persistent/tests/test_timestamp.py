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
import sys

MAX_32_BITS = 2 ** 31 - 1
MAX_64_BITS = 2 ** 63 - 1

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
        before = self._makeOne(2011, 2, 16, 14, 37, 22.80544)
        after = self._makeOne(before.raw())
        self.assertEqual(before.raw(), after.raw())
        self.assertEqual(before.timeTime(), 1297867042.80544)

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
        ERRORS = (ValueError, TypeError)
        SERIAL = _makeOctets('\x01' * 8)
        ts = self._makeOne(SERIAL)
        self.assertRaises(ERRORS, ts.laterThan, None)
        self.assertRaises(ERRORS, ts.laterThan, '')
        self.assertRaises(ERRORS, ts.laterThan, ())
        self.assertRaises(ERRORS, ts.laterThan, [])
        self.assertRaises(ERRORS, ts.laterThan, {})
        self.assertRaises(ERRORS, ts.laterThan, object())

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
        self.assertTrue(later is ts2)

    def test_repr(self):
        from persistent.timestamp import _makeOctets
        SERIAL = _makeOctets('\x01' * 8)
        ts = self._makeOne(SERIAL)
        self.assertEqual(repr(ts), repr(SERIAL))

    def test_comparisons_to_non_timestamps(self):
        import operator
        from persistent._compat import PYTHON2
        # Check the corner cases when comparing non-comparable types
        ts = self._makeOne(2011, 2, 16, 14, 37, 22.0)

        def check_py2(op, passes):
            if passes == 'neither':
                self.assertFalse(op(ts, None))
                self.assertFalse(op(None, ts))
            elif passes == 'both':
                self.assertTrue(op(ts, None))
                self.assertTrue(op(None, ts))
            elif passes == 'first':
                self.assertTrue(op(ts, None))
                self.assertFalse(op(None, ts))
            else:
                self.assertFalse(op(ts, None))
                self.assertTrue(op(None, ts))

        def check_py3(op, passes):
            if passes == 'neither':
                self.assertFalse(op(ts, None))
                self.assertFalse(op(None, ts))
            elif passes == 'both':
                self.assertTrue(op(ts, None))
                self.assertTrue(op(None, ts))
            else:
                self.assertRaises(TypeError, op, ts, None)
                self.assertRaises(TypeError, op, None, ts)

        check = check_py2 if PYTHON2 else check_py3

        for op_name, passes in (('lt', 'second'),
                                ('gt', 'first'),
                                ('le', 'second'),
                                ('ge', 'first'),
                                ('eq', 'neither'),
                                ('ne', 'both')):
            op = getattr(operator, op_name)
            check(op, passes)


class TimeStampTests(pyTimeStampTests):

    def _getTargetClass(self):
        from persistent.timestamp import TimeStamp
        return TimeStamp


class PyAndCComparisonTests(unittest.TestCase):
    """
    Compares C and Python implementations.
    """

    # A particular instant in time
    now = 1229959248.3
    # That instant in time split as the result of this expression:
    #    (time.gmtime(now)[:5] + (now % 60,))
    now_ts_args = (2008, 12, 22, 15, 20, 48.299999952316284)

    def _make_many_instants(self):
        # Given the above data, return many slight variations on
        # it to test matching
        yield self.now_ts_args
        for i in range(2000):
            yield self.now_ts_args[:-1] + (self.now_ts_args[-1] + (i % 60.0)/100.0 , )

    def _makeC(self, *args, **kwargs):
        from persistent.timestamp import TimeStamp
        return TimeStamp(*args, **kwargs)

    def _makePy(self, *args, **kwargs):
        from persistent.timestamp import pyTimeStamp
        return pyTimeStamp(*args, **kwargs)

    @property
    def _is_jython(self):
        import platform
        py_impl = getattr(platform, 'python_implementation', lambda: None)
        return py_impl() == 'Jython'

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
        c, py = self._make_C_and_Py(*self.now_ts_args)
        self.assertEqual(c.raw(), py.raw())

    def test_equal(self):
        c, py = self._make_C_and_Py(*self.now_ts_args)

        self.assertEqual(c, py)

    def test_hash_equal(self):
        c, py = self._make_C_and_Py(*self.now_ts_args)
        self.assertEqual(hash(c), hash(py))

    def test_py_hash_32_64_bit(self):
        # We happen to know that on a 32-bit platform, the hashcode
        # of the c version should be exactly
        # -1419374591
        # and the 64-bit should be exactly:
        # -3850693964765720575
        # Fake out the python version to think it's on a 32-bit
        # platform and test the same; also verify 64 bit
        from persistent import timestamp as MUT
        bit_32_hash = -1419374591
        bit_64_hash = -3850693964765720575
        orig_maxint = MUT._MAXINT

        is_32_bit_hash = orig_maxint == MAX_32_BITS

        orig_c_long = None
        c_int64 = None
        c_int32 = None
        if hasattr(MUT, 'c_long'):
            import ctypes
            orig_c_long = MUT.c_long
            c_int32 = ctypes.c_int32
            c_int64 = ctypes.c_int64
            # win32, even on 64-bit long, has funny sizes
            is_32_bit_hash = c_int32 == ctypes.c_long

        try:
            MUT._MAXINT = MAX_32_BITS
            MUT.c_long = c_int32

            py = self._makePy(*self.now_ts_args)
            self.assertEqual(hash(py), bit_32_hash)

            MUT._MAXINT = int(2 ** 63 - 1)
            MUT.c_long = c_int64
            # call __hash__ directly to avoid interpreter truncation
            # in hash() on 32-bit platforms
            if not self._is_jython:
                self.assertEqual(py.__hash__(), bit_64_hash)
            else:
                # Jython 2.7's ctypes module doesn't properly
                # implement the 'value' attribute by truncating.
                # (It does for native calls, but not visibly to Python).
                # Therefore we get back the full python long. The actual
                # hash() calls are correct, though, because the JVM uses
                # 32-bit ints for its hashCode methods.
                self.assertEqual(
                    py.__hash__(),
                    384009219096809580920179179233996861765753210540033)
        finally:
            MUT._MAXINT = orig_maxint
            if orig_c_long is not None:
                MUT.c_long = orig_c_long
            else:
                del MUT.c_long

        # These are *usually* aliases, but aren't required
        # to be (and aren't under Jython 2.7).
        if is_32_bit_hash:
            self.assertEqual(py.__hash__(), bit_32_hash)
        else:
            self.assertEqual(py.__hash__(), bit_64_hash)

    def test_hash_equal_constants(self):
        # The simple constants make it easier to diagnose
        # a difference in algorithms
        import persistent.timestamp as MUT
        # We get 32-bit hash values on 32-bit platforms, or on the JVM
        # OR on Windows (whether compiled in 64 or 32-bit mode)
        is_32_bit = MUT._MAXINT == (2**31 - 1) or self._is_jython or sys.platform == 'win32'

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
        if is_32_bit:
            self.assertEqual(hash(c), -721379967)
        else:
            self.assertEqual(hash(c), 1000006000001)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x00\x00\x01\x00\x00\x00')
        if is_32_bit:
            self.assertEqual(hash(c), 583896275)
        else:
            self.assertEqual(hash(c), 1000009000027000019)
        self.assertEqual(hash(c), hash(py))

        # Overflow kicks in at this point on 64-bit platforms
        c, py = self._make_C_and_Py(b'\x00\x00\x00\x01\x00\x00\x00\x00')
        if is_32_bit:
            self.assertEqual(hash(c), 1525764953)
        else:
            self.assertEqual(hash(c), -4442925868394654887)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x00\x00\x01\x00\x00\x00\x00\x00')
        if is_32_bit:
            self.assertEqual(hash(c), -429739973)
        else:
            self.assertEqual(hash(c), -3993531167153147845)
        self.assertEqual(hash(c), hash(py))

        c, py = self._make_C_and_Py(b'\x01\x00\x00\x00\x00\x00\x00\x00')
        if is_32_bit:
            self.assertEqual(hash(c), 263152323)
        else:
            self.assertEqual(hash(c), -3099646879006235965)
        self.assertEqual(hash(c), hash(py))

    def test_ordering(self):
        small_c  = self._makeC(b'\x00\x00\x00\x00\x00\x00\x00\x01')
        big_c    = self._makeC(b'\x01\x00\x00\x00\x00\x00\x00\x00')

        small_py = self._makePy(b'\x00\x00\x00\x00\x00\x00\x00\x01')
        big_py = self._makePy(b'\x01\x00\x00\x00\x00\x00\x00\x00')

        self.assertTrue(small_py < big_py)
        self.assertTrue(small_py <= big_py)

        self.assertTrue(small_py < big_c)
        self.assertTrue(small_py <= big_c)
        self.assertTrue(small_py <= small_c)

        self.assertTrue(small_c < big_c)
        self.assertTrue(small_c <= big_c)

        self.assertTrue(small_c <= big_py)
        self.assertTrue(big_c > small_py)
        self.assertTrue(big_c >= big_py)

        self.assertFalse(big_c == small_py)
        self.assertFalse(small_py == big_c)

        self.assertTrue(big_c != small_py)
        self.assertTrue(small_py != big_c)


def test_suite():
    suite = [
        unittest.makeSuite(Test__UTC),
        unittest.makeSuite(pyTimeStampTests),
        unittest.makeSuite(TimeStampTests),
    ]

    try:
        from persistent.timestamp import pyTimeStamp
        from persistent.timestamp import TimeStamp
    except ImportError:
        pass
    else:
        if pyTimeStamp != TimeStamp:
            # We have both implementations available
            suite.append(unittest.makeSuite(PyAndCComparisonTests))

    return unittest.TestSuite(suite)
