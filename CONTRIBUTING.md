# Contributing

Thanks for improving the Redot Git Plugin. Keep changes narrowly scoped to
the editor Git provider; Redot owns the Version Control UI.

## Before opening a pull request

1. Clone with all submodules and keep the revisions in `UPSTREAM_LOCK.md`
   unchanged unless the pull request is explicitly a dependency update.
2. Build a production library with `test_harness=no`.
3. Run `python scripts/compare_vcs_api.py --output reports/api-diffs/git-editor-vcs-interface.md`
   and confirm both tracked reports do not change unexpectedly. Keep the 26.2
   binding baseline; the 26.3 evidence is not a binding-generation input.
   Run `python -m unittest discover -s tests -p "test_*.py" -v`.
4. Run the production activation fixture with both Redot 26.2 and 26.3 using
   the same production library.
5. Build a separate test-only library and run
   `tests/run_provider_tests.py` with both editors using that same test library.
6. For changes to credentials, callbacks, URL handling, fetch, pull, or push,
   also run `tests/run_private_transport_tests.py` and confirm its sentinel
   scan is clean.
7. Run `scripts/audit_binary.py` for every production binary built on the
   current host. Save each result with `--record <records-dir>/<platform-id>.json`
   and pass that directory to packaging with `--audit-records <records-dir>`.
   Release records must match the current auditor version and binary SHA-256.
8. For release changes, run `tests/run_export_isolation.py` with the exact
   Redot editor/template and confirm the package command fails closed if any
   declared platform is missing.
9. Run `git diff --check` and clang-format the changed C++ files.

The exact commands and prerequisites are in `README.md`. Do not commit native
build outputs, generated packages, caches, fixture repositories, credentials,
or local Redot state.

## Design rules

- Preserve the `GitPlugin` class and existing `EditorVCSInterface` contract.
- Prefer the smallest change proven by a failing fixture or API report.
- Do not add a replacement VCS dock, credential store, engine patch, or
  automatic force-push behavior.
- Keep credentials ephemeral and sanitize diagnostics before they reach
  Redot's output.
- Treat a crash, timeout, parse/load error, unexplained warning, or secret
  sentinel match as a failed check. The only temporary exception is ADR-0014:
  exact official 26.3 exit defects must be reported separately as
  `known_engine_shutdown_crash`, `known_engine_shutdown_leak`,
  `known_engine_import_crash`, or `known_engine_import_leak`, never described
  as clean passes. A banner-less crash requires the exact Windows
  access-violation status, completed shutdown, a passing result, explicit
  confirmation that all providers were freed, and only allowlisted output.
  Import exceptions require no provider activity or plugin frames. Verify a
  patched 26.3 editor cleanly when available.

## Commits and pull requests

Explain the user-visible behavior, the reason for the change, and the exact
validation performed. Include fixture evidence for bug fixes. If a check
could not be run, name the missing platform or prerequisite precisely.

Security reports do not belong in public issues. Follow `SECURITY.md`.
