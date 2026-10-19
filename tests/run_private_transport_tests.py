#!/usr/bin/env python3
"""Run authenticated HTTPS and SSH Git workflows against an ephemeral container."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from diagnostics import check_process, controlled_environment, engine_identity, run_process, sanitize

from provider_layout import install_provider, install_scenario_driver


RESULT_PREFIX = "REDOT_GIT_PRIVATE_TEST="
IMAGE = "redot-git-private-fixture:26.2"


def run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    return run_process(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )


def checked(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 90,
) -> str:
    process = run(command, cwd, env=env, timeout=timeout)
    if process.returncode:
        raise RuntimeError(sanitize(process.stderr.strip() or process.stdout.strip()))
    return process.stdout.strip()


def find_ssh_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path("C:/Program Files/Git/usr/bin") / f"{name}.exe"
    if candidate.is_file():
        return str(candidate)
    raise FileNotFoundError(f"Could not find {name}")


def install_fixture(root: Path, project: Path, provider: Path) -> None:
    shutil.copytree(root / "tests" / "fixture", project)
    install_provider(root, project, provider)


def generate_keys(fixtures: Path, ssh_keygen: str, passphrase: str) -> None:
    checked(
        [ssh_keygen, "-q", "-t", "rsa", "-b", "3072", "-m", "PEM", "-N", passphrase, "-f", str(fixtures / "client")],
        fixtures,
    )
    checked(
        [ssh_keygen, "-q", "-t", "rsa", "-b", "3072", "-m", "PEM", "-N", "", "-f", str(fixtures / "setup")],
        fixtures,
    )


def wait_for_fixture(fixtures: Path, container: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if (fixtures / "ready").is_file():
            return
        status = checked(["docker", "inspect", "--format", "{{.State.Running}}", container], fixtures)
        if status != "true":
            break
        time.sleep(0.25)
    logs = run(["docker", "logs", container], fixtures).stdout
    raise RuntimeError(f"Transport fixture did not become ready.\n{logs}")


def mapped_port(container: str, container_port: int, cwd: Path) -> int:
    value = checked(["docker", "port", container, f"{container_port}/tcp"], cwd)
    return int(value.rsplit(":", 1)[1])


def initialize_project(project: Path, git: str) -> None:
    checked([git, "init", "--initial-branch=main"], project)
    checked([git, "config", "user.name", "Private Transport Fixture"], project)
    checked([git, "config", "user.email", "private@example.invalid"], project)


def prepare_https(
    project: Path,
    peer: Path,
    git: str,
    url: str,
    ca: Path,
    username: str,
    password: str,
) -> None:
    authorization = base64.b64encode(f"{username}:{password}".encode()).decode()
    options = [
        "-c",
        "http.sslBackend=openssl",
        "-c",
        f"http.sslCAInfo={ca}",
        "-c",
        f"http.extraHeader=Authorization: Basic {authorization}",
    ]
    initialize_project(project, git)
    checked([git, *options, "fetch", url, "main"], project)
    checked([git, "checkout", "-B", "main", "FETCH_HEAD"], project)
    checked([git, *options, "clone", url, str(peer)], peer.parent)
    checked([git, "config", "user.name", "HTTPS Peer"], peer)
    checked([git, "config", "user.email", "https-peer@example.invalid"], peer)
    (peer / "upstream-https.txt").write_text("upstream over https\n", encoding="utf-8", newline="\n")
    checked([git, "add", "upstream-https.txt"], peer)
    checked([git, "commit", "-m", "HTTPS upstream"], peer)
    checked([git, *options, "push", "origin", "main"], peer)


def ssh_command(ssh: str, key: Path, port: int, known_hosts: Path) -> str:
    return (
        f'"{ssh}" -i "{key}" -l git -p {port} -o BatchMode=yes '
        f'-o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="{known_hosts}"'
    )


def prepare_ssh(
    project: Path,
    peer: Path,
    git: str,
    url: str,
    command: str,
) -> None:
    options = ["-c", f"core.sshCommand={command}"]
    initialize_project(project, git)
    checked([git, *options, "fetch", url, "main"], project)
    checked([git, "checkout", "-B", "main", "FETCH_HEAD"], project)
    checked([git, *options, "clone", url, str(peer)], peer.parent)
    checked([git, "config", "user.name", "SSH Peer"], peer)
    checked([git, "config", "user.email", "ssh-peer@example.invalid"], peer)
    (peer / "upstream-ssh.txt").write_text("upstream over ssh\n", encoding="utf-8", newline="\n")
    checked([git, "add", "upstream-ssh.txt"], peer)
    checked([git, "commit", "-m", "SSH upstream"], peer)
    checked([git, *options, "push", "origin", "main"], peer)


def run_provider(redot: Path, project: Path, env: dict[str, str]) -> dict[str, object]:
    install_scenario_driver(project, "private_transport_scenario.gd")
    command = [
        str(redot),
        "--headless", "--audio-driver", "Dummy",
        "--editor",
        "--path",
        str(project),
        "--quit-after",
        "12",
    ]
    process = run(command, project, env=env)
    output = process.stdout + process.stderr
    result = None
    for line in output.splitlines():
        if line.startswith(RESULT_PREFIX):
            result = json.loads(line.removeprefix(RESULT_PREFIX))
            break
    if result is None:
        result = {"passed": False}
    identity = engine_identity(redot, project)
    diagnostics = check_process(process, identity=identity,
                                result_passed=result.get("passed") is True, provider_active=True,
                                providers_freed=result.get("providers_freed"))
    return {
        "redot_version": identity,
        "exit_code": process.returncode,
        "result": result,
        "output": output,
        "diagnostics": diagnostics,
        "passed": diagnostics["passed"],
    }


def scan_for_sentinels(project: Path, output: str, sentinels: tuple[str, ...]) -> list[str]:
    matches = []
    for path in project.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            matches.extend(f"{path.relative_to(project).as_posix()}:sentinel" for sentinel in sentinels if sentinel.encode() in data)
    matches.extend("output:sentinel" for sentinel in sentinels if sentinel in output)
    return matches



def run_negative_transports(
    redot: Path, project: Path, env: dict[str, str], container: str, fixtures: Path,
    git: str, peer: Path, https_options: list[str], sentinels: tuple[str, ...],
) -> list[dict[str, object]]:
    reports = []
    redirect_env = env | {
        "REDOT_GIT_NEGATIVE_CASE": "redirect",
        "REDOT_GIT_REMOTE_URL": env["REDOT_GIT_REMOTE_URL"].replace("/git/", "/redirect/"),
    }
    redirect = run_provider(redot, project, redirect_env)
    target_log = fixtures / "redirect-access.log"
    no_target_requests = target_log.is_file() and not target_log.read_text(encoding="utf-8").strip()
    redirect["verification"] = {
        "redirect_target_unvisited": no_target_requests,
        "success_marker_absent": all(marker not in redirect["output"] for marker in ("Fetch ended", "Pull ended", "Push ended")),
        "sentinel_matches": scan_for_sentinels(project, redirect["output"], sentinels),
    }
    redirect["passed"] = redirect["passed"] and no_target_requests and redirect["verification"]["success_marker_absent"] and not redirect["verification"]["sentinel_matches"]
    reports.append(redirect)
    checked([git, *https_options, "fetch", "origin"], peer)
    before = checked([git, "rev-parse", "origin/main"], peer)
    hook = "#!/bin/sh\necho 'fixture receive hook declined' >&2\nexit 1\n"
    checked(["docker", "exec", container, "sh", "-c", 'printf "%s" "$1" > /srv/git/https.git/hooks/pre-receive; chmod 0755 /srv/git/https.git/hooks/pre-receive', "fixture-hook", hook], fixtures)
    rejection = run_provider(redot, project, env | {"REDOT_GIT_NEGATIVE_CASE": "hook-rejection"})
    checked([git, *https_options, "fetch", "origin"], peer)
    after = checked([git, "rev-parse", "origin/main"], peer)
    rejection["verification"] = {
        "remote_unchanged": before == after,
        "rejection_reported": "Push rejected:" in rejection["output"],
        "success_marker_absent": "Push ended" not in rejection["output"],
        "sentinel_matches": scan_for_sentinels(project, rejection["output"], sentinels),
    }
    rejection["passed"] = rejection["passed"] and before == after and rejection["verification"]["rejection_reported"] and rejection["verification"]["success_marker_absent"] and not rejection["verification"]["sentinel_matches"]
    reports.append(rejection)
    return reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redot", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--git", default="git")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    arguments.redot = arguments.redot.resolve()
    arguments.provider = arguments.provider.resolve()

    root = Path(__file__).resolve().parents[1]
    temp_root = Path(tempfile.mkdtemp(prefix="redot-git-private-"))
    fixtures = temp_root / "fixtures"
    fixtures.mkdir()
    container = f"redot-git-private-{uuid.uuid4().hex[:12]}"
    http_username = "transport-user-42"
    http_password = "SENTINEL_HTTPS_PASSWORD_42"
    ssh_passphrase = "SENTINEL_SSH_PASSPHRASE_42"
    (fixtures / "http_username").write_text(http_username + "\n", encoding="utf-8", newline="\n")
    (fixtures / "http_password").write_text(http_password + "\n", encoding="utf-8", newline="\n")
    generate_keys(fixtures, find_ssh_tool("ssh-keygen"), ssh_passphrase)

    reports: list[dict[str, object]] = []
    base_env = controlled_environment()
    profile = temp_root / "profile"
    (profile / ".ssh").mkdir(parents=True)
    base_env["HOME"] = str(profile)
    base_env["USERPROFILE"] = str(profile)

    try:
        if not arguments.skip_build:
            checked(["docker", "build", "--tag", IMAGE, str(root / "tests" / "transport")], root, timeout=300)
        checked(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                container,
                "--publish",
                "127.0.0.1::22",
                "--publish",
                "127.0.0.1::443",
                "--volume",
                f"{fixtures}:/fixtures",
                IMAGE,
            ],
            root,
        )
        wait_for_fixture(fixtures, container)
        https_port = mapped_port(container, 443, root)
        ssh_port = mapped_port(container, 22, root)
        host_key = checked(["docker", "exec", container, "cat", "/etc/ssh/ssh_host_ed25519_key.pub"], root)
        key_kind, key_value, *_comment = host_key.split()
        known_hosts = profile / ".ssh" / "known_hosts"
        known_hosts.write_text(f"[localhost]:{ssh_port} {key_kind} {key_value}\n", encoding="utf-8", newline="\n")

        https_project = temp_root / "https project-\u00e9"
        https_peer = temp_root / "https-peer"
        install_fixture(root, https_project, arguments.provider)
        shutil.copy2(fixtures / "ca.crt", https_project / "ca.crt")
        https_url = f"https://localhost:{https_port}/git/https.git"
        prepare_https(
            https_project,
            https_peer,
            arguments.git,
            https_url,
            fixtures / "ca.crt",
            http_username,
            http_password,
        )
        https_env = base_env | {
            "REDOT_GIT_TRANSPORT": "https",
            "REDOT_GIT_REMOTE_URL": https_url,
            "REDOT_GIT_USERNAME": http_username,
            "REDOT_GIT_PASSWORD": http_password,
            "REDOT_GIT_PUBLIC_KEY": "",
            "REDOT_GIT_PRIVATE_KEY": "",
            "REDOT_GIT_PASSPHRASE": "",
        }
        https_report = run_provider(arguments.redot, https_project, https_env)
        https_options = [
            "-c",
            "http.sslBackend=openssl",
            "-c",
            f"http.sslCAInfo={fixtures / 'ca.crt'}",
            "-c",
            "http.extraHeader=Authorization: Basic "
            + base64.b64encode(f"{http_username}:{http_password}".encode()).decode(),
        ]
        checked([arguments.git, *https_options, "fetch", "origin"], https_peer)
        pushed_https = checked([arguments.git, "show", "origin/main:provider-https.txt"], https_peer)
        https_report["verification"] = {
            "remote_content": pushed_https,
            "sentinel_matches": scan_for_sentinels(
                https_project,
                https_report["output"],
                (http_username, http_password),
            ),
        }
        if pushed_https != "pushed over https" or https_report["verification"]["sentinel_matches"]:
            https_report["passed"] = False
        reports.append(https_report)
        reports.extend(run_negative_transports(
            arguments.redot, https_project, https_env, container, fixtures,
            arguments.git, https_peer, https_options, (http_username, http_password),
        ))

        ssh_project = temp_root / "ssh project-\u00e9"
        ssh_peer = temp_root / "ssh-peer"
        install_fixture(root, ssh_project, arguments.provider)
        ssh_url = f"ssh://localhost:{ssh_port}/srv/git/ssh.git"
        setup_ssh_command = ssh_command(find_ssh_tool("ssh"), fixtures / "setup", ssh_port, known_hosts)
        prepare_ssh(ssh_project, ssh_peer, arguments.git, ssh_url, setup_ssh_command)
        ssh_env = base_env | {
            "REDOT_GIT_TRANSPORT": "ssh",
            "REDOT_GIT_REMOTE_URL": ssh_url,
            "REDOT_GIT_USERNAME": "git",
            "REDOT_GIT_PASSWORD": "",
            "REDOT_GIT_PUBLIC_KEY": str(fixtures / "client.pub"),
            "REDOT_GIT_PRIVATE_KEY": str(fixtures / "client"),
            "REDOT_GIT_PASSPHRASE": ssh_passphrase,
        }
        ssh_report = run_provider(arguments.redot, ssh_project, ssh_env)
        checked([arguments.git, "-c", f"core.sshCommand={setup_ssh_command}", "fetch", "origin"], ssh_peer)
        pushed_ssh = checked([arguments.git, "show", "origin/main:provider-ssh.txt"], ssh_peer)
        ssh_report["verification"] = {
            "remote_content": pushed_ssh,
            "sentinel_matches": scan_for_sentinels(
                ssh_project,
                ssh_report["output"],
                (ssh_passphrase, str(fixtures / "client.pub"), str(fixtures / "client")),
            ),
        }
        if pushed_ssh != "pushed over ssh" or ssh_report["verification"]["sentinel_matches"]:
            ssh_report["passed"] = False
        reports.append(ssh_report)
    finally:
        run(["docker", "rm", "--force", container], root)
        if arguments.keep:
            print("Fixture retained (--keep)", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    summary = {
        "provider_sha256": hashlib.sha256(arguments.provider.read_bytes()).hexdigest(),
        "reports": reports,
        "passed": len(reports) == 4 and all(report["passed"] for report in reports),
    }
    summary = sanitize(summary, {str(arguments.redot): "$REDOT_BIN", str(arguments.provider): "<provider binary>",
                                 str(temp_root): "<temp dir>", str(root): "<repo clone>"})
    reports = summary["reports"]
    serialized = json.dumps(summary, indent=2, ensure_ascii=False)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized + "\n", encoding="utf-8", newline="\n")
    compact = {
        "provider_sha256": summary["provider_sha256"],
        "passed": summary["passed"],
        "reports": [
            {
                "transport": report["result"].get("transport"),
                "passed": report["passed"],
                "outcome": report["diagnostics"]["outcome"],
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
