"""Regression checks for the engine loader's minimum-version rules."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("compare_vcs_api", Path(__file__).resolve().parents[1] / "scripts" / "compare_vcs_api.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class LoaderCompatibilityTests(unittest.TestCase):
    def test_pre_4_1_minima_are_rejected(self):
        for minimum in ("0", "3.9", "4.0", "4.0.99"):
            self.assertFalse(contract.loader_accepts(minimum, (26, 3, 0), (4, 5, 2)))

    def test_redot_version_is_used_before_godot_fallback(self):
        self.assertTrue(contract.loader_accepts("26.2", (26, 3, 0), (4, 5, 2)))
        self.assertFalse(contract.loader_accepts("26.4", (26, 3, 0), (4, 5, 2)))

    def test_godot_fallback_respects_disable_flag(self):
        self.assertTrue(contract.loader_accepts("4.3", (4, 2, 0), (4, 5, 2)))
        self.assertFalse(contract.loader_accepts("4.3", (4, 2, 0), (4, 5, 2), True))

    def test_retained_minimum_accepts_both_targets(self):
        for version in ((26, 2, 0), (26, 3, 0)):
            self.assertTrue(contract.loader_accepts("4.3", version, (4, 5, 2)))


if __name__ == "__main__":
    unittest.main()
