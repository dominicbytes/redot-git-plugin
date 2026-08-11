#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]]; then
  echo "Usage: ./release.sh --input-root <assembled-addon> [package_release.py options]" >&2
  exit 2
fi

exec python3 "$repository/scripts/package_release.py" "$@"
