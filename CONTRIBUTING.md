# Contributing

Thanks for improving the Redot Git Plugin. Keep changes narrowly scoped to
the editor Git provider; Redot owns the Version Control UI.

## Before opening a pull request

1. Clone with all submodules and keep the revisions in `UPSTREAM_LOCK.md`
   unchanged unless the pull request is explicitly a dependency update.
2. Build a production library with `test_harness=no`.
3. Run `python scripts/compare_vcs_api.py` and confirm the tracked report does
   not change unexpectedly.
4. Run the production activation fixture with Redot 26.2.
5. Build a separate test-only library and run
   `tests/run_provider_tests.py`.
6. For changes to credentials, callbacks, URL handling, fetch, pull, or push,
   also run `tests/run_private_transport_tests.py` and confirm its sentinel
   scan is clean.
7. Run `scripts/audit_binary.py` for every production binary built on the
   current host.
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
  sentinel match as a failed check.

## Commits and pull requests

Explain the user-visible behavior, the reason for the change, and the exact
validation performed. Include fixture evidence for bug fixes. If a check
could not be run, name the missing platform or prerequisite precisely.

Security reports do not belong in public issues. Follow `SECURITY.md`.
