"""Shared release payload checks with redacted diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass


TEST_MARKERS = (
    "redot_git_test_harness",
    "test_initialize",
    "test_sanitize_output",
    "test_credentials_empty",
)
# Drive and network roots are generic. POSIX user/build roots avoid confusing
# protocol endpoints and runtime configuration names with build locations.
PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<drive>[A-Za-z]:[/\\]+[A-Za-z0-9_.-][^\x00-\x20\"<>|]*)"
    r"|(?<![A-Za-z0-9_./\\:@])(?P<unc>\\{2,}[A-Za-z0-9_-][A-Za-z0-9_.-]*\\+[^\x00-\x20\"<>|]+)"
    r"|(?<![A-Za-z0-9_./\\:@])(?P<posix>/"
    r"(?:home|Users|root|build|builds|workspace|workspaces|tmp|private|var/tmp|mnt|Volumes|opt)/"
    r"[^\x00-\x20\"<>|]+)"
)
PRINTABLE = re.compile(r"[ -~]{4,}")


@dataclass(frozen=True)
class Finding:
    offset: int
    category: str
    encoding: str

    def diagnostic(self) -> str:
        return (
            f"offset={self.offset} category={self.category} "
            f"encoding={self.encoding} value=<redacted>"
        )


def scan_bytes(data: bytes) -> list[Finding]:
    findings: set[Finding] = set()
    views = [(data.decode("latin-1"), "ASCII", 0, 1)]
    for encoding in ("utf-16-le", "utf-16-be"):
        for alignment in (0, 1):
            size = (len(data) - alignment) // 2 * 2
            views.append((
                data[alignment:alignment + size].decode(encoding, errors="replace"),
                encoding,
                alignment,
                2,
            ))
    for value, encoding, alignment, width in views:
        for run in PRINTABLE.finditer(value):
            for match in PATH_PATTERN.finditer(run.group()):
                findings.add(Finding(
                    alignment + width * (run.start() + match.start()),
                    f"absolute-{match.lastgroup}-path",
                    encoding,
                ))
        lowered = value.lower()
        for marker in TEST_MARKERS:
            start = 0
            while (offset := lowered.find(marker, start)) != -1:
                findings.add(Finding(
                    alignment + width * offset, "test-harness-marker", encoding
                ))
                start = offset + len(marker)
    return sorted(findings, key=lambda item: (item.offset, item.category, item.encoding))


def ensure_clean(data: bytes) -> None:
    findings = scan_bytes(data)
    if findings:
        counts = sum(item.category.startswith("absolute-") for item in findings)
        markers = len(findings) - counts
        raise RuntimeError(
            f"payload rejected: absolute-path matches={counts}, "
            f"test-harness matches={markers}; "
            + "; ".join(item.diagnostic() for item in findings[:8])
        )
