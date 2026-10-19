"""Prepare a patched libgit2 build copy while preserving the locked submodule."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def prepare_source(source: Path, target: Path, patch: Path) -> Path:
    original = (source / "src/util/net.c").read_bytes()
    identity = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                              capture_output=True, check=False)
    revision = identity.stdout.strip() if identity.returncode == 0 else b""
    signature = hashlib.sha256(revision + original + patch.read_bytes()).hexdigest()
    stamp = target / ".redirect-patch"
    patched = target / "src/util/net.c"
    if stamp.is_file() and patched.is_file():
        recorded = stamp.read_text().splitlines()
        if recorded == [signature, hashlib.sha256(patched.read_bytes()).hexdigest()]:
            return target
    # Recreate invalidated copies so removed or renamed upstream files vanish.
    if target.exists():
        shutil.rmtree(target)
    # Copy upstream timestamps so unrelated C objects need not rebuild.
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    # git apply also works outside repositories. Stop discovery at the build
    # copy's parent so patches cannot affect the enclosing source checkout.
    environment["GIT_CEILING_DIRECTORIES"] = str(target.parent.resolve())
    for options in (["--check"], []):
        process = subprocess.run(["git", "apply", "--unidiff-zero", *options, str(patch.resolve())], cwd=target,
                                 env=environment, capture_output=True, check=False)
        if process.returncode:
            raise RuntimeError("libgit2 redirect security patch did not apply; build refused")
    stamp.write_text(signature + "\n" + hashlib.sha256(patched.read_bytes()).hexdigest() + "\n")
    return target
