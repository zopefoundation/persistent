class TrivialJar:
    """
    Jar that only supports registering objects so ``_p_changed``
    can be tested.
    """

    def register(self, ob):
        """Does nothing"""


class ResettingJar:
    """Testing stub for _p_jar attribute.
    """

    def __init__(self):
        from zope.interface import directlyProvides

        from persistent import PickleCache  # XXX stub it!
        from persistent.interfaces import IPersistentDataManager
        self.cache = self._cache = PickleCache(self)
        self.oid = 1
        self.registered = {}
        directlyProvides(self, IPersistentDataManager)

    def add(self, obj):
        import struct
        obj._p_oid = struct.pack(">Q", self.oid)
        self.oid += 1
        obj._p_jar = self
        self.cache[obj._p_oid] = obj

    # the following methods must be implemented to be a jar

    def setstate(self, obj):
        # Trivial setstate() implementation that just re-initializes
        # the object.  This isn't what setstate() is supposed to do,
        # but it suffices for the tests.
        obj.__class__.__init__(obj)


class RememberingJar:
    """Testing stub for _p_jar attribute.
    """

    def __init__(self):
        from persistent import PickleCache  # XXX stub it!
        self.cache = PickleCache(self)
        self.oid = 1
        self.registered = {}

    def add(self, obj):
        import struct
        obj._p_oid = struct.pack(">Q", self.oid)
        self.oid += 1
        obj._p_jar = self
        self.cache[obj._p_oid] = obj
        # Remember object's state for later.
        self.obj = obj
        self.remembered = obj.__getstate__()

    def fake_commit(self):
        self.remembered = self.obj.__getstate__()
        self.obj._p_changed = 0

    # the following methods must be implemented to be a jar

    def register(self, obj):
        self.registered[obj] = 1

    def setstate(self, obj):
        # Trivial setstate() implementation that resets the object's
        # state as of the time it was added to the jar.
        # This isn't what setstate() is supposed to do,
        # but it suffices for the tests.
        obj.__setstate__(self.remembered)


def copy_test(self, obj):
    import copy

    # Test copy.copy. Do this first, because depending on the
    # version of Python, `UserDict.copy()` may wind up
    # mutating the original object's ``data`` (due to our
    # BWC with ``_container``). This shows up only as a failure
    # of coverage.
    obj.test = [1234]  # Make sure instance vars are also copied.
    obj_copy = copy.copy(obj)
    self.assertIsNot(obj.data, obj_copy.data)
    self.assertEqual(obj.data, obj_copy.data)
    self.assertIs(obj.test, obj_copy.test)

    # Test internal copy
    obj_copy = obj.copy()
    self.assertIsNot(obj.data, obj_copy.data)
    self.assertEqual(obj.data, obj_copy.data)

    return obj_copy


def skipIfNoCExtension(o):
    import unittest

    from persistent._compat import _c_optimizations_available
    from persistent._compat import _c_optimizations_ignored
    from persistent._compat import _should_attempt_c_optimizations

    if _should_attempt_c_optimizations(
    ) and not _c_optimizations_available():  # pragma: no cover
        return unittest.expectedFailure(o)
    return unittest.skipIf(
        _c_optimizations_ignored() or not _c_optimizations_available(),
        "The C extension is not available"
    )(o)
