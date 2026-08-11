# Security policy

## Supported version

Security fixes are prepared for the current Redot 26.2 port release line.
Older development snapshots are not supported.

## Reporting a vulnerability

Once this repository is hosted on GitHub, use its private security advisory
form: **Security** -> **Advisories** -> **Report a vulnerability**. Until that
private channel is enabled, contact the repository owner directly rather
than filing a public issue.

Do not include a real password, access token, SSH passphrase, private key,
credential-bearing URL, or unredacted personal repository path. Use synthetic
sentinels and state whether the value appeared in logs, project files, Git
configuration, crash output, or a release archive.

Helpful reports include the Redot version and commit, plugin version or
commit, operating system, transport type, minimal reproduction, expected
sanitization boundary, and whether the issue reproduces with disposable
credentials.

The maintainer will acknowledge a private report, reproduce it in an isolated
fixture, prepare a fix and regression test, and coordinate disclosure after a
patched release is available. No response-time guarantee is made before the
public repository and private reporting channel exist.
