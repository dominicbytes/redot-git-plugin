#!/usr/bin/env python3
"""Exercise provider endpoints through a test-only Redot binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from diagnostics import check_process, engine_identity, run_process, sanitize
from typing import Callable

from provider_layout import install_provider, install_scenario_driver


RESULT_PREFIX = "REDOT_GIT_PROVIDER_TEST="
Prepare = Callable[[Path, Path], None]


def run(command: list[str], cwd: Path, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return run_process(
        command,
        cwd=cwd,
        timeout=timeout,
    )


def checked(command: list[str], cwd: Path) -> None:
    process = run(command, cwd)
    if process.returncode:
        raise RuntimeError(sanitize(process.stderr.strip() or process.stdout.strip()))


def command_output(command: list[str], cwd: Path) -> str:
    process = run(command, cwd)
    if process.returncode:
        raise RuntimeError(sanitize(process.stderr.strip() or process.stdout.strip()))
    return process.stdout.strip()


def install_fixture(root: Path, temp_root: Path, provider: Path) -> Path:
    project = temp_root / "project with space-\u00e9"
    shutil.copytree(root / "tests" / "fixture", project)
    install_provider(root, project, provider)
    return project


def initialize_repository(project: Path, git: str) -> None:
    checked([git, "init", "--initial-branch=main"], project)
    checked([git, "config", "user.name", "Redot Git Fixture"], project)
    checked([git, "config", "user.email", "fixture@example.invalid"], project)


def prepare_local(project: Path, temp_root: Path, git: str) -> None:
    initialize_repository(project, git)
    files = {
        "tracked.txt": "baseline\n",
        "discard.txt": "keep\n",
        "unicode.txt": "caf\u00e9\n",
    }
    for name, contents in files.items():
        (project / name).write_text(contents, encoding="utf-8", newline="\n")
    checked([git, "add", *files], project)
    checked([git, "commit", "-m", "Fixture baseline"], project)
    (project / "tracked.txt").write_text("baseline\nchanged\n", encoding="utf-8", newline="\n")
    (project / "discard.txt").write_text("discard me\n", encoding="utf-8", newline="\n")
    (project / "untracked.txt").write_text("commit me\n", encoding="utf-8", newline="\n")
    (project / "unstage.txt").write_text("stage cycle\n", encoding="utf-8", newline="\n")
    checked([git, "init", "--bare", "--initial-branch=main", str(temp_root / "remote.git")], temp_root)


def create_remote_base(project: Path, temp_root: Path, git: str) -> tuple[Path, Path]:
    initialize_repository(project, git)
    (project / "base.txt").write_text("base\n", encoding="utf-8", newline="\n")
    checked([git, "add", "base.txt"], project)
    checked([git, "commit", "-m", "Remote base"], project)

    remote = temp_root / "remote.git"
    checked([git, "init", "--bare", "--initial-branch=main", str(remote)], temp_root)
    checked([git, "remote", "add", "origin", remote.as_posix()], project)
    checked([git, "push", "--set-upstream", "origin", "main"], project)

    peer = temp_root / "peer"
    checked([git, "clone", remote.as_posix(), str(peer)], temp_root)
    checked([git, "config", "user.name", "Remote Fixture"], peer)
    checked([git, "config", "user.email", "remote@example.invalid"], peer)
    return remote, peer


def prepare_remote_fast_forward(project: Path, temp_root: Path, git: str) -> None:
    _remote, peer = create_remote_base(project, temp_root, git)
    (peer / "upstream.txt").write_text("from upstream\n", encoding="utf-8", newline="\n")
    checked([git, "add", "upstream.txt"], peer)
    checked([git, "commit", "-m", "Upstream fast-forward"], peer)
    checked([git, "push", "origin", "main"], peer)


def prepare_divergence(project: Path, temp_root: Path, git: str, conflict: bool = False) -> None:
    _remote, peer = create_remote_base(project, temp_root, git)
    if conflict:
        (project / "conflict.txt").write_text("base\n", encoding="utf-8", newline="\n")
        checked([git, "add", "conflict.txt"], project)
        checked([git, "commit", "-m", "Conflict base"], project)
        checked([git, "push", "origin", "main"], project)
        checked([git, "pull", "--ff-only"], peer)
        (project / "conflict.txt").write_text("local side\n", encoding="utf-8", newline="\n")
        (peer / "conflict.txt").write_text("remote side\n", encoding="utf-8", newline="\n")
        local_path = remote_path = "conflict.txt"
    else:
        (project / "local-side.txt").write_text("local side\n", encoding="utf-8", newline="\n")
        (peer / "remote-side.txt").write_text("remote side\n", encoding="utf-8", newline="\n")
        local_path, remote_path = "local-side.txt", "remote-side.txt"

    checked([git, "add", local_path], project)
    checked([git, "commit", "-m", "Local divergence"], project)
    checked([git, "add", remote_path], peer)
    checked([git, "commit", "-m", "Remote divergence"], peer)
    checked([git, "push", "origin", "main"], peer)


def prepare_security(project: Path, git: str) -> None:
    initialize_repository(project, git)
    (project / "security.txt").write_text("security baseline\n", encoding="utf-8", newline="\n")
    checked([git, "add", "security.txt"], project)
    checked([git, "commit", "-m", "Security baseline"], project)


def prepare_edge_matrix(project: Path, git: str) -> None:
    initialize_repository(project, git)
    checked([git, "config", "user.name", "Jos\u00e9 Fixture"], project)
    files = {
        "modified.txt": "original\n",
        "deleted.txt": "delete me\n",
        "rename-old.txt": "rename me\n",
        "staged-rename-old.txt": "stage rename me\n",
        "binary.bin": b"\x00\x01baseline\x00",
        "large.txt": "line\n" * 20000,
    }
    for name, contents in files.items():
        path = project / name
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents, encoding="utf-8", newline="\n")
    checked([git, "add", *files], project)
    checked([git, "commit", "-m", "Root caf\u00e9", "-m", "root body"], project)
    (project / "second.txt").write_text("second\n", encoding="utf-8", newline="\n")
    checked([git, "add", "second.txt"], project)
    checked([git, "commit", "-m", "Second commit"], project)

    (project / "modified.txt").write_text("original\nmodified\n", encoding="utf-8", newline="\n")
    (project / "deleted.txt").unlink()
    (project / "rename-old.txt").rename(project / "renamed.txt")
    checked([git, "mv", "staged-rename-old.txt", "staged-renamed.txt"], project)
    (project / "staged-new.txt").write_text("staged new\n", encoding="utf-8", newline="\n")
    checked([git, "add", "staged-new.txt"], project)
    (project / "binary.bin").write_bytes(b"\x00\x02changed\x00")
    (project / "large.txt").write_text("line changed\n" * 20000, encoding="utf-8", newline="\n")
    (project / "unicod\u00e9 file.txt").write_text("unicode path\n", encoding="utf-8", newline="\n")


def prepare_detached(project: Path, git: str) -> None:
    initialize_repository(project, git)
    (project / "detached.txt").write_text("detached baseline\n", encoding="utf-8", newline="\n")
    checked([git, "add", "detached.txt"], project)
    checked([git, "commit", "-m", "Detached baseline"], project)
    checked([git, "checkout", "--detach"], project)


def prepare_local_regression(project: Path, temp_root: Path, git: str, scenario: str) -> None:
    initialize_repository(project, git)
    if scenario == "unborn_line":
        return
    files = {"asset[1].txt": "base\n", "asset1.txt": "base\n"}
    if scenario.startswith("external_"):
        files = {"selected.txt": "base\n", "external.txt": "base\n"}
    elif scenario in ("rename_commit", "staged_path"):
        files = {"old.txt": "rename content\n"}
    elif scenario == "branch_collision":
        files = {"branch.txt": "base\n"}
    elif scenario == "legacy_encoding":
        files = {"legacy.txt": "base\n"}
    elif scenario.startswith("merge_") or scenario == "pending_pull":
        files = {"base.txt": "base\n"}
    for name, content in files.items():
        (project / name).write_text(content, encoding="utf-8", newline="\n")
    checked([git, "add", *files], project)
    checked([git, "commit", "-m", "Regression baseline"], project)
    if scenario.startswith("literal_"):
        for name in files:
            (project / name).write_text("changed\n", encoding="utf-8", newline="\n")
        if scenario == "literal_unstage":
            checked([git, "add", "--all"], project)
    elif scenario.startswith("external_"):
        (project / "external.txt").write_text("external changed\n", encoding="utf-8", newline="\n")
        (project / "selected.txt").write_text("selected changed\n", encoding="utf-8", newline="\n")
        if scenario == "external_unstage":
            checked([git, "add", "selected.txt"], project)
    elif scenario == "rename_commit":
        (project / ".git" / "info").mkdir(exist_ok=True)
        (project / ".git" / "info" / "exclude").write_text("*\n!old.txt\n!destination.txt\n", encoding="utf-8")
        (project / "old.txt").rename(project / "destination.txt")
    elif scenario == "staged_path":
        checked([git, "mv", "old.txt", "index.txt"], project)
        (project / "index.txt").rename(project / "working.txt")
    elif scenario == "branch_collision":
        checked([git, "config", "core.autocrlf", "false"], project)
        checked([git, "tag", "feature"], project)
        checked([git, "checkout", "-b", "feature"], project)
        (project / "branch.txt").write_text("feature\n", encoding="utf-8", newline="\n")
        checked([git, "add", "branch.txt"], project)
        checked([git, "commit", "-m", "Feature branch"], project)
        checked([git, "checkout", "main"], project)
    elif scenario.startswith("merge_") or scenario == "pending_pull":
        for branch in ("side", "second"):
            checked([git, "checkout", "-b", branch, "main"], project)
            (project / f"{branch}.txt").write_text(f"{branch}\n", encoding="utf-8", newline="\n")
            checked([git, "add", f"{branch}.txt"], project)
            checked([git, "commit", "-m", f"Add {branch}"], project)
        checked([git, "checkout", "main"], project)
        if scenario == "pending_pull":
            remote = temp_root / "remote.git"
            checked([git, "clone", "--bare", str(project), str(remote)], temp_root)
            checked([git, "remote", "add", "origin", remote.as_posix()], project)
        if scenario != "merge_external":
            branches = ["side", "second"] if scenario == "merge_octopus" else ["side"]
            checked([git, "merge", "--no-ff", "--no-commit", *branches], project)
    elif scenario == "legacy_encoding":
        tree = command_output([git, "rev-parse", "HEAD^{tree}"], project)
        parent = command_output([git, "rev-parse", "HEAD"], project)
        for encoding, message in ((None, b"Fallback \xe9\n"), ("ISO-8859-1", b"Declared \xc3\xa9\n"), ("latin1", b"Alias \xc3\xa9\n")):
            header = f"tree {tree}\nparent {parent}\n".encode()
            header += b"author Jos\xe9 <fixture@example.invalid> 1700000000 +0000\ncommitter Fixture <fixture@example.invalid> 1700000000 +0000\n"
            if encoding:
                header += f"encoding {encoding}\n".encode()
            payload = project / ".git" / "commit-payload"
            payload.write_bytes(header + b"\n" + message)
            parent = command_output([git, "hash-object", "-t", "commit", "-w", str(payload)], project)
        checked([git, "update-ref", "HEAD", parent], project)
        (project / "legacy.txt").write_bytes(b"caf\xe9\n\xff changed\n")


def prepare_index_regression(project: Path, git: str, scenario: str) -> None:
    initialize_repository(project, git)
    checked([git, "config", "core.ignorecase", "true"], project)
    files = {"Name.txt": "original blob\n"}
    if scenario.startswith("missing_index_"):
        files = {"selected.txt": "selected baseline\n", "external.txt": "external baseline\n"}
    for name, content in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    checked([git, "add", *files], project)
    if scenario.startswith("case_unstage_"):
        checked([git, "update-index", "--chmod=+x", "Name.txt"], project)
    checked([git, "commit", "-m", "Index regression baseline"], project)
    if scenario.startswith("case_unstage_"):
        checked([git, "mv", "Name.txt", "intermediate.txt"], project)
        checked([git, "mv", "intermediate.txt", "name.txt"], project)
    elif scenario.startswith("missing_index_"):
        (project / "selected.txt").write_text("selected changed\n", encoding="utf-8", newline="\n")


def execute_index_regressions(execute: Callable[[str, Prepare], tuple[Path, Path, dict[str, object]]], git: str) -> None:
    scenarios = (
        "case_unstage_old_first", "case_unstage_new_first",
        "missing_index_stage", "missing_index_unstage", "missing_index_commit",
    )
    for scenario in scenarios:
        _root, project, report = execute(
            scenario, lambda project, _temp_root, case=scenario: prepare_index_regression(project, git, case)
        )
        expected = ""
        tree_command = [git, "ls-tree", "-r", "--format=%(objectmode) %(objectname) 0%x09%(path)", "HEAD"]
        if scenario.startswith("case_unstage_"):
            expected = command_output(tree_command, project)
        elif scenario == "missing_index_stage":
            blob = command_output([git, "hash-object", "selected.txt"], project)
            expected = f"100644 {blob} 0\tselected.txt"
        elif scenario == "missing_index_unstage":
            expected = command_output([*tree_command, "--", "selected.txt"], project)
        actual = command_output([git, "ls-files", "--stage"], project)
        verification = {"expected_entries": expected, "index_entries": actual}
        if scenario.startswith("case_unstage_"):
            verification["ignorecase"] = command_output([git, "config", "core.ignorecase"], project)
            verification["case_insensitive_worktree"] = (project / "NAME.TXT").exists()
        if scenario == "missing_index_commit":
            verification["head_entries"] = command_output(tree_command, project)
            report["passed"] = report["passed"] and verification["head_entries"] == ""
        report["verification"] = verification
        report["passed"] = report["passed"] and actual == expected


def execute_local_regressions(execute: Callable[[str, Prepare], tuple[Path, Path, dict[str, object]]], git: str) -> None:
    scenarios = (
        "literal_stage", "literal_unstage", "literal_discard",
        "external_stage", "external_unstage", "external_commit",
        "rename_commit", "staged_path", "branch_collision",
        "merge_external", "merge_aborted", "merge_resumed", "merge_octopus",
        "pending_pull", "legacy_encoding", "unborn_line",
    )
    for scenario in scenarios:
        execute(scenario, lambda project, temp_root, case=scenario: prepare_local_regression(project, temp_root, git, case))


def parse_result(output: str) -> dict[str, object]:
    for line in output.splitlines():
        if line.startswith(RESULT_PREFIX):
            return json.loads(line.removeprefix(RESULT_PREFIX))
    raise ValueError("Redot did not emit the provider test marker")


def run_scenario(redot: Path, project: Path, scenario: str, identity: str) -> dict[str, object]:
    install_scenario_driver(project, "provider_scenario.gd")
    command = [
        str(redot),
        "--headless", "--audio-driver", "Dummy",
        "--editor",
        "--path",
        str(project),
        "--quit-after",
        "12",
        "--",
        scenario,
    ]
    process = run(command, project)
    output = process.stdout + process.stderr
    try:
        result = parse_result(output)
    except (ValueError, json.JSONDecodeError):
        result = {"scenario": scenario, "passed": False}
    diagnostics = check_process(process, identity=identity, result_passed=result.get("passed") is True,
                                provider_active=True, scenario=scenario,
                                providers_freed=result.get("providers_freed"))
    return {
        "command": command,
        "exit_code": process.returncode,
        "result": result,
        "output": output,
        "diagnostics": diagnostics,
        "passed": diagnostics["passed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redot", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--git", default="git")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    arguments.redot = arguments.redot.resolve()
    arguments.provider = arguments.provider.resolve()
    identity = engine_identity(arguments.redot, root)
    reports: list[dict[str, object]] = []
    retained: list[Path] = []

    def execute(scenario: str, prepare: Prepare | None = None) -> tuple[Path, Path, dict[str, object]]:
        temp_root = Path(tempfile.mkdtemp(prefix=f"redot-git-{scenario}-"))
        retained.append(temp_root)
        project = install_fixture(root, temp_root, arguments.provider)
        if prepare is not None:
            prepare(project, temp_root)
        report = run_scenario(arguments.redot, project, scenario, identity)
        report["metadata_created"] = {
            name: (project / name).exists() for name in (".git", ".gitignore", ".gitattributes")
        }
        reports.append(report)
        return temp_root, project, report

    try:
        execute_index_regressions(execute, arguments.git)
        execute_local_regressions(execute, arguments.git)
        execute("local", lambda project, temp_root: prepare_local(project, temp_root, arguments.git))

        _root, _project, nonrepo_report = execute("nonrepo")
        if any(nonrepo_report["metadata_created"].values()):
            nonrepo_report["passed"] = False

        _root, unborn_project, unborn_report = execute(
            "unborn", lambda project, _temp_root: initialize_repository(project, arguments.git)
        )
        unborn_report["native_head"] = command_output([arguments.git, "rev-parse", "HEAD"], unborn_project)

        _root, edge_project, edge_report = execute(
            "edge", lambda project, _temp_root: prepare_edge_matrix(project, arguments.git)
        )
        edge_report["verification"] = {
            "head_message": command_output([arguments.git, "log", "-1", "--format=%B"], edge_project),
            "current_branch": command_output([arguments.git, "branch", "--show-current"], edge_project),
        }
        if edge_report["verification"]["head_message"] != "Provider caf\u00e9\nsecond line" or edge_report["verification"]["current_branch"] != "main":
            edge_report["passed"] = False

        _root, detached_project, detached_report = execute(
            "detached", lambda project, _temp_root: prepare_detached(project, arguments.git)
        )
        detached_report["verification"] = {
            "current_branch": command_output([arguments.git, "branch", "--show-current"], detached_project)
        }
        if detached_report["verification"]["current_branch"] != "main":
            detached_report["passed"] = False

        remote_root, remote_project, remote_report = execute(
            "remote", lambda project, temp_root: prepare_remote_fast_forward(project, temp_root, arguments.git)
        )
        local_tip = command_output([arguments.git, "rev-parse", "HEAD"], remote_project)
        bare_tip = command_output(
            [arguments.git, "--git-dir", str(remote_root / "remote.git"), "rev-parse", "refs/heads/main"], remote_root
        )
        remote_report["verification"] = {"local_tip": local_tip, "remote_tip": bare_tip}
        if local_tip != bare_tip:
            remote_report["passed"] = False

        for scenario, force_expected in (("reject", False), ("force", True)):
            case_root, case_project, case_report = execute(
                scenario, lambda project, temp_root: prepare_divergence(project, temp_root, arguments.git)
            )
            local_tip = command_output([arguments.git, "rev-parse", "HEAD"], case_project)
            bare_tip = command_output(
                [arguments.git, "--git-dir", str(case_root / "remote.git"), "rev-parse", "refs/heads/main"], case_root
            )
            case_report["verification"] = {"local_tip": local_tip, "remote_tip": bare_tip}
            if (bare_tip == local_tip) is not force_expected:
                case_report["passed"] = False

        _root, merge_project, merge_report = execute(
            "merge", lambda project, temp_root: prepare_divergence(project, temp_root, arguments.git)
        )
        merge_parents = command_output([arguments.git, "rev-list", "--parents", "-n", "1", "HEAD"], merge_project).split()
        merge_report["verification"] = {"parent_count": len(merge_parents) - 1}
        if len(merge_parents) != 3:
            merge_report["passed"] = False

        _root, conflict_project, conflict_report = execute(
            "conflict", lambda project, temp_root: prepare_divergence(project, temp_root, arguments.git, conflict=True)
        )
        unmerged_before = command_output([arguments.git, "ls-files", "-u"], conflict_project)
        conflict_report["verification"] = {
            "merge_head_exists": (conflict_project / ".git" / "MERGE_HEAD").exists(),
            "unmerged_entries": bool(unmerged_before),
        }
        if not all(conflict_report["verification"].values()):
            conflict_report["passed"] = False

        resolution_report = run_scenario(arguments.redot, conflict_project, "resolve", identity)
        resolution_parents = command_output(
            [arguments.git, "rev-list", "--parents", "-n", "1", "HEAD"], conflict_project
        ).split()
        resolution_report["verification"] = {
            "parent_count": len(resolution_parents) - 1,
            "merge_head_exists": (conflict_project / ".git" / "MERGE_HEAD").exists(),
            "unmerged_entries": bool(command_output([arguments.git, "ls-files", "-u"], conflict_project)),
        }
        if (
            len(resolution_parents) != 3
            or resolution_report["verification"]["merge_head_exists"]
            or resolution_report["verification"]["unmerged_entries"]
        ):
            resolution_report["passed"] = False
        reports.append(resolution_report)

        _root, security_project, security_report = execute(
            "security", lambda project, _temp_root: prepare_security(project, arguments.git)
        )
        sentinels = (
            "sentinel-user-42",
            "SENTINEL_PASSWORD_42",
            "SENTINEL_PASSPHRASE_42",
            "SENTINEL_URL_SECRET_42",
            "SENTINEL_QUERY_SECRET_42",
            "C:" + chr(47) + "sentinel/PUBLIC_KEY_42.pub",
            "C:" + chr(47) + "sentinel/PRIVATE_KEY_42",
        )
        leaked = []
        for path in security_project.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                leaked.extend(f"{path.relative_to(security_project).as_posix()}:sentinel" for sentinel in sentinels if sentinel.encode() in data)
        combined_output = security_report["output"]
        leaked.extend("output:sentinel" for sentinel in sentinels if sentinel in combined_output)
        security_report["verification"] = {"sentinel_matches": leaked}
        if leaked:
            security_report["passed"] = False
    finally:
        if arguments.keep:
            for path in retained:
                print("Fixture retained (--keep)", file=sys.stderr)
        else:
            for path in retained:
                shutil.rmtree(path, ignore_errors=True)

    summary = {
        "redot_version": identity,
        "provider_sha256": hashlib.sha256(arguments.provider.read_bytes()).hexdigest(),
        "reports": reports,
        "passed": all(report["passed"] for report in reports),
    }
    replacements = {str(arguments.redot): "$REDOT_BIN", str(arguments.provider): "<provider binary>", str(root): "<repo clone>"}
    replacements.update({str(path): "<temp dir>" for path in retained})
    summary = sanitize(summary, replacements)
    reports = summary["reports"]
    serialized = json.dumps(summary, indent=2, ensure_ascii=False)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized + "\n", encoding="utf-8", newline="\n")
    if arguments.verbose:
        print(serialized)
    else:
        compact = {
            "redot_version": identity,
            "provider_sha256": summary["provider_sha256"],
            "passed": summary["passed"],
            "reports": [
                {
                    "scenario": report["result"].get("scenario"),
                    "passed": report["passed"],
                    "exit_code": report["exit_code"],
                    "outcome": report["diagnostics"]["outcome"],
                    "failures": report["diagnostics"]["failures"],
                    "verification": report.get("verification"),
                }
                for report in reports
            ],
        }
        print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(sanitize(str(error)), file=sys.stderr)
        sys.exit(1)
