## Summary

Describe the user-visible behavior and why this change is needed.

## Validation

- [ ] Redot 26.2 and 26.3 API comparisons and Python unit tests pass.
- [ ] Production library builds with `test_harness=no`.
- [ ] Same production binary activates on Redot 26.2 and 26.3; record any ADR-0013 classification.
- [ ] Provider parity suite passes on both editors with the same test-only build.
- [ ] Private HTTPS/SSH fixture passes when transport or credential code changed.
- [ ] Changed C++ files pass clang-format.
- [ ] `git diff --check` passes.
- [ ] No credentials, fixture repositories, caches, or binaries were committed.

List exact commands, platforms, and any check that could not be run.

## Scope

- [ ] The change preserves Redot's existing Version Control UI and the
  `GitPlugin` compatibility boundary.
- [ ] Documentation, notices, and upstream locks were updated when applicable.
