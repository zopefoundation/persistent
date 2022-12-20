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

import re
import unittest

import copyreg
from persistent._compat import PYPY
from persistent.tests.utils import skipIfNoCExtension
from collections import UserDict as IterableUserDict

# pylint:disable=R0904,W0212,E1101
# pylint:disable=attribute-defined-outside-init,too-many-lines
# pylint:disable=blacklisted-name,useless-object-inheritance
# Hundreds of unused jar and OID vars make this useless
# pylint:disable=unused-variable


class _Persistent_Base:

    # py2/3 compat
    assertRaisesRegex = getattr(unittest.TestCase,
                                'assertRaisesRegex',
                                unittest.TestCase.assertRaisesRegexp)

    def _getTargetClass(self):
        # concrete testcase classes must override
        raise NotImplementedError()

    def _makeCache(self, jar):
        # concrete testcase classes must override
        raise NotImplementedError()

    def _makeRealCache(self, jar):
        return self._makeCache(jar)

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def _makeJar(self, real_cache=False):
        from zope.interface import implementer
        from persistent.interfaces import IPersistentDataManager

        @implementer(IPersistentDataManager)
        class _Jar:
            _cache = None
            # Set this to a value to have our `setstate`
            # pass it through to the object's __setstate__
            setstate_calls_object = None

            # Set this to a value to have our `setstate`
            # set the _p_serial of the object
            setstate_sets_serial = None
            def __init__(self):
                self._loaded = []
                self._registered = []
            def setstate(self, obj):
                self._loaded.append(obj._p_oid)
                if self.setstate_calls_object is not None:
                    obj.__setstate__(self.setstate_calls_object)
                if self.setstate_sets_serial is not None:
                    obj._p_serial = self.setstate_sets_serial
            def register(self, obj):
                self._registered.append(obj._p_oid)

        jar = _Jar()
        jar._cache = self._makeRealCache(jar) if real_cache else self._makeCache(jar)
        return jar

    def _makeBrokenJar(self):
        from zope.interface import implementer
        from persistent.interfaces import IPersistentDataManager

        @implementer(IPersistentDataManager)
        class _BrokenJar:
            def __init__(self):
                self.called = 0
            def register(self, ob):
                self.called += 1
                raise NotImplementedError()
            def setstate(self, ob):
                raise NotImplementedError()

        jar = _BrokenJar()
        jar._cache = self._makeCache(jar)
        return jar

    def _makeOneWithJar(self, klass=None, broken_jar=False, real_cache=False):
        OID = b'\x01' * 8
        if klass is not None:
            inst = klass()
        else:
            inst = self._makeOne()
        jar = self._makeJar(real_cache=real_cache) if not broken_jar else self._makeBrokenJar()
        jar._cache.new_ghost(OID, inst) # assigns _p_jar, _p_oid
        # Be sure it really returned a ghost.
        assert inst._p_status == 'ghost'
        return inst, jar, OID

    def test_class_conforms_to_IPersistent(self):
        from zope.interface.verify import verifyClass
        from persistent.interfaces import IPersistent
        verifyClass(IPersistent, self._getTargetClass())

    def test_instance_conforms_to_IPersistent(self):
        from zope.interface.verify import verifyObject
        from persistent.interfaces import IPersistent
        verifyObject(IPersistent, self._makeOne())

    def test_instance_cannot_be_weakly_referenced(self):
        if PYPY: # pragma: no cover
            self.skipTest('On PyPy, everything can be weakly referenced')
        import weakref
        inst = self._makeOne()
        with self.assertRaises(TypeError):
            weakref.ref(inst)

    def test_ctor(self):
        from persistent.persistence import _INITIAL_SERIAL
        inst = self._makeOne()
        self.assertEqual(inst._p_jar, None)
        self.assertEqual(inst._p_oid, None)
        self.assertEqual(inst._p_serial, _INITIAL_SERIAL)
        self.assertEqual(inst._p_changed, False)
        self.assertEqual(inst._p_sticky, False)
        self.assertEqual(inst._p_status, 'unsaved')

    def test_del_jar_no_jar(self):
        inst = self._makeOne()
        del inst._p_jar  # does not raise
        self.assertEqual(inst._p_jar, None)

    def test_del_jar_while_in_cache(self):
        inst, _, OID = self._makeOneWithJar()
        def _test():
            del inst._p_jar
        self.assertRaises(ValueError, _test)

    def test_del_jar_like_ZODB_abort(self):
        # When a ZODB connection aborts, it removes registered objects from
        # the cache, deletes their jar, deletes their OID, and finally sets
        # p_changed to false
        inst, jar, OID = self._makeOneWithJar()
        del jar._cache[OID]
        del inst._p_jar
        self.assertEqual(inst._p_jar, None)

    def test_del_jar_of_inactive_object_that_has_no_state(self):
        # If an object is ghosted, and we try to delete its
        # jar, we shouldn't activate the object.

        # Simulate a POSKeyError on _p_activate; this can happen aborting
        # a transaction using ZEO
        broken_jar = self._makeBrokenJar()
        inst = self._makeOne()
        inst._p_oid = 42
        inst._p_jar = broken_jar

        # make it inactive
        inst._p_deactivate()
        self.assertEqual(inst._p_status, "ghost")

        # delete the jar; if we activated the object, the broken
        # jar would raise NotImplementedError
        del inst._p_jar

    def test_assign_p_jar_w_new_jar(self):
        inst, jar, OID = self._makeOneWithJar()
        new_jar = self._makeJar()

        with self.assertRaisesRegex(ValueError,
                                    "can not change _p_jar of cached object"):
            inst._p_jar = new_jar

    def test_assign_p_jar_w_valid_jar(self):
        jar = self._makeJar()
        inst = self._makeOne()
        inst._p_jar = jar
        self.assertEqual(inst._p_status, 'saved')
        self.assertTrue(inst._p_jar is jar)
        inst._p_jar = jar # reassign only to same DM

    def test_assign_p_jar_not_in_cache_allowed(self):
        jar = self._makeJar()
        inst = self._makeOne()
        inst._p_jar = jar
        # Both of these are allowed
        inst._p_jar = self._makeJar()
        inst._p_jar = None
        self.assertEqual(inst._p_jar, None)

    def test_assign_p_oid_w_invalid_oid(self):
        inst, jar, OID = self._makeOneWithJar()

        with self.assertRaisesRegex(ValueError,
                                    'can not change _p_oid of cached object'):
            inst._p_oid = object()

    def test_assign_p_oid_w_valid_oid(self):
        OID = b'\x01' * 8
        inst = self._makeOne()
        inst._p_oid = OID
        self.assertEqual(inst._p_oid, OID)
        inst._p_oid = OID  # reassign only same OID

    def test_assign_p_oid_w_new_oid_wo_jar(self):
        OID1 = b'\x01' * 8
        OID2 = b'\x02' * 8
        inst = self._makeOne()
        inst._p_oid = OID1
        inst._p_oid = OID2
        self.assertEqual(inst._p_oid, OID2)

    def test_assign_p_oid_w_None_wo_jar(self):
        OID1 = b'\x01' * 8
        inst = self._makeOne()
        inst._p_oid = OID1
        inst._p_oid = None
        self.assertEqual(inst._p_oid, None)

    def test_assign_p_oid_w_new_oid_w_jar(self):
        inst, jar, OID = self._makeOneWithJar()
        new_OID = b'\x02' * 8
        def _test():
            inst._p_oid = new_OID
        self.assertRaises(ValueError, _test)

    def test_assign_p_oid_not_in_cache_allowed(self):
        jar = self._makeJar()
        inst = self._makeOne()
        inst._p_jar = jar
        inst._p_oid = 1 # anything goes
        inst._p_oid = 42
        self.assertEqual(inst._p_oid, 42)

    def test_delete_p_oid_wo_jar(self):
        OID = b'\x01' * 8
        inst = self._makeOne()
        inst._p_oid = OID
        del inst._p_oid
        self.assertEqual(inst._p_oid, None)

    def test_delete_p_oid_w_jar(self):
        inst, jar, OID = self._makeOneWithJar()
        with self.assertRaises(ValueError):
            del inst._p_oid

    def test_delete_p_oid_of_subclass_calling_p_delattr(self):
        class P(self._getTargetClass()):
            def __delattr__(self, name):
                super()._p_delattr(name)
                raise AssertionError("Should not get here")

        inst, _jar, _oid = self._makeOneWithJar(klass=P)
        with self.assertRaises(ValueError):
            del inst._p_oid

    def test_del_oid_like_ZODB_abort(self):
        # When a ZODB connection aborts, it removes registered objects from
        # the cache, deletes their jar, deletes their OID, and finally sets
        # p_changed to false
        inst, jar, OID = self._makeOneWithJar()
        del jar._cache[OID]
        del inst._p_oid
        self.assertEqual(inst._p_oid, None)

    def test_assign_p_serial_w_invalid_type(self):
        inst = self._makeOne()
        def _test():
            inst._p_serial = object()
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_w_None(self):
        inst = self._makeOne()
        def _test():
            inst._p_serial = None
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_too_short(self):
        inst = self._makeOne()
        def _test():
            inst._p_serial = b'\x01\x02\x03'
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_too_long(self):
        inst = self._makeOne()
        def _test():
            inst._p_serial = b'\x01\x02\x03' * 3
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_w_valid_serial(self):
        SERIAL = b'\x01' * 8
        inst = self._makeOne()
        inst._p_serial = SERIAL
        self.assertEqual(inst._p_serial, SERIAL)

    def test_delete_p_serial(self):
        from persistent.persistence import _INITIAL_SERIAL
        SERIAL = b'\x01' * 8
        inst = self._makeOne()
        inst._p_serial = SERIAL
        self.assertEqual(inst._p_serial, SERIAL)
        del inst._p_serial
        self.assertEqual(inst._p_serial, _INITIAL_SERIAL)

    def test_query_p_changed_unsaved(self):
        inst = self._makeOne()
        self.assertEqual(inst._p_changed, False)

    def test_query_p_changed_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertEqual(inst._p_changed, None)

    def test_query_p_changed_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        self.assertEqual(inst._p_changed, False)

    def test_query_p_changed_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        self.assertEqual(inst._p_changed, True)

    def test_assign_p_changed_none_from_unsaved(self):
        inst = self._makeOne()
        inst._p_changed = None
        self.assertEqual(inst._p_status, 'unsaved')

    def test_assign_p_changed_true_from_unsaved(self):
        inst = self._makeOne()
        inst._p_changed = True
        self.assertEqual(inst._p_status, 'unsaved')

    def test_assign_p_changed_false_from_unsaved(self):
        inst = self._makeOne()
        inst._p_changed = False
        self.assertEqual(inst._p_status, 'unsaved')

    def test_assign_p_changed_none_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        inst._p_changed = None
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_true_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        inst._p_changed = True
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(list(jar._loaded), [OID])
        self.assertEqual(list(jar._registered), [OID])

    def test_assign_p_changed_false_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        inst._p_changed = False
        self.assertEqual(inst._p_status, 'ghost') # ??? this is what C does
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_none_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        jar._loaded = []
        inst._p_changed = None
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_true_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        jar._loaded[:] = []
        inst._p_changed = True
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [OID])

    def test_assign_p_changed_false_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        jar._loaded = []
        inst._p_changed = False
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_none_from_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_changed = None
        # assigning None is ignored when dirty
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_true_from_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_changed = True
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_false_from_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_changed = False
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_assign_p_changed_none_when_sticky(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        inst._p_changed = None
        self.assertEqual(inst._p_status, 'sticky')
        self.assertEqual(inst._p_changed, False)
        self.assertEqual(inst._p_sticky, True)

    def test_delete_p_changed_from_unsaved(self):
        inst = self._makeOne()
        del inst._p_changed
        self.assertEqual(inst._p_status, 'unsaved')

    def test_delete_p_changed_from_unsaved_w_dict(self):
        class Derived(self._getTargetClass()):
            pass
        inst = Derived()
        inst.foo = 'bar'
        del inst._p_changed
        self.assertEqual(inst._p_status, 'unsaved')
        self.assertEqual(inst.foo, 'bar')

    def test_delete_p_changed_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        del inst._p_changed
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_delete_p_changed_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        jar._loaded = []
        jar._registered = []
        del inst._p_changed
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_delete_p_changed_from_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        del inst._p_changed
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_delete_p_changed_when_sticky(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        del inst._p_changed
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_changed, None)
        self.assertEqual(inst._p_sticky, False)

    def test_assign_p_sticky_true_when_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate() # XXX
        def _test():
            inst._p_sticky = True
        self.assertRaises(ValueError, _test)

    def test_assign_p_sticky_false_when_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate() # XXX
        def _test():
            inst._p_sticky = False
        self.assertRaises(ValueError, _test)

    def test_assign_p_sticky_true_non_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        self.assertTrue(inst._p_sticky)

    def test_assign_p_sticky_false_non_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = False
        self.assertFalse(inst._p_sticky)

    def test__p_status_unsaved(self):
        inst = self._makeOne()
        self.assertEqual(inst._p_status, 'unsaved')

    def test__p_status_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'ghost')

    def test__p_status_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_changed = True
        self.assertEqual(inst._p_status, 'changed')

    def test__p_status_changed_sticky(self):
        # 'sticky' is not a state, but a separate flag.
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        inst._p_sticky = True
        self.assertEqual(inst._p_status, 'sticky')

    def test__p_status_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        self.assertEqual(inst._p_status, 'saved')

    def test__p_status_saved_sticky(self):
        # 'sticky' is not a state, but a separate flag.
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = False
        inst._p_sticky = True
        self.assertEqual(inst._p_status, 'sticky')

    def test__p_mtime_no_serial(self):
        inst = self._makeOne()
        self.assertEqual(inst._p_mtime, None)

    def test__p_mtime_w_serial(self):
        from persistent.timestamp import TimeStamp
        WHEN_TUPLE = (2011, 2, 15, 13, 33, 27.5)
        ts = TimeStamp(*WHEN_TUPLE)
        inst, jar, OID = self._makeOneWithJar()
        inst._p_serial = ts.raw()
        self.assertEqual(inst._p_mtime, ts.timeTime())

    def test__p_mtime_activates_object(self):
        # Accessing _p_mtime implicitly unghostifies the object
        from persistent.timestamp import TimeStamp
        WHEN_TUPLE = (2011, 2, 15, 13, 33, 27.5)
        ts = TimeStamp(*WHEN_TUPLE)
        inst, jar, OID = self._makeOneWithJar()
        jar.setstate_sets_serial = ts.raw()
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_mtime, ts.timeTime())
        self.assertEqual(inst._p_status, 'saved')

    def test__p_state_unsaved(self):
        inst = self._makeOne()
        inst._p_changed = True
        self.assertEqual(inst._p_state, 0)

    def test__p_state_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertEqual(inst._p_state, -1)

    def test__p_state_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_changed = True
        self.assertEqual(inst._p_state, 1)

    def test__p_state_changed_sticky(self):
        # 'sticky' is not a state, but a separate flag.
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        inst._p_sticky = True
        self.assertEqual(inst._p_state, 2)

    def test__p_state_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        self.assertEqual(inst._p_state, 0)

    def test__p_state_saved_sticky(self):
        # 'sticky' is not a state, but a separate flag.
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = False
        inst._p_sticky = True
        self.assertEqual(inst._p_state, 2)

    def test_query_p_estimated_size_new(self):
        inst = self._makeOne()
        self.assertEqual(inst._p_estimated_size, 0)

    def test_query_p_estimated_size_del(self):
        inst = self._makeOne()
        inst._p_estimated_size = 123
        self.assertEqual(inst._p_estimated_size, 128)
        del inst._p_estimated_size
        self.assertEqual(inst._p_estimated_size, 0)

    def test_assign_p_estimated_size_wrong_type(self):
        inst = self._makeOne()

        with self.assertRaises(TypeError):
            inst._p_estimated_size = None

        try:
            constructor = long
        except NameError:
            constructor = str

        with self.assertRaises(TypeError):
            inst._p_estimated_size = constructor(1)

    def test_assign_p_estimated_size_negative(self):
        inst = self._makeOne()
        def _test():
            inst._p_estimated_size = -1
        self.assertRaises(ValueError, _test)

    def test_assign_p_estimated_size_small(self):
        inst = self._makeOne()
        inst._p_estimated_size = 123
        self.assertEqual(inst._p_estimated_size, 128)

    def test_assign_p_estimated_size_just_over_threshold(self):
        inst = self._makeOne()
        inst._p_estimated_size = 1073741697
        self.assertEqual(inst._p_estimated_size, 16777215 * 64)

    def test_assign_p_estimated_size_bigger(self):
        inst = self._makeOne()
        inst._p_estimated_size = 1073741697 * 2
        self.assertEqual(inst._p_estimated_size, 16777215 * 64)

    def test___getattribute___p__names(self):
        NAMES = ['_p_jar',
                 '_p_oid',
                 '_p_changed',
                 '_p_serial',
                 '_p_state',
                 '_p_estimated_size',
                 '_p_sticky',
                 '_p_status',
                ]
        inst, jar, OID = self._makeOneWithJar()
        self._clearMRU(jar)
        for name in NAMES:
            getattr(inst, name)
        self._checkMRU(jar, [])
        # _p_mtime is special, it activates the object
        getattr(inst, '_p_mtime')
        self._checkMRU(jar, [OID])

    def test___getattribute__special_name(self):
        from persistent.persistence import SPECIAL_NAMES
        inst, jar, OID = self._makeOneWithJar()
        self._clearMRU(jar)
        for name in SPECIAL_NAMES:
            getattr(inst, name, None)
        self._checkMRU(jar, [])

    def test___getattribute__normal_name_from_unsaved(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst = Derived()
        self.assertEqual(getattr(inst, 'normal', None), 'value')

    def test___getattribute__normal_name_from_ghost(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_deactivate()
        self._clearMRU(jar)
        self.assertEqual(getattr(inst, 'normal', None), 'value')
        self._checkMRU(jar, [OID])

    def test___getattribute__normal_name_from_saved(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = False
        self._clearMRU(jar)
        self.assertEqual(getattr(inst, 'normal', None), 'value')
        self._checkMRU(jar, [OID])

    def test___getattribute__normal_name_from_changed(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = True
        self._clearMRU(jar)
        self.assertEqual(getattr(inst, 'normal', None), 'value')
        self._checkMRU(jar, [OID])

    def test___getattribute___non_cooperative(self):
        # Getting attributes is NOT cooperative with the superclass.
        # This comes from the C implementation and is maintained
        # for backwards compatibility. (For example, Persistent and
        # ExtensionClass.Base/Acquisition take special care to mix together.)
        class Base:
            def __getattribute__(self, name):
                if name == 'magic':
                    return 42
                return super().__getattribute__(name) # pragma: no cover

        self.assertEqual(getattr(Base(), 'magic'), 42)

        class Derived(self._getTargetClass(), Base):
            pass

        self.assertRaises(AttributeError, getattr, Derived(), 'magic')

    def test___setattr___p__names(self):
        SERIAL = b'\x01' * 8
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        NAMES = [('_p_jar', jar),
                 ('_p_oid', OID),
                 ('_p_changed', False),
                 ('_p_serial', SERIAL),
                 ('_p_estimated_size', 0),
                 ('_p_sticky', False),
                ]
        self._clearMRU(jar)
        for name, value in NAMES:
            setattr(inst, name, value)
        self._checkMRU(jar, [])

    def test___setattr___v__name(self):
        class Derived(self._getTargetClass()):
            pass
        inst, jar, OID = self._makeOneWithJar(Derived)
        self._clearMRU(jar)
        inst._v_foo = 'bar'
        self.assertEqual(inst._p_status, 'saved')
        self._checkMRU(jar, [])

    def test___setattr__normal_name_from_unsaved(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst = Derived()
        setattr(inst, 'normal', 'after')
        self.assertEqual(getattr(inst, 'normal', None), 'after')
        self.assertEqual(inst._p_status, 'unsaved')

    def test___setattr__normal_name_from_ghost(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_deactivate()
        self._clearMRU(jar)
        setattr(inst, 'normal', 'after')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [OID])
        self.assertEqual(getattr(inst, 'normal', None), 'after')
        self.assertEqual(inst._p_status, 'changed')

    def test___setattr__normal_name_from_saved(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = False
        self._clearMRU(jar)
        setattr(inst, 'normal', 'after')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [OID])
        self.assertEqual(getattr(inst, 'normal', None), 'after')
        self.assertEqual(inst._p_status, 'changed')

    def test__setattr__class__from_saved(self):
        # Setting __class__ activates the object and uses
        # the old class's methods to do so. See
        # https://github.com/zopefoundation/persistent/issues/155
        P = self._getTargetClass()

        setstate = []

        class OriginalClass(P):
            def __setstate__(self, state):
                setstate.append(type(self))
                P.__setstate__(self, state)

        class NewClass(P):
            "Does nothing"

        inst, jar, OID = self._makeOneWithJar(OriginalClass)
        # Make the fake jar call __setstate__ when the object is activated
        jar.setstate_calls_object = {}
        inst._p_changed = False
        self._clearMRU(jar)

        # Assigning to __class__...
        inst.__class__ = NewClass
        # ...uses the original __setstate__ method...
        self.assertEqual(setstate, [OriginalClass])
        # ...and activates the object
        self.assertTrue(inst._p_changed)

    def test__setattr__dict__from_saved(self):
        # Setting __dict__ activates the object and uses
        # the old class's methods to do so. See
        # https://github.com/zopefoundation/persistent/issues/155
        class Derived(self._getTargetClass()):
            "Nothing special"

        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = False
        self._clearMRU(jar)

        # Assigning to __dict__...
        inst.__dict__ = {}
        # ...activates the object
        self.assertTrue(inst._p_changed)

    def test___setattr__normal_name_from_changed(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = True
        self._clearMRU(jar)
        jar._registered = []
        setattr(inst, 'normal', 'after')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [])
        self.assertEqual(getattr(inst, 'normal', None), 'after')
        self.assertEqual(inst._p_status, 'changed')

    def test___delattr___p__names(self):
        NAMES = ['_p_changed',
                 '_p_serial',
                ]
        inst, jar, OID = self._makeOneWithJar()
        self._clearMRU(jar)
        jar._registered = []
        for name in NAMES:
            delattr(inst, name)
        self._checkMRU(jar, [])
        self.assertEqual(jar._registered, [])

    def test___delattr__normal_name_from_unsaved(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst = Derived()
        delattr(inst, 'normal')
        self.assertEqual(getattr(inst, 'normal', None), 'before')

    def test___delattr__normal_name_from_ghost(self, real_cache=False):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived, real_cache=real_cache)
        inst._p_deactivate()
        self._clearMRU(jar)
        jar._registered = []
        def _test():
            delattr(inst, 'normal')
        self.assertRaises(AttributeError, _test)
        self.assertEqual(inst._p_status, 'changed') # ??? this is what C does
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [OID])
        self.assertEqual(getattr(inst, 'normal', None), 'before')

    def test___delattr__normal_name_from_ghost_real_cache(self):
        self.test___delattr__normal_name_from_ghost(real_cache=True)

    def test___delattr__normal_name_from_saved(self, real_cache=False):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived, real_cache=real_cache)
        inst._p_changed = False
        self._clearMRU(jar)
        jar._registered = []
        delattr(inst, 'normal')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [OID])
        self.assertEqual(getattr(inst, 'normal', None), 'before')

    def test___delattr__normal_name_from_saved_real_cache(self):
        self.test___delattr__normal_name_from_saved(real_cache=True)

    def test___delattr__normal_name_from_changed(self, real_cache=False):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived, real_cache=real_cache)
        inst._p_changed = True
        self._clearMRU(jar)
        jar._registered = []
        delattr(inst, 'normal')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [])
        self.assertEqual(getattr(inst, 'normal', None), 'before')

    def test___delattr__normal_name_from_changed_real_cache(self):
        self.test___delattr__normal_name_from_changed(real_cache=True)

    def test___getstate__(self):
        inst = self._makeOne()
        self.assertEqual(inst.__getstate__(), None)

    def test___getstate___derived_w_dict(self):
        class Derived(self._getTargetClass()):
            pass
        inst = Derived()
        inst.foo = 'bar'
        inst._p_baz = 'bam'
        inst._v_qux = 'spam'
        self.assertEqual(inst.__getstate__(), {'foo': 'bar'})

    def test___getstate___derived_w_slots(self):
        class Derived(self._getTargetClass()):
            __slots__ = ('foo', 'baz', '_p_baz', '_v_qux')
        inst = Derived()
        inst.foo = 'bar'
        inst._p_baz = 'bam'
        inst._v_qux = 'spam'
        self.assertEqual(inst.__getstate__(), (None, {'foo': 'bar'}))

    def test___getstate___derived_w_slots_in_base_and_derived(self):
        class Base(self._getTargetClass()):
            __slots__ = ('foo',)
        class Derived(Base):
            __slots__ = ('baz', 'qux',)
        inst = Derived()
        inst.foo = 'bar'
        inst.baz = 'bam'
        inst.qux = 'spam'
        self.assertEqual(inst.__getstate__(),
                         (None, {'foo': 'bar', 'baz': 'bam', 'qux': 'spam'}))

    def test___getstate___derived_w_slots_in_base_but_not_derived(self):
        class Base(self._getTargetClass()):
            __slots__ = ('foo',)
        class Derived(Base):
            pass
        inst = Derived()
        inst.foo = 'bar'
        inst.baz = 'bam'
        inst.qux = 'spam'
        self.assertEqual(inst.__getstate__(),
                         ({'baz': 'bam', 'qux': 'spam'}, {'foo': 'bar'}))

    def test___setstate___empty(self):
        inst = self._makeOne()
        inst.__setstate__(None) # doesn't raise, but doesn't change anything

    def test___setstate___nonempty(self):
        from persistent.persistence import _INITIAL_SERIAL
        inst = self._makeOne()
        self.assertRaises((ValueError, TypeError),
                          inst.__setstate__, {'bogus': 1})
        self.assertEqual(inst._p_jar, None)
        self.assertEqual(inst._p_oid, None)
        self.assertEqual(inst._p_serial, _INITIAL_SERIAL)
        self.assertEqual(inst._p_changed, False)
        self.assertEqual(inst._p_sticky, False)

    def test___setstate___nonempty_derived_w_dict(self):
        class Derived(self._getTargetClass()):
            pass
        inst = Derived()
        inst.foo = 'bar'
        inst.__setstate__({'baz': 'bam'})
        self.assertEqual(inst.__dict__, {'baz': 'bam'})

    def test___setstate___nonempty_derived_w_dict_w_two_keys(self):
        class Derived(self._getTargetClass()):
            pass
        inst = Derived()
        inst.foo = 'bar'
        inst.__setstate__({'baz': 'bam', 'biz': 'boz'})
        self.assertEqual(inst.__dict__, {'baz': 'bam', 'biz': 'boz'})

    def test___setstate___derived_w_slots(self):
        class Derived(self._getTargetClass()):
            __slots__ = ('foo', '_p_baz', '_v_qux')
        inst = Derived()
        inst.__setstate__((None, {'foo': 'bar'}))
        self.assertEqual(inst.foo, 'bar')

    def test___setstate___derived_w_slots_in_base_classes(self):
        class Base(self._getTargetClass()):
            __slots__ = ('foo',)
        class Derived(Base):
            __slots__ = ('baz', 'qux',)
        inst = Derived()
        inst.__setstate__((None, {'foo': 'bar', 'baz': 'bam', 'qux': 'spam'}))
        self.assertEqual(inst.foo, 'bar')
        self.assertEqual(inst.baz, 'bam')
        self.assertEqual(inst.qux, 'spam')

    def test___setstate___derived_w_slots_in_base_but_not_derived(self):
        class Base(self._getTargetClass()):
            __slots__ = ('foo',)
        class Derived(Base):
            pass
        inst = Derived()
        inst.__setstate__(({'baz': 'bam', 'qux': 'spam'}, {'foo': 'bar'}))
        self.assertEqual(inst.foo, 'bar')
        self.assertEqual(inst.baz, 'bam')
        self.assertEqual(inst.qux, 'spam')

    if not PYPY:
        def test___setstate___interns_dict_keys(self):
            class Derived(self._getTargetClass()):
                pass
            inst1 = Derived()
            inst2 = Derived()
            key1 = 'key'
            key2 = 'ke'; key2 += 'y'  # construct in a way that won't intern the literal
            self.assertFalse(key1 is key2)
            inst1.__setstate__({key1: 1})
            inst2.__setstate__({key2: 2})
            key1 = list(inst1.__dict__.keys())[0]
            key2 = list(inst2.__dict__.keys())[0]
            self.assertTrue(key1 is key2)

            inst1 = Derived()
            inst2 = Derived()
            key1 = 'key'
            key2 = 'ke'; key2 += 'y'  # construct in a way that won't intern the literal
            self.assertFalse(key1 is key2)
            state1 = IterableUserDict({key1: 1})
            state2 = IterableUserDict({key2: 2})
            k1 = list(state1.keys())[0]
            k2 = list(state2.keys())[0]
            self.assertFalse(k1 is k2)  # verify
            inst1.__setstate__(state1)
            inst2.__setstate__(state2)
            key1 = list(inst1.__dict__.keys())[0]
            key2 = list(inst2.__dict__.keys())[0]
            self.assertTrue(key1 is key2)

    def test___setstate___doesnt_fail_on_non_string_keys(self):
        class Derived(self._getTargetClass()):
            pass
        inst1 = Derived()
        inst1.__setstate__({1: 2})
        self.assertTrue(1 in inst1.__dict__)

        class MyStr(str):
            pass
        mystr = MyStr('mystr')
        inst1.__setstate__({mystr: 2})
        self.assertTrue(mystr in inst1.__dict__)

    def test___setstate___doesnt_fail_on_non_dict(self):
        class Derived(self._getTargetClass()):
            pass
        inst1 = Derived()

        state = IterableUserDict({'foobar': [1, 2]})

        inst1.__setstate__(state)
        self.assertTrue(hasattr(inst1, 'foobar'))

    def test___reduce__(self):
        inst = self._makeOne()
        first, second, third = inst.__reduce__()
        self.assertTrue(first is copyreg.__newobj__)
        self.assertEqual(second, (self._getTargetClass(),))
        self.assertEqual(third, None)

    def test___reduce__w_subclass_having_getnewargs(self):
        class Derived(self._getTargetClass()):
            def __getnewargs__(self):
                return ('a', 'b')
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.assertTrue(first is copyreg.__newobj__)
        self.assertEqual(second, (Derived, 'a', 'b'))
        self.assertEqual(third, {})

    def test___reduce__w_subclass_having_getstate(self):
        class Derived(self._getTargetClass()):
            def __getstate__(self):
                return {}
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.assertTrue(first is copyreg.__newobj__)
        self.assertEqual(second, (Derived,))
        self.assertEqual(third, {})

    def test___reduce__w_subclass_having_getnewargs_and_getstate(self):
        class Derived(self._getTargetClass()):
            def __getnewargs__(self):
                return ('a', 'b')
            def __getstate__(self):
                return {'foo': 'bar'}
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.assertTrue(first is copyreg.__newobj__)
        self.assertEqual(second, (Derived, 'a', 'b'))
        self.assertEqual(third, {'foo': 'bar'})

    def _get_cucumber(self, name):
        # Checks that it's actually a subclass of what we're testing;
        # if it isn't, the test is skipped. The cucumbers module can
        # only subclass either the C or Python implementation, not
        # both
        from persistent.tests import cucumbers
        cls = getattr(cucumbers, name)
        if not issubclass(cls, self._getTargetClass()):
            self.skipTest("Cucumber is not correct implementation")
        return cls

    def test_pickle_roundtrip_simple(self):
        import pickle
        # XXX s.b. 'examples'
        Simple = self._get_cucumber('Simple')
        inst = Simple('testing')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_getnewargs_and_getstate(self):
        import pickle
        # XXX s.b. 'examples'
        Custom = self._get_cucumber('Custom')
        inst = Custom('x', 'y')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_missing_slot(self):
        import pickle
        # XXX s.b. 'examples'
        SubSlotted = self._get_cucumber('SubSlotted')
        inst = SubSlotted('x', 'y', 'z')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_filled_slot(self):
        import pickle
        # XXX s.b. 'examples'
        SubSlotted = self._get_cucumber('SubSlotted')
        inst = SubSlotted('x', 'y', 'z')
        inst.s4 = 'a'
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_and_empty_dict(self):
        import pickle
        # XXX s.b. 'examples'
        SubSubSlotted = self._get_cucumber('SubSubSlotted')
        inst = SubSubSlotted('x', 'y', 'z')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_and_filled_dict(self):
        import pickle
        # XXX s.b. 'examples'
        SubSubSlotted = self._get_cucumber('SubSubSlotted')
        inst = SubSubSlotted('x', 'y', 'z', foo='bar', baz='bam')
        inst.s4 = 'a'
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test__p_activate_from_unsaved(self):
        inst = self._makeOne()
        inst._p_activate() # noop w/o jar
        self.assertEqual(inst._p_status, 'unsaved')

    def test__p_activate_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        inst._p_activate()
        self.assertEqual(inst._p_status, 'saved')

    def test__p_activate_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_changed = False
        inst._p_activate() # noop from 'saved' state
        self.assertEqual(inst._p_status, 'saved')

    def test__p_activate_only_sets_state_once(self):
        inst, jar, OID = self._makeOneWithJar()
        # No matter how many times we call _p_activate, it
        # only sets state once, the first time
        inst._p_invalidate() # make it a ghost
        self.assertEqual(list(jar._loaded), [])

        inst._p_activate()
        self.assertEqual(list(jar._loaded), [OID])

        inst._p_activate()
        self.assertEqual(list(jar._loaded), [OID])

    def test__p_activate_leaves_object_in_saved_even_if_object_mutated_self(self):
        # If the object's __setstate__ set's attributes
        # when called by p_activate, the state is still
        # 'saved' when done. Furthemore, the object is not
        # registered with the jar

        class WithSetstate(self._getTargetClass()):
            state = None
            def __setstate__(self, state):
                self.state = state

        inst, jar, OID = self._makeOneWithJar(klass=WithSetstate)
        inst._p_invalidate() # make it a ghost
        self.assertEqual(inst._p_status, 'ghost')

        jar.setstate_calls_object = 42
        inst._p_activate()
        # It get loaded
        self.assertEqual(list(jar._loaded), [OID])
        # and __setstate__ got called to mutate the object
        self.assertEqual(inst.state, 42)
        # but it's still in the saved state
        self.assertEqual(inst._p_status, 'saved')
        # and it is not registered as changed by the jar
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_from_unsaved(self):
        inst = self._makeOne()
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'unsaved')

    def test__p_deactivate_from_unsaved_w_dict(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst = Derived()
        inst._p_changed = True
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'unsaved')
        self.assertEqual(inst.__dict__, {'normal': 'after'})

    def test__p_deactivate_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        jar._loaded = []
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_from_saved_w_dict(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate()
        jar._loaded = []
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst.__dict__, {})
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_from_changed(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst.normal = 'after'
        jar._loaded = []
        jar._registered = []
        inst._p_deactivate()
        # assigning None is ignored when dirty
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(inst.__dict__, {'normal': 'after'})
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_from_changed_w_dict(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_deactivate()
        # assigning None is ignored when dirty
        self.assertEqual(inst._p_status, 'changed')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_deactivate_when_sticky(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        inst._p_deactivate()
        self.assertEqual(inst._p_status, 'sticky')
        self.assertEqual(inst._p_changed, False)
        self.assertEqual(inst._p_sticky, True)

    def test__p_invalidate_from_unsaved(self):
        inst = self._makeOne()
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'unsaved')

    def test__p_invalidate_from_unsaved_w_dict(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst = Derived()
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'unsaved')
        self.assertEqual(inst.__dict__, {'normal': 'after'})

    def test__p_invalidate_from_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_saved(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        jar._loaded = []
        jar._registered = []
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_saved_w_dict(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate()
        jar._loaded = []
        jar._registered = []
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst.__dict__, {})
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_changed(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_changed_w_dict(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst.__dict__, {})
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_changed_w_slots(self):
        class Derived(self._getTargetClass()):
            __slots__ = {
                'myattr1': 'value1',
                'myattr2': 'value2',
                'unset': None
            }

            def __init__(self):
                self.myattr1 = 'value1'
                self.myattr2 = 'value2'

        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        for slot, expected_value in Derived.__slots__.items():
            slot_descriptor = getattr(Derived, slot)
            if expected_value:
                self.assertEqual(slot_descriptor.__get__(inst), expected_value)
            else:
                with self.assertRaises(AttributeError):
                    slot_descriptor.__get__(inst)

        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])

        for slot in Derived.__slots__:
            __traceback_info__ = slot, inst
            slot_descriptor = getattr(Derived, slot)
            with self.assertRaises(AttributeError):
                slot_descriptor.__get__(inst)

        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test__p_invalidate_from_changed_w_slots_compat(self):
        # check that (for backward-compatibility reason) slots are not released
        # for classes where __new__ is overwritten. Attributes in __dict__
        # should be always released.
        class Derived(self._getTargetClass()):
            __slots__ = ('myattr1', 'myattr2', '__dict__')
            def __new__(cls):
                obj = cls.__base__.__new__(cls)
                obj.myattr1 = 'value1'
                obj.myattr2 = 'value2'
                obj.foo = 'foo1' # .foo & .bar are in __dict__
                obj.bar = 'bar2'
                return obj
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate()
        inst._p_changed = True
        jar._loaded = []
        jar._registered = []
        self.assertEqual(Derived.myattr1.__get__(inst), 'value1')
        self.assertEqual(Derived.myattr2.__get__(inst), 'value2')
        self.assertEqual(inst.__dict__, {'foo': 'foo1', 'bar': 'bar2'})
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(Derived.myattr1.__get__(inst), 'value1')
        self.assertEqual(Derived.myattr2.__get__(inst), 'value2')
        self.assertEqual(inst.__dict__, {})
        self.assertEqual(list(jar._loaded), [])
        self.assertEqual(list(jar._registered), [])

    def test_p_invalidate_with_slots_broken_jar(self):
        # If jar.setstate() raises a POSKeyError (or any error)
        # clearing an object with unset slots doesn't result in a
        # SystemError, the original error is propagated

        class Derived(self._getTargetClass()):
            __slots__ = ('slot1',)

        # Pre-cache in __slotnames__; cpersistent goes directly for this
        # and avoids a call to copyreg. (If it calls the python code in
        # copyreg, the pending exception will be immediately propagated by
        # copyreg, not by us.)
        copyreg._slotnames(Derived)

        inst, jar, OID = self._makeOneWithJar(Derived, broken_jar=True)
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertRaises(NotImplementedError, inst._p_activate)


    def test__p_invalidate_from_sticky(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        self.assertEqual(inst._p_status, 'sticky')
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_changed, None)
        self.assertEqual(inst._p_sticky, False)

    def test__p_invalidate_from_sticky_w_dict(self):
        class Derived(self._getTargetClass()):
            def __init__(self):
                self.normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = True
        inst._p_invalidate()
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_changed, None)
        self.assertEqual(inst._p_sticky, False)
        self.assertEqual(inst.__dict__, {})

    def test__p_getattr_w__p__names(self):
        NAMES = ['_p_jar',
                 '_p_oid',
                 '_p_changed',
                 '_p_serial',
                 '_p_mtime',
                 '_p_state',
                 '_p_estimated_size',
                 '_p_sticky',
                 '_p_status',
                ]
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        for name in NAMES:
            self.assertTrue(inst._p_getattr(name))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_getattr_w_special_names(self):
        from persistent.persistence import SPECIAL_NAMES
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        for name in SPECIAL_NAMES:
            self.assertTrue(inst._p_getattr(name))
            self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_getattr_w_normal_name(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertFalse(inst._p_getattr('normal'))
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [OID])
        self._checkMRU(jar, [OID])

    def test__p_setattr_w__p__name(self):
        SERIAL = b'\x01' * 8
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertTrue(inst._p_setattr('_p_serial', SERIAL))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_serial, SERIAL)
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_setattr_w_normal_name(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.assertFalse(inst._p_setattr('normal', 'value'))
        # _p_setattr doesn't do the actual write for normal names
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [OID])
        self._checkMRU(jar, [OID])

    def test__p_delattr_w__p__names(self):
        NAMES = ['_p_changed',
                 '_p_serial',
                ]
        inst, jar, OID = self._makeOneWithJar()
        inst._p_changed = True
        jar._loaded = []
        for name in NAMES:
            self.assertTrue(inst._p_delattr(name))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_changed, None)
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_delattr_w_normal_name(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_deactivate()
        self.assertFalse(inst._p_delattr('normal'))
        # _p_delattr doesn't do the actual delete for normal names
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [OID])
        self._checkMRU(jar, [OID])

    def test_set__p_changed_w_broken_jar(self):
        # When an object is modified, it registers with its data manager.
        # If that registration fails, the exception is propagated and the
        # object stays in the up-to-date state.
        # It shouldn't change to the modified state, because it won't
        # be saved when the transaction commits.
        class P(self._getTargetClass()):
            def __init__(self):
                self.x = 0

        p = P()
        p._p_oid = b'1'
        p._p_jar = self._makeBrokenJar()
        self.assertEqual(p._p_state, 0)
        self.assertEqual(p._p_jar.called, 0)
        def _try():
            p._p_changed = 1
        self.assertRaises(NotImplementedError, _try)
        self.assertEqual(p._p_jar.called, 1)
        self.assertEqual(p._p_state, 0)

    def test__p_activate_w_broken_jar(self):
        # Make sure that exceptions that occur inside the data manager's
        # ``setstate()`` method propagate out to the caller.
        class P(self._getTargetClass()):
            def __init__(self):
                self.x = 0
        p = P()
        p._p_oid = b'1'
        p._p_jar = self._makeBrokenJar()
        p._p_deactivate()
        self.assertEqual(p._p_state, -1)
        self.assertRaises(NotImplementedError, p._p_activate)
        self.assertEqual(p._p_state, -1)

    def test__ancient_dict_layout_bug(self):
        # We once had a bug in the `Persistent` class that calculated an
        # incorrect offset for the ``__dict__`` attribute.  It assigned
        # ``__dict__`` and ``_p_jar`` to the same location in memory.
        # This is a simple test to make sure they have different locations.
        class P(self._getTargetClass()):
            def __init__(self):
                self.x = 0
            def inc(self):
                self.x += 1
        p = P()
        p.inc()
        p.inc()
        self.assertTrue('x' in p.__dict__)
        self.assertTrue(p._p_jar is None)

    def test_w_diamond_inheritance(self):
        class A(self._getTargetClass()):
            pass
        class B(self._getTargetClass()):
            pass
        class C(A, B):
            pass
        class D:
            pass
        class E(D, B):
            pass
        # no raise
        A(), B(), C(), D(), E()

    def test_w_alternate_metaclass(self):
        class alternateMeta(type):
            pass
        class alternate:
            __metaclass__ = alternateMeta
        class mixedMeta(alternateMeta, type):
            pass
        # no raise
        class mixed1(alternate, self._getTargetClass()):
            pass
        class mixed2(self._getTargetClass(), alternate):
            pass

    def test_setattr_in_subclass_is_not_called_creating_an_instance(self):
        class subclass(self._getTargetClass()):
            _v_setattr_called = False
            def __setattr__(self, name, value):
                raise AssertionError("Should not be called")
        inst = subclass()
        self.assertEqual(object.__getattribute__(inst, '_v_setattr_called'), False)

    def test_can_set__p_attrs_if_subclass_denies_setattr(self):
        # ZODB defines a PersistentBroken subclass that only lets us
        # set things that start with _p, so make sure we can do that
        class Broken(self._getTargetClass()):
            def __setattr__(self, name, value):
                if name.startswith('_p_'):
                    super().__setattr__(name, value)
                else:
                    raise AssertionError("Can't change broken objects")

        KEY = b'123'
        jar = self._makeJar()

        broken = Broken()
        broken._p_oid = KEY
        broken._p_jar = jar

        broken._p_changed = True
        broken._p_changed = 0

    def test_p_invalidate_calls_p_deactivate(self):
        class P(self._getTargetClass()):
            deactivated = False
            def _p_deactivate(self):
                self.deactivated = True
        p = P()
        p._p_invalidate()
        self.assertTrue(p.deactivated)


    def test_new_ghost_success_not_already_ghost_dict(self):
        # https://github.com/zopefoundation/persistent/issues/49
        # calling new_ghost on an object that already has state just changes
        # its flags, it doesn't destroy the state.
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        class TestPersistent(self._getTargetClass()):
            pass
        KEY = b'123'
        jar = self._makeJar()
        cache = self._makeRealCache(jar)
        candidate = TestPersistent()

        candidate.set_by_new = 1
        self.assertEqual(candidate._p_state, UPTODATE)
        cache.new_ghost(KEY, candidate)

        self.assertIs(cache.get(KEY), candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_state, GHOST)
        self.assertEqual(candidate.set_by_new, 1)

    def test_new_ghost_success_not_already_ghost_slot(self):
        # https://github.com/zopefoundation/persistent/issues/49
        # calling new_ghost on an object that already has state just changes
        # its flags, it doesn't destroy the state.
        from persistent.interfaces import GHOST
        from persistent.interfaces import UPTODATE
        class TestPersistent(self._getTargetClass()):
            __slots__ = ('set_by_new', '__weakref__')
        KEY = b'123'
        jar = self._makeJar()
        cache = self._makeRealCache(jar)
        candidate = TestPersistent()
        candidate.set_by_new = 1
        self.assertEqual(candidate._p_state, UPTODATE)
        cache.new_ghost(KEY, candidate)

        self.assertIs(cache.get(KEY), candidate)
        self.assertEqual(candidate._p_oid, KEY)
        self.assertEqual(candidate._p_state, GHOST)
        self.assertEqual(candidate.set_by_new, 1)

    # The number 12345678 as a p64, 8-byte string
    _PACKED_OID = b'\x00\x00\x00\x00\x00\xbcaN'
    # The number 12345678 printed in hex
    _HEX_OID = '0xbc614e'

    def _normalize_repr(self, r):
        # addresses
        r = re.sub(r'at 0x[0-9a-fA-F]*', 'at 0xdeadbeef', r)
        # Python 3.7 removed the trailing , in exception reprs
        r = r.replace("',)", "')")
        return r

    def _normalized_repr(self, o):
        return self._normalize_repr(repr(o))

    def test_repr_no_oid_no_jar(self):
        p = self._makeOne()
        result = self._normalized_repr(p)
        self.assertEqual(result, '<persistent.Persistent object at 0xdeadbeef>')

    def test_repr_no_oid_in_jar(self):
        p = self._makeOne()

        class Jar:
            def __repr__(self):
                return '<SomeJar>'

        p._p_jar = Jar()

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef in <SomeJar>>")

    def test_repr_oid_no_jar(self):
        p = self._makeOne()
        p._p_oid = self._PACKED_OID

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef oid " + self._HEX_OID + ">")

    def test_64bit_oid(self):
        import struct
        p = self._makeOne()
        oid_value = 2 << 62
        self.assertEqual(oid_value.bit_length(), 64)
        oid = struct.pack(">Q", oid_value)
        self.assertEqual(oid, b'\x80\x00\x00\x00\x00\x00\x00\x00')

        p._p_oid = oid
        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            '<persistent.Persistent object at 0xdeadbeef oid 0x8000000000000000>'
        )

    def test_repr_no_oid_repr_jar_raises_exception(self):
        p = self._makeOne()

        class Jar:
            def __repr__(self):
                raise Exception('jar repr failed')

        p._p_jar = Jar()

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef in Exception('jar repr failed')>")


    def test_repr_oid_raises_exception_no_jar(self):
        p = self._makeOne()

        class BadOID(bytes):
            def __repr__(self):
                raise Exception("oid repr failed")

        # Our OID is bytes, 8 bytes long. We don't call its repr.
        p._p_oid = BadOID(self._PACKED_OID)

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef oid " + self._HEX_OID + ">")

        # Anything other than 8 bytes, though, we do.
        p._p_oid = BadOID(b'1234567')

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef oid Exception('oid repr failed')>")


    def test_repr_oid_and_jar_raise_exception(self):
        p = self._makeOne()

        class BadOID(bytes):
            def __repr__(self):
                raise Exception("oid repr failed")
        p._p_oid = BadOID(b'1234567')

        class Jar:
            def __repr__(self):
                raise Exception('jar repr failed')

        p._p_jar = Jar()


        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef oid Exception('oid repr failed')"
            " in Exception('jar repr failed')>")

    def test_repr_no_oid_repr_jar_raises_baseexception(self):
        p = self._makeOne()

        class Jar:
            def __repr__(self):
                raise BaseException('jar repr failed')

        p._p_jar = Jar()
        with self.assertRaisesRegex(BaseException, 'jar repr failed'):
            repr(p)

    def test_repr_oid_raises_baseexception_no_jar(self):
        p = self._makeOne()

        class BadOID(bytes):
            def __repr__(self):
                raise BaseException("oid repr failed")
        p._p_oid = BadOID(b'12345678')

        # An 8 byte byte string doesn't have repr called.
        repr(p)

        # Anything other does.
        p._p_oid = BadOID(b'1234567')
        with self.assertRaisesRegex(BaseException, 'oid repr failed'):
            repr(p)

    def test_repr_oid_and_jar(self):
        p = self._makeOne()
        p._p_oid = self._PACKED_OID

        class Jar:
            def __repr__(self):
                return '<SomeJar>'

        p._p_jar = Jar()

        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.Persistent object at 0xdeadbeef oid " + self._HEX_OID + " in <SomeJar>>")

    def test__p_repr(self):
        class P(self._getTargetClass()):
            def _p_repr(self):
                return "Override"
        p = P()
        self.assertEqual("Override", repr(p))

    def test__p_repr_exception(self):
        class P(self._getTargetClass()):
            def _p_repr(self):
                raise Exception("_p_repr failed")
        p = P()
        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.tests.test_persistence.P object at 0xdeadbeef"
            " _p_repr Exception('_p_repr failed')>")

        p._p_oid = self._PACKED_OID
        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.tests.test_persistence.P object at 0xdeadbeef oid " + self._HEX_OID
            + " _p_repr Exception('_p_repr failed')>")

        class Jar:
            def __repr__(self):
                return '<SomeJar>'

        p._p_jar = Jar()
        result = self._normalized_repr(p)
        self.assertEqual(
            result,
            "<persistent.tests.test_persistence.P object at 0xdeadbeef oid " + self._HEX_OID
            + " in <SomeJar> _p_repr Exception('_p_repr failed')>")

    def test__p_repr_in_instance_ignored(self):
        class P(self._getTargetClass()):
            pass
        p = P()
        p._p_repr = lambda: "Instance"
        result = self._normalized_repr(p)
        self.assertEqual(result,
                         '<persistent.tests.test_persistence.P object at 0xdeadbeef>')

    def test__p_repr_baseexception(self):
        class P(self._getTargetClass()):
            def _p_repr(self):
                raise BaseException("_p_repr failed")
        p = P()
        with self.assertRaisesRegex(BaseException, '_p_repr failed'):
            repr(p)

class PyPersistentTests(unittest.TestCase, _Persistent_Base):

    def _getTargetClass(self):
        from persistent.persistence import PersistentPy
        assert PersistentPy.__module__ == 'persistent.persistence', PersistentPy.__module__
        return PersistentPy

    def _makeCache(self, jar):

        class _Cache:
            def __init__(self, jar):
                self._jar = jar
                self._mru = []
                self._data = {}
            def mru(self, oid):
                self._mru.append(oid)
            def new_ghost(self, oid, obj):
                obj._p_jar = self._jar
                obj._p_oid = oid
                # The C implementation always returns actual ghosts,
                # make sure we do too. However, we can't call
                # _p_deactivate(), because that clears the dictionary.
                # The C pickle cache makes the object a ghost just by
                # setting its status to 'ghost', without going though
                # _p_deactivate(). Thus, we do the same by setting the
                # flags.
                object.__setattr__(obj, '_Persistent__flags', None)
                self._data[oid] = obj
            def get(self, oid):
                return self._data.get(oid)
            def __delitem__(self, oid):
                del self._data[oid]
            def update_object_size_estimation(self, oid, new_size):
                pass

        return _Cache(jar)

    def _getRealCacheClass(self):
        from persistent.picklecache import PickleCachePy as PickleCache
        return PickleCache

    def _makeRealCache(self, jar):
        PickleCache = self._getRealCacheClass()
        return PickleCache(jar, 10)

    def _checkMRU(self, jar, value):
        if not isinstance(jar._cache, self._getRealCacheClass()):
            # We can't do this for the real cache.
            self.assertEqual(list(jar._cache._mru), value)

    def _clearMRU(self, jar):
        if not isinstance(jar._cache, self._getRealCacheClass()):
            # We can't do this for the real cache.
            jar._cache._mru[:] = []

    def test_accessed_with_jar_and_oid_but_not_in_cache(self):
        # This scenario arises in ZODB: ZODB.serialize.ObjectWriter
        # can assign a jar and an oid to newly seen persistent objects,
        # but because they are newly created, they aren't in the
        # pickle cache yet.
        # Nothing should blow up when this happens
        KEY = b'123'
        jar = self._makeJar()
        c1 = self._makeOne()
        c1._p_oid = KEY
        c1._p_jar = jar

        def mru(oid):
            # Mimic what the real cache does
            if oid not in jar._cache._mru:
                raise KeyError(oid)
            raise AssertionError("Should never get here")
        jar._cache.mru = mru
        c1._p_accessed()
        self._checkMRU(jar, [])

    def test_accessed_invalidated_with_jar_and_oid_but_no_cache(self):
        # This scenario arises in ZODB tests where the jar is faked
        KEY = b'123'
        class Jar:
            accessed = False
            def __getattr__(self, name):
                if name == '_cache':
                    self.accessed = True
                raise AttributeError(name)
            def register(self, *args):
                pass
        c1 = self._makeOne()

        c1._p_oid = KEY
        c1._p_jar = Jar()
        c1._p_changed = True
        self.assertEqual(c1._p_state, 1)
        c1._p_accessed()
        self.assertTrue(c1._p_jar.accessed)

        c1._p_jar.accessed = False
        c1._p_invalidate_deactivate_helper()
        self.assertTrue(c1._p_jar.accessed)

        c1._p_jar.accessed = False
        c1._Persistent__flags = None # coverage
        c1._p_invalidate_deactivate_helper()
        self.assertTrue(c1._p_jar.accessed)

    def test_p_activate_with_jar_without_oid(self):
        # Works, but nothing happens
        inst = self._makeOne()
        inst._p_jar = object()
        inst._p_oid = None
        object.__setattr__(inst, '_Persistent__flags', None)
        inst._p_activate()

    def test_p_accessed_with_jar_without_oid(self):
        # Works, but nothing happens
        inst = self._makeOne()
        inst._p_jar = object()
        inst._p_accessed()

    def test_p_accessed_with_jar_with_oid_as_ghost(self):
        # Works, but nothing happens
        inst = self._makeOne()
        inst._p_jar = object()
        inst._p_oid = 42
        inst._Persistent__flags = None
        inst._p_accessed()


@skipIfNoCExtension
class CPersistentTests(unittest.TestCase, _Persistent_Base):

    def _getTargetClass(self):
        from persistent._compat import _c_optimizations_available as get_c
        return get_c()['persistent.persistence'].Persistent

    def _checkMRU(self, jar, value):
        pass # Figure this out later

    def _clearMRU(self, jar):
        pass # Figure this out later

    def _makeCache(self, jar):
        from persistent._compat import _c_optimizations_available as get_c
        PickleCache = get_c()['persistent.picklecache'].PickleCache
        return PickleCache(jar)


@skipIfNoCExtension
class Test_simple_new(unittest.TestCase):

    def _callFUT(self, x):
        from persistent._compat import _c_optimizations_available as get_c
        simple_new = get_c()['persistent.persistence'].simple_new
        return simple_new(x)

    def test_w_non_type(self):
        self.assertRaises(TypeError, self._callFUT, '')

    def test_w_type(self):
        TO_CREATE = [type, list, tuple, object, dict]
        for typ in TO_CREATE:
            self.assertTrue(isinstance(self._callFUT(typ), typ))

def test_suite():
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
