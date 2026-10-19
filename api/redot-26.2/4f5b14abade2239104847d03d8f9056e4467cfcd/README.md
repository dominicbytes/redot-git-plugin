# Redot 26.2 API lock

This directory freezes the extension contract used to build and verify the
plugin.

| File | SHA-256 | Provenance |
|---|---|---|
| `extension_api.json` | `453a0cc128bb58333a001f7f43573a5961d973fb7b151af43139869f22d5915c` | `Redot-Engine/redot-cpp` commit `598ec78e86b2c240a023f6de13daba70f7de8610` |
| `gdextension_interface.h` | `4cd695e86b92e2bf4e60bbe19ce137faf41205da1cf94f29e069afec0f7bf320` | `Redot-Engine/redot-cpp` commit `598ec78e86b2c240a023f6de13daba70f7de8610` |
| `EditorVCSInterface.xml` | `0f91a2c47fd7a2d21d8a50fc354633e85afcce3ef16c2090d4ba3e9eb0eda86e` | `Redot-Engine/redot-engine` commit `4f5b14abade2239104847d03d8f9056e4467cfcd` |
| `editor_vcs_interface.cpp` | `f506c3d9b3fd6ea9f3803ce19b793b4e6723d1ba0713372f75dd4ae9cca98137` | `Redot-Engine/redot-engine` commit `4f5b14abade2239104847d03d8f9056e4467cfcd` |
| `editor_vcs_interface.h` | `b21426608f8e8457f3e9e59fb63322de2779e5afb64f7c2f3b951e7cd6cc8fd8` | `Redot-Engine/redot-engine` commit `4f5b14abade2239104847d03d8f9056e4467cfcd` |

The official Windows editor reports
`26.2.stable.official.4f5b14aba` and its Windows release ZIP has SHA-256
`4644c7591bbe8019b861deb0ccdb64fd4f59a88514abf7c788cf176c259855af`.
Its API-dump commands crash with signal 11 in this build. The two generated
contract files above therefore come from the Redot C++ binding commit signed
and labeled “Sync with Redot 26.2-stable”; the exact engine XML and C++ files
are included as a separate source-level cross-check. This exception must be rechecked when Redot publishes a fixed
26.2 editor build.
