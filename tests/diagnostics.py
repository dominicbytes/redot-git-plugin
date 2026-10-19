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
# Only these deliberate negative cases may produce provider diagnostics.
EXPECTED = {
    "nonrepo": (r"WARNING: GitPlugin: No existing Git repository was found\. Initialize one before enabling version control\.",),
    "edge": (
        r"ERROR: GitPlugin: Could not create branch from HEAD\. Error -12: .*refs/heads/invalid branch.*",
        r"ERROR: GitPlugin: Could not delete branch reference of main\. Error -1: .*current HEAD.*",
    ),
    "reject": (r"ERROR: GitPlugin: Failed to push\. Error -11: cannot push because a reference .*",),
    "merge": (r"ERROR: GitPlugin: Changes are staged\. Make a merge commit\.",),
    "conflict": (r"ERROR: GitPlugin: Index has conflicts\. Solve conflicts and make a merge commit\.",),
    "security": (
        r"ERROR: GitPlugin: Remote URLs must not contain credentials\. Use Redot's version-control credential fields instead\.",
        r'ERROR: GitPlugin: Could not connect to remote "invalid"\. .*Error -1: failed to connect to 127\.0\.0\.1: .*',
    ),
}


def classify(output: str, exit_code: int, *, identity: str, result_passed: bool,
             provider_active: bool = True, scenario: str = "", timed_out: bool = False) -> dict[str, Any]:
    """Accept the known shutdown crash only after a successful provider shutdown."""
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    shutdown = re.search(r"^" + re.escape(SHUTDOWN_MARKER) + r"$", output, re.MULTILINE)
    marker = shutdown.start() if shutdown else -1
    crash = CRASH_BANNER.search(output)
    known_crash = (
        not timed_out and identity == OFFICIAL_26_3 and exit_code in CRASH_CODES
        and result_passed and provider_active and marker >= 0
        and crash is not None and marker < crash.start()
    )
    failures: list[str] = []
    if timed_out:
        failures.append("engine timed out")
    if not result_passed:
        failures.append("scenario result did not pass")
    if provider_active and marker < 0:
        failures.append("provider shutdown marker missing")
    if exit_code != 0 and not known_crash:
        failures.append(f"engine exited with code {exit_code}")
    allowed_context = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if CRASH_BANNER.search(line):
            if not known_crash:
                failures.append("unexpected crash banner")
            continue
        if line.startswith("at:"):
            if not allowed_context:
                failures.append("unexpected diagnostic context")
            continue
        if DIAGNOSTIC.search(line):
            expected = any(re.fullmatch(pattern, line) for pattern in EXPECTED.get(scenario, ()))
            allowed_context = expected or (known_crash and LEAK.fullmatch(line) is not None)
            if not allowed_context:
                failures.append("unexpected diagnostic: " + line)
        elif line:
            allowed_context = False
    return {
        "outcome": "failed" if failures else "known_engine_shutdown_crash" if known_crash else "passed",
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
    for path in (profile, hooks, templates, profile / "xdg"):
        path.mkdir(parents=True, exist_ok=True)
    empty = directory / "empty.gitconfig"
    empty.touch()
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
        "HOME": str(profile), "USERPROFILE": str(profile), "XDG_CONFIG_HOME": str(profile / "xdg"),
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
                  scenario: str = "") -> dict[str, Any]:
    return classify(process.stdout + (process.stderr or ""), process.returncode,
                    identity=identity, result_passed=result_passed,
                    provider_active=provider_active, scenario=scenario,
                    timed_out=getattr(process, "timed_out", False))


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
