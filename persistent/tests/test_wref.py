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
import unittest


class WeakRefTests(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.wref import WeakRef
        return WeakRef

    def _makeOne(self, ob):
        return self._getTargetClass()(ob)

    def test_ctor_target_wo_jar(self):
        from persistent._compat import _b
        target = _makeTarget()
        wref = self._makeOne(target)
        self.assertTrue(wref._v_ob is target)
        self.assertEqual(wref.oid, _b('OID'))
        self.assertTrue(wref.dm is None)
        self.assertFalse('database_name' in wref.__dict__)

    def test_ctor_target_w_jar(self):
        from persistent._compat import _b
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        wref = self._makeOne(target)
        self.assertTrue(wref._v_ob is target)
        self.assertEqual(wref.oid, _b('OID'))
        self.assertTrue(wref.dm is jar)
        self.assertEqual(wref.database_name, 'testing')

    def test___call___target_in_volatile(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        wref = self._makeOne(target)
        self.assertTrue(wref() is target)

    def test___call___target_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        jar[target._p_oid] = target
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertTrue(wref() is target)

    def test___call___target_not_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertTrue(wref() is None)

    def test___hash___w_target(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        wref = self._makeOne(target)
        self.assertEqual(hash(wref), hash(target))

    def test___hash___wo_target(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertRaises(TypeError, hash, wref)

    def test___eq___w_non_weakref(self):
        target = _makeTarget()
        lhs = self._makeOne(target)
        self.assertNotEqual(lhs, object())
        # Test belt-and-suspenders directly
        self.assertFalse(lhs.__eq__(object()))

    def test___eq___w_both_same_target(self):
        target = _makeTarget()
        lhs = self._makeOne(target)
        rhs_target = _makeTarget()
        rhs = self._makeOne(target)
        self.assertEqual(lhs, rhs)

    def test___eq___w_both_different_targets(self):
        lhs_target = _makeTarget(oid='LHS')
        lhs = self._makeOne(lhs_target)
        rhs_target = _makeTarget(oid='RHS')
        rhs = self._makeOne(rhs_target)
        self.assertNotEqual(lhs, rhs)

    def test___eq___w_lhs_gone_target_not_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        lhs = self._makeOne(target)
        del lhs._v_ob
        rhs = self._makeOne(target)
        self.assertRaises(TypeError, lambda: lhs == rhs)

    def test___eq___w_lhs_gone_target_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        jar[target._p_oid] = target
        lhs = self._makeOne(target)
        del lhs._v_ob
        rhs_target = _makeTarget()
        rhs = self._makeOne(target)
        self.assertEqual(lhs, rhs)

    def test___eq___w_rhs_gone_target_not_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        lhs = self._makeOne(target)
        rhs = self._makeOne(target)
        del rhs._v_ob
        self.assertRaises(TypeError, lambda: lhs == rhs)

    def test___eq___w_rhs_gone_target_in_jar(self):
        target = _makeTarget()
        target._p_jar = jar = _makeJar()
        jar[target._p_oid] = target
        lhs = self._makeOne(target)
        rhs = self._makeOne(target)
        del rhs._v_ob
        self.assertEqual(lhs, rhs)


class PersistentWeakKeyDictionaryTests(unittest.TestCase):

    def _getTargetClass(self):
        from persistent.wref import PersistentWeakKeyDictionary
        return PersistentWeakKeyDictionary

    def _makeOne(self, adict, **kw):
        return self._getTargetClass()(adict, **kw)

    def test_ctor_w_adict_none_no_kwargs(self):
        pwkd = self._makeOne(None)
        self.assertEqual(pwkd.data, {})

    def test_ctor_w_adict_as_dict(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne({key: value})
        self.assertTrue(pwkd[key] is value)

    def test_ctor_w_adict_as_items(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne([(key, value)])
        self.assertTrue(pwkd[key] is value)

    def test___getstate___empty(self):
        pwkd = self._makeOne(None)
        self.assertEqual(pwkd.__getstate__(), {'data': []})

    def test___getstate___filled(self):
        from persistent.wref import WeakRef
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne([(key, value)])
        self.assertEqual(pwkd.__getstate__(),
                         {'data': [(WeakRef(key), value)]})

    def test___setstate___empty(self):
        from persistent.wref import WeakRef
        from persistent._compat import _b
        jar = _makeJar()
        KEY = _b('KEY')
        KEY2 = _b('KEY2')
        KEY3 = _b('KEY3')
        VALUE = _b('VALUE')
        VALUE2 = _b('VALUE2')
        VALUE3 = _b('VALUE3')
        key = jar[KEY] = _makeTarget(oid=KEY)
        key._p_jar = jar
        kref = WeakRef(key)
        value = jar[VALUE] = _makeTarget(oid=VALUE)
        value._p_jar = jar
        key2 = _makeTarget(oid=KEY2)
        key2._p_jar = jar # not findable
        kref2 = WeakRef(key2)
        del kref2._v_ob  # force a miss
        value2 = jar[VALUE2] = _makeTarget(oid=VALUE2)
        value2._p_jar = jar
        key3 = jar[KEY3] = _makeTarget(oid=KEY3) # findable
        key3._p_jar = jar
        kref3 = WeakRef(key3)
        del kref3._v_ob  # force a miss, but win in the lookup
        value3 = jar[VALUE3] = _makeTarget(oid=VALUE3)
        value3._p_jar = jar
        pwkd = self._makeOne(None)
        pwkd.__setstate__({'data':
                            [(kref, value), (kref2, value2), (kref3, value3)]})
        self.assertTrue(pwkd[key] is value)
        self.assertTrue(pwkd.get(key2) is None)
        self.assertTrue(pwkd[key3] is value3)

    def test___setitem__(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne(None)
        pwkd[key] = value
        self.assertTrue(pwkd[key] is value)

    def test___getitem___miss(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne(None)
        def _try():
            return pwkd[key]
        self.assertRaises(KeyError, _try)

    def test___delitem__(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne([(key, value)])
        del pwkd[key]
        self.assertTrue(pwkd.get(key) is None)

    def test___delitem___miss(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne(None)
        def _try():
            del pwkd[key]
        self.assertRaises(KeyError, _try)

    def test_get_miss_w_explicit_default(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne(None)
        self.assertTrue(pwkd.get(key, value) is value)

    def test___contains___miss(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        pwkd = self._makeOne(None)
        self.assertFalse(key in pwkd)

    def test___contains___hit(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne([(key, value)])
        self.assertTrue(key in pwkd)

    def test___iter___empty(self):
        jar = _makeJar()
        pwkd = self._makeOne(None)
        self.assertEqual(list(pwkd), [])

    def test___iter___filled(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        pwkd = self._makeOne([(key, value)])
        self.assertEqual(list(pwkd), [key])

    def test_update_w_other_pwkd(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        source = self._makeOne([(key, value)])
        target = self._makeOne(None)
        target.update(source)
        self.assertTrue(target[key] is value)

    def test_update_w_dict(self):
        jar = _makeJar()
        key = jar['key'] = _makeTarget(oid='KEY')
        key._p_jar = jar
        value = jar['value'] = _makeTarget(oid='VALUE')
        value._p_jar = jar
        source = dict([(key, value)])
        target = self._makeOne(None)
        target.update(source)
        self.assertTrue(target[key] is value)
 

def _makeTarget(oid='OID', **kw):
    from persistent import Persistent
    from persistent._compat import _b
    class Derived(Persistent):
        def __hash__(self):
            return hash(self._p_oid)
        def __eq__(self, other):
            return self._p_oid == other._p_oid
        def __repr__(self):
            return 'Derived: %s' % self._p_oid
    derived = Derived()
    for k, v in kw.items():
        setattr(derived, k, v)
    derived._p_oid = _b(oid)
    return derived

def _makeJar():
    class _DB(object):
        database_name = 'testing'
    class _Jar(dict):
        db = lambda self: _DB()
    return _Jar()

def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(WeakRefTests),
        unittest.makeSuite(PersistentWeakKeyDictionaryTests),
    ))
