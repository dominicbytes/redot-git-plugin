# Architecture decisions

## ADR-0003: Keep the port backend-only

- Date: 2026-08-10
- Status: accepted
- Decision: Adapt the upstream `GitPlugin` implementation to Redot 26.2 while
  retaining the direct `EditorVCSInterface` subclass, registered class name,
  addon path, and Redot-owned Version Control UI.
- Consequence: No replacement dock, engine patch, runtime component,
  credential store, or speculative adapter is included.

## ADR-0004: Bind to the exact Redot 26.2 source contract

- Date: 2026-08-10
- Status: accepted
- Decision: Replace the godot-cpp gitlink with
  `Redot-Engine/redot-cpp@598ec78e86b2c240a023f6de13daba70f7de8610`
  and verify the engine commit's API files by SHA-256.
- Context: The official editor's API dump commands crash in this build. The
  exact engine-source API, generated redot-cpp binding, 23-method comparison,
  successful native build, and bounded runtime load form the compatibility
  proof.
- Consequence: A different Redot engine or binding commit requires a new API
  report and rebuild.

## ADR-0005: Expose fixture calls only in a separate test build

- Date: 2026-08-10
- Status: accepted
- Decision: Gate direct provider bindings behind
  `REDOT_GIT_TEST_HARNESS`, controlled by the SCons `test_harness` option.
- Consequence: The fixture can exercise every provider endpoint without
  adding production API. Packaging scans binaries for test markers and
  rejects a contaminated release.

## ADR-0006: Make remote credentials ephemeral and fail closed

- Date: 2026-08-10
- Status: accepted
- Decision: Keep credentials on the active provider instance, clear them at
  shutdown, centralize diagnostic redaction, reject remote URLs with user
  information or credential-like query parameters, and support SSH agent
  fallback.
- Consequence: Users enter HTTPS tokens and SSH key details through Redot's
  credential fields. The provider does not persist or infer credentials from
  URLs.

## ADR-0007: Release one deterministic three-platform addon

- Date: 2026-08-10
- Status: accepted
- Decision: Build Windows x86-64, Linux x86-64, and macOS universal in
  independent CI jobs, then create one normalized archive only after every
  job and the API gate pass.
- Consequence: A partial local package is visibly labeled and cannot be
  mistaken for a release. Archive timestamps, order, modes, content, and
  checksums are deterministic.

## ADR-0008: Preserve pinned third-party source diagnostics

- Date: 2026-08-10
- Status: accepted
- Decision: Do not patch the locked OpenSSL or libssh2 submodules merely to
  suppress their Windows generator/configuration diagnostics.
- Context: OpenSSL 3.6.3 emits known Perl generator diagnostics on Windows,
  and libssh2's static CMake build warns while probing for OpenSSL DLLs. The
  final static libraries build successfully, the plugin has no external
  OpenSSL/libssh2 dependency, and Redot activation is clean.
- Consequence: These messages are documented dependency baselines, not
  silently reclassified as plugin runtime warnings.

## ADR-0009: Prepare hosting without publishing

- Date: 2026-08-10
- Status: accepted
- Decision: Add local GitHub workflows, issue forms, security policy,
  contribution guidance, provenance, and release tooling, but do not create a
  repository, push a branch, or publish a release without explicit owner
  authorization.

## ADR-0010: Exclude the editor provider from game exports

- Date: 2026-08-10
- Status: accepted
- Decision: Add `addons/godot-git-plugin/*` to every game export preset's
  exclusion filter and verify the exported game without the provider.
- Context: Redot 26.2 retains an editor-only `.gdextension` descriptor in the
  export pack unless the preset excludes it. The descriptor then produces a
  missing runtime-library diagnostic even though the declared native
  libraries are editor-only.
- Consequence: Installation remains unchanged, while release documentation
  and export-isolation tests make this preset requirement explicit.

## ADR-0011: Publish a named Redot fork while preserving upstream topology

- Date: 2026-08-10
- Status: accepted
- Decision: Publish `dominicbytes/redot-git-plugin` as a GitHub fork of
  `godotengine/godot-git-plugin`, retain the original repository as local
  `upstream`, and use `redot-26.2` as the downstream default branch.
- Consequence: GitHub preserves the original fork relationship while the
  repository name, description, README, topics, and default branch make the
  Redot target explicit. Source publication does not authorize a release tag
  or downloadable release before the remaining gates pass.

## ADR-0012: Pin libssh2 master until a tagged release includes the fixes

- Date: 2026-10-19
- Status: accepted
- Context: libssh2 1.11.0 predates strict KEX for CVE-2023-48795
  (Terrapin). Version 1.11.1 adds strict KEX, but no tagged release
  contains the ETM decrypt heap-overflow fix
  `42e33d81577ed4b95d4b4f6f845e5ee8efe5eeb4` (GHSA-6c79-444r-wx26).
- Decision: Pin unmodified libssh2 master at
  `3209951db4e47ef902db047d12f9f464f835c27e` (2026-10-16,
  source version `1.11.2_DEV`). This also includes the SSH-agent infinite-loop
  fix, the decompression check, and subsequent fixes. Full commit identity,
  rather than the development version label, defines the dependency.
- Consequence: Accept an untagged upstream snapshot to obtain these fixes
  without maintaining a local security patch. Move to the next tagged
  release containing them when available, after repeating build, transport,
  and binary audits. Keep the dependency source unmodified under ADR-0008.
