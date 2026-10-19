"""Regression checks for fail-closed runtime classification."""

import os
import shutil
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from diagnostics import OFFICIAL_26_3, check_process, classify, controlled_environment, run_process, sanitize


class DiagnosticsTests(unittest.TestCase):
    def classify(self, output, code=0, **kwargs):
        return classify(output, code, identity=kwargs.pop("identity", OFFICIAL_26_3),
                        result_passed=kwargs.pop("result_passed", True), **kwargs)

    def test_nonrepo_completed_shutdown_is_classified(self):
        warning = "WARNING: GitPlugin: No existing Git repository was found. Initialize one before enabling version control."
        leak = "WARNING: ObjectDB instances leaked at exit (run with --verbose for details)."
        text = warning + "\nGitPlugin: Shut down\n" + leak
        result = self.classify(text, scenario="nonrepo", providers_freed=True)
        self.assertEqual(result["outcome"], "known_engine_shutdown_leak")
        for output, options in (
            (warning + "\n" + leak, {}),
            (text, {"result_passed": False}),
            (text, {"providers_freed": False}),
            (text, {"scenario": "local"}),
        ):
            with self.subTest(output=output, options=options):
                self.assertFalse(self.classify(output, **({"scenario": "nonrepo", "providers_freed": True} | options))["passed"])

    def test_nonrepo_runner_requires_completed_shutdown(self):
        from run_provider_tests import run_scenario

        warning = "WARNING: GitPlugin: No existing Git repository was found. Initialize one before enabling version control."
        marker = 'REDOT_GIT_PROVIDER_TEST={"scenario":"nonrepo","initialized":false,"passed":true,"providers_freed":true}'
        for shutdown, accepted in (("GitPlugin: Shut down\n", True), ("", False)):
            with self.subTest(shutdown=shutdown):
                process = subprocess.CompletedProcess(
                    ["engine", "--editor", "--", "nonrepo"], 0, warning + "\n" + shutdown + marker, "")
                with patch("run_provider_tests.install_scenario_driver"), patch(
                    "run_provider_tests.run", return_value=process
                ):
                    report = run_scenario(Path("engine"), Path("fixture"), "nonrepo",
                                          "26.2.stable.official.4f5b14aba")
                self.assertEqual(report["passed"], accepted)

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

    def test_leaks_without_completed_shutdown_fail(self):
        text = "WARNING: ObjectDB instances leaked at exit (run with --verbose for details)."
        self.assertFalse(self.classify(text)["passed"])

    def test_exact_official_exit_zero_leaks_are_classified(self):
        lines = (
            "ERROR: 1 RID allocations of type 'N6RendererSceneCull8InstanceE' were leaked at exit.",
            'WARNING: 1 RIDs of type "Canvas" were leaked.',
            "WARNING: ObjectDB instances leaked at exit (run with --verbose for details).",
        )
        for line in lines:
            with self.subTest(line=line):
                text = "GitPlugin: Shut down\n" + line + "\n   at: cleanup (core/object/object.cpp:1)"
                result = self.classify(text, providers_freed=True)
                self.assertTrue(result["passed"])
                self.assertEqual(result["outcome"], "known_engine_shutdown_leak")

    def test_leak_tolerance_requires_exact_identity_and_success(self):
        text = "GitPlugin: Shut down\nWARNING: ObjectDB instances leaked at exit (run with --verbose for details)."
        for options in (
            {"identity": "26.2.stable.official.4f5b14aba"},
            {"identity": "26.3.stable.custom_build.85e520394"},
            {"result_passed": False}, {"providers_freed": False},
            {"providers_freed": "true"}, {"timed_out": True},
            {"provider_active": False},
        ):
            with self.subTest(options=options):
                self.assertFalse(self.classify(text, **options)["passed"])

    def test_leak_tolerance_rejects_other_diagnostics_and_exit_codes(self):
        text = "GitPlugin: Shut down\nWARNING: ObjectDB instances leaked at exit (run with --verbose for details)."
        for extra in ("ERROR: provider load failed", "WARNING: unknown warning", "CrashHandler: Program crashed"):
            with self.subTest(extra=extra):
                self.assertFalse(self.classify(text + "\n" + extra)["passed"])
        for code in (1, 2, 139):
            with self.subTest(code=code):
                self.assertFalse(self.classify(text, code)["passed"])

    def test_clean_shutdown_remains_a_clean_pass(self):
        self.assertEqual(self.classify("GitPlugin: Shut down")["outcome"], "passed")

    def test_shutdown_crash_rejects_unfreed_instances(self):
        text = "GitPlugin: Shut down\nCrashHandler: Program crashed"
        self.assertFalse(self.classify(text, 139, providers_freed=False)["passed"])

    def test_pure_import_crash_without_provider_activity_is_classified(self):
        for code in (0xC0000005, -1073741819, 139, -11):
            for output in ("Import complete\n====", "CrashHandler: Program crashed"):
                with self.subTest(code=code, output=output):
                    result = self.classify(output, code, import_only=True, provider_active=False)
                    self.assertTrue(result["passed"])
                    self.assertEqual(result["outcome"], "known_engine_import_crash")

    def test_import_crash_allows_only_engine_leak_diagnostics(self):
        text = "WARNING: ObjectDB instances leaked at exit (run with --verbose for details).\n   at: cleanup (core/object/object.cpp:1)"
        self.assertTrue(self.classify(text, 139, import_only=True, provider_active=False)["passed"])
        self.assertFalse(self.classify(text + "\nERROR: provider failed", 139,
                                       import_only=True, provider_active=False)["passed"])

    def test_import_exception_rejects_provider_activity_and_frames(self):
        for line in (
            "GitPlugin: Loaded system CA certificates", "Found a repository at <fixture project>",
            "Selected repository path: <fixture project>", "GitPlugin: Shut down",
            "[1] libgit_plugin.windows.editor.x86_64.dll!git_plugin_init",
            "[1] GitPlugin::_initialize", "   at: check_errors (src/git_plugin.cpp:1)",
            "[1] credentials_cb (src/git_callbacks.cpp:1)",
        ):
            with self.subTest(line=line):
                self.assertFalse(self.classify(line + "\nCrashHandler: Program crashed", 139,
                                               import_only=True, provider_active=False)["passed"])

    def test_import_exception_rejects_other_engines_and_failed_results(self):
        for options in (
            {"identity": "26.2.stable.official.4f5b14aba"},
            {"identity": "26.3.stable.custom_build.85e520394"},
            {"result_passed": False}, {"timed_out": True}, {"providers_freed": False},
        ):
            with self.subTest(options=options):
                self.assertFalse(self.classify("CrashHandler: Program crashed", 139,
                                               import_only=True, provider_active=False, **options)["passed"])
        self.assertFalse(self.classify("CrashHandler: Program crashed", 1,
                                       import_only=True, provider_active=False)["passed"])

    def test_real_nonrepo_crash_without_shutdown_remains_fatal(self):
        self.assertFalse(self.classify("Import complete\n====", 0xC0000005,
                                       scenario="nonrepo", provider_active=False)["passed"])
        self.assertFalse(self.classify("CrashHandler: Program crashed", 139,
                                       import_only=True, provider_active=True)["passed"])

    def test_import_tolerance_requires_an_import_only_command(self):
        for arguments, accepted in (
            (["engine", "--editor", "--import"], True),
            (["engine", "--editor"], False),
            (["engine", "--editor", "--import", "--script", "scenario.gd"], False),
            (["engine", "--editor", "--import", "--", "nonrepo"], False),
            (["engine", "--import", "--export-release", "preset"], False),
        ):
            with self.subTest(arguments=arguments):
                process = subprocess.CompletedProcess(arguments, 139, "CrashHandler: Program crashed", "")
                result = check_process(process, identity=OFFICIAL_26_3)
                self.assertEqual(result["passed"], accepted)

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
