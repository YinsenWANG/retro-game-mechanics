import json
import struct
import unittest
from pathlib import Path

from tests.fixtures import (Bits, cart_png, cart_rom, legacy_code, pxa_code,
                            pxa_literal, pxa_literals, temporary_directory)
from pico8_cart import (CART_SIZE, CartError, P8_CHARSET, decompress_code,
                       p8scii_to_unicode, parse_p8_text, read_cartridge,
                       unpack_cartridge)


class P8sciiTests(unittest.TestCase):
    def test_ascii_and_extended_characters(self):
        self.assertEqual(len(P8_CHARSET), 256)
        self.assertEqual(p8scii_to_unicode(bytes(range(32, 127))),
                         "".join(chr(i) for i in range(32, 127)))
        self.assertEqual(p8scii_to_unicode(bytes([0, 9, 10, 13, 16, 31])),
                         "�\t\n\r▮゜")
        self.assertEqual(p8scii_to_unicode(bytes(range(127, 154))),
                         "○█▒🐱⬇️░✽●♥☉웃⌂⬅️😐♪🅾️◆…➡️★⧗⬆️ˇ∧❎▤▥")
        self.assertEqual(p8scii_to_unicode(bytes([154, 203, 204, 253, 254, 255])),
                         "あょアョ◜◝")

    def test_uncompressed_stops_at_nul_and_preserves_icons(self):
        self.assertEqual(decompress_code(b"\x80\x83\x8e\0ignored"), "█⬇️🅾️")
        self.assertEqual(decompress_code(b""), "")

    def test_legacy_literals_and_overlapping_reference(self):
        # Escaped P8SCII bytes, then distance 1 / length 4 (overlap).
        self.assertEqual(decompress_code(legacy_code(b"\0\x80\x3c\x21\0\0", 5)), "█" * 5)
        self.assertEqual(decompress_code(legacy_code(bytes([1, 2, 3, 13]), 4)), "\n 0a")
        self.assertEqual(decompress_code(legacy_code(b"", 0)), "")

    def test_legacy_invalid_streams(self):
        for stream, size in [(b"", 1), (b"\0", 1), (b"\0\0", 1),
                             (b"\x3c", 2), (b"\x3c\x01", 2),
                             (b"\0A\x3c\x00", 3), (b"\0A\x3c\x02", 3)]:
            with self.subTest(stream=stream), self.assertRaises(CartError):
                decompress_code(legacy_code(stream, size))

    def test_compressed_headers_are_checked(self):
        for magic in [b"\0pxa", b":c:\0"]:
            for size in range(4, 8):
                with self.subTest(magic=magic, size=size), self.assertRaisesRegex(CartError, "header"):
                    decompress_code(magic.ljust(size, b"\0"))
        for size in [0, 7, 9, 65535]:
            with self.subTest(size=size), self.assertRaisesRegex(CartError, "compressed size"):
                decompress_code(b"\0pxa" + struct.pack(">HH", 1, size))

    def test_pxa_literals_cover_every_byte_and_move_to_front(self):
        values = bytes(range(256)) + b"AAA\xff\xff\xff\x80\x80"
        self.assertEqual(decompress_code(pxa_literals(values)), p8scii_to_unicode(values))
        self.assertEqual(decompress_code(pxa_literals(b"")), "")

    def test_pxa_raw_run_and_all_offset_widths(self):
        for width in [5, 10, 15]:
            bits = Bits()
            bits.put(0, 1); bits.put(1, 1); bits.put(0, 1); bits.put(0, 10)
            for byte in b"AB\0":
                bits.put(byte, 8)
            bits.put(0, 1)
            bits.put(width != 15, 1)
            if width != 15:
                bits.put(width == 5, 1)
            bits.put(1, width)  # distance 2
            bits.put(0, 3)  # length 3
            with self.subTest(width=width):
                self.assertEqual(decompress_code(pxa_code(bits, 5)), "ABABA")

    def test_pxa_overlapping_extended_length(self):
        bits = Bits()
        pxa_literal(bits, ord("A"), list(range(256)))
        bits.put(0, 1); bits.put(1, 1); bits.put(1, 1); bits.put(0, 5)
        bits.put(7, 3); bits.put(7, 3); bits.put(0, 3)
        self.assertEqual(decompress_code(pxa_code(bits, 18)), "A" * 18)

    def test_pxa_truncation_and_invalid_references(self):
        with self.assertRaisesRegex(CartError, "truncated"):
            decompress_code(pxa_code(Bits(), 1))
        bits = Bits()
        bits.put(0, 1); bits.put(1, 1); bits.put(1, 1); bits.put(0, 5); bits.put(0, 3)
        with self.assertRaisesRegex(CartError, "back-reference"):
            decompress_code(pxa_code(bits, 3))
        bits = Bits()
        bits.put(1, 1)
        for _ in range(4):
            bits.put(1, 1)
        bits.put(0, 1); bits.put(16, 8)  # index 256
        with self.assertRaisesRegex(CartError, "move-to-front"):
            decompress_code(pxa_code(bits, 1))
        bits = Bits()
        bits.put(0, 1); bits.put(1, 1); bits.put(0, 1); bits.put(0, 10)
        bits.put(ord("A"), 8)  # raw run lacks its NUL terminator
        with self.assertRaisesRegex(CartError, "truncated"):
            decompress_code(pxa_code(bits, 1))


class CartridgeTests(unittest.TestCase):
    def test_text_line_endings_sections_and_unicode(self):
        text = ("pico-8 cartridge // synthetic\nversion 42\n__lua__\nprint('█')\n"
                "__gfx__\n01\n__map__\n0100\n__gff__\n01\n__sfx__\n__music__\n__label__\n")
        for ending in ["\n", "\r\n", "\r"]:
            with self.subTest(ending=ending):
                cart = parse_p8_text(text.replace("\n", ending))
                self.assertEqual(cart.version, 42)
                self.assertEqual(cart.code, "print('█')")
                self.assertEqual(cart.sections["map"], "0100")
                self.assertEqual(cart.sections["sfx"], "")
        self.assertEqual(parse_p8_text("pico-8 cartridge\n__lua__\n").code, "")

    def test_invalid_text_is_rejected(self):
        for text in ["", "garbage", "pico-8 cartridge\nversion bogus\n__lua__",
                     "pico-8 cartridge\nversion \n__lua__"]:
            with self.subTest(text=text), self.assertRaises(CartError):
                parse_p8_text(text)

    def test_png_and_raw_read_and_unpack_regions(self):
        data = bytes((i * 13) & 255 for i in range(0x4300))
        rom = cart_rom(pxa_literals(b"print(1)\n\x80"), data)
        image, payload = cart_png(rom)
        with temporary_directory() as directory:
            root = Path(directory)
            for name, contents, fmt in [("cart.p8.png", image, "p8.png"),
                                        ("cart.p8.rom", rom, "p8.rom")]:
                source = root / name
                source.write_bytes(contents)
                cart = read_cartridge(source)
                self.assertEqual(cart.source_format, fmt)
                self.assertEqual(cart.code, "print(1)\n█")
                self.assertEqual(cart.rom, data)
                self.assertEqual(cart.trailer, payload[CART_SIZE:] if fmt == "p8.png" else None)
                output = root / (fmt + "-unpacked")
                unpack_cartridge(cart, output)
                self.assertEqual((output / "code.p8lua").read_text(encoding="utf-8"), cart.code)
                for region, start, end in [("gfx", 0, 0x2000), ("map", 0x2000, 0x3000),
                                           ("gff", 0x3000, 0x3100), ("music", 0x3100, 0x3200),
                                           ("sfx", 0x3200, 0x4300)]:
                    self.assertEqual((output / (region + ".bin")).read_bytes(), data[start:end])
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(set(manifest["files"]), {p.name for p in output.iterdir()} - {"manifest.json"})
                with self.assertRaises(FileExistsError):
                    unpack_cartridge(cart, output)

    def test_malformed_file_dispatch(self):
        with temporary_directory() as directory:
            for name, contents in [("bad.png", b"not png"), ("bad.p8", b"\xff"),
                                   ("bad.p8.rom", bytes(CART_SIZE - 1)),
                                   ("large.rom", bytes(CART_SIZE + 1))]:
                path = Path(directory) / name
                path.write_bytes(contents)
                with self.subTest(name=name), self.assertRaises(CartError):
                    read_cartridge(path)
