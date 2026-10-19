#!/usr/bin/env python3
"""Run the compiled provider inside a temporary Redot editor project."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from provider_layout import install_provider


# An OpenSSL configuration that cannot load. The provider must ignore it,
# because a config file can make OpenSSL load arbitrary provider modules.
PLANTED_OPENSSL_CONFIG = """openssl_conf = openssl_init
[openssl_init]
providers = provider_sect
[provider_sect]
planted = planted_sect
[planted_sect]
module = planted-provider-that-does-not-exist
activate = 1
"""


def run(
    command: list[str], cwd: Path, timeout: int = 30, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def prepare_repository(project: Path, git: str) -> None:
    for command in (
        [git, "init", "--initial-branch=main"],
        [git, "config", "user.name", "Redot Git Fixture"],
        [git, "config", "user.email", "fixture@example.invalid"],
    ):
        result = run(command, project)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    (project / "tracked.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
    for command in ([git, "add", "tracked.txt"], [git, "commit", "-m", "Fixture baseline"]):
        result = run(command, project)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    (project / "untracked.txt").write_text("provider should report this\n", encoding="utf-8", newline="\n")


def enable_provider(project: Path) -> None:
    project_file = project / "project.godot"
    contents = project_file.read_text(encoding="utf-8")
    contents += (
        "\n[editor]\n\n"
        "version_control/autoload_on_startup=true\n"
        'version_control/plugin_name="GitPlugin"\n'
    )
    project_file.write_text(contents, encoding="utf-8", newline="\n")


def validate(output: str) -> tuple[dict[str, object], list[str]]:
    result = {
        "repository_discovered": "Found a repository at " in output,
        "provider_initialized": "GitPlugin: Loaded system CA certificates" in output,
    }
    failures = []
    if not result["repository_discovered"]:
        failures.append("the editor did not initialize the provider against the repository")
    if not result["provider_initialized"]:
        failures.append("the provider did not finish initialization")
    return result, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redot", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--git", default="git")
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args()

    redot = arguments.redot.resolve()
    provider = arguments.provider.resolve()

    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests" / "fixture"
    temp_root = Path(tempfile.mkdtemp(prefix="redot-git-fixture-"))
    project = temp_root / "project"
    try:
        shutil.copytree(fixture, project)
        install_provider(root, project, provider)
        prepare_repository(project, arguments.git)

        import_command = [
            str(redot),
            "--headless",
            "--editor",
            "--path",
            str(project),
            "--import",
            "--quit-after",
            "120",
        ]
        import_process = run(import_command, project, timeout=45)
        enable_provider(project)

        command = [
            str(redot),
            "--headless",
            "--editor",
            "--path",
            str(project),
            "--quit-after",
            "120",
        ]
        planted_config = temp_root / "planted-openssl.cnf"
        planted_config.write_text(PLANTED_OPENSSL_CONFIG, encoding="utf-8", newline="\n")
        provider_env = dict(os.environ, OPENSSL_CONF=str(planted_config))
        process = run(command, project, timeout=45, env=provider_env)
        combined = process.stdout + process.stderr
        result, failures = validate(combined)
        if process.returncode:
            failures.append(f"Redot exited with code {process.returncode}")
        if import_process.returncode:
            failures.append(f"Redot import exited with code {import_process.returncode}")
        for label, output in (("import", import_process.stdout + import_process.stderr), ("smoke", combined)):
            if "ERROR:" in output or "SCRIPT ERROR:" in output or "WARNING:" in output:
                failures.append(f"{label} output contained an error or warning")

        report = {
            "command": command,
            "import_command": import_command,
            "import_exit_code": import_process.returncode,
            "provider_sha256": __import__("hashlib").sha256(provider.read_bytes()).hexdigest(),
            "redot_exit_code": process.returncode,
            "result": result,
            "failures": failures,
            "import_output": import_process.stdout + import_process.stderr,
            "output": combined,
        }
        print(__import__("json").dumps(report, indent=2))
        return 1 if failures else 0
    finally:
        if arguments.keep:
            print(f"Fixture retained at {temp_root}", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
