#!/usr/bin/env python3
"""Fail a release build with the wrong architecture, symbols, dependencies, or markers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


TEST_MARKERS = (
    b"redot_git_test_harness",
    b"test_initialize",
    b"test_sanitize_output",
    b"test_credentials_empty",
)
BUILD_PATH_MARKERS = (
    b":\\users\\",
    b"/home/runner/work/",
    b"\\runner\\work\\",
    b"/users/runner/work/",
)
WINDOWS_DEPENDENCIES = {
    "ADVAPI32.DLL",
    "CRYPT32.DLL",
    "KERNEL32.DLL",
    "SECUR32.DLL",
    "USER32.DLL",
    "WS2_32.DLL",
}
LINUX_DEPENDENCIES = {
    "ld-linux-x86-64.so.2",
    "libc.so.6",
    "libm.so.6",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(name: str, arguments: list[str]) -> str:
    executable = shutil.which(name)
    if executable is None and os.name == "nt" and name == "dumpbin":
        tools = os.environ.get("VCToolsInstallDir")
        if tools:
            candidate = Path(tools) / "bin" / "Hostx64" / "x64" / "dumpbin.exe"
            if candidate.is_file():
                executable = str(candidate)
    if executable is None:
        raise RuntimeError(f"required audit tool is unavailable: {name}")
    process = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode:
        raise RuntimeError(
            f"{name} exited with {process.returncode}: "
            + (process.stderr.strip() or process.stdout.strip())
        )
    return process.stdout


def scan_markers(path: Path) -> None:
    data = path.read_bytes().lower()
    for marker in TEST_MARKERS:
        if marker in data:
            raise RuntimeError(f"binary contains test-harness marker: {marker.decode()}")
    for marker in BUILD_PATH_MARKERS:
        if marker in data:
            raise RuntimeError(
                f"binary contains an absolute build-path marker: {marker.decode()}"
            )


def audit_windows(path: Path) -> dict[str, object]:
    headers = command("dumpbin", ["/headers", str(path)])
    exports = command("dumpbin", ["/exports", str(path)])
    dependents = command("dumpbin", ["/dependents", str(path)])
    if "machine (x64)" not in headers.lower():
        raise RuntimeError("Windows binary is not PE x86-64")
    if not re.search(r"\bgit_plugin_init\b", exports):
        raise RuntimeError("Windows binary does not export git_plugin_init")
    dependencies = sorted(
        {
            line.strip().upper()
            for line in dependents.splitlines()
            if re.fullmatch(r"[A-Za-z0-9_.-]+\.dll", line.strip(), re.IGNORECASE)
        }
    )
    unexpected = sorted(set(dependencies) - WINDOWS_DEPENDENCIES)
    if unexpected:
        raise RuntimeError(
            "Windows binary has unexpected dynamic dependencies: "
            + ", ".join(unexpected)
        )
    return {"architecture": "PE x86-64", "dynamic_dependencies": dependencies}


def audit_linux(path: Path) -> dict[str, object]:
    identity = command("readelf", ["-h", str(path)])
    dynamic = command("readelf", ["-d", str(path)])
    symbols = command("readelf", ["-Ws", str(path)])
    if not re.search(r"Class:\s+ELF64", identity) or not re.search(
        r"Machine:\s+Advanced Micro Devices X86-64", identity
    ):
        raise RuntimeError("Linux binary is not ELF x86-64")
    if not re.search(r"\bgit_plugin_init\b", symbols):
        raise RuntimeError("Linux binary does not export git_plugin_init")
    dependencies = sorted(
        set(re.findall(r"Shared library: \[([^]]+)\]", dynamic))
    )
    unexpected = sorted(set(dependencies) - LINUX_DEPENDENCIES)
    if unexpected:
        raise RuntimeError(
            "Linux binary has unexpected dynamic dependencies: "
            + ", ".join(unexpected)
        )
    return {"architecture": "ELF x86-64", "dynamic_dependencies": dependencies}


def audit_macos(path: Path) -> dict[str, object]:
    architectures = set(command("lipo", ["-archs", str(path)]).split())
    if architectures != {"arm64", "x86_64"}:
        raise RuntimeError(
            "macOS binary is not universal arm64+x86_64: "
            + ", ".join(sorted(architectures))
        )
    linked = command("otool", ["-L", str(path)])
    symbols = command("nm", ["-gU", str(path)])
    if not re.search(r"\b_git_plugin_init\b", symbols):
        raise RuntimeError("macOS binary does not export git_plugin_init")
    dependencies = {
        line.strip().split()[0]
        for line in linked.splitlines()
        if line[:1].isspace() and line.strip()
    }
    dependencies.discard(str(path))
    dependencies = sorted(dependencies)
    unexpected = [
        dependency
        for dependency in dependencies
        if not dependency.startswith("/usr/lib/")
        and not dependency.startswith("/System/Library/Frameworks/")
    ]
    if unexpected:
        raise RuntimeError(
            "macOS binary has non-system dynamic dependencies: "
            + ", ".join(unexpected)
        )
    return {
        "architecture": "Mach-O universal arm64+x86_64",
        "dynamic_dependencies": dependencies,
    }


AUDITORS = {
    "linux": audit_linux,
    "macos": audit_macos,
    "windows": audit_windows,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted(AUDITORS), required=True)
    parser.add_argument("--binary", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.binary.is_file():
        parser.error(f"binary does not exist: {arguments.binary}")

    try:
        scan_markers(arguments.binary)
        platform_report = AUDITORS[arguments.platform](arguments.binary)
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "binary": arguments.binary.name,
                "passed": True,
                "platform": arguments.platform,
                "sha256": sha256(arguments.binary),
                "size": arguments.binary.stat().st_size,
                **platform_report,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
