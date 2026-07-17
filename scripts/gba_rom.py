#!/usr/bin/env python3
"""Inspect an authorized Game Boy Advance ROM without extracting game assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


HEADER_SIZE = 0xC0
MAX_ROM_SIZE = 32 * 1024 * 1024
ROM_BASE = 0x08000000
ROM_MIRROR_END = 0x0E000000
SAVE_MARKERS = (
    b"EEPROM_V", b"SRAM_V", b"SRAM_F_V", b"FLASH_V", b"FLASH512_V", b"FLASH1M_V"
)
PERIPHERAL_MARKERS = (b"SIIRTC_V", b"AGBPrint", b"RFU_", b"NINTENDO_MP")


class GbaRomError(ValueError):
    pass


def _ascii(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("ascii", errors="replace").rstrip()


def header_checksum(data: bytes) -> int:
    """Return the GBA header complement byte for offsets A0h..BCh."""
    return (-sum(data[0xA0:0xBD]) - 0x19) & 0xFF


def _entry_point(data: bytes) -> dict[str, object]:
    word = struct.unpack_from("<I", data, 0)[0]
    result: dict[str, object] = {"offset": 0, "raw_word": f"0x{word:08x}"}
    if word >> 24 == 0xEA:
        displacement = word & 0x00FFFFFF
        if displacement & 0x00800000:
            displacement -= 0x01000000
        target = 8 + displacement * 4
        result.update({"instruction": "ARM B", "target_rom_offset": target,
                       "target_address": f"0x{ROM_BASE + target:08x}",
                       "target_in_file": 0 <= target < len(data)})
    else:
        result["instruction"] = "unrecognized (expected an ARM branch)"
    return result


def _find_markers(data: bytes, markers: tuple[bytes, ...]) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for marker in markers:
        start = 0
        while True:
            offset = data.find(marker, start)
            if offset < 0:
                break
            end = offset
            while end < min(len(data), offset + 32) and 0x20 <= data[end] <= 0x7E:
                end += 1
            found.append({"marker": _ascii(data[offset:end]), "offset": offset})
            start = offset + len(marker)
    return sorted(found, key=lambda item: (int(item["offset"]), str(item["marker"])))


def _pointer_summary(data: bytes) -> dict[str, object]:
    targets: dict[int, int] = {}
    total = 0
    for source in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<I", data, source)[0]
        if ROM_BASE <= value < ROM_MIRROR_END:
            target = (value - ROM_BASE) % 0x02000000
            if target < len(data):
                total += 1
                targets[target] = targets.get(target, 0) + 1
    popular = sorted(targets.items(), key=lambda item: (-item[1], item[0]))[:32]
    return {
        "aligned_rom_pointer_count": total,
        "unique_target_count": len(targets),
        "top_targets": [{"rom_offset": offset, "reference_count": count}
                        for offset, count in popular],
        "warning": "Heuristic only: constants and compressed data may resemble pointers; unaligned pointers are omitted.",
    }


def inspect_rom(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if path.suffix.lower() not in {".gba", ".agb", ".bin"}:
        raise GbaRomError("expected .gba, .agb, or explicitly supplied .bin input")
    if len(data) < HEADER_SIZE:
        raise GbaRomError(f"file is too small for a GBA header: {len(data)} bytes")
    if len(data) > MAX_ROM_SIZE:
        raise GbaRomError(f"file exceeds the 32 MiB GBA cartridge address window: {len(data)} bytes")

    stored_checksum = data[0xBD]
    computed_checksum = header_checksum(data)
    fixed = data[0xB2]
    size_power_of_two = len(data) >= 0x10000 and len(data) & (len(data) - 1) == 0
    warnings: list[str] = []
    if fixed != 0x96:
        warnings.append(f"fixed header byte is 0x{fixed:02x}, expected 0x96")
    if stored_checksum != computed_checksum:
        warnings.append("header complement checksum does not match")
    if not size_power_of_two:
        warnings.append("ROM size is not a conventional power of two of at least 64 KiB")

    return {
        "format": "Game Boy Advance cartridge ROM",
        "source": {"filename": path.name, "size": len(data),
                   "sha256": hashlib.sha256(data).hexdigest()},
        "header": {
            "byte_range": {"start": 0, "end_exclusive": HEADER_SIZE},
            "entry_point": _entry_point(data),
            "title": _ascii(data[0xA0:0xAC]),
            "game_code": _ascii(data[0xAC:0xB0]),
            "maker_code": _ascii(data[0xB0:0xB2]),
            "fixed_value": fixed,
            "main_unit_code": data[0xB3],
            "device_type": data[0xB4],
            "software_version": data[0xBC],
            "header_checksum_stored": stored_checksum,
            "header_checksum_computed": computed_checksum,
            "header_checksum_valid": stored_checksum == computed_checksum,
        },
        "validation": {"size_within_gba_window": True,
                       "conventional_power_of_two_size": size_power_of_two,
                       "fixed_value_valid": fixed == 0x96, "warnings": warnings},
        "technology_markers": {"save": _find_markers(data, SAVE_MARKERS),
                               "peripherals": _find_markers(data, PERIPHERAL_MARKERS),
                               "warning": "String markers suggest linked libraries, not guaranteed runtime use."},
        "pointer_index": _pointer_summary(data),
        "limits": [
            "No code/data boundary, compression scheme, asset format, or gameplay meaning is inferred automatically.",
            "The Nintendo logo bytes are intentionally not emitted.",
            "No ROM bytes or game assets are copied by this inspector.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="authorized local .gba/.agb ROM")
    parser.add_argument("--json", action="store_true", help="write JSON to standard output")
    parser.add_argument("--output", type=Path, help="write the JSON manifest to this path")
    args = parser.parse_args()
    try:
        result = inspect_rom(args.rom)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        if args.json or not args.output:
            print(encoded, end="")
        return 0
    except (OSError, GbaRomError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
