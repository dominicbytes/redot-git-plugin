#!/usr/bin/env python3
"""Compare the provider surface with the pinned Redot EditorVCSInterface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ENGINE_COMMIT = "4f5b14abade2239104847d03d8f9056e4467cfcd"
REDOT_CPP_COMMIT = "598ec78e86b2c240a023f6de13daba70f7de8610"
ENGINE_26_3_COMMIT = "85e5203945af15755dd2f66cb6fdf7545fd88c0b"

EXPECTED_HASHES = {
    "extension_api.json": "453a0cc128bb58333a001f7f43573a5961d973fb7b151af43139869f22d5915c",
    "gdextension_interface.h": "4cd695e86b92e2bf4e60bbe19ce137faf41205da1cf94f29e069afec0f7bf320",
    "EditorVCSInterface.xml": "0f91a2c47fd7a2d21d8a50fc354633e85afcce3ef16c2090d4ba3e9eb0eda86e",
    "editor_vcs_interface.cpp": "f506c3d9b3fd6ea9f3803ce19b793b4e6723d1ba0713372f75dd4ae9cca98137",
    "editor_vcs_interface.h": "b21426608f8e8457f3e9e59fb63322de2779e5afb64f7c2f3b951e7cd6cc8fd8",
}

TARGETS = {
    "26.2": (ENGINE_COMMIT, EXPECTED_HASHES),
    "26.3": (ENGINE_26_3_COMMIT, EXPECTED_HASHES | {
        "extension_api.json": "4c709d5920855dfe7294d01b9899d21aec4e94d3df9fc46f7aa90ad8fff5a38e",
        "gdextension_interface.h": "558c1f54f5e37afdf259fec29d6eb72da83781afdce48e51a1783942f9cf9895",
    }),
}


def loader_accepts(minimum: str, redot: tuple[int, int, int],
                   godot: tuple[int, int, int], disable_godot_checks: bool = False) -> bool:
    """Mirror the loader's minimum gate and Godot-version fallback."""
    parts = minimum.split(".")
    # The loader reads major/minor/patch, defaulting absent components to zero.
    version = tuple(max(0, int(part)) if re.fullmatch(r"[+-]?\d+", part) else 0
                    for part in (parts + ["0", "0"])[:3])
    return version >= (4, 1, 0) and (
        version <= redot or (not disable_godot_checks and version <= godot)
    )


EXPECTED_ENUMS = {
    "ChangeType": {
        "CHANGE_TYPE_NEW": 0,
        "CHANGE_TYPE_MODIFIED": 1,
        "CHANGE_TYPE_RENAMED": 2,
        "CHANGE_TYPE_DELETED": 3,
        "CHANGE_TYPE_TYPECHANGE": 4,
        "CHANGE_TYPE_UNMERGED": 5,
    },
    "TreeArea": {
        "TREE_AREA_COMMIT": 0,
        "TREE_AREA_STAGED": 1,
        "TREE_AREA_UNSTAGED": 2,
    },
}

EXPECTED_SCHEMAS = {
    "create_diff_line": ["new_line_no", "old_line_no", "content", "status"],
    "create_diff_hunk": ["new_lines", "old_lines", "new_start", "old_start", "diff_lines"],
    "create_diff_file": ["new_file", "old_file", "diff_hunks"],
    "create_commit": ["message", "author", "unix_timestamp", "offset_minutes", "id"],
    "create_status_file": ["file_path", "change_type", "area"],
}

METHOD_RE = re.compile(
    r"^\s*(?P<return>[\w:<>, ]+?)\s+(?P<name>_\w+)\((?P<args>.*)\)\s+override;",
    re.MULTILINE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_arguments(arguments: str) -> list[str]:
    if not arguments.strip():
        return []
    result: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(arguments):
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
        elif character == "," and depth == 0:
            result.append(arguments[start:index].strip())
            start = index + 1
    result.append(arguments[start:].strip())
    return result


def normalize_cpp_type(value: str) -> str:
    value = re.sub(r"\bconst\b", "", value)
    value = value.replace("&", "").replace(" ", "")
    return value


def parse_cpp_argument(value: str) -> tuple[str, str]:
    match = re.match(r"^(?P<type>.*?)(?P<name>[A-Za-z_]\w*)$", value.strip())
    if not match:
        raise ValueError(f"Unable to parse C++ argument: {value}")
    cpp_type = match.group("type").rstrip()
    return normalize_cpp_type(cpp_type), match.group("name")


def parse_provider_header(path: Path) -> dict[str, dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    methods: dict[str, dict[str, object]] = {}
    for match in METHOD_RE.finditer(text):
        methods[match.group("name")] = {
            "return": normalize_cpp_type(match.group("return")),
            "arguments": [parse_cpp_argument(value) for value in split_arguments(match.group("args"))],
        }
    return methods


def api_type(value: dict[str, object] | None) -> str:
    if value is None:
        return "void"
    type_name = str(value["type"])
    mappings = {
        "bool": "bool",
        "String": "godot::String",
        "typedarray::Dictionary": "godot::TypedArray<godot::Dictionary>",
        "typedarray::String": "godot::TypedArray<godot::String>",
    }
    if type_name == "int" and value.get("meta") == "int32":
        return "int32_t"
    return mappings.get(type_name, type_name)


def api_signature(method: dict[str, object]) -> dict[str, object]:
    arguments = []
    for argument in method.get("arguments", []):
        arguments.append((api_type(argument), argument["name"]))
    return {
        "return": api_type(method.get("return_value")),
        "arguments": arguments,
    }


def format_signature(name: str, signature: dict[str, object]) -> str:
    arguments = ", ".join(f"{kind} {arg_name}" for kind, arg_name in signature["arguments"])
    return f"{signature['return']} {name}({arguments})"


def extract_schema(source: str, function_name: str) -> list[str]:
    start = source.find(f"EditorVCSInterface::{function_name}(")
    if start == -1:
        return []
    body_start = source.find("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body = source[body_start:index]
                return re.findall(r'\["([^"]+)"\]', body)
    return []


def compare(root: Path, target: str = "26.2") -> tuple[str, bool]:
    engine_commit, expected_hashes = TARGETS[target]
    api_dir = root / "api" / f"redot-{target}" / engine_commit
    failures: list[str] = []
    hash_rows = []
    for name, expected in expected_hashes.items():
        path = api_dir / name
        actual = sha256(path) if path.is_file() else "missing"
        result = "PASS" if actual == expected else "FAIL"
        if result == "FAIL":
            failures.append(f"{name} hash")
        hash_rows.append((name, expected, actual, result))

    api = json.loads((api_dir / "extension_api.json").read_text(encoding="utf-8"))
    header = api["header"]
    editor_class = next(item for item in api["classes"] if item["name"] == "EditorVCSInterface")
    required_methods = {
        item["name"]: api_signature(item)
        for item in editor_class["methods"]
        if item.get("is_virtual") and item.get("is_required")
    }
    if len(required_methods) != 23:
        failures.append("expected exactly 23 required virtuals")
    baseline = json.loads((root / "api" / "redot-26.2" / ENGINE_COMMIT / "extension_api.json").read_text(encoding="utf-8"))
    baseline_class = next(item for item in baseline["classes"] if item["name"] == "EditorVCSInterface")
    if editor_class != baseline_class:
        failures.append("VCS surface differs from 26.2 baseline")
    provider_methods = parse_provider_header(root / "godot-git-plugin" / "src" / "git_plugin.h")

    method_rows = []
    for name, expected in required_methods.items():
        actual = provider_methods.get(name)
        result = "Adopt" if actual == expected else "Adapt"
        if result != "Adopt":
            failures.append(f"method {name}")
        method_rows.append(
            (
                name,
                format_signature(name, expected),
                format_signature(name, actual) if actual else "missing",
                result,
            )
        )
    unexpected = sorted(set(provider_methods) - set(required_methods))
    if unexpected:
        failures.append("unexpected override methods")

    enum_rows = []
    api_enums = {
        item["name"]: {entry["name"]: entry["value"] for entry in item["values"]}
        for item in editor_class["enums"]
    }
    for name, expected in EXPECTED_ENUMS.items():
        actual = api_enums.get(name, {})
        result = "Adopt" if actual == expected else "Reject"
        if result != "Adopt":
            failures.append(f"enum {name}")
        enum_rows.append((name, expected, actual, result))

    source = (api_dir / "editor_vcs_interface.cpp").read_text(encoding="utf-8")
    schema_rows = []
    for name, expected in EXPECTED_SCHEMAS.items():
        actual = extract_schema(source, name)
        result = "Adopt" if actual == expected else "Reject"
        if result != "Adopt":
            failures.append(f"schema {name}")
        schema_rows.append((name, expected, actual, result))

    registration_source = (root / "godot-git-plugin" / "src" / "gdlibrary.cpp").read_text(encoding="utf-8")
    provider_header = (root / "godot-git-plugin" / "src" / "git_plugin.h").read_text(encoding="utf-8")
    manifest = (root / "addons" / "godot-git-plugin" / "git_plugin.gdextension").read_text(encoding="utf-8")
    minimum_match = re.search(r'compatibility_minimum\s*=\s*"([^"]+)"', manifest)
    minimum = minimum_match.group(1) if minimum_match else "missing"
    disable_godot_checks = bool(re.search(r"disable_godot_checks\s*=\s*true", manifest))
    registration_checks = {
        "Direct EditorVCSInterface subclass": "class GitPlugin : public godot::EditorVCSInterface" in provider_header,
        "ClassDB name remains GitPlugin": "register_class<GitPlugin>()" in registration_source,
        "Editor-only initialization": registration_source.count("MODULE_INITIALIZATION_LEVEL_EDITOR") >= 2,
        "Manifest and exported entry symbol agree": (
            'entry_symbol = "git_plugin_init"' in manifest and "git_plugin_init(" in registration_source
        ),
        "Manifest minimum accepted by Redot loader": (
            minimum != "missing" and loader_accepts(minimum, (26, int(target.split(".")[1]), 0), (4, 5, 2), disable_godot_checks)
        ),
        "Manifest minimum retains 4.3": minimum == "4.3",
        "VCS surface equals the 26.2 baseline": editor_class == baseline_class,
        "Exactly 23 required virtuals": len(required_methods) == 23,
    }
    for name, passed in registration_checks.items():
        if not passed:
            failures.append(name)

    lines = [
        "# Redot EditorVCSInterface compatibility report",
        "",
        "Generated by `scripts/compare_vcs_api.py`; edit the inputs or script, not this report.",
        "",
        "## Locked target",
        "",
        f"- Redot engine commit: `{engine_commit}`",
        f"- Redot editor identity: `{target}.stable.official.{engine_commit[:9]}`",
        f"- Retained 26.2 C++ binding commit: `{REDOT_CPP_COMMIT}`",
        f"- API identity: `{header['version_full_name']}`",
        f"- API version: `{header['version_major']}.{header['version_minor']}.{header['version_patch']}`",
        f"- Precision: `{header['precision']}`",
        f"- Required provider virtuals: `{len(required_methods)}`",
        "",
        "## Evidence hashes",
        "",
        "| File | Expected SHA-256 | Actual SHA-256 | Result |",
        "|---|---|---|---|",
    ]
    lines.extend(f"| `{name}` | `{expected}` | `{actual}` | {result} |" for name, expected, actual, result in hash_rows)
    lines.extend(
        [
            "",
            "## Required virtual methods",
            "",
            f"| Method | Redot {target} contract | Provider declaration | Decision |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(f"| `{name}` | `{expected}` | `{actual}` | {result} |" for name, expected, actual, result in method_rows)
    lines.extend(
        [
            "",
            "## Enums",
            "",
            "| Enum | Expected values | Redot values | Decision |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(f"| `{name}` | `{expected}` | `{actual}` | {result} |" for name, expected, actual, result in enum_rows)
    lines.extend(
        [
            "",
            "## Helper dictionary schemas",
            "",
            "| Helper | Expected key order | Redot key order | Decision |",
            "|---|---|---|---|",
        ]
    )
    lines.extend(f"| `{name}` | `{expected}` | `{actual}` | {result} |" for name, expected, actual, result in schema_rows)
    lines.extend(
        [
            "",
            "## Registration and manifest",
            "",
            "| Check | Result |",
            "|---|---|",
        ]
    )
    lines.extend(f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in registration_checks.items())
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            (
                f"PASS — the provider surface is source-compatible with the pinned Redot {target} contract. "
                "No adapter class, endpoint rename, enum translation, or helper-schema translation is required."
                if not failures
                else "FAIL — unresolved rows: " + ", ".join(failures) + "."
            ),
            "",
            "Allowed product metadata differences are limited to Redot branding/build identity. Runtime ABI and "
            "registration still require a successful native build and bounded editor load.",
            "",
        ]
    )
    return "\n".join(lines), not failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="26.2 report; 26.3 is written alongside with a -26.3 suffix")
    arguments = parser.parse_args()

    passed = True
    for target in TARGETS:
        report, target_passed = compare(arguments.root.resolve(), target)
        passed = passed and target_passed
        if arguments.output:
            output = arguments.output
            if target == "26.3":
                output = output.with_stem(output.stem + "-26.3")
            if not output.is_absolute():
                output = arguments.root / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8", newline="\n")
        else:
            print(report, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
