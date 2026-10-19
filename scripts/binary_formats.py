"""Bounded, host-independent parsers for release library formats."""

from __future__ import annotations

import struct


WINDOWS_DEPENDENCIES = {
    "ADVAPI32.DLL", "CRYPT32.DLL", "KERNEL32.DLL",
    "SECUR32.DLL", "USER32.DLL", "WS2_32.DLL",
}
LINUX_DEPENDENCIES = {"ld-linux-x86-64.so.2", "libc.so.6", "libm.so.6"}


class Binary:
    def __init__(self, data: bytes, endian: str = "<") -> None:
        self.data = data
        self.endian = endian

    def region(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise RuntimeError("truncated or invalid binary range")
        return self.data[offset:offset + size]

    def unpack(self, layout: str, offset: int) -> tuple:
        return struct.unpack(self.endian + layout, self.region(
            offset, struct.calcsize(self.endian + layout)
        ))

    def string(self, offset: int, limit: int | None = None) -> str:
        end = len(self.data) if limit is None else limit
        self.region(offset, end - offset)
        terminator = self.data.find(b"\0", offset, end)
        if terminator < 0:
            raise RuntimeError("unterminated binary string")
        try:
            return self.data[offset:terminator].decode("ascii")
        except UnicodeDecodeError:
            raise RuntimeError("non-ASCII binary symbol or dependency") from None


def audit_windows(data: bytes) -> dict[str, object]:
    binary = Binary(data)
    if binary.region(0, 2) != b"MZ":
        raise RuntimeError("Windows binary is not PE x86-64 DLL")
    pe, = binary.unpack("I", 60)
    if binary.region(pe, 4) != b"PE\0\0":
        raise RuntimeError("invalid PE signature")
    machine, sections, _, _, _, optional_size, flags = binary.unpack("HHIIIHH", pe + 4)
    optional = pe + 24
    if machine != 0x8664 or not flags & 0x2000 or binary.unpack("H", optional)[0] != 0x20B:
        raise RuntimeError("Windows binary is not PE x86-64 DLL")
    if optional_size < 128:
        raise RuntimeError("missing PE data directories")
    binary.region(optional, optional_size)
    directory_count, = binary.unpack("I", optional + 108)
    if directory_count < 2 or 112 + directory_count * 8 > optional_size:
        raise RuntimeError("invalid PE data directories")
    section_table = optional + optional_size
    mappings = []
    for index in range(sections):
        section = section_table + 40 * index
        binary.region(section, 40)
        virtual_size, rva, raw_size, raw = binary.unpack("IIII", section + 8)
        binary.region(raw, raw_size)
        mappings.append((rva, raw_size, raw))

    def location(rva: int, size: int = 1) -> int:
        for start, length, raw in mappings:
            if start <= rva and rva + size <= start + length:
                return raw + rva - start
        raise RuntimeError("unmapped PE address")

    def string(rva: int) -> str:
        for start, length, raw in mappings:
            if start <= rva < start + length:
                return binary.string(raw + rva - start, raw + length)
        raise RuntimeError("unmapped PE string")

    export_rva, export_size = binary.unpack("II", optional + 112)
    if not export_rva or export_size < 40:
        raise RuntimeError("Windows binary does not export git_plugin_init")
    export = location(export_rva, 40)
    functions, names, function_rva, name_rva, ordinal_rva = binary.unpack("IIIII", export + 20)
    function_table = location(function_rva, functions * 4)
    name_table = location(name_rva, names * 4)
    ordinals = location(ordinal_rva, names * 2)
    found = False
    for index in range(names):
        name, = binary.unpack("I", name_table + index * 4)
        if string(name) != "git_plugin_init":
            continue
        ordinal, = binary.unpack("H", ordinals + index * 2)
        if ordinal >= functions:
            raise RuntimeError("invalid PE export ordinal")
        address, = binary.unpack("I", function_table + ordinal * 4)
        if not address or export_rva <= address < export_rva + export_size:
            raise RuntimeError("PE entry point is absent or forwarded")
        location(address)
        found = True
    if not found:
        raise RuntimeError("Windows binary does not export git_plugin_init")

    dependencies: set[str] = set()
    import_rva, import_size = binary.unpack("II", optional + 120)
    if import_rva:
        table = location(import_rva, import_size)
        terminated = False
        for offset in range(table, table + import_size - 19, 20):
            descriptor = binary.unpack("IIIII", offset)
            if not any(descriptor):
                terminated = True
                break
            dependencies.add(string(descriptor[3]).upper())
        if not terminated:
            raise RuntimeError("unterminated PE import table")
    # Delay-loaded imports require the same allowlist as regular imports.
    if directory_count > 13:
        delay_rva, delay_size = binary.unpack("II", optional + 112 + 13 * 8)
        if delay_rva or delay_size:
            raise RuntimeError("PE delay imports are not supported in release libraries")
    if dependencies - WINDOWS_DEPENDENCIES:
        raise RuntimeError("Windows binary has unexpected dynamic dependencies")
    return {"architecture": "PE x86-64", "dynamic_dependencies": sorted(dependencies)}


def audit_linux(data: bytes) -> dict[str, object]:
    binary = Binary(data)
    if binary.region(0, 7) != b"\x7fELF\x02\x01\x01":
        raise RuntimeError("Linux binary is not little-endian ELF64")
    kind, machine, version = binary.unpack("HHI", 16)
    if kind != 3 or machine != 62 or version != 1:
        raise RuntimeError("Linux binary is not ELF x86-64 shared object")
    section_offset, = binary.unpack("Q", 40)
    header_size, _, _, entry_size, count, names_index = binary.unpack("HHHHHH", 52)
    if header_size != 64 or entry_size != 64 or not count or names_index >= count:
        raise RuntimeError("invalid ELF section table")
    binary.region(section_offset, count * entry_size)
    sections = [
        binary.unpack("IIQQQQIIQQ", section_offset + index * entry_size)
        for index in range(count)
    ]
    for section in sections:
        if section[1] != 8:  # SHT_NOBITS has no on-disk contents.
            binary.region(section[4], section[5])

    def text(section_index: int, offset: int) -> str:
        if section_index >= count or sections[section_index][1] != 3:
            raise RuntimeError("invalid ELF string table")
        section = sections[section_index]
        return binary.string(section[4] + offset, section[4] + section[5])

    found = False
    dependencies: set[str] = set()
    for section in sections:
        name = text(names_index, section[0])
        if section[1] == 11 and name == ".dynsym":
            if section[9] != 24 or section[5] % 24:
                raise RuntimeError("invalid ELF dynamic symbol table")
            for offset in range(section[4], section[4] + section[5], 24):
                symbol_name, info, visibility, defined, _, _ = binary.unpack("IBBHQQ", offset)
                if text(section[6], symbol_name) != "git_plugin_init":
                    continue
                if (
                    info >> 4 in (1, 2) and info & 15 == 2
                    and visibility & 3 in (0, 3) and 0 < defined < count
                    and sections[defined][2] & 4
                ):
                    found = True
        if section[1] == 6:
            if section[9] != 16 or section[5] % 16:
                raise RuntimeError("invalid ELF dynamic table")
            for offset in range(section[4], section[4] + section[5], 16):
                tag, value = binary.unpack("qQ", offset)
                if tag == 0:
                    break
                if tag == 1:
                    dependencies.add(text(section[6], value))
    if not found:
        raise RuntimeError("ELF .dynsym lacks defined GLOBAL/WEAK FUNC git_plugin_init")
    if dependencies - LINUX_DEPENDENCIES:
        raise RuntimeError("Linux binary has unexpected dynamic dependencies")
    return {"architecture": "ELF x86-64", "dynamic_dependencies": sorted(dependencies)}


def audit_macho_slice(data: bytes, expected_cpu: int) -> set[str]:
    magic = data[:4]
    endian = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}.get(magic)
    if endian is None:
        raise RuntimeError("macOS slice is not Mach-O 64-bit")
    binary = Binary(data, endian)
    _, cpu, _, kind, count, command_size, _, _ = binary.unpack("IIIIIIII", 0)
    if cpu != expected_cpu or kind != 6:
        raise RuntimeError("macOS slice has wrong architecture or is not a dylib")
    binary.region(32, command_size)
    end = 32 + command_size
    offset = 32
    symbol_table = None
    executable_sections: set[int] = set()
    section_number = 0
    dependencies: set[str] = set()
    for _ in range(count):
        command, size = binary.unpack("II", offset)
        if size < 8 or size % 8 or offset + size > end:
            raise RuntimeError("invalid Mach-O load command")
        if command == 0x19:  # LC_SEGMENT_64
            if size < 72:
                raise RuntimeError("invalid Mach-O segment")
            sections, = binary.unpack("I", offset + 64)
            if size != 72 + sections * 80:
                raise RuntimeError("invalid Mach-O section table")
            for index in range(sections):
                section_number += 1
                flags, = binary.unpack("I", offset + 72 + index * 80 + 64)
                if flags & (0x80000000 | 0x400):
                    executable_sections.add(section_number)
        if command == 2:  # LC_SYMTAB
            if size != 24 or symbol_table is not None:
                raise RuntimeError("invalid Mach-O symbol table command")
            symbol_table = binary.unpack("IIII", offset + 8)
        if command in (0xC, 0x80000018, 0x8000001F, 0x80000023, 0x20):
            if size < 24:
                raise RuntimeError("invalid Mach-O dependency command")
            name, = binary.unpack("I", offset + 8)
            if name < 24:
                raise RuntimeError("invalid Mach-O dependency name")
            dependencies.add(binary.string(offset + name, offset + size))
        offset += size
    if offset != end or symbol_table is None:
        raise RuntimeError("missing Mach-O symbol table or invalid load commands")
    symbols, count, strings, string_size = symbol_table
    binary.region(symbols, count * 16)
    binary.region(strings, string_size)
    found = False
    for index in range(count):
        name, kind, section, _, _ = binary.unpack("IBBHQ", symbols + index * 16)
        if binary.string(strings + name, strings + string_size) != "_git_plugin_init":
            continue
        # N_EXT, N_SECT, no debugging or private-external bits, executable section.
        if kind == 0x0F and section in executable_sections:
            found = True
    if not found:
        raise RuntimeError("Mach-O slice lacks defined exported git_plugin_init")
    if any(
        not item.startswith("/usr/lib/")
        and not item.startswith("/System/Library/Frameworks/")
        for item in dependencies
    ):
        raise RuntimeError("macOS binary has non-system dynamic dependencies")
    return dependencies


def audit_macos(data: bytes) -> dict[str, object]:
    formats = {
        b"\xca\xfe\xba\xbe": (">", False),
        b"\xbe\xba\xfe\xca": ("<", False),
        b"\xca\xfe\xba\xbf": (">", True),
        b"\xbf\xba\xfe\xca": ("<", True),
    }
    if data[:4] not in formats:
        raise RuntimeError("macOS binary is not Mach-O universal arm64+x86_64")
    endian, wide = formats[data[:4]]
    binary = Binary(data, endian)
    count, = binary.unpack("I", 4)
    if count != 2:
        raise RuntimeError("macOS binary must contain exactly arm64+x86_64 slices")
    stride = 32 if wide else 20
    ranges = []
    cpus: set[int] = set()
    dependencies: set[str] = set()
    for index in range(count):
        entry = binary.unpack("IIQQII" if wide else "IIIII", 8 + index * stride)
        cpu, _, offset, size, alignment = entry[:5]
        if cpu not in (0x1000007, 0x100000C) or cpu in cpus:
            raise RuntimeError("macOS binary has missing or duplicate architectures")
        if offset < 8 + count * stride or alignment > 63 or offset % (1 << alignment):
            raise RuntimeError("invalid Mach-O slice alignment")
        if any(offset < stop and offset + size > start for start, stop in ranges):
            raise RuntimeError("overlapping Mach-O slices")
        ranges.append((offset, offset + size))
        cpus.add(cpu)
        dependencies.update(audit_macho_slice(binary.region(offset, size), cpu))
    return {
        "architecture": "Mach-O universal arm64+x86_64",
        "dynamic_dependencies": sorted(dependencies),
    }


AUDITORS = {"linux": audit_linux, "macos": audit_macos, "windows": audit_windows}
