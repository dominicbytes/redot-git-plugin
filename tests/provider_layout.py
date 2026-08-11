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
