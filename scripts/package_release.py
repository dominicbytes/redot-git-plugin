#!/usr/bin/env python3
"""Create a deterministic, audited Redot Git Plugin release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SOURCE_DATE_EPOCH = 1785436021
ADDON_NAME = "godot-git-plugin"
MANIFEST = "git_plugin.gdextension"
PLATFORM_BINARIES = {
    "linux-x86_64": Path("linux/libgit_plugin.linux.editor.x86_64.so"),
    "macos-universal": Path("macos/libgit_plugin.macos.editor.universal.dylib"),
    "windows-x86_64": Path("windows/libgit_plugin.windows.editor.x86_64.dll"),
}
DOCUMENTS = (
    Path("README.md"),
    Path("LICENSE"),
    Path("THIRDPARTY.md"),
    Path("VERSION"),
    Path("LICENSES/OpenSSL-Apache-2.0.txt"),
)
TEST_MARKERS = (
    b"REDOT_GIT_TEST_HARNESS",
    b"test_initialize",
    b"test_sanitize_output",
    b"test_credentials_empty",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_version(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]*", cleaned):
        raise ValueError(f"invalid release version: {value!r}")
    return cleaned


def ensure_production_binary(path: Path) -> None:
    data = path.read_bytes()
    for marker in TEST_MARKERS:
        if marker in data:
            raise RuntimeError(
                f"{path} contains test-harness marker {marker.decode('ascii')!r}"
            )


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def normalized_zip(source_root: Path, output: Path, epoch: int) -> None:
    timestamp = datetime.fromtimestamp(epoch, timezone.utc)
    zip_timestamp = (
        max(timestamp.year, 1980),
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        timestamp.second - (timestamp.second % 2),
    )
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=zip_timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def package(
    repository: Path,
    input_root: Path,
    output_dir: Path,
    version: str,
    epoch: int,
    allow_partial: bool,
) -> Path:
    source_manifest = input_root / MANIFEST
    if not source_manifest.is_file():
        raise FileNotFoundError(f"missing addon manifest: {source_manifest}")

    included = [
        platform
        for platform, relative in PLATFORM_BINARIES.items()
        if (input_root / relative).is_file()
    ]
    missing = sorted(set(PLATFORM_BINARIES) - set(included))
    if missing and not allow_partial:
        raise RuntimeError(
            "release is incomplete; missing platform binaries: " + ", ".join(missing)
        )
    if not included:
        raise RuntimeError("no platform binaries were supplied")

    for platform in included:
        ensure_production_binary(input_root / PLATFORM_BINARIES[platform])

    output_dir.mkdir(parents=True, exist_ok=True)
    version_slug = version.replace("+", "-")
    completeness = "" if not missing else "-partial-" + "-".join(included)
    archive_name = f"redot-git-plugin-v{version_slug}{completeness}.zip"
    archive_path = output_dir / archive_name

    with tempfile.TemporaryDirectory(prefix="redot-git-release-") as temporary:
        stage = Path(temporary)
        addon = stage / "addons" / ADDON_NAME
        addon.mkdir(parents=True)
        shutil.copy2(source_manifest, addon / MANIFEST)

        for platform in included:
            relative = PLATFORM_BINARIES[platform]
            destination = addon / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_root / relative, destination)

        for document in DOCUMENTS:
            source = repository / document
            if not source.is_file():
                raise FileNotFoundError(f"missing release document: {source}")
            destination = addon / document
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        payload_files = sorted(
            item for item in addon.rglob("*") if item.is_file()
        )
        payload = [
            {
                "path": path.relative_to(addon).as_posix(),
                "sha256": sha256(path),
                "size": path.stat().st_size,
            }
            for path in payload_files
        ]
        release_manifest = {
            "complete_platform_set": not missing,
            "format": 1,
            "included_platforms": included,
            "missing_platforms": missing,
            "project": "Redot Git Plugin",
            "redot": {
                "engine_commit": "4f5b14abade2239104847d03d8f9056e4467cfcd",
                "version": "26.2.stable",
            },
            "source_date_epoch": epoch,
            "upstream_provider_commit": "de3324668df0ee52aeff8f4ab28db0a48203f514",
            "version": version,
            "files": payload,
        }
        manifest_path = addon / "MANIFEST.json"
        write_json(manifest_path, release_manifest)

        checksum_files = sorted(
            item
            for item in addon.rglob("*")
            if item.is_file() and item.name != "SHA256SUMS.txt"
        )
        (addon / "SHA256SUMS.txt").write_text(
            "".join(
                f"{sha256(path)}  {path.relative_to(addon).as_posix()}\n"
                for path in checksum_files
            ),
            encoding="utf-8",
            newline="\n",
        )

        normalized_zip(stage, archive_path, epoch)
        shutil.copy2(
            manifest_path,
            output_dir / f"redot-git-plugin-v{version_slug}{completeness}-manifest.json",
        )

    archive_hash = sha256(archive_path)
    (output_dir / f"{archive_name}.sha256").write_text(
        f"{archive_hash}  {archive_name}\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "archive": str(archive_path),
                "complete_platform_set": not missing,
                "included_platforms": included,
                "sha256": archive_hash,
            },
            indent=2,
        )
    )
    return archive_path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=repository / "dist")
    parser.add_argument("--version")
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="create a visibly named audit package when one or more platforms are absent",
    )
    arguments = parser.parse_args()

    version = safe_version(
        arguments.version
        if arguments.version is not None
        else (repository / "VERSION").read_text(encoding="utf-8")
    )
    try:
        package(
            repository=repository,
            input_root=arguments.input_root.resolve(),
            output_dir=arguments.output_dir.resolve(),
            version=version,
            epoch=arguments.source_date_epoch,
            allow_partial=arguments.allow_partial,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
