"""Synthetic release-tool regression fixtures; no native tools are required."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_binary
import binary_formats
import binary_scan
import package_release


def pe_fixture() -> bytes:
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x2002)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 260, 16)
    struct.pack_into("<II", data, 264, 0x1000, 128)
    data[392:400] = b".text\0\0\0"
    struct.pack_into("<IIII", data, 400, 1536, 0x1000, 1536, 512)
    struct.pack_into("<IIIII", data, 532, 1, 1, 0x1028, 0x102C, 0x1030)
    struct.pack_into("<IIH", data, 552, 0x1100, 0x1040, 0)
    data[576:592] = b"git_plugin_init\0"
    data[768] = 0xC3
    return bytes(data)


def elf_fixture(
    binding: int = 1, kind: int = 2, defined: int = 1,
    visibility: int = 0, dynamic_symbols: bool = True,
) -> bytes:
    names = b"\0.text\0.shstrtab\0.dynstr\0.dynsym\0.dynamic\0.symtab\0"
    strings = b"\0git_plugin_init\0libc.so.6\0"
    data = bytearray(1024)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", data, 16, 3, 62, 1)
    struct.pack_into("<Q", data, 40, 640)
    struct.pack_into("<HHHHHH", data, 52, 64, 0, 0, 64, 6, 2)
    data[128] = 0xC3
    data[144:144 + len(names)] = names
    data[208:208 + len(strings)] = strings
    struct.pack_into("<IBBHQQ", data, 280, 1, binding << 4 | kind, visibility, defined, 128, 1)
    struct.pack_into("<qQqQ", data, 320, 1, 17, 0, 0)
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (1, 1, 6, 128, 128, 1, 0, 0, 1, 0),
        (7, 3, 0, 0, 144, len(names), 0, 0, 1, 0),
        (17, 3, 0, 0, 208, len(strings), 0, 0, 1, 0),
        (25 if dynamic_symbols else 42, 11 if dynamic_symbols else 2,
         0, 0, 256, 48, 3, 1, 8, 24),
        (33, 6, 0, 0, 320, 32, 3, 0, 8, 16),
    ]
    for index, section in enumerate(sections):
        struct.pack_into("<IIQQQQIIQQ", data, 640 + index * 64, *section)
    return bytes(data)


def macho_slice(cpu: int, defined: bool = True) -> bytes:
    data = bytearray(512)
    struct.pack_into("<IIIIIIII", data, 0, 0xFEEDFACF, cpu, 0, 6, 2, 176, 0, 0)
    struct.pack_into("<II", data, 32, 0x19, 152)
    struct.pack_into("<I", data, 96, 1)
    struct.pack_into("<I", data, 168, 0x80000400)
    struct.pack_into("<IIIIII", data, 184, 2, 24, 256, 1, 272, 18)
    struct.pack_into("<IBBHQ", data, 256, 1, 0x0F if defined else 1, 1 if defined else 0, 0, 320)
    data[272:290] = b"\0_git_plugin_init\0\0"
    data[320] = 0xC3
    return bytes(data)


def macho_fixture(second_defined: bool = True, wide: bool = False) -> bytes:
    data = bytearray(1152)
    struct.pack_into(">II", data, 0, 0xCAFEBABF if wide else 0xCAFEBABE, 2)
    offsets = (128, 640)
    for index, cpu in enumerate((0x1000007, 0x100000C)):
        if wide:
            struct.pack_into(">IIQQII", data, 8 + 32 * index, cpu, 0, offsets[index], 512, 6, 0)
        else:
            struct.pack_into(">IIIII", data, 8 + 20 * index, cpu, 0, offsets[index], 512, 6)
        data[offsets[index]:offsets[index] + 512] = macho_slice(
            cpu, index == 0 or second_defined
        )
    return bytes(data)


def synthetic_paths() -> list[str]:
    slash = "/"
    backslash = chr(92)
    return [
        "Q" + chr(58) + backslash + backslash.join(("sample-build", "obj", "source.cpp")),
        "R" + chr(58) + slash + slash.join(("sample-build", "source.cpp")),
        slash + slash.join(("home", "sample-account", "build", "source.cpp")),
        slash + slash.join(("Users", "sample-account", "build", "source.cpp")),
        slash + slash.join(("workspace", "build", "source.cpp")),
        backslash * 2 + backslash.join(("sample-server", "sample-share", "source.cpp")),
    ]


class ScannerTests(unittest.TestCase):
    def test_paths_at_both_alignments_and_byte_orders(self) -> None:
        for value in synthetic_paths():
            for encoding in ("ascii", "utf-16-le", "utf-16-be"):
                for alignment in (0, 1):
                    with self.subTest(encoding=encoding, alignment=alignment):
                        data = b"\0" * alignment + value.encode(encoding) + b"\0\0"
                        matches = binary_scan.scan_bytes(data)
                        self.assertTrue(any(
                            item.offset == alignment and item.category.startswith("absolute-")
                            for item in matches
                        ))
                        with self.assertRaises(RuntimeError) as raised:
                            binary_scan.ensure_clean(data)
                        self.assertNotIn(value, str(raised.exception))
                        self.assertIn("value=<redacted>", str(raised.exception))

    def test_relative_paths_system_libraries_and_runtime_names(self) -> None:
        values = (
            "src/git_plugin.cpp", "docs/build.md", "res" + chr(58) + "//addons/example/plugin.gd",
            "KERNEL32.DLL", "libc.so.6", "/usr/lib/libSystem.B.dylib",
            "/System/Library/Frameworks/Security.framework/Versions/A/Security",
            "https" + chr(58) + "//example.invalid/info/refs", "/info/refs?service=git-upload-pack",
            chr(92) * 2 + "." + chr(92) + "pipe" + chr(92) + "openssh-ssh-agent",
        )
        for value in values:
            for encoding in ("ascii", "utf-16-le", "utf-16-be"):
                with self.subTest(value=value, encoding=encoding):
                    self.assertEqual([], binary_scan.scan_bytes(value.encode(encoding)))

    def test_neutral_openssl_install_prefix_is_allowed(self) -> None:
        backslash = chr(92)
        drive = "C" + chr(58)
        allowed = (
            backslash.join((drive, "redot-git-plugin", "ssl")),
            backslash.join((drive, "redot-git-plugin", "openssl", "lib", "ossl-modules")),
            drive + "/redot-git-plugin/openssl/lib/engines-3",
        )
        for value in allowed:
            for encoding in ("ascii", "utf-16-le"):
                with self.subTest(value=value, encoding=encoding):
                    self.assertEqual([], binary_scan.scan_bytes(value.encode(encoding)))
        rejected = (
            backslash.join((drive, "redot-git-plugin-build", "source.cpp")),
            backslash.join((drive, "redot-git-plugin", "..", "sample-build", "source.cpp")),
            backslash.join(("D" + chr(58), "redot-git-plugin", "ssl")),
        )
        for value in rejected:
            with self.subTest(value=value):
                self.assertTrue(binary_scan.scan_bytes(value.encode("ascii")))

    def test_backslash_runs_in_compiled_tables_are_not_unc_paths(self) -> None:
        backslash = b"\\"
        samples = (
            b"\x88Pu(" + backslash * 2 + b"m" + backslash * 2 + b"\xda1\xb8\x86",
            b"\x86" + backslash * 2 + b"mm" + backslash * 2 + b"\xda1\xb8",
            b"L" + backslash * 3 + b"XXX0" + backslash * 4 + b"XXXXPPTPPT  \x1c",
            b"(" + backslash * 3 + b"server" + backslash + b"share\x00",
        )
        for data in samples:
            with self.subTest(data=data):
                self.assertEqual([], binary_scan.scan_bytes(data))

    def test_escaped_paths_in_text(self) -> None:
        for value in synthetic_paths():
            encoded = json.dumps({"path": value}).encode("ascii")
            self.assertTrue(binary_scan.scan_bytes(encoded))

    def test_test_markers_in_all_encodings(self) -> None:
        for encoding in ("ascii", "utf-16-le", "utf-16-be"):
            data = b"\0" + "ReDoT_GiT_TeSt_HaRnEsS".encode(encoding)
            self.assertTrue(any(
                item.category == "test-harness-marker"
                for item in binary_scan.scan_bytes(data)
            ))


class FormatTests(unittest.TestCase):
    def test_valid_platforms(self) -> None:
        for platform, data in (
            ("windows", pe_fixture()), ("linux", elf_fixture()),
            ("macos", macho_fixture()), ("macos", macho_fixture(wide=True)),
        ):
            with self.subTest(platform=platform):
                report = audit_binary.audit_bytes(data, platform)
                self.assertIs(report["passed"], True)
                self.assertEqual(hashlib.sha256(data).hexdigest(), report["sha256"])

    def test_placeholders_wrong_formats_and_truncation(self) -> None:
        for platform, fixture in (
            ("windows", pe_fixture()), ("linux", elf_fixture()), ("macos", macho_fixture()),
        ):
            for data in (b"placeholder", fixture[:60], b"MZ" + bytes(200)):
                with self.subTest(platform=platform, size=len(data)):
                    with self.assertRaises(RuntimeError):
                        audit_binary.audit_bytes(data, platform)

    def test_pe_requires_dll_architecture_and_real_export(self) -> None:
        for offset, layout, value in (
            (132, "H", 0x14C), (150, "H", 2), (552, "I", 0),
            (552, "I", 0x1040), (560, "H", 1),
        ):
            data = bytearray(pe_fixture())
            struct.pack_into("<" + layout, data, offset, value)
            with self.subTest(offset=offset, value=value):
                with self.assertRaises(RuntimeError):
                    binary_formats.audit_windows(bytes(data))
        data = pe_fixture().replace(b"git_plugin_init", b"git_plugin_fake")
        with self.assertRaises(RuntimeError):
            binary_formats.audit_windows(data)

    def test_elf_requires_defined_global_or_weak_dynamic_function(self) -> None:
        binary_formats.audit_linux(elf_fixture(binding=2))
        for arguments in (
            {"defined": 0}, {"binding": 0}, {"kind": 1}, {"visibility": 2},
            {"dynamic_symbols": False}, {"defined": 6},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(RuntimeError):
                    binary_formats.audit_linux(elf_fixture(**arguments))
        for offset, value in ((16, 2), (18, 183)):
            data = bytearray(elf_fixture())
            struct.pack_into("<H", data, offset, value)
            with self.assertRaises(RuntimeError):
                binary_formats.audit_linux(bytes(data))

    def test_dependency_allowlists(self) -> None:
        data = bytearray(pe_fixture())
        struct.pack_into("<II", data, 272, 0x1200, 40)
        struct.pack_into("<IIIII", data, 1024, 0, 0, 0, 0x1240, 0)
        data[1088:1101] = b"ADVAPI32.DLL\0"
        self.assertEqual(["ADVAPI32.DLL"], binary_formats.audit_windows(bytes(data))["dynamic_dependencies"])
        data[1088:1101] = b"UNTRUSTED.DLL"
        with self.assertRaisesRegex(RuntimeError, "unexpected dynamic dependencies"):
            binary_formats.audit_windows(bytes(data))
        with self.assertRaisesRegex(RuntimeError, "unexpected dynamic dependencies"):
            binary_formats.audit_linux(elf_fixture().replace(b"libc.so.6", b"libz.so.9"))

    def test_macos_requires_both_slices_and_defined_exports(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "defined exported"):
            binary_formats.audit_macos(macho_fixture(second_defined=False))
        data = bytearray(macho_fixture())
        struct.pack_into(">I", data, 28, 0x1000007)
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            binary_formats.audit_macos(bytes(data))
        with self.assertRaises(RuntimeError):
            binary_formats.audit_macos(macho_slice(0x1000007))
        data = bytearray(macho_fixture())
        struct.pack_into(">I", data, 8 + 20 + 8, 128)
        with self.assertRaisesRegex(RuntimeError, "overlapping"):
            binary_formats.audit_macos(bytes(data))


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repo"
        self.addon = self.root / "addon"
        self.output = self.root / "out"
        self.records = self.root / "records"
        self.records.mkdir()
        self.addon.mkdir()
        (self.addon / package_release.MANIFEST).write_text("[configuration]\n", encoding="utf-8")
        for document in package_release.DOCUMENTS:
            path = self.repository / document
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Release document.\n", encoding="utf-8")
        self.binary = self.addon / package_release.PLATFORM_BINARIES["windows-x86_64"]
        self.binary.parent.mkdir()
        self.binary.write_bytes(pe_fixture())

    def package(self, **options) -> Path:
        with contextlib.redirect_stdout(io.StringIO()):
            return package_release.package(
                self.repository, self.addon, self.output, "1.0", 1785436021,
                **{"allow_partial": True, **options},
            )

    def record(self) -> Path:
        path = self.records / "windows-x86_64.json"
        package_release.write_json(path, audit_binary.audit_bytes(self.binary.read_bytes(), "windows"))
        return path

    def test_records_required_and_local_escape_is_explicit(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "required"):
            self.package()
        with self.assertRaisesRegex(RuntimeError, "requires --allow-partial"):
            self.package(allow_partial=False, skip_audit_records=True)
        self.assertIn("-partial-", self.package(skip_audit_records=True).name)

    def test_records_bound_to_hash_platform_and_version(self) -> None:
        for key, value in (
            ("sha256", "0" * 64), ("platform", "linux"),
            ("tool_version", "0"), ("passed", False), ("format", True),
        ):
            path = self.record()
            report = json.loads(path.read_text(encoding="utf-8"))
            report[key] = value
            package_release.write_json(path, report)
            with self.subTest(key=key):
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    self.package(audit_records=self.records)
        self.record()
        self.package(audit_records=self.records)
        self.binary.write_bytes(self.binary.read_bytes() + b"\0")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.package(audit_records=self.records)

    def test_records_missing_or_invalid(self) -> None:
        for content in (None, "{", "[]"):
            path = self.records / "windows-x86_64.json"
            if content is not None:
                path.write_text(content, encoding="utf-8")
            with self.assertRaises(RuntimeError):
                self.package(audit_records=self.records)

    def test_placeholders_rejected_even_for_local_packages(self) -> None:
        self.binary.write_bytes(b"placeholder")
        with self.assertRaises(RuntimeError):
            self.package(skip_audit_records=True)

    def test_full_package_requires_all_platforms(self) -> None:
        self.record()
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            self.package(allow_partial=False, audit_records=self.records)
        for platform, data in (("linux-x86_64", elf_fixture()), ("macos-universal", macho_fixture())):
            binary = self.addon / package_release.PLATFORM_BINARIES[platform]
            binary.parent.mkdir()
            binary.write_bytes(data)
            package_release.write_json(
                self.records / (platform + ".json"),
                audit_binary.audit_bytes(data, platform.split("-")[0]),
            )
        archive = self.package(allow_partial=False, audit_records=self.records)
        self.assertNotIn("-partial-", archive.name)

    def test_every_archived_file_including_documents_is_scanned(self) -> None:
        for encoding in ("ascii", "utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                (self.repository / "README.md").write_bytes(synthetic_paths()[0].encode(encoding))
                with self.assertRaisesRegex(RuntimeError, "absolute-path matches"):
                    self.package(skip_audit_records=True)
                self.assertEqual([], list(self.output.glob("*.zip")))

    def test_case_sensitive_order_and_deterministic_bytes(self) -> None:
        extras = (Path("a.txt"), Path("Z.txt"))
        for path in extras:
            (self.repository / path).write_text(path.name, encoding="utf-8")
        with mock.patch.object(package_release, "DOCUMENTS", package_release.DOCUMENTS + extras):
            first = self.package(skip_audit_records=True).read_bytes()
            second = self.package(skip_audit_records=True).read_bytes()
        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(sorted(archive.namelist()), archive.namelist())
            prefix = "addons/godot-git-plugin/"
            manifest = json.loads(archive.read(prefix + "MANIFEST.json"))
            names = [item["path"] for item in manifest["files"]]
            self.assertEqual(sorted(names), names)
            checksums = archive.read(prefix + "SHA256SUMS.txt").decode().splitlines()
            names = [line.split("  ", 1)[1] for line in checksums]
            self.assertEqual(sorted(names), names)
            self.assertLess(names.index("Z.txt"), names.index("a.txt"))

    def test_output_uses_filename_and_errors_hide_input_paths(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            package_release.package(
                self.repository, self.addon, self.output, "1.0", 1785436021,
                allow_partial=True, skip_audit_records=True,
            )
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertEqual(Path(json.loads(output.getvalue())["archive"]).name,
                         json.loads(output.getvalue())["archive"])
        with mock.patch.object(sys, "argv", ["audit_binary.py", "--platform", "windows",
                                            "--binary", str(self.root / "missing.dll")]):
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(1, audit_binary.main())
        self.assertNotIn(str(self.root), errors.getvalue())

    def test_audit_cli_writes_record(self) -> None:
        record = self.records / "windows-x86_64.json"
        with mock.patch.object(sys, "argv", [
            "audit_binary.py", "--platform", "windows", "--binary", str(self.binary),
            "--record", str(record),
        ]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, audit_binary.main())
        audit_binary.verify_record(record, audit_binary.audit_bytes(pe_fixture(), "windows"))


if __name__ == "__main__":
    unittest.main()
