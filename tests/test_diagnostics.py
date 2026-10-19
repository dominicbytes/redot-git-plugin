"""Regression checks for fail-closed runtime classification."""

import os
import shutil
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from diagnostics import OFFICIAL_26_3, classify, controlled_environment, run_process, sanitize


class DiagnosticsTests(unittest.TestCase):
    def classify(self, output, code=0, **kwargs):
        return classify(output, code, identity=kwargs.pop("identity", OFFICIAL_26_3),
                        result_passed=kwargs.pop("result_passed", True), **kwargs)

    def test_plugin_crash_before_marker_fails(self):
        result = self.classify("CrashHandler: Program crashed\nGitPlugin: Shut down", 139)
        self.assertEqual(result["outcome"], "failed")

    def test_unknown_diagnostic_fails(self):
        self.assertFalse(self.classify("GitPlugin: Shut down\nERROR: unexpected failure")["passed"])

    def test_timeout_fails_even_with_success_output(self):
        self.assertFalse(self.classify("GitPlugin: Shut down", timed_out=True)["passed"])

    def test_exact_official_shutdown_crash_is_classified(self):
        output = "GitPlugin: Shut down\nWARNING: ObjectDB instances leaked at exit (run with --verbose for details).\n   at: cleanup (core/object/object.cpp:1)\nCrashHandler: Program crashed with signal 11"
        for code in (0xC0000005, -1073741819, 139, -11):
            with self.subTest(code=code):
                self.assertEqual(self.classify(output, code)["outcome"], "known_engine_shutdown_crash")

    def test_other_identity_fails(self):
        self.assertFalse(self.classify("GitPlugin: Shut down\nCrashHandler: Program crashed", 139,
                                       identity="26.3.stable.custom_build.85e520394")["passed"])

    def test_failed_result_and_missing_marker_fail(self):
        for text, passed in (("CrashHandler: Program crashed", True),
                             ("GitPlugin: Shut down\nCrashHandler: Program crashed", False)):
            self.assertFalse(self.classify(text, 139, result_passed=passed)["passed"])

    def test_unknown_diagnostic_survives_known_crash_gate(self):
        text = "GitPlugin: Shut down\nERROR: provider load failed\nCrashHandler: Program crashed"
        self.assertFalse(self.classify(text, 139)["passed"])

    def test_leaks_without_known_crash_fail(self):
        text = "GitPlugin: Shut down\nWARNING: ObjectDB instances leaked at exit (run with --verbose for details)."
        self.assertFalse(self.classify(text)["passed"])

    def test_expected_negative_case_is_scoped(self):
        text = "GitPlugin: Shut down\nERROR: GitPlugin: Changes are staged. Make a merge commit.\n   at: push_error (core/variant/variant_utility.cpp:1)"
        self.assertTrue(self.classify(text, scenario="merge")["passed"])
        self.assertFalse(self.classify(text, scenario="local")["passed"])

    def test_controlled_environment_discards_host_git_overrides(self):
        with patch.dict(os.environ, {"GIT_DIR": "poison", "GIT_CONFIG_COUNT": "99"}):
            env = controlled_environment()
        self.assertNotIn("GIT_DIR", env)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "4")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_VALUE_2"], "false")

    @unittest.skipUnless(shutil.which("git"), "Git is required for environment integration")
    def test_host_git_configuration_cannot_break_fixture_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            poison = root / "host.gitconfig"
            poison.write_text("[commit]\n\tgpgsign = true\n", encoding="utf-8")
            with patch.dict(os.environ, {"GIT_DIR": str(root / "missing"),
                                         "GIT_CONFIG_GLOBAL": str(poison)}):
                init = run_process(["git", "init", "--initial-branch=main"], root)
                commit = run_process(["git", "-c", "user.name=Fixture", "-c",
                                      "user.email=fixture@example.invalid", "commit",
                                      "--allow-empty", "-m", "Environment fixture"], root)
            self.assertEqual(init.returncode, 0)
            self.assertEqual(commit.returncode, 0)

    def test_timeout_is_returned_for_classification(self):
        with patch("diagnostics.subprocess.run", side_effect=subprocess.TimeoutExpired(["engine"], 1)):
            result = run_process(["engine"], Path("."), timeout=1)
        self.assertTrue(result.timed_out)

    def test_report_sanitization_preserves_public_urls(self):
        url = "https://redotengine.org/docs/extension"
        self.assertEqual(sanitize(url), url)

    def test_reports_remove_paths_recursively(self):
        path = "Z:" + chr(92) + "private" + chr(92) + "checkout"
        value = sanitize({"command": [path], "output": "Found a repository at " + path})
        self.assertNotIn(path, str(value))
        self.assertIn("<local path>", str(value))


if __name__ == "__main__":
    unittest.main()
