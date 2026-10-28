# Upstream and dependency lock

This file defines the source and binary provenance for
`3.2.1-redot.26.3.1`. Full commit IDs are authoritative; branch and version
names are descriptive only.

## Provider baseline

| Field | Locked value |
| --- | --- |
| Upstream repository | `https://github.com/godotengine/godot-git-plugin` |
| Downstream fork | `https://github.com/dominicbytes/redot-git-plugin` |
| Downstream release branch | `redot-26.3` |
| Upstream release lineage | `v3.2.1` plus four commits |
| Provider commit | `de3324668df0ee52aeff8f4ab28db0a48203f514` |
| Provider commit time | `2026-07-30T18:27:01Z` |
| Downstream version | `3.2.1-redot.26.3.1` |
| Downstream intent | Redot 26.2 and 26.3 editor-only adaptation; retain full upstream history |
| License | MIT, with bundled dependency notices in `THIRDPARTY.md` |

The reproducibility epoch is `1785436021`, the provider commit time in UTC.

## Redot 26.2 binding baseline and supported target

| Field | Locked value |
| --- | --- |
| Redot release | `redot-26.2-stable` |
| Editor identity | `26.2.stable.official.4f5b14aba` |
| Engine commit | `4f5b14abade2239104847d03d8f9056e4467cfcd` |
| API lineage | `Godot Engine v4.5.2.stable.redot.custom_build` |
| Precision | single |
| Windows release asset | `Redot_v26.2-stable_windows_win64.zip` |
| Windows asset SHA-256 | `4644c7591bbe8019b861deb0ccdb64fd4f59a88514abf7c788cf176c259855af` |
| Linux release asset | `Redot_v26.2-stable_linux_x64.zip` |
| Linux asset SHA-256 | `f474d890806c41af15513cf5a8600243e241882e11b68dbb95660e3465b5b1e4` |
| macOS release asset | `Redot_v26.2-stable_macos_universal.zip` |
| macOS asset SHA-256 | `128cb7bca69b95a3998a84e72b0990a302ce5b1919dfb56cfdc709c2c87925ae` |
| redot-cpp source | `https://github.com/dominicbytes/redot-cpp` |
| redot-cpp commit | `9e7161bd7a3572a36ffa93109e73169861e9f834` |

The exact API evidence is stored under
`api/redot-26.2/4f5b14abade2239104847d03d8f9056e4467cfcd/`.
`scripts/compare_vcs_api.py` verifies those hashes and the 23-method
`EditorVCSInterface` contract before a release build is packaged.

## Redot 26.3 supported runtime target

| Field | Locked value |
| --- | --- |
| Redot release | `redot-26.3-stable` |
| Editor identity | `26.3.stable.official.85e520394` |
| Engine commit | `85e5203945af15755dd2f66cb6fdf7545fd88c0b` |
| API lineage | Godot-compatible 4.5.2; Redot 26.3.0 stable official |
| Precision | single |
| Windows release asset | `Redot_v26.3-stable_windows_win64.zip` |
| Windows asset SHA-256 | `2c6c7b4e96a88ca44eb413d9a5d43b8468b60a346c2448854c1a0c6bc9baab76` |
| Linux release asset | `Redot_v26.3-stable_linux_x64.zip` |
| Linux asset SHA-256 | `7d5155b80f4262f0a394c5040e539bb330cb63dd147bedd9172d83ec2efdbd91` |
| macOS release asset | `Redot_v26.3-stable_macos_universal.zip` |
| macOS asset SHA-256 | `bf781ae53dfaa4bbc6aadd21ebf2c69da3681ed85894d3ab2a816f0b03755a34` |

The exact runtime-target evidence is under
`api/redot-26.3/85e5203945af15755dd2f66cb6fdf7545fd88c0b/`.
The 26.2 API baseline above is retained; the owner binding fork adds the Array
initializer-list constructor fix. The pinned
redot-cpp cannot generate bindings for 26.3's added Struct variant; do not
build it against the 26.3 JSON. One binary built on 26.2 supports both editors.
The comparison verifies both sets of evidence and equality of the complete
VCS class surface, including the same 23 required methods.

## Native dependency gitlinks

| Dependency | Version in source | Commit | License summary |
| --- | --- | --- | --- |
| redot-cpp | Owner fork, 26.2 API | `9e7161bd7a3572a36ffa93109e73169861e9f834` | MIT |
| libgit2 | 1.9.7 | `49e408b3208bc3093757a1c2db938d3590f3f412` | GPL-2.0-only with linking exception and bundled notices |
| libssh2 | 1.11.2_DEV (master, 2026-10-16) | `3209951db4e47ef902db047d12f9f464f835c27e` | BSD-3-Clause |
| OpenSSL | 3.6.5 | `c8bd5a57108599ac650bbae77fcabe3109dab2e8` | Apache-2.0 for current source, plus bundled legacy notices |

The libgit2 build additionally applies
`thirdparty/git2/patches/0001-restrict-redirect-origin.patch` to a generated
build copy, preserving the locked submodule. When off-site redirects are
forbidden, scheme, host and port must all remain unchanged, preventing
cached HTTP credentials from reaching another port. Patch application is
idempotent and fails the build on drift. This security fix should be reported
upstream and removed after a pinned upstream release includes it. See ADR-0016.

libgit2 1.9.7 fixes SSH repository-path command injection
([CVE-2026-5917](https://github.com/libgit2/libgit2/blob/49e408b3208bc3093757a1c2db938d3590f3f412/docs/changelog.md)).

OpenSSL 3.6.5 includes the [2026-09-29 security advisory](https://github.com/openssl/openssl/blob/c8bd5a57108599ac650bbae77fcabe3109dab2e8/CHANGES.md)
fixes, including CVE-2026-35189 (CRLDP memory allocation).

libssh2 is pinned to an untagged master commit because no tagged release
contains the [ETM decrypt heap-overflow fix](https://github.com/libssh2/libssh2/commit/42e33d81577ed4b95d4b4f6f845e5ee8efe5eeb4)
(GHSA-6c79-444r-wx26). The pin also includes strict KEX for
CVE-2023-48795 (Terrapin, introduced in 1.11.1), the SSH-agent infinite-loop
fix (`d0a0210`), the decompression check (`d48eaed`), and subsequent fixes.
Move to the next tagged release containing these fixes when one exists;
repeat build, transport, and binary audits before changing the pin.
See ADR-0012 in `DECISIONS.md`.

## Reproducible build policy

- Initialize submodules recursively and reject a gitlink mismatch.
- Build production binaries with `test_harness=no` and `debug_symbols=no`.
- Set `SOURCE_DATE_EPOCH=1785436021`.
- Map build-root paths out of compiler output and request deterministic MSVC
  compilation and linking.
- Link the native dependencies statically; platform dependency inspection
  must show only operating-system libraries.
- Package only the manifest, the three declared editor binaries,
  `README.md`, `LICENSE`, `THIRDPARTY.md`, `VERSION`, and generated manifests
  and checksums.
- The package command fails when any platform is missing or a binary contains
  test-harness markers.

Production binary sizes, SHA-256 hashes, audit records, and archive checksums
are produced by CI for this release. They are not predeclared here.
