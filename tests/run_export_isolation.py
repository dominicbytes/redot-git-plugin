#!/usr/bin/env python3
"""Prove that the editor-only provider is excluded from exported games."""

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


PRESET_NAME = "Redot Git Export Isolation"
ADDON_EXPORT_EXCLUDE = "addons/godot-git-plugin/*"
PLATFORMS = {
    "linux": {
        "export_platform": "Linux",
        "output": "redot-git-export.x86_64",
    },
    "windows": {
        "export_platform": "Windows Desktop",
        "output": "redot-git-export.exe",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str], cwd: Path, timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return run_process(
        command,
        cwd=cwd,
        timeout=timeout,
    )


def write_fixture(project: Path, addon_root: Path, platform: str, template: Path) -> Path:
    shutil.copytree(addon_root, project / "addons" / "godot-git-plugin")
    (project / "project.godot").write_text(
        """[application]

config/name="Redot Git Export Isolation"
run/main_scene="res://main.tscn"

[rendering]

renderer/rendering_method="gl_compatibility"
""",
        encoding="utf-8",
        newline="\n",
    )
    (project / "main.tscn").write_text(
        """[gd_scene load_steps=2 format=3]

[ext_resource path="res://main.gd" type="Script" id="1"]

[node name="Main" type="Node"]
script = ExtResource("1")
""",
        encoding="utf-8",
        newline="\n",
    )
    (project / "main.gd").write_text(
        """extends Node


func _ready() -> void:
	var result_path := "user://redot_git_export_isolation.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--redot-git-result="):
			result_path = argument.trim_prefix("--redot-git-result=")
	var class_visible := ClassDB.class_exists("GitPlugin")
	var payload := {
		"class_visible": class_visible,
		"passed": not class_visible,
	}
	var result := FileAccess.open(result_path, FileAccess.WRITE)
	if result == null:
		get_tree().quit(2)
		return
	result.store_string(JSON.stringify(payload, "\t"))
	result.close()
	get_tree().quit(0 if payload.passed else 1)
""",
        encoding="utf-8",
        newline="\n",
    )

    config = PLATFORMS[platform]
    template_value = json.dumps(template.resolve().as_posix())
    (project / "export_presets.cfg").write_text(
        f"""[preset.0]

name={json.dumps(PRESET_NAME)}
platform={json.dumps(config['export_platform'])}
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter={json.dumps(ADDON_EXPORT_EXCLUDE)}
export_path=""
patches=PackedStringArray()
patch_delta_encoding=false
patch_delta_compression_level_zstd=19
patch_delta_min_reduction=0.1
patch_delta_include_filters="*"
patch_delta_exclude_filters=""
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release={template_value}
debug/export_console_wrapper=1
binary_format/embed_pck=true
binary_format/architecture="x86_64"
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
shader_baker/enabled=false
codesign/enable=false
""",
        encoding="utf-8",
        newline="\n",
    )
    return project / "dist" / str(config["output"])




def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redot", type=Path, required=True)
    parser.add_argument("--addon-root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args()
    arguments.redot = arguments.redot.resolve()
    arguments.addon_root = arguments.addon_root.resolve()
    arguments.template = arguments.template.resolve()

    for label, path in (
        ("Redot editor", arguments.redot),
        ("addon root", arguments.addon_root),
        ("export template", arguments.template),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist")

    manifest = arguments.addon_root / "git_plugin.gdextension"
    if not manifest.is_file():
        parser.error("addon manifest does not exist")

    temp_root = Path(tempfile.mkdtemp(prefix="redot-git-export-"))
    project = temp_root / "project"
    project.mkdir()
    failures: list[str] = []
    try:
        identity = engine_identity(arguments.redot.resolve(), temp_root)
        executable = write_fixture(
            project, arguments.addon_root, arguments.platform, arguments.template
        )
        executable.parent.mkdir()

        import_process = run(
            [
                str(arguments.redot),
                "--headless", "--audio-driver", "Dummy",
                "--editor",
                "--path",
                str(project),
                "--import",
                "--quit-after",
                "120",
            ],
            project,
            timeout=60,
        )
        export_process = run(
            [
                str(arguments.redot),
                "--headless", "--audio-driver", "Dummy",
                "--path",
                str(project),
                "--quit-after",
                "120",
                "--export-release",
                PRESET_NAME,
                str(executable),
            ],
            project,
            timeout=240,
        )
        import_diagnostics = check_process(import_process, identity=identity)
        export_diagnostics = check_process(export_process, identity=identity)
        failures.extend(import_diagnostics["failures"])
        failures.extend(export_diagnostics["failures"])
        if not executable.is_file():
            failures.append("exported executable was not created")

        provider_files = sorted(
            path
            for path in arguments.addon_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".dll", ".dylib", ".so"}
        )
        provider_hashes = {sha256(path): path.name for path in provider_files}
        distribution = sorted(
            path for path in executable.parent.rglob("*") if path.is_file()
        )
        distribution_hashes = {sha256(path): path for path in distribution}
        copied_provider_files = [
            path.relative_to(executable.parent).as_posix()
            for digest, path in distribution_hashes.items()
            if digest in provider_hashes
        ]
        copied_provider_names = [
            path.relative_to(executable.parent).as_posix()
            for path in distribution
            if path.name in {provider.name for provider in provider_files}
        ]
        if copied_provider_files or copied_provider_names:
            failures.append("export distribution contains an editor provider library")

        runtime_result: dict[str, object] | None = None
        run_exit_code: int | None = None
        run_markers: list[str] = []
        run_process: subprocess.CompletedProcess[str] | None = None
        result_path = temp_root / "runtime-result.json"
        if executable.is_file():
            if arguments.platform == "linux":
                executable.chmod(executable.stat().st_mode | 0o111)
            run_process = run(
                [
                    str(executable),
                    "--headless", "--audio-driver", "Dummy",
                    "--quit-after",
                    "120",
                    "--",
                    "--redot-git-result=" + result_path.resolve().as_posix(),
                ],
                executable.parent,
                timeout=60,
            )
            run_exit_code = run_process.returncode
            runtime_diagnostics = check_process(run_process, identity=identity)
            run_markers = runtime_diagnostics["failures"]
            failures.extend(run_markers)
            if not result_path.is_file():
                failures.append("exported game did not write its isolation result")
            else:
                runtime_result = json.loads(result_path.read_text(encoding="utf-8"))
                if runtime_result.get("passed") is not True:
                    failures.append("GitPlugin was visible in the exported game")

        version = identity
        template_version = engine_identity(arguments.template.resolve(), project)
        report = {
            "distribution": [
                {
                    "path": path.relative_to(executable.parent).as_posix(),
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
                for path in distribution
            ],
            "export_exit_code": export_process.returncode,
            "export_exclude_filter": ADDON_EXPORT_EXCLUDE,
            "export_diagnostics": export_diagnostics,
            "failures": failures,
            "import_exit_code": import_process.returncode,
            "import_diagnostics": import_diagnostics,
            "passed": not failures,
            "platform": arguments.platform,
            "provider_binaries": [
                {
                    "name": path.name,
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
                for path in provider_files
            ],
            "provider_files_in_distribution": sorted(
                set(copied_provider_files + copied_provider_names)
            ),
            "redot_version": version,
            "run_exit_code": run_exit_code,
            "run_log_markers": run_markers,
            "runtime_result": runtime_result,
            "template_sha256": sha256(arguments.template),
            "template_version": template_version,
        }
        report = sanitize(report, {str(arguments.redot.resolve()): "$REDOT_BIN", str(temp_root): "<temp dir>"})
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if arguments.output:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(serialized, encoding="utf-8", newline="\n")
        print(serialized, end="")
        if failures:
            failed_processes = [
                ("import", import_process),
                ("export", export_process),
            ]
            if run_process is not None:
                failed_processes.append(("runtime", run_process))
            for label, process in failed_processes:
                print(f"--- {label} stdout ---\n{sanitize(process.stdout)}", file=sys.stderr)
                print(f"--- {label} stderr ---\n{sanitize(process.stderr)}", file=sys.stderr)
        return 1 if failures else 0
    finally:
        if arguments.keep:
            print("Fixture retained (--keep)", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(sanitize(str(error)), file=sys.stderr)
        raise SystemExit(1)
