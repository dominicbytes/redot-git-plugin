# Redot 26.3 API evidence

This directory freezes the runtime target contract for engine commit
`85e5203945af15755dd2f66cb6fdf7545fd88c0b`, editor identity
`26.3.stable.official.85e520394`.

| File | SHA-256 |
|---|---|
| `editor_vcs_interface.cpp` | `f506c3d9b3fd6ea9f3803ce19b793b4e6723d1ba0713372f75dd4ae9cca98137` |
| `editor_vcs_interface.h` | `b21426608f8e8457f3e9e59fb63322de2779e5afb64f7c2f3b951e7cd6cc8fd8` |
| `EditorVCSInterface.xml` | `0f91a2c47fd7a2d21d8a50fc354633e85afcce3ef16c2090d4ba3e9eb0eda86e` |
| `extension_api.json` | `4c709d5920855dfe7294d01b9899d21aec4e94d3df9fc46f7aa90ad8fff5a38e` |
| `gdextension_interface.h` | `558c1f54f5e37afdf259fec29d6eb72da83781afdce48e51a1783942f9cf9895` |

The official editor generated `extension_api.json` and `gdextension_interface.h`
with `$REDOT_BIN --headless --dump-extension-api --dump-gdextension-interface`.
The dumped interface header is byte-identical to the engine source header.
The XML and editor VCS header/source are from the engine commit above and are
byte-identical to the locked 26.2 counterparts.

The JSON reports Godot-compatible 4.5.2 and its `redot_header` reports
26.3.0 stable official. The interface header appends
`GDEXTENSION_VARIANT_TYPE_STRUCT` immediately before `VARIANT_MAX`. The JSON
also adds builtin `Struct`, WorldScape3D/Mode7 classes, and `OS.get_real_path`;
the plugin's VCS contract is unchanged.

These files are verification evidence, not binding-generation inputs. Retain
the 26.2 redot-cpp commit and 26.2 API baseline for both supported editors.
The pinned bindings cannot be generated against the new Struct/VARIANT_MAX
surface. One binary built on 26.2 is tested on both 26.2 and 26.3.
