#!/usr/bin/env python3
"""Read local PICO-8 .p8 and .p8.png cartridges without PICO-8.

The PNG decoder uses only Python's standard library. It extracts the 32 KiB
cartridge payload hidden in the low two bits of each RGBA channel and supports
both legacy :c: and current pxa code compression.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CART_WIDTH = 160
CART_HEIGHT = 205
ROM_SIZE = 0x4300
CART_SIZE = 0x8000
CODE_SIZE = CART_SIZE - ROM_SIZE

SECTION_NAMES = ("lua", "gfx", "gff", "map", "sfx", "music", "label")

OLD_TABLE = [
    None, "\n", " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "!", "#", "%", "(", ")", "{", "}", "[", "]", "<", ">", "+", "=",
    "/", "*", ":", ";", ".", ",", "~", "_",
]

P8_CHARSET = [
    "�", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "\t", "\n", "ᵇ", "ᶜ", "\r", "ᵉ", "ᶠ",
    "▮", "■", "□", "⁙", "⁘", "‖", "◀", "▶", "「", "」", "¥", "•", "、", "。", "゛", "゜",
] + [chr(value) for value in range(0x20, 0x7F)] + [
    "○", "█", "▒", "🐱", "⬇️", "░", "✽", "●", "♥", "☉", "웃", "⌂", "⬅️", "😐", "♪", "🅾️", "◆",
    "…", "➡️", "★", "⧗", "⬆️", "ˇ", "∧", "❎", "▤", "▥", "あ", "い", "う", "え", "お", "か",
    "き", "く", "け", "こ", "さ", "し", "す", "せ", "そ", "た", "ち", "つ", "て", "と", "な", "に",
    "ぬ", "ね", "の", "は", "ひ", "ふ", "へ", "ほ", "ま", "み", "む", "め", "も", "や", "ゆ", "よ",
    "ら", "り", "る", "れ", "ろ", "わ", "を", "ん", "っ", "ゃ", "ゅ", "ょ", "ア", "イ", "ウ", "エ",
    "オ", "カ", "キ", "ク", "ケ", "コ", "サ", "シ", "ス", "セ", "ソ", "タ", "チ", "ツ", "テ", "ト",
    "ナ", "ニ", "ヌ", "ネ", "ノ", "ハ", "ヒ", "フ", "ヘ", "ホ", "マ", "ミ", "ム", "メ", "モ", "ヤ",
    "ユ", "ヨ", "ラ", "リ", "ル", "レ", "ロ", "ワ", "ヲ", "ン", "ッ", "ャ", "ュ", "ョ", "◜", "◝",
]


class CartError(ValueError):
    pass


@dataclass
class Cartridge:
    source_format: str
    version: int | None
    code: str
    sections: dict[str, str]
    rom: bytes | None = None
    trailer: bytes | None = None


class BitReader:
    """Least-significant-bit-first reader used by PICO-8's pxa stream."""

    def __init__(self, data: bytes):
        self.data = data
        self.byte_pos = 0
        self.buffer = 0
        self.available = 0

    def bits(self, count: int) -> int:
        while self.available < count:
            if self.byte_pos >= len(self.data):
                raise CartError("truncated pxa stream")
            self.buffer |= self.data[self.byte_pos] << self.available
            self.byte_pos += 1
            self.available += 8
        value = self.buffer & ((1 << count) - 1)
        self.buffer >>= count
        self.available -= count
        return value

    def bit(self) -> bool:
        return bool(self.bits(1))


def p8scii_to_unicode(data: bytes) -> str:
    return "".join(P8_CHARSET[value] for value in data)


def _paeth(a: int, b: int, c: int) -> int:
    estimate = a + b - c
    da, db, dc = abs(estimate - a), abs(estimate - b), abs(estimate - c)
    return a if da <= db and da <= dc else b if db <= dc else c


def decode_rgba_png(
    data: bytes, *, expected_size: tuple[int, int] | None = None
) -> tuple[int, int, bytes]:
    """Decode a non-interlaced 8-bit RGBA PNG into row-major bytes."""
    if not data.startswith(PNG_SIGNATURE):
        raise CartError("not a PNG file")

    pos = len(PNG_SIGNATURE)
    width = height = None
    compressed = bytearray()
    seen_idat = ended_idat = False
    while True:
        if pos + 12 > len(data):
            raise CartError("truncated PNG chunk or missing IEND")
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        if length > 0x7FFFFFFF or pos + 12 + length > len(data):
            raise CartError("truncated or oversized PNG chunk")
        payload = data[pos + 8 : pos + 8 + length]
        crc = struct.unpack_from(">I", data, pos + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise CartError("PNG chunk CRC mismatch")
        pos += 12 + length
        if width is None and kind != b"IHDR":
            raise CartError("PNG must start with IHDR")
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise CartError("invalid or duplicate PNG IHDR")
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if not (0 < width <= 0x7FFFFFFF and 0 < height <= 0x7FFFFFFF):
                raise CartError("invalid PNG dimensions")
            if (depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise CartError("expected a non-interlaced 8-bit RGBA PNG")
            if expected_size is not None and (width, height) != expected_size:
                raise CartError(f"expected {expected_size[0]}x{expected_size[1]}, got {width}x{height}")
        elif kind == b"IDAT":
            if ended_idat:
                raise CartError("PNG IDAT chunks must be consecutive")
            seen_idat = True
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or not seen_idat or pos != len(data):
                raise CartError("invalid PNG IEND, missing IDAT, or trailing data")
            break
        else:
            if seen_idat:
                ended_idat = True
            if kind != b"PLTE" and not kind[0] & 0x20:
                raise CartError("unsupported critical PNG chunk")

    stride = width * 4
    expected = height * (stride + 1)
    if expected >= sys.maxsize:
        raise CartError("PNG dimensions exceed decoder capacity")
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise CartError(f"invalid PNG zlib stream: {exc}") from exc
    if len(raw) != expected:
        raise CartError(f"unexpected PNG data length: {len(raw)} != {expected}")
    if not inflater.eof or inflater.unconsumed_tail or inflater.unused_data:
        raise CartError("truncated PNG zlib stream or trailing compressed data")

    decoded = bytearray(height * stride)
    src = 0
    for row in range(height):
        filter_type = raw[src]
        src += 1
        current = bytearray(raw[src : src + stride])
        src += stride
        previous_start = (row - 1) * stride
        for i in range(stride):
            left = current[i - 4] if i >= 4 else 0
            up = decoded[previous_start + i] if row else 0
            up_left = decoded[previous_start + i - 4] if row and i >= 4 else 0
            if filter_type == 1:
                current[i] = (current[i] + left) & 0xFF
            elif filter_type == 2:
                current[i] = (current[i] + up) & 0xFF
            elif filter_type == 3:
                current[i] = (current[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                current[i] = (current[i] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise CartError(f"unknown PNG filter {filter_type}")
        decoded[row * stride : (row + 1) * stride] = current
    return width, height, bytes(decoded)


def payload_from_png(data: bytes) -> bytes:
    width, height, rgba = decode_rgba_png(data, expected_size=(CART_WIDTH, CART_HEIGHT))
    payload = bytearray()
    for i in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[i : i + 4]
        payload.append(
            (blue & 3) | ((green & 3) << 2) | ((red & 3) << 4) | ((alpha & 3) << 6)
        )
    return bytes(payload)


def decompress_code(code_region: bytes) -> str:
    header = code_region[:4]
    if header in (b"\x00pxa", b":c:\x00") and len(code_region) < 8:
        raise CartError("truncated compressed code header")
    if header == b"\x00pxa":
        unc_size, compressed_size = struct.unpack(">HH", code_region[4:8])
        if not 8 <= compressed_size <= len(code_region):
            raise CartError("invalid pxa compressed size")
        stream = code_region[8:compressed_size]
        reader = BitReader(stream)
        mtf = list(range(256))
        output = bytearray()
        while len(output) < unc_size:
            if reader.bit():
                extra = 0
                while reader.bit():
                    extra += 1
                    if extra > 4:
                        raise CartError("invalid pxa move-to-front index")
                index = reader.bits(4 + extra) + ((1 << (4 + extra)) - 16)
                if index >= len(mtf):
                    raise CartError("invalid pxa move-to-front index")
                value = mtf[index]
                output.append(value)
                mtf[1 : index + 1] = mtf[0:index]
                mtf[0] = value
            else:
                if reader.bit():
                    offset_bits = 5 if reader.bit() else 10
                else:
                    offset_bits = 15
                offset = reader.bits(offset_bits) + 1
                if offset == 1 and offset_bits == 10:
                    while True:
                        value = reader.bits(8)
                        if value == 0:
                            break
                        if len(output) < unc_size:
                            output.append(value)
                else:
                    count = 3
                    while True:
                        part = reader.bits(3)
                        count += part
                        if part != 7:
                            break
                    if offset > len(output):
                        raise CartError("invalid pxa back-reference")
                    for _ in range(min(count, unc_size - len(output))):
                        output.append(output[-offset])
        return p8scii_to_unicode(output[:unc_size])

    if header == b":c:\x00":
        unc_size = struct.unpack(">H", code_region[4:6])[0]
        pos = 8
        output = bytearray()
        while len(output) < unc_size and pos < len(code_region):
            value = code_region[pos]
            pos += 1
            if value == 0:
                if pos >= len(code_region):
                    raise CartError("truncated legacy compressed stream")
                literal = code_region[pos]
                pos += 1
                if literal == 0:
                    break
                output.append(literal)
            elif value <= 0x3B:
                output.append(ord(OLD_TABLE[value]))
            else:
                if pos >= len(code_region):
                    raise CartError("truncated legacy back-reference")
                second = code_region[pos]
                pos += 1
                count = (second >> 4) + 2
                offset = ((value - 0x3C) << 4) + (second & 0x0F)
                if offset == 0 or offset > len(output):
                    raise CartError("invalid legacy back-reference")
                for _ in range(min(count, unc_size - len(output))):
                    output.append(output[-offset])
        if len(output) != unc_size:
            raise CartError("truncated legacy compressed stream")
        return p8scii_to_unicode(output)

    return p8scii_to_unicode(code_region.split(b"\x00", 1)[0])


def parse_p8_text(text: str) -> Cartridge:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines[0].startswith("pico-8 cartridge"):
        raise CartError("expected a PICO-8 text cartridge header")
    version = None
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines:
        if line.startswith("version ") and version is None:
            try:
                version = int(line[len("version "):])
            except ValueError as exc:
                raise CartError("invalid PICO-8 cartridge version") from exc
        if line.startswith("__") and line.endswith("__"):
            candidate = line.strip("_").lower()
            if candidate in SECTION_NAMES:
                current = candidate
                sections.setdefault(current, [])
                continue
        if current is not None:
            sections[current].append(line)
    flat = {name: "\n".join(values).rstrip("\n") for name, values in sections.items()}
    return Cartridge("p8", version, flat.get("lua", ""), flat)


def read_cartridge(cart_path: Path) -> Cartridge:
    data = cart_path.read_bytes()
    if data.startswith(PNG_SIGNATURE) or cart_path.suffix.lower() == ".png":
        payload = payload_from_png(data)
        rom = payload[:ROM_SIZE]
        code = decompress_code(payload[ROM_SIZE:CART_SIZE])
        return Cartridge("p8.png", payload[CART_SIZE] if len(payload) > CART_SIZE else None, code, {}, rom, payload[CART_SIZE:])
    if cart_path.name.lower().endswith((".p8.rom", ".rom")):
        if len(data) != CART_SIZE:
            raise CartError(f"expected a {CART_SIZE}-byte raw cartridge, got {len(data)} bytes")
        return Cartridge("p8.rom", None, decompress_code(data[ROM_SIZE:CART_SIZE]), {}, data[:ROM_SIZE])
    try:
        return parse_p8_text(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CartError("invalid UTF-8 text cartridge") from exc


def cartridge_summary(cart: Cartridge) -> dict[str, object]:
    return {
        "format": cart.source_format,
        "version": cart.version,
        "code_chars": len(cart.code),
        "code_lines": cart.code.count("\n") + bool(cart.code),
        "sections": sorted(cart.sections),
        "rom_bytes": len(cart.rom) if cart.rom is not None else None,
        "trailer_bytes": len(cart.trailer) if cart.trailer is not None else None,
    }


def unpack_cartridge(cart: Cartridge, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    files: list[str] = []

    code_path = output_dir / "code.p8lua"
    code_path.write_text(cart.code, encoding="utf-8")
    files.append(code_path.name)

    if cart.rom is not None:
        regions = {
            "cart-data.rom": cart.rom,
            "gfx.bin": cart.rom[0x0000:0x2000],
            "map.bin": cart.rom[0x2000:0x3000],
            "gff.bin": cart.rom[0x3000:0x3100],
            "music.bin": cart.rom[0x3100:0x3200],
            "sfx.bin": cart.rom[0x3200:0x4300],
        }
        for filename, payload in regions.items():
            (output_dir / filename).write_bytes(payload)
            files.append(filename)
        if cart.trailer:
            (output_dir / "trailer.bin").write_bytes(cart.trailer)
            files.append("trailer.bin")
    else:
        for section_name, section_text in sorted(cart.sections.items()):
            if section_name == "lua":
                continue
            filename = f"{section_name}.txt"
            (output_dir / filename).write_text(section_text, encoding="utf-8")
            files.append(filename)

    manifest = cartridge_summary(cart)
    manifest["files"] = files
    manifest["rom_regions"] = {
        "gfx": [0x0000, 0x2000],
        "map": [0x2000, 0x3000],
        "gff": [0x3000, 0x3100],
        "music": [0x3100, 0x3200],
        "sfx": [0x3200, 0x4300],
    } if cart.rom is not None else None
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cartridge", type=Path, help="local .p8, .p8.png, or .p8.rom file")
    parser.add_argument("--extract-code", type=Path, help="write Lua source to this path")
    parser.add_argument("--extract-rom", type=Path, help="write the 0x4300-byte ROM data block")
    parser.add_argument("--extract-dir", type=Path, help="create a directory with code, asset regions, trailer, and manifest")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    try:
        cart = read_cartridge(args.cartridge)
        if args.extract_code:
            args.extract_code.write_text(cart.code, encoding="utf-8")
        if args.extract_rom:
            if cart.rom is None:
                raise CartError("ROM extraction is only available for .p8.png input")
            args.extract_rom.write_bytes(cart.rom)
        if args.extract_dir:
            unpack_cartridge(cart, args.extract_dir)
        summary = cartridge_summary(cart)
        print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in summary.items()))
        return 0
    except (OSError, CartError, struct.error, zlib.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
