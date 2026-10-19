"""Shared, fail-closed engine diagnostics and disposable process environment."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping


OFFICIAL_26_3 = "26.3.stable.official.85e520394"
SHUTDOWN_MARKER = "GitPlugin: Shut down"
CRASH_CODES = {0xC0000005, -1073741819, 139, -11}
CRASH_BANNER = re.compile(r"CrashHandler|Program crashed|handle_crash|Fatal signal|Segmentation fault", re.I)
DIAGNOSTIC = re.compile(r"\b(?:ERROR|WARNING|FATAL):|SCRIPT ERROR|\bCRASH\b|CrashHandler|Program crashed|handle_crash|Segmentation fault", re.I)
LEAK = re.compile(
    r"(?:ERROR: \d+ RID allocations of type '.+' were leaked at exit\."
    r'|WARNING: \d+ RIDs of type ".+" were leaked\.'
    r"|WARNING: ObjectDB instances leaked at exit \(run with --verbose for details\)\.)$"
)
PROVIDER_ACTIVITY = re.compile(
    r"GitPlugin:|GitPlugin::|libgit_plugin|git_plugin\.(?:cpp|h)|git_callbacks\.(?:cpp|h)"
    r"|Found a repository at |Selected repository path:|git_libgit2_init|test_initialize",
    re.I,
)
# Ordinary output accepted by the two additional exit exceptions. Diagnostics
# still pass through the scenario and leak allowlists below.
ENGINE_OUTPUT = re.compile(
    r"Redot Engine v26\.3\.stable\.official\.85e520394 \([0-9 :\-]+ UTC\) - https[:]//redotengine\.org"
    r"|\[\s*(?:\d+%|DONE)\s*\] (?:first_scan_filesystem|update_scripts_classes|loading_editor_layout)(?: \|(?: .*)?)?"
    r"|={3,}"
)
PROVIDER_OUTPUT = re.compile(
    r"Found a repository at .+|Selected repository path: .+"
    r"|GitPlugin: (?:Loaded system CA certificates|Shut down|Already up to date|Fast Forwarded|(?:Fetch|Pull|Push) ended)"
    r"|GitPlugin: Performing (?:(?:fetch|pull) from|push to) [^\r\n]+"
    r"|REDOT_GIT_PROVIDER_TEST=\{.*\}"
    r"|(?:remote: )?Counting objects \d+"
    r"|(?:remote: )?Compressing objects: \d+% \(\d+/\d+\)(?:, done)?"
    r"|Resolving deltas \d+/\d+|Received \d+/\d+ objects \(\d+\) in \d+ bytes"
    r"|Writing Objects: \d+% \(\d+/\d+, \d+ bytes done\.\)"
    r"|\[updated\] (?:[0-9a-f]{7,8}\.\.\.[0-9a-f]{7,8} )?refs/[^\r\n]+"
    r"|\* \[new\] [0-9a-f]{7,8} refs/[^\r\n]+"
    r"|remote: https[:]//\[redacted\]@example\.invalid/repo\?(?:token|%74oken)=\[redacted\](?: \[redacted\]){0,3}"
)
# Only these deliberate negative cases may produce provider diagnostics.
EXPECTED = {
    "nonrepo": (r"WARNING: GitPlugin: No existing Git repository was found\. Initialize one before enabling version control\.",),
    "edge": (
        r"ERROR: GitPlugin: Could not create branch from HEAD\. Error -12: .*refs/heads/invalid branch.*",
        r"ERROR: GitPlugin: Could not delete branch reference of main\. Error -1: .*current HEAD.*",
    ),
    "reject": (r"ERROR: GitPlugin: Failed to push\. Error -11: cannot push because a reference .*",),
    "merge": (r"ERROR: GitPlugin: Changes are staged\. Make a merge commit\.",),
    "pending_pull": (r"ERROR: GitPlugin: Finish or abort the current repository operation before pulling\.",),
    "conflict": (r"ERROR: GitPlugin: Index has conflicts\. Solve conflicts and make a merge commit\.",),
    "security": (
        r"ERROR: GitPlugin: Remote URLs must not contain credentials\. Use Redot's version-control credential fields instead\.",
        r"ERROR: GitPlugin: Push rejected: refs/heads/main hook declined https://\[redacted\]@example\.invalid/repo\?token=\[redacted\](?: \[redacted\]){3}",
        r"ERROR: GitPlugin: Push rejected: refs/heads/main failed to lock file '.+[\\/]refs[\\/]heads[\\/]main\.lock' for writing:(?: .+)?",
        r"ERROR: GitPlugin: Failed to push\. Error -7: remote rejected a reference update in git_plugin\.cpp:GitPlugin::_push#L\d+",
        r"ERROR: GitPlugin: Could not lookup remote \"\[redacted\]\"\. Error -3: remote '\[redacted\]' does not exist in git_plugin\.cpp:GitPlugin::_(?:fetch|pull|push)#L\d+",
    ),
    "transport_redirect": (
        r"ERROR: GitPlugin: Could not connect to remote \"negative-redirect\"\. Are your credentials correct\? Try using a PAT token \(in case you are using Github\) as your password\. Error -1: cannot redirect from 'localhost' to '127\.0\.0\.1' in git_plugin\.cpp:GitPlugin::_(?:fetch|pull)#L\d+",
        r"ERROR: GitPlugin: Failed to push\. Error -1: cannot redirect from 'localhost' to '127\.0\.0\.1' in git_plugin\.cpp:GitPlugin::_push#L\d+",
    ),
    "transport_hook_rejection": (
        r"ERROR: GitPlugin: Push rejected: refs/heads/main pre-receive hook declined",
        r"ERROR: GitPlugin: Failed to push\. Error -7: remote rejected a reference update in git_plugin\.cpp:GitPlugin::_push#L\d+",
    ),
}


def classify(output: str, exit_code: int, *, identity: str, result_passed: bool,
             provider_active: bool = True, scenario: str = "", timed_out: bool = False,
             providers_freed: bool | None = None, import_only: bool = False) -> dict[str, Any]:
    """Separate exact official-engine exit defects from clean provider results."""
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    shutdown = re.search(r"^" + re.escape(SHUTDOWN_MARKER) + r"$", output, re.MULTILINE)
    marker = shutdown.start() if shutdown else -1
    crash = CRASH_BANNER.search(output)
    eligible = (
        not timed_out and identity == OFFICIAL_26_3 and result_passed
        and (providers_freed is None or providers_freed is True)
    )
    bannerless_crash = (
        eligible and exit_code in {0xC0000005, -1073741819} and provider_active
        and marker >= 0 and crash is None and providers_freed is True
    )
    known_crash = bannerless_crash or (
        eligible and exit_code in CRASH_CODES and provider_active and marker >= 0
        and crash is not None and marker < crash.start()
    )
    known_leak = (
        eligible and exit_code == 0 and provider_active and marker >= 0 and crash is None
        and any(LEAK.fullmatch(line.strip()) for line in output.splitlines())
    )
    known_import_crash = (
        eligible and import_only and not provider_active and exit_code in CRASH_CODES
        and PROVIDER_ACTIVITY.search(output) is None
    )
    known_import_leak = (
        eligible and import_only and not provider_active and exit_code == 0 and crash is None
        and PROVIDER_ACTIVITY.search(output) is None
        and any(LEAK.fullmatch(line.strip()) for line in output.splitlines())
    )
    strict_lines = bannerless_crash or known_import_leak
    engine_exit = known_crash or known_leak or known_import_crash or known_import_leak
    failures: list[str] = []
    if timed_out:
        failures.append("engine timed out")
    if not result_passed:
        failures.append("scenario result did not pass")
    if providers_freed is not None and providers_freed is not True:
        failures.append("provider instances were not freed")
    if provider_active and marker < 0:
        failures.append("provider shutdown marker missing")
    if exit_code != 0 and not (known_crash or known_import_crash):
        failures.append(f"engine exited with code {exit_code}")
    allowed_context = False
    offset = 0
    for raw_line in output.splitlines(keepends=True):
        line_start = offset
        offset += len(raw_line)
        line = raw_line.strip()
        # Ordinary output printed while the provider was active belongs to the
        # scenario, whose own assertions already passed. After a banner-less
        # crash only the output following the shutdown marker must be known.
        check_output = strict_lines and not (bannerless_crash and line_start < marker)
        if CRASH_BANNER.search(line):
            if not (known_crash or known_import_crash):
                failures.append("unexpected crash banner")
            continue
        if line.startswith("at:"):
            engine_context = re.fullmatch(
                r"at: (?:_free_rids \(servers/rendering/renderer_canvas_cull\.cpp[:]\d+\)"
                r"|cleanup \(core/object/object\.cpp[:]\d+\)"
                r"|push_(?:warning|error) \(core/variant/variant_utility\.cpp[:]\d+\))", line
            )
            if not allowed_context or (strict_lines and engine_context is None):
                failures.append("unexpected diagnostic context")
            continue
        if DIAGNOSTIC.search(line):
            expected = any(re.fullmatch(pattern, line) for pattern in EXPECTED.get(scenario, ()))
            allowed_context = expected or (engine_exit and LEAK.fullmatch(line) is not None)
            if not allowed_context:
                failures.append("unexpected diagnostic: " + line)
        elif line:
            if check_output:
                if allowed_context and (
                    line == "GDScript backtrace (most recent call first):"
                    or re.fullmatch(r"\[\d+\] \w+ \(res[:]//(?:provider_scenario\.gd|addons/fixture-driver/driver\.gd)[:]\d+\)", line)
                ):
                    continue
                if not (ENGINE_OUTPUT.fullmatch(line) or (
                    provider_active and PROVIDER_OUTPUT.fullmatch(line)
                )):
                    failures.append("unexpected output: " + line)
            allowed_context = False
    outcome = "passed"
    if known_crash:
        outcome = "known_engine_shutdown_crash"
    elif known_leak:
        outcome = "known_engine_shutdown_leak"
    elif known_import_crash:
        outcome = "known_engine_import_crash"
    elif known_import_leak:
        outcome = "known_engine_import_leak"
    return {
        "outcome": "failed" if failures else outcome,
        "passed": not failures,
        "failures": failures,
    }


_environment = tempfile.TemporaryDirectory(prefix="redot-git-environment-")


def controlled_environment() -> dict[str, str]:
    """Ignore host Git configuration and hooks for every child process."""
    directory = Path(_environment.name)
    profile = directory / "profile"
    hooks = directory / "hooks"
    templates = directory / "templates"
    for path in (profile, hooks, templates, profile / "xdg", profile / "appdata", profile / "localappdata"):
        path.mkdir(parents=True, exist_ok=True)
    empty = directory / "empty.gitconfig"
    empty.touch()
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
        "HOME": str(profile), "USERPROFILE": str(profile), "XDG_CONFIG_HOME": str(profile / "xdg"),
        "APPDATA": str(profile / "appdata"), "LOCALAPPDATA": str(profile / "localappdata"),
        "GIT_CONFIG_COUNT": "4",
        "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": str(hooks),
        "GIT_CONFIG_KEY_2": "commit.gpgsign", "GIT_CONFIG_VALUE_2": "false",
        "GIT_CONFIG_KEY_3": "init.templateDir", "GIT_CONFIG_VALUE_3": str(templates),
    })
    return env


def run_process(command: list[str], cwd: Path, *, timeout: int = 45,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = controlled_environment()
    if env is not None:
        process_env.update({key: value for key, value in env.items() if not key.upper().startswith("GIT_")})
    try:
        # Merge streams at the source: shutdown-before-crash ordering is evidence.
        result = subprocess.run(command, cwd=cwd, env=process_env, check=False,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              encoding="utf-8", errors="replace", timeout=timeout)
        result.stderr = ""
        return result
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        result = subprocess.CompletedProcess(command, -1, output, "")
        result.timed_out = True
        return result


def engine_identity(redot: Path, cwd: Path) -> str:
    result = run_process([str(redot), "--headless", "--audio-driver", "Dummy", "--quit-after", "2", "--version"], cwd, timeout=15)
    if result.returncode:
        raise RuntimeError("engine identity check failed")
    return result.stdout.strip()


def check_process(process: subprocess.CompletedProcess[str], *, identity: str,
                  result_passed: bool = True, provider_active: bool = False,
                  scenario: str = "", providers_freed: bool | None = None) -> dict[str, Any]:
    arguments = process.args if isinstance(process.args, (list, tuple)) else []
    import_only = (
        "--import" in arguments and ("--editor" in arguments or "-e" in arguments)
        and not any(flag in arguments for flag in (
            "--script", "-s", "--", "--export-release", "--export-debug", "--export-pack",
        ))
    )
    return classify(process.stdout + (process.stderr or ""), process.returncode,
                    identity=identity, result_passed=result_passed,
                    provider_active=provider_active, scenario=scenario,
                    timed_out=getattr(process, "timed_out", False),
                    providers_freed=providers_freed, import_only=import_only)


def sanitize(value: Any, replacements: Mapping[str, str] | None = None) -> Any:
    """Remove machine paths recursively before a report or exception is printed."""
    if isinstance(value, dict):
        return {sanitize(key, replacements): sanitize(item, replacements) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, replacements) for item in value]
    if not isinstance(value, str):
        return value
    paths = dict(replacements or {})
    paths[_environment.name] = "<controlled environment>"
    for original, replacement in sorted(paths.items(), key=lambda item: len(item[0]), reverse=True):
        for spelling in {original, original.replace("\\", "/"), original.replace("/", "\\")}:
            value = value.replace(spelling, replacement)
    value = re.sub(r"(?<![\w])[A-Za-z]:[\\/][^\r\n\"'<>]*", "<local path>", value)
    value = re.sub(r"\\\\[^\s\"'<>]+", "<local path>", value)
    value = re.sub(r"(?<![/:\w])/(?:[^\s/\"'<>]+/)+[^\s\"'<>]*", "<local path>", value)
    return value
