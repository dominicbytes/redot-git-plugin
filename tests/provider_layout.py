"""Install a compiled provider into the matching fixture addon layout."""

from __future__ import annotations

import shutil
from pathlib import Path


PROVIDER_LAYOUTS = {
    ".dll": ("windows", "libgit_plugin.windows.editor.x86_64.dll"),
    ".so": ("linux", "libgit_plugin.linux.editor.x86_64.so"),
    ".dylib": ("macos", "libgit_plugin.macos.editor.universal.dylib"),
}


def install_provider(root: Path, project: Path, provider: Path) -> None:
    layout = PROVIDER_LAYOUTS.get(provider.suffix.lower())
    if layout is None:
        raise ValueError(f"unsupported provider library type: {provider}")

    platform, filename = layout
    addon = project / "addons" / "godot-git-plugin"
    platform_dir = addon / platform
    platform_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        root / "addons" / "godot-git-plugin" / "git_plugin.gdextension",
        addon,
    )
    shutil.copy2(provider, platform_dir / filename)
    # Load the installed extension before editor-plugin activation on first open.
    # The editor still performs its normal resource scan in that same process.
    cache = project / ".godot"
    cache.mkdir(exist_ok=True)
    (cache / "extension_list.cfg").write_text(
        "res://addons/godot-git-plugin/git_plugin.gdextension\n",
        encoding="utf-8", newline="\n",
    )


def install_scenario_driver(project: Path, script: str) -> None:
    """Run a SceneTree scenario inside the normal editor lifecycle.

    Using --editor --script replaces the editor SceneTree and leaks its UI
    resources even in a plugin-free control. An EditorPlugin driver leaves
    ownership of the editor tree with the engine.
    """
    addon = project / "addons" / "fixture-driver"
    addon.mkdir(parents=True, exist_ok=True)
    (addon / "plugin.cfg").write_text(
        '[plugin]\nname="Fixture driver"\ndescription="Test only"\n'
        'author=""\nversion="1"\nscript="driver.gd"\n', encoding="utf-8", newline="\n"
    )
    (addon / "driver.gd").write_text(
        f"""@tool
extends EditorPlugin

func _enter_tree() -> void:
	call_deferred("_run_fixture")

func _run_fixture() -> void:
	var scenario: SceneTree = load("res://{script}").new()
	scenario.call("_run")
	scenario.free()
""", encoding="utf-8", newline="\n"
    )
    project_file = project / "project.godot"
    contents = project_file.read_text(encoding="utf-8")
    if "[editor_plugins]" not in contents:
        contents += '\n[editor_plugins]\nenabled=PackedStringArray("res://addons/fixture-driver/plugin.cfg")\n'
        project_file.write_text(contents, encoding="utf-8", newline="\n")
