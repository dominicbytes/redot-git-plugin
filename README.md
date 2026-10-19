<p align="center">
  <img src="icon.svg" width="180" alt="Redot Git Plugin icon">
</p>

# Redot Git Plugin

> [!IMPORTANT]
> This is the Redot-specific downstream fork of
> [`godotengine/godot-git-plugin`](https://github.com/godotengine/godot-git-plugin).
> It targets Redot 26.2; Godot users should use the upstream plugin.

An editor-only Git provider for Redot 26.2. It implements Redot's existing
`EditorVCSInterface` with libgit2; Redot continues to own the Version Control
dock, dialogs, diffs, and confirmations.

This port is based on
[`godotengine/godot-git-plugin@de332466`](https://github.com/godotengine/godot-git-plugin/commit/de3324668df0ee52aeff8f4ab28db0a48203f514)
and preserves the upstream `GitPlugin` class and `addons/godot-git-plugin`
path for compatibility.

## Features

- Inspect tracked, staged, untracked, renamed, deleted, type-changed, and
  conflicted files.
- Stage, unstage, discard, commit, and browse bounded commit history.
- View staged, unstaged, commit, root-commit, rename, deletion, large-text,
  binary, hunk, and line diffs.
- Create, switch, list, and remove branches, including safe detached-HEAD
  handling.
- Create and remove remotes; fetch, pull, merge, push, and explicitly force
  push.
- Authenticate with HTTPS credentials, SSH keys and passphrases, or the SSH
  agent without persisting secrets in project files.
- Use Redot's CA certificate bundle for HTTPS remotes.

The provider does not create a repository during activation. Initialize the
project with Git first, either through Redot's own metadata workflow or with
`git init`.

## Compatibility

| Component | Supported target |
| --- | --- |
| Redot | 26.2 stable, engine commit `4f5b14abade2239104847d03d8f9056e4467cfcd` |
| Windows | x86-64 editor |
| Linux | x86-64 editor |
| macOS | Universal editor binary: arm64 and x86-64 |
| Runtime/export | Editor only; no runtime or exported-game dependency |

The GDExtension manifest uses Redot's Godot-compatible API lineage. This
package is built and tested for Redot, and does not claim compatibility with
upstream Godot releases.

## Installation

1. Download the release ZIP and its `.sha256` sidecar.
2. Verify the SHA-256 checksum.
3. Extract the ZIP at the project root. The manifest must end up at
   `res://addons/godot-git-plugin/git_plugin.gdextension`.
4. Ensure the project is already inside a Git repository.
5. Open Redot's Version Control setup, select `GitPlugin`, and initialize the
   provider.

For HTTPS remotes, enter the account name and token in Redot's credential
fields. For SSH remotes, use the SSH username, public/private key paths, and
optional passphrase fields. Do not put passwords, tokens, or private key data
in a remote URL. URLs containing user information or credential-like query
parameters are rejected.

## Exporting games

The provider is editor-only. In every game export preset, add
`addons/godot-git-plugin/*` to the **Resources > Filters to exclude** field.
The equivalent preset entry is:

```ini
exclude_filter="addons/godot-git-plugin/*"
```

Redot 26.2 otherwise retains the editor-only `.gdextension` descriptor in the
export pack and the exported game reports a missing runtime library. The
exclusion keeps the installed editor provider out of both the game package and
the runtime extension list.

## Building from source

Clone recursively so every pinned dependency is present:

```shell
git clone --recursive https://github.com/dominicbytes/redot-git-plugin.git
cd redot-git-plugin
```

Required tools are Python 3.9 or newer, SCons 4.10.1, CMake, Perl, NASM, and a
platform C/C++ toolchain. On Windows, use an x64 MSVC developer shell with
`nmake` available and native Windows Perl, such as Strawberry Perl, ahead
of Git for Windows/MSYS or Cygwin Perl on `PATH`. OpenSSL with MSVC requires
Perl to report `MSWin32`.

Production examples:

```shell
scons platform=windows arch=x86_64 build_profile=build_profile.json debug_symbols=no test_harness=no
scons platform=linux arch=x86_64 build_profile=build_profile.json debug_symbols=no test_harness=no
scons platform=macos arch=universal macos_deployment_target=10.13 build_profile=build_profile.json debug_symbols=no test_harness=no
```

Outputs are written beneath `addons/godot-git-plugin/<platform>/`. The build
statically links the pinned OpenSSL, libssh2, libgit2, and redot-cpp sources.
Exact revisions and the reproducibility epoch are recorded in
[`UPSTREAM_LOCK.md`](UPSTREAM_LOCK.md).

`test_harness=yes` exposes provider methods to the fixture and must never be
used for a release binary. The packaging tool checks for these bindings and
fails closed.

## Validation

Set `REDOT_BIN` to the Redot 26.2 console editor and run the contract and
production smoke checks:

```shell
python scripts/compare_vcs_api.py
python tests/run_fixture.py --redot "$REDOT_BIN" --provider <production-library>
python scripts/audit_binary.py --platform <windows|linux|macos> --binary <production-library>
```

Build a separate test-only library and run the complete local parity suite:

```shell
scons platform=windows arch=x86_64 build_profile=build_profile.json debug_symbols=no test_harness=yes target_path=addons/redot-git-test/
python tests/run_provider_tests.py --redot "$REDOT_BIN" --provider addons/redot-git-test/windows/libgit_plugin.windows.editor.x86_64.dll
```

The private transport fixture additionally requires Docker. It creates
disposable local HTTPS and SSH Git servers, uses synthetic credentials, and
scans all captured output for secret sentinels:

```shell
python tests/run_private_transport_tests.py --redot "$REDOT_BIN" --provider addons/redot-git-test/windows/libgit_plugin.windows.editor.x86_64.dll
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full change checklist.

## Packaging

The release workflow combines platform artifacts only after all builds and
the API gate pass. To package an already assembled addon locally:

```shell
python scripts/package_release.py --input-root <assembled-addon> --audit-records <records-dir> --output-dir dist
```

The tool creates a deterministic ZIP, manifest, and checksum sidecar. It
requires Windows x86-64, Linux x86-64, and macOS universal binaries by
default. Each platform also requires a JSON record written by the current
binary auditor, bound to that library's SHA-256, size, and platform. For example:

```shell
python scripts/audit_binary.py --platform windows --binary <production-library> --record <records-dir>/windows-x86_64.json
```

Use `linux-x86_64.json` and `macos-universal.json` for the other records.
The auditor validates library format, architecture, defined exported entry
point, system dependencies, test markers, and absolute build paths without
requiring host-specific binary inspection tools. The package command repeats
these checks and scans every archived file, including documents, for paths
and test markers. Diagnostics identify offsets and categories with values
redacted. Archive entries, manifests, and checksums use case-sensitive POSIX
name ordering on every host.

`--allow-partial` permits missing platforms in visibly named local packages.
To omit audit records locally, explicitly use both flags:

```shell
./release.sh --input-root <assembled-addon> --output-dir dist --allow-partial --skip-audit-records
```

All binary and payload checks still run. Such packages have a partial name and
record their unverified audit-record status; they are not releases.

## Limitations

This is the same backend boundary as the upstream provider, not a general Git
client. It does not add Git LFS transport, submodule-management UI,
merge-resolution UI, hosting-service features, or credential persistence.
Network operations use Redot's synchronous `EditorVCSInterface`; test a
representative large repository before adopting the plugin team-wide.

## Security

Credentials are instance-bound and cleared at shutdown. Diagnostics pass
through a centralized sanitizer, and credential-bearing remote URLs are
rejected. Please report suspected credential exposure privately as described
in [`SECURITY.md`](SECURITY.md); never attach a real token, passphrase, or key
to an issue.

## Provenance and license

The provider is a Redot adaptation of the MIT-licensed Godot Git Plugin. The
port keeps full Git history and exact submodule pins. Redot-specific changes,
API evidence, decisions, and upstream synchronization notes live in this
repository.

The plugin is licensed under the [MIT License](LICENSE). Required notices for
redot-cpp, libgit2, libssh2, OpenSSL, and their bundled components are in
[`THIRDPARTY.md`](THIRDPARTY.md).

## Notes

I vibe coded this in GPT Sol 5.6. Use at your own risk. Actual programmers are welcome to submit PR's and feedback.

## About Dominic Bytes

Greetings! I am Dominic Bytes, the synth walker. I hail from the distant future. Where brains occupy robot bodies, time travel is a trip to the corner store, and the neon glow of our attire is powered by the light of our souls. Join me on a 1.21 gigawatt powered journey of chill vibes with gaming, anime, movies, and more!

- [Website](https://dominicbytes.carrd.co/)
- [X](https://x.com/DominicBytes)
- [Twitch](https://www.twitch.tv/dominicbytes)
- [YouTube](http://www.youtube.com/@DominicBytes)
- [Kick](https://kick.com/dominicbytes)
