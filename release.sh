#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]]; then
  echo "Usage: ./release.sh --input-root <assembled-addon> [package_release.py options]" >&2
  echo "Release packages require --audit-records <records-dir>." >&2
  echo "Local packages: --allow-partial --skip-audit-records (all binary checks still run)." >&2
  exit 2
fi

python_bin=python3
if ! "$python_bin" --version >/dev/null 2>&1; then
  python_bin=python
fi
exec "$python_bin" "$repository/scripts/package_release.py" "$@"
