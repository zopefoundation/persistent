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

class _Persistent_Base(object):

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def _makeJar(self):
        from zope.interface import implements
        from persistent.interfaces import IPersistentDataManager

        class _Jar(object):
            implements(IPersistentDataManager)
            def __init__(self):
                self._loaded = []
                self._registered = []
            def setstate(self, obj):
                self._loaded.append(obj._p_oid)
            def register(self, obj):
                self._registered.append(obj._p_oid)

        jar = _Jar()
        jar._cache = self._makeCache(jar)
        return jar

    def _makeOneWithJar(self, klass=None):
        from persistent.timestamp import _makeOctets
        OID = _makeOctets('\x01' * 8)
        if klass is not None:
            inst = klass()
        else:
            inst = self._makeOne()
        jar = self._makeJar()
        jar._cache.new_ghost(OID, inst) # assigns _p_jar, _p_oid
        return inst, jar, OID

    def test_class_conforms_to_IPersistent(self):
        from zope.interface.verify import verifyClass
        from persistent.interfaces import IPersistent
        verifyClass(IPersistent, self._getTargetClass())

    def test_instance_conforms_to_IPersistent(self):
        from zope.interface.verify import verifyObject
        from persistent.interfaces import IPersistent
        verifyObject(IPersistent, self._makeOne())

    def test_ctor(self):
        from persistent.pyPersistence import _INITIAL_SERIAL
        inst = self._makeOne()
        self.assertEqual(inst._p_jar, None)
        self.assertEqual(inst._p_oid, None)
        self.assertEqual(inst._p_serial, _INITIAL_SERIAL)
        self.assertEqual(inst._p_changed, False)
        self.assertEqual(inst._p_sticky, False)
        self.assertEqual(inst._p_status, 'unsaved')

    def test_assign_p_jar_w_new_jar(self):
        inst, jar, OID = self._makeOneWithJar()
        new_jar = self._makeJar()
        def _test():
            inst._p_jar = new_jar
        self.assertRaises(ValueError, _test)

    def test_assign_p_jar_w_valid_jar(self):
        jar = self._makeJar()
        inst = self._makeOne()
        inst._p_jar = jar
        self.assertEqual(inst._p_status, 'saved')
        self.failUnless(inst._p_jar is jar)
        inst._p_jar = jar # reassign only to same DM

    def test_assign_p_oid_w_invalid_oid(self):
        inst, jar, OID = self._makeOneWithJar()
        def _test():
            inst._p_oid = object()
        self.assertRaises(ValueError, _test)

    def test_assign_p_oid_w_valid_oid(self):
        from persistent.timestamp import _makeOctets
        OID = _makeOctets('\x01' * 8)
        inst = self._makeOne()
        inst._p_oid = OID 
        self.assertEqual(inst._p_oid, OID)
        inst._p_oid = OID  # reassign only same OID

    def test_assign_p_oid_w_new_oid_wo_jar(self):
        from persistent.timestamp import _makeOctets
        OID1 = _makeOctets('\x01' * 8)
        OID2 = _makeOctets('\x02' * 8)
        inst = self._makeOne()
        inst._p_oid = OID1
        inst._p_oid = OID2
        self.assertEqual(inst._p_oid, OID2)

    def test_assign_p_oid_w_new_oid_w_jar(self):
        from persistent.timestamp import _makeOctets
        inst, jar, OID = self._makeOneWithJar()
        new_OID = _makeOctets('\x02' * 8)
        def _test():
            inst._p_oid = new_OID
        self.assertRaises(ValueError, _test)

    def test_delete_p_oid_wo_jar(self):
        from persistent.timestamp import _makeOctets
        OID = _makeOctets('\x01' * 8)
        inst = self._makeOne()
        inst._p_oid = OID
        del inst._p_oid
        self.assertEqual(inst._p_oid, None)

    def test_delete_p_oid_w_jar(self):
        inst, jar, OID = self._makeOneWithJar()
        def _test():
            del inst._p_oid
        self.assertRaises(ValueError, _test)

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
            inst._p_serial = '\x01\x02\x03'
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_too_long(self):
        inst = self._makeOne()
        def _test():
            inst._p_serial = '\x01\x02\x03' * 3
        self.assertRaises(ValueError, _test)

    def test_assign_p_serial_w_valid_serial(self):
        from persistent.timestamp import _makeOctets
        SERIAL = _makeOctets('\x01' * 8)
        inst = self._makeOne()
        inst._p_serial = SERIAL 
        self.assertEqual(inst._p_serial, SERIAL)

    def test_delete_p_serial(self):
        from persistent.timestamp import _makeOctets
        from persistent.pyPersistence import _INITIAL_SERIAL
        SERIAL = _makeOctets('\x01' * 8)
        inst = self._makeOne()
        inst._p_serial = SERIAL 
        self.assertEqual(inst._p_serial, SERIAL)
        del(inst._p_serial)
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
        self.failUnless(inst._p_sticky)

    def test_assign_p_sticky_false_non_ghost(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_activate() # XXX
        inst._p_changed = False
        inst._p_sticky = False
        self.failIf(inst._p_sticky)

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
        inst._p_estimated_size = 1073741697 * 1024
        self.assertEqual(inst._p_estimated_size, 16777215 * 64)

    def test___getattribute___p__names(self):
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
        self._clearMRU(jar)
        for name in NAMES:
            getattr(inst, name)
        self._checkMRU(jar, [])

    def test___getattribute__special_name(self):
        from persistent.pyPersistence import SPECIAL_NAMES
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

    def test___setattr___p__names(self):
        from persistent.timestamp import _makeOctets
        SERIAL = _makeOctets('\x01' * 8)
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

    def test___delattr__normal_name_from_ghost(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
        inst, jar, OID = self._makeOneWithJar(Derived)
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

    def test___delattr__normal_name_from_saved(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = False
        self._clearMRU(jar)
        jar._registered = []
        delattr(inst, 'normal')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [OID])
        self.assertEqual(getattr(inst, 'normal', None), 'before')

    def test___delattr__normal_name_from_changed(self):
        class Derived(self._getTargetClass()):
            normal = 'before'
            def __init__(self):
                self.__dict__['normal'] = 'after'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_changed = True
        self._clearMRU(jar)
        jar._registered = []
        delattr(inst, 'normal')
        self._checkMRU(jar, [OID])
        self.assertEqual(jar._registered, [])
        self.assertEqual(getattr(inst, 'normal', None), 'before')

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
            __slots__ = ('foo', '_p_baz', '_v_qux')
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
        from persistent.pyPersistence import _INITIAL_SERIAL
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

    def test___reduce__(self):
        from persistent._compat import copy_reg
        inst = self._makeOne()
        first, second, third = inst.__reduce__()
        self.failUnless(first is copy_reg.__newobj__)
        self.assertEqual(second, (self._getTargetClass(),))
        self.assertEqual(third, None)

    def test___reduce__w_subclass_having_getnewargs(self):
        from persistent._compat import copy_reg
        class Derived(self._getTargetClass()):
            def __getnewargs__(self):
                return ('a', 'b')
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.failUnless(first is copy_reg.__newobj__)
        self.assertEqual(second, (Derived, 'a', 'b'))
        self.assertEqual(third, {})

    def test___reduce__w_subclass_having_getstate(self):
        from persistent._compat import copy_reg
        class Derived(self._getTargetClass()):
            def __getstate__(self):
                return {}
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.failUnless(first is copy_reg.__newobj__)
        self.assertEqual(second, (Derived,))
        self.assertEqual(third, {})

    def test___reduce__w_subclass_having_getnewargs_and_getstate(self):
        from persistent._compat import copy_reg
        class Derived(self._getTargetClass()):
            def __getnewargs__(self):
                return ('a', 'b')
            def __getstate__(self):
                return {'foo': 'bar'}
        inst = Derived()
        first, second, third = inst.__reduce__()
        self.failUnless(first is copy_reg.__newobj__)
        self.assertEqual(second, (Derived, 'a', 'b'))
        self.assertEqual(third, {'foo': 'bar'})

    def test_pickle_roundtrip_simple(self):
        import pickle
        # XXX s.b. 'examples'
        from persistent.tests.cucumbers import Simple
        inst = Simple('testing')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_getnewargs_and_getstate(self):
        import pickle
        # XXX s.b. 'examples'
        from persistent.tests.cucumbers import Custom
        inst = Custom('x', 'y')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_missing_slot(self):
        import pickle
        # XXX s.b. 'examples'
        from persistent.tests.cucumbers import SubSlotted
        inst = SubSlotted('x', 'y', 'z')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_filled_slot(self):
        import pickle
        # XXX s.b. 'examples'
        from persistent.tests.cucumbers import SubSlotted
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
        from persistent.tests.cucumbers import SubSubSlotted
        inst = SubSubSlotted('x', 'y', 'z')
        copy = pickle.loads(pickle.dumps(inst))
        self.assertEqual(copy, inst)
        for protocol in 0, 1, 2:
            copy = pickle.loads(pickle.dumps(inst, protocol))
            self.assertEqual(copy, inst)

    def test_pickle_roundtrip_w_slots_and_filled_dict(self):
        import pickle
        # XXX s.b. 'examples'
        from persistent.tests.cucumbers import SubSubSlotted
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
            self.failUnless(inst._p_getattr(name))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_getattr_w_special_names(self):
        from persistent.pyPersistence import SPECIAL_NAMES
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        for name in SPECIAL_NAMES:
            self.failUnless(inst._p_getattr(name))
            self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_getattr_w_normal_name(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.failIf(inst._p_getattr('normal'))
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [OID])
        self._checkMRU(jar, [OID])

    def test__p_setattr_w__p__name(self):
        from persistent.timestamp import _makeOctets
        SERIAL = _makeOctets('\x01' * 8)
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.failUnless(inst._p_setattr('_p_serial', SERIAL))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_serial, SERIAL)
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_setattr_w_normal_name(self):
        inst, jar, OID = self._makeOneWithJar()
        inst._p_deactivate()
        self.failIf(inst._p_setattr('normal', 'value'))
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
            self.failUnless(inst._p_delattr(name))
        self.assertEqual(inst._p_status, 'ghost')
        self.assertEqual(inst._p_changed, None)
        self.assertEqual(list(jar._loaded), [])
        self._checkMRU(jar, [])

    def test__p_delattr_w_normal_name(self):
        class Derived(self._getTargetClass()):
            normal = 'value'
        inst, jar, OID = self._makeOneWithJar(Derived)
        inst._p_deactivate()
        self.failIf(inst._p_delattr('normal'))
        # _p_delattr doesn't do the actual delete for normal names
        self.assertEqual(inst._p_status, 'saved')
        self.assertEqual(list(jar._loaded), [OID])
        self._checkMRU(jar, [OID])

class PyPersistentTests(unittest.TestCase, _Persistent_Base):

    def _getTargetClass(self):
        from persistent.pyPersistence import Persistent
        return Persistent

    def _makeCache(self, jar):

        class _Cache(object):
            def __init__(self, jar):
                self._jar = jar
                self._mru = []
            def mru(self, oid):
                self._mru.append(oid)
            def new_ghost(self, oid, obj):
                obj._p_jar = self._jar
                obj._p_oid = oid

        return _Cache(jar)

    def _checkMRU(self, jar, value):
        self.assertEqual(list(jar._cache._mru), value)

    def _clearMRU(self, jar):
        jar._cache._mru[:] = []
 
_add_to_suite = [PyPersistentTests]

try:
    from persistent import cPersistence
except ImportError:
    pass
else:
    class CPersistentTests(unittest.TestCase, _Persistent_Base):

        def _getTargetClass(self):
            from persistent.cPersistence import Persistent
            return Persistent

        def _checkMRU(self, jar, value):
            pass # Figure this out later
    
        def _clearMRU(self, jar):
            pass # Figure this out later

        def _makeCache(self, jar):
            from persistent.cPickleCache import PickleCache
            return PickleCache(jar)

    _add_to_suite.append(CPersistentTests)

    class Test_simple_new(unittest.TestCase):

        def _callFUT(self, x):
            from persistent.cPersistence import simple_new
            return simple_new(x)

        def test_w_non_type(self):
            self.assertRaises(TypeError, self._callFUT, '')

        def test_w_type(self):
            for typ in (type, list, dict, tuple, object):
                self.assertTrue(isinstance(self._callFUT(typ), typ))

    _add_to_suite.append(Test_simple_new)

def test_suite():
    return unittest.TestSuite([unittest.makeSuite(x) for x in _add_to_suite])
