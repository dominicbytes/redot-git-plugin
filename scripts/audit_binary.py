#!/usr/bin/env python3
"""Fail a release build with the wrong architecture, symbols, dependencies, or markers."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from binary_formats import AUDITORS
from binary_scan import ensure_clean


AUDIT_TOOL_VERSION = "2"
AUDIT_RECORD_FORMAT = 1


def audit_bytes(data: bytes, platform: str) -> dict[str, object]:
    ensure_clean(data)
    return {
        "format": AUDIT_RECORD_FORMAT,
        "tool_version": AUDIT_TOOL_VERSION,
        "passed": True,
        "platform": platform,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        **AUDITORS[platform](data),
    }


def verify_record(path: Path, report: dict[str, object]) -> None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("missing or invalid audit record") from None
    if not isinstance(record, dict) or any(
        record.get(key) != value or type(record.get(key)) is not type(value)
        for key, value in report.items()
    ):
        raise RuntimeError("audit record does not match binary, platform, or tool version")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted(AUDITORS), required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--record", type=Path, help="write a SHA-256-bound JSON audit record")
    arguments = parser.parse_args()
    try:
        report = {
            "binary": arguments.binary.name,
            **audit_bytes(arguments.binary.read_bytes(), arguments.platform),
        }
        if arguments.record:
            arguments.record.parent.mkdir(parents=True, exist_ok=True)
            arguments.record.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n",
            )
    except OSError:
        print("error: cannot read binary or write audit record", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
