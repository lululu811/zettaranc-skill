#!/usr/bin/env python3
"""
Post-build fix for the "mis-aligned LINKEDIT string pool" bug in lld 22.1.8
on macOS 15+.

The bug: lld places the LC_SYMTAB.stroff at an offset that is 4-byte aligned
but not 8-byte aligned. Newer macOS dyld enforces 8-byte alignment and
refuses to load the .so, even though the binary itself is correct.

What this script does:
  1. Walk load commands; locate LC_SYMTAB and the __LINKEDIT LC_SEGMENT_64.
  2. If LC_SYMTAB.stroff is not 8-byte aligned, compute the padding (always
     4 bytes when stroff is exactly 4 mod 8).
  3. Insert zero bytes at file offset == stroff so the string table data
     shifts to the next 8-byte boundary.
  4. Update LC_SYMTAB.stroff to the new (aligned) file offset.
  5. Update the __LINKEDIT segment's filesize by the same amount.
  6. For each LC_SEGMENT_64 whose fileoff lies strictly after the insertion
     point, bump fileoff by the padding size.

This is a workaround for lld issue. Once lld fixes the upstream bug, this
script can be removed.

Usage: python3 fix_linkedit_alignment.py <path-to-dylib>
"""
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x02

# struct segment_command_64 layout (sizeof = 72):
#   uint32_t cmd            @ 0
#   uint32_t cmdsize        @ 4
#   char     segname[16]    @ 8
#   uint64_t vmaddr         @ 24
#   uint64_t vmsize         @ 32
#   uint64_t fileoff        @ 40
#   uint64_t filesize       @ 48
#   int32_t  maxprot        @ 56
#   int32_t  initprot       @ 60
#   uint32_t nsects         @ 64
#   uint32_t flags          @ 68
SEG_FILEOFF_OFF = 40
SEG_FILESIZE_OFF = 48

# struct symtab_command layout (sizeof = 24):
#   uint32_t cmd            @ 0
#   uint32_t cmdsize        @ 4
#   uint32_t symoff         @ 8
#   uint32_t nsyms          @ 12
#   uint32_t stroff         @ 16
#   uint32_t strsize        @ 20
SYM_STROFF_OFF = 16


def read_u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def read_u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0]


def write_u32(buf, off, val):
    struct.pack_into("<I", buf, off, val)


def write_u64(buf, off, val):
    struct.pack_into("<Q", buf, off, val)


def fix(path: Path) -> int:
    data = bytearray(path.read_bytes())
    magic = read_u32(data, 0)
    if magic not in (MH_MAGIC_64, MH_CIGAM_64):
        print(f"  not a 64-bit Mach-O (magic=0x{magic:08x}), skipping")
        return 1

    ncmds = read_u32(data, 16)

    cmd_off = 32  # sizeof(mach_header_64)
    stroff = None
    stroff_field_off = None
    linkedit_filesize_field_off = None
    linkedit_filesize = None
    segment_fileoff_offs = []

    for i in range(ncmds):
        cmd = read_u32(data, cmd_off)
        cmdsize = read_u32(data, cmd_off + 4)
        if cmdsize == 0:
            print(f"  cmdsize 0 at offset {cmd_off}, aborting")
            return 1
        if cmd == LC_SYMTAB:
            symoff_val = read_u32(data, cmd_off + 8)
            nsyms = read_u32(data, cmd_off + 12)
            stroff_val = read_u32(data, cmd_off + 16)
            strsize = read_u32(data, cmd_off + 20)
            print(f"  LC_SYMTAB: symoff=0x{symoff_val:x} nsyms={nsyms} "
                  f"stroff=0x{stroff_val:x} strsize={strsize}")
            stroff = stroff_val
            stroff_field_off = cmd_off + SYM_STROFF_OFF
        elif cmd == LC_SEGMENT_64:
            segname = data[cmd_off + 8 : cmd_off + 24].split(b"\x00", 1)[0].decode("ascii", "ignore")
            fileoff_val = read_u64(data, cmd_off + SEG_FILEOFF_OFF)
            filesize_val = read_u64(data, cmd_off + SEG_FILESIZE_OFF)
            print(f"  LC_SEGMENT_64: {segname!r} fileoff=0x{fileoff_val:x} "
                  f"filesize=0x{filesize_val:x}")
            segment_fileoff_offs.append(cmd_off + SEG_FILEOFF_OFF)
            if segname == "__LINKEDIT":
                linkedit_filesize_field_off = cmd_off + SEG_FILESIZE_OFF
                linkedit_filesize = filesize_val
        cmd_off += cmdsize

    if stroff is None:
        print("  no LC_SYMTAB found, nothing to do")
        return 0
    if stroff % 8 == 0:
        print(f"  stroff 0x{stroff:x} is already 8-byte aligned, no fix needed")
        return 0

    pad = (8 - (stroff % 8)) % 8
    if pad == 0:
        pad = 8
    print(f"  stroff misaligned by {stroff % 8} bytes; "
          f"inserting {pad} zero bytes at file offset 0x{stroff:x}")

    new_data = data[:stroff] + b"\x00" * pad + data[stroff:]

    write_u32(new_data, stroff_field_off, stroff + pad)

    if linkedit_filesize_field_off is not None:
        new_linkedit_size = linkedit_filesize + pad
        write_u64(new_data, linkedit_filesize_field_off, new_linkedit_size)
        print(f"  bumped __LINKEDIT.filesize 0x{linkedit_filesize:x} -> "
              f"0x{new_linkedit_size:x}")

    for seg_off in segment_fileoff_offs:
        cur = read_u64(new_data, seg_off)
        if cur > stroff:
            write_u64(new_data, seg_off, cur + pad)
            print(f"  bumped segment fileoff 0x{cur:x} -> 0x{cur + pad:x}")

    path.write_bytes(new_data)
    print(f"  wrote {len(new_data)} bytes to {path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: fix_linkedit_alignment.py <dylib>")
        sys.exit(2)
    sys.exit(fix(Path(sys.argv[1])))
