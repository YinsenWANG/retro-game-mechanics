"""Generate original synthetic bytes in memory, without ROMs, BIOS or artwork."""

import struct
import tempfile
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def temporary_directory():
    """Keep synthetic files inside the checkout and remove them after each test."""
    return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1],
                                      prefix=".synthetic-tests-")


def chunk(kind, payload=b""):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def ihdr(width, height, depth=8, color=6, compression=0, filtering=0, interlace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color,
                                       compression, filtering, interlace))


def png_from_raw(width, height, raw, *, compressed=None):
    return (PNG_SIGNATURE + ihdr(width, height)
            + chunk(b"IDAT", zlib.compress(raw) if compressed is None else compressed)
            + chunk(b"IEND"))


def filtered_rows(width, height, rgba, filters):
    """Independent forward filter encoder, inverse to the production decoder."""
    stride = width * 4
    assert len(rgba) == height * stride
    result = bytearray()
    for y in range(height):
        kind = filters[y % len(filters)]
        result.append(kind)
        for x in range(stride):
            value = rgba[y * stride + x]
            left = rgba[y * stride + x - 4] if x >= 4 else 0
            up = rgba[(y - 1) * stride + x] if y else 0
            corner = rgba[(y - 1) * stride + x - 4] if y and x >= 4 else 0
            if kind == 4:
                prediction = left + up - corner
                candidates = (left, up, corner)
                predictor = min(candidates, key=lambda v: abs(prediction - v))
            else:
                predictor = (0, left, up, (left + up) // 2)[kind]
            result.append((value - predictor) & 255)
    return bytes(result)


def rgba_png(width, height, rgba, filters=(0,)):
    return png_from_raw(width, height, filtered_rows(width, height, rgba, filters))


def cart_rom(code=b"print(1)\n", data=None):
    assert len(code) <= 0x3D00
    return (bytes(0x4300) if data is None else data) + code.ljust(0x3D00, b"\0")


def cart_png(rom=None, filters=(0, 1, 2, 3, 4)):
    rom = cart_rom() if rom is None else rom
    payload = rom + bytes([42]) + bytes(range(1, 32))
    assert len(payload) == 160 * 205
    rgba = bytes(channel for value in payload for channel in
                 (0xA0 | ((value >> 4) & 3), 0xB0 | ((value >> 2) & 3),
                  0xC0 | (value & 3), 0xF0 | ((value >> 6) & 3)))
    return rgba_png(160, 205, rgba, filters), payload


def legacy_code(stream, size):
    return b":c:\0" + struct.pack(">H", size) + b"\0\0" + stream


class Bits:
    def __init__(self):
        self.values = []

    def put(self, value, count):
        self.values.extend((value >> i) & 1 for i in range(count))

    def bytes(self):
        result = bytearray((len(self.values) + 7) // 8)
        for i, value in enumerate(self.values):
            result[i // 8] |= value << (i % 8)
        return bytes(result)


def pxa_literal(bits, value, mtf):
    index = mtf.index(value)
    extra = 0
    while index >= (1 << (5 + extra)) - 16:
        extra += 1
    bits.put(1, 1)
    for _ in range(extra):
        bits.put(1, 1)
    bits.put(0, 1)
    bits.put(index - ((1 << (4 + extra)) - 16), 4 + extra)
    mtf.remove(value)
    mtf.insert(0, value)


def pxa_code(bits, size):
    stream = bits.bytes()
    return b"\0pxa" + struct.pack(">HH", size, len(stream) + 8) + stream


def pxa_literals(values):
    bits = Bits()
    mtf = list(range(256))
    for value in values:
        pxa_literal(bits, value, mtf)
    return pxa_code(bits, len(values))


def gba_rom(size=0x200):
    """Zero logo area deliberately: header checks do not prove authenticity."""
    data = bytearray(size)
    struct.pack_into("<I", data, 0, 0xEA00002E)  # B to ROM+0xC0
    data[0xA0:0xAC] = b"SYNTHETIC   "
    data[0xAC:0xB0] = b"TEST"
    data[0xB0:0xB2] = b"00"
    data[0xB2] = 0x96
    data[0xBC] = 7
    data[0xBD] = (-sum(data[0xA0:0xBD]) - 0x19) & 255
    struct.pack_into("<I", data, 0xC0, 0xE12FFF1E)  # BX lr
    return data


def lz77(size, stream):
    return b"\x10" + size.to_bytes(3, "little") + stream
