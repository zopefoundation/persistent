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

    def _makeTarget(self, **kw):
        from persistent import Persistent
        class Derived(Persistent):
            def __eq__(self, other):
                return self._p_oid == other._p_oid
        derived = Derived()
        for k, v in kw.items():
            setattr(derived, k, v)
        derived._p_oid = 'OID'
        return derived

    def _makeJar(self):
        class _DB(object):
            database_name = 'testing'
        class _Jar(dict):
            db = lambda self: _DB()
        return _Jar()

    def _makeOne(self, ob):
        return self._getTargetClass()(ob)

    def test_ctor_target_wo_jar(self):
        target = self._makeTarget()
        wref = self._makeOne(target)
        self.assertTrue(wref._v_ob is target)
        self.assertEqual(wref.oid, 'OID')
        self.assertTrue(wref.dm is None)
        self.assertFalse('database_name' in wref.__dict__)

    def test_ctor_target_w_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        wref = self._makeOne(target)
        self.assertTrue(wref._v_ob is target)
        self.assertEqual(wref.oid, 'OID')
        self.assertTrue(wref.dm is jar)
        self.assertEqual(wref.database_name, 'testing')

    def test___call___target_in_volatile(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        wref = self._makeOne(target)
        self.assertTrue(wref() is target)

    def test___call___target_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        jar[target._p_oid] = target
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertTrue(wref() is target)

    def test___call___target_not_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertTrue(wref() is None)

    def test___hash___w_target(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        wref = self._makeOne(target)
        self.assertEqual(hash(wref), hash(target))

    def test___hash___wo_target(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        wref = self._makeOne(target)
        del wref._v_ob
        self.assertRaises(TypeError, hash, wref)

    def test___eq___w_both_same_target(self):
        target = self._makeTarget()
        lhs = self._makeOne(target)
        rhs_target = self._makeTarget()
        rhs = self._makeOne(target)
        self.assertEqual(lhs, rhs)

    def test___eq___w_both_different_targets(self):
        lhs_target = self._makeTarget()
        lhs_target._p_oid = 'LHS'
        lhs = self._makeOne(lhs_target)
        rhs_target = self._makeTarget()
        rhs_target._p_oid = 'RHS'
        rhs = self._makeOne(rhs_target)
        self.assertNotEqual(lhs, rhs)

    def test___eq___w_lhs_gone_target_not_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        lhs = self._makeOne(target)
        del lhs._v_ob
        rhs = self._makeOne(target)
        self.assertRaises(TypeError, lambda: lhs == rhs)

    def test___eq___w_lhs_gone_target_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        jar[target._p_oid] = target
        lhs = self._makeOne(target)
        del lhs._v_ob
        rhs_target = self._makeTarget()
        rhs = self._makeOne(target)
        self.assertEqual(lhs, rhs)

    def test___eq___w_rhs_gone_target_not_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        lhs = self._makeOne(target)
        rhs = self._makeOne(target)
        del rhs._v_ob
        self.assertRaises(TypeError, lambda: lhs == rhs)

    def test___eq___w_rhs_gone_target_in_jar(self):
        target = self._makeTarget()
        target._p_jar = jar = self._makeJar()
        jar[target._p_oid] = target
        lhs = self._makeOne(target)
        rhs = self._makeOne(target)
        del rhs._v_ob
        self.assertEqual(lhs, rhs)


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(WeakRefTests),
    ))
