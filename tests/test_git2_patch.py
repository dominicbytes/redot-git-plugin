"""The redirect security patch must be repeatable and fail on source drift."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.git2_patch import prepare_source


class RedirectPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        (self.source / "src/util").mkdir(parents=True)
        self.original = (ROOT / "thirdparty/git2/libgit2/src/util/net.c").read_bytes()
        (self.source / "src/util/net.c").write_bytes(self.original)
        self.target = self.root / "build-copy"
        self.patch = ROOT / "thirdparty/git2/patches/0001-restrict-redirect-origin.patch"

    def test_patch_is_idempotent_and_preserves_source(self) -> None:
        prepare_source(self.source, self.target, self.patch)
        net = self.target / "src/util/net.c"
        patched = net.read_text()
        self.assertIn("git__strcasecmp(original->scheme, tmp.scheme) != 0 ||", patched)
        self.assertIn("strcmp(original->port, tmp.port) != 0", patched)
        timestamp = net.stat().st_mtime_ns
        prepare_source(self.source, self.target, self.patch)
        self.assertEqual(timestamp, net.stat().st_mtime_ns)
        self.assertEqual(self.original, (self.source / "src/util/net.c").read_bytes())

    def test_repair_modified_build_copy(self) -> None:
        prepare_source(self.source, self.target, self.patch)
        net = self.target / "src/util/net.c"
        expected = net.read_bytes()
        net.write_bytes(b"drift")
        prepare_source(self.source, self.target, self.patch)
        self.assertEqual(expected, net.read_bytes())

    def test_upstream_drift_refuses_build(self) -> None:
        net = self.source / "src/util/net.c"
        net.write_bytes(self.original.replace(b"!allow_offsite &&", b"allow_offsite &&"))
        with self.assertRaisesRegex(RuntimeError, "security patch did not apply"):
            prepare_source(self.source, self.target, self.patch)
        self.assertFalse((self.target / ".redirect-patch").exists())


if __name__ == "__main__":
    unittest.main()
