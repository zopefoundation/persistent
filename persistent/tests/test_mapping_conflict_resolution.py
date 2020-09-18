import unittest

from persistent.tests.utils import TrivialJar
from persistent.mapping import PersistentMapping, PersistentMappingConflictError


class PersistentMappingConflictResolutionTests(unittest.TestCase):
    def _getTargetClass(self):
        return PersistentMapping

    def _makeJar(self):
        return TrivialJar()

    def _makeOne(self, *args, **kwargs):
        inst = self._getTargetClass()(*args, **kwargs)
        inst._p_jar = self._makeJar()
        return inst

    def setUp(self):
        self.one = self._makeOne()

    def test_conflict(self):
        with self.assertRaises(PersistentMappingConflictError):
            self.one._p_resolveConflict(
                {"deeper": {}}, {"deeper": {"foo": "DOH"}}, {"deeper": {"foo": "NEH"}}
            )

    def test_empty(self):
        assert {} == self.one._p_resolveConflict({}, {}, {})

    def test_empty_apply_diff_left(self):
        assert {"foo": "bar"} == self.one._p_resolveConflict({}, {"foo": "bar"}, {})

    def test_empty_apply_diff_right(self):
        assert {"foo": "bar"} == self.one._p_resolveConflict({}, {}, {"foo": "bar"})

    def test_empty_apply_diff_both_same(self):
        assert {"foo": "bar"} == self.one._p_resolveConflict(
            {}, {"foo": "bar"}, {"foo": "bar"}
        )

    def test_empty_apply_diff_both_different(self):
        assert {"foo": "bar", "boo": "far"} == self.one._p_resolveConflict(
            {}, {"boo": "far"}, {"foo": "bar"}
        )

    def test_edit_both_different(self):
        assert {"foo": "after", "bar": "after"} == self.one._p_resolveConflict(
            {"foo": "before", "bar": "before"},
            {"foo": "after", "bar": "before"},
            {"foo": "before", "bar": "after"},
        )

    def test_not_empty_deletion(self):
        assert {} == self.one._p_resolveConflict({"boo": "far"}, {}, {})

    def test_not_empty_apply_diff_left(self):
        assert {"foo": "bar", "boo": "far"} == self.one._p_resolveConflict(
            {"boo": "far"}, {"boo": "far", "foo": "bar"}, {"boo": "far"}
        )

    def test_not_empty_apply_diff_right(self):
        assert {"foo": "bar", "boo": "far"} == self.one._p_resolveConflict(
            {"boo": "far"}, {"boo": "far"}, {"boo": "far", "foo": "bar"}
        )

    def test_not_empty_apply_diff_both_same(self):
        assert {"foo": "bar", "boo": "far"} == self.one._p_resolveConflict(
            {"boo": "far"}, {"boo": "far", "foo": "bar"}, {"boo": "far", "foo": "bar"}
        )

    def test_not_empty_apply_diff_both_different(self):
        assert {
            "foo": "bar",
            "boo": "far",
            "bar": "buz",
        } == self.one._p_resolveConflict(
            {"boo": "far"}, {"boo": "far", "bar": "buz"}, {"boo": "far", "foo": "bar"}
        )

    def test_nested(self):
        assert {"deeper": {}} == self.one._p_resolveConflict(
            {"deeper": {}}, {"deeper": {}}, {"deeper": {}}
        )

    def test_nested_apply_diff_left(self):
        assert {"deeper": {"foo": "bar"}} == self.one._p_resolveConflict(
            {"deeper": {}}, {"deeper": {"foo": "bar"}}, {"deeper": {}}
        )

    def test_nested_apply_diff_right(self):
        assert {"deeper": {"foo": "bar"}} == self.one._p_resolveConflict(
            {"deeper": {}}, {"deeper": {}}, {"deeper": {"foo": "bar"}}
        )

    def test_nested_apply_diff_both_same(self):
        assert {"deeper": {"foo": "bar"}} == self.one._p_resolveConflict(
            {"deeper": {}}, {"deeper": {"foo": "bar"}}, {"deeper": {"foo": "bar"}}
        )

    def test_nested_apply_diff_both_different(self):
        assert {"deeper": {"foo": "bar", "boo": "far"}} == self.one._p_resolveConflict(
            {"deeper": {}}, {"deeper": {"boo": "far"}}, {"deeper": {"foo": "bar"}}
        )
