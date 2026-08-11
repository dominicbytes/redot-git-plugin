# Upstream and dependency lock

This file defines the source and binary provenance for
`3.2.1-redot.26.2.1`. Full commit IDs are authoritative; branch and version
names are descriptive only.

## Provider baseline

| Field | Locked value |
| --- | --- |
| Upstream repository | `https://github.com/godotengine/godot-git-plugin` |
| Downstream fork | `https://github.com/dominicbytes/redot-git-plugin` |
| Downstream default branch | `redot-26.2` |
| Upstream release lineage | `v3.2.1` plus four commits |
| Provider commit | `de3324668df0ee52aeff8f4ab28db0a48203f514` |
| Provider commit time | `2026-07-30T18:27:01Z` |
| Downstream version | `3.2.1-redot.26.2.1` |
| Downstream intent | Redot 26.2 editor-only adaptation; retain full upstream history |
| License | MIT, with bundled dependency notices in `THIRDPARTY.md` |

The reproducibility epoch is `1785436021`, the provider commit time in UTC.

## Redot target

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
| redot-cpp branch | `26.2` |
| redot-cpp commit | `598ec78e86b2c240a023f6de13daba70f7de8610` |

The exact API evidence is stored under
`api/redot-26.2/4f5b14abade2239104847d03d8f9056e4467cfcd/`.
`scripts/compare_vcs_api.py` verifies those hashes and the 23-method
`EditorVCSInterface` contract before a release build is packaged.

## Native dependency gitlinks

| Dependency | Version in source | Commit | License summary |
| --- | --- | --- | --- |
| redot-cpp | Redot 26.2 branch | `598ec78e86b2c240a023f6de13daba70f7de8610` | MIT |
| libgit2 | 1.9.6 | `26055f5af74ab1cf636d272e8a34315496d3f06f` | GPL-2.0-only with linking exception and bundled notices |
| libssh2 | 1.11.0 | `1c3f1b7da588f2652260285529ec3c1f1125eb4e` | BSD-3-Clause |
| OpenSSL | 3.6.3 | `aae016bfd52fcad2bc9657c2c782cfdf73b1ed5f` | Apache-2.0 for current source, plus bundled legacy notices |

The prior `THIRDPARTY.md` libssh2 URL named a different commit than the
gitlink. The notice now names the actual locked gitlink above.

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

The verified clean production libraries are:

| Platform | Size | SHA-256 | Local proof |
| --- | ---: | --- | --- |
| Windows x86-64 | 7,860,224 | `fe658e70083537c5f928416ffa70fb4c8d30b6379836c8c6a47ec5ef22a14573` | PE/dependency/path/test-marker audit, no-op hash identity, clean Redot activation |
| Linux x86-64 | 11,974,840 | `23f35514f3f6cfd21e6d5a13cffee34cd583c1fe338076e0212c3ccdba320ae8` | ELF/dependency/path/test-marker audit, no-op hash identity, clean Redot activation |

The matching Windows export template executable has SHA-256
`723097ce13cc7c28202ce67337f167d15482ea57147be33ea1c5d7818a45b137`
and identifies itself as `26.2.stable.official.4f5b14aba`. macOS and the full
release archive are generated only from fresh CI artifacts and are not
predeclared here.
