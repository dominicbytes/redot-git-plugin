## Summary

Describe the user-visible behavior and why this change is needed.

## Validation

- [ ] Redot 26.2 API comparison passes.
- [ ] Production library builds with `test_harness=no`.
- [ ] Production activation fixture passes without errors or warnings.
- [ ] Provider parity suite passes with a separate test-only build.
- [ ] Private HTTPS/SSH fixture passes when transport or credential code changed.
- [ ] Changed C++ files pass clang-format.
- [ ] `git diff --check` passes.
- [ ] No credentials, fixture repositories, caches, or binaries were committed.

List exact commands, platforms, and any check that could not be run.

## Scope

- [ ] The change preserves Redot's existing Version Control UI and the
  `GitPlugin` compatibility boundary.
- [ ] Documentation, notices, and upstream locks were updated when applicable.
