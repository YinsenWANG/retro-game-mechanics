import struct
import unittest
import zlib
from unittest.mock import patch

from tests.fixtures import PNG_SIGNATURE, cart_png, chunk, ihdr, png_from_raw, rgba_png
from pico8_cart import CartError, _paeth, decode_rgba_png, payload_from_png


class PngTests(unittest.TestCase):
    def test_all_filters_and_mixed_rows(self):
        rgba = bytes((i * 73 + i // 7 * 31) & 255 for i in range(7 * 6 * 4))
        for filters in [(i,) for i in range(5)] + [(0, 1, 2, 3, 4)]:
            with self.subTest(filters=filters):
                self.assertEqual(decode_rgba_png(rgba_png(7, 6, rgba, filters)), (7, 6, rgba))

    def test_paeth_ties(self):
        self.assertEqual(_paeth(5, 5, 5), 5)
        self.assertEqual(_paeth(0, 3, 1), 3)  # up/corner tie prefers up
        self.assertEqual(_paeth(3, 0, 1), 3)  # left/corner tie prefers left

    def test_payload_channel_order_and_trailer(self):
        image, payload = cart_png()
        self.assertEqual(payload_from_png(image), payload)

    def test_split_idat_and_ancillary_chunks(self):
        encoded = zlib.compress(b"\0\x01\x02\x03\x04")
        image = (PNG_SIGNATURE + ihdr(1, 1) + chunk(b"tEXt", b"test\0synthetic")
                 + chunk(b"IDAT", encoded[:3]) + chunk(b"IDAT", b"")
                 + chunk(b"IDAT", encoded[3:]) + chunk(b"IEND"))
        self.assertEqual(decode_rgba_png(image), (1, 1, b"\x01\x02\x03\x04"))

    def test_crc_on_every_chunk(self):
        chunks = [ihdr(1, 1), chunk(b"tEXt", b"test\0x"),
                  chunk(b"IDAT", zlib.compress(bytes(5))), chunk(b"IEND")]
        for i in range(len(chunks)):
            damaged = list(chunks)
            damaged[i] = damaged[i][:-1] + bytes([damaged[i][-1] ^ 1])
            with self.subTest(chunk=i), self.assertRaisesRegex(CartError, "CRC"):
                decode_rgba_png(PNG_SIGNATURE + b"".join(damaged))

    def test_every_truncated_prefix_is_rejected(self):
        image = rgba_png(1, 1, bytes(4))
        for end in range(len(image)):
            with self.subTest(end=end), self.assertRaises(CartError):
                decode_rgba_png(image[:end])

    def test_declared_chunk_payload_beyond_eof(self):
        image = PNG_SIGNATURE + ihdr(1, 1) + struct.pack(">I", 1000) + b"IDATshort"
        with self.assertRaisesRegex(CartError, "truncated"):
            decode_rgba_png(image)

    def test_required_chunk_structure(self):
        header = ihdr(1, 1)
        pixels = chunk(b"IDAT", zlib.compress(bytes(5)))
        end = chunk(b"IEND")
        malformed = [pixels + header + end, header + header + pixels + end,
                     header + end, header + pixels, header + pixels + chunk(b"IEND", b"x"),
                     chunk(b"IHDR", b"x") + pixels + end]
        for body in malformed:
            with self.subTest(body=body), self.assertRaises(CartError):
                decode_rgba_png(PNG_SIGNATURE + body)

    def test_nonconsecutive_idat_unknown_critical_and_trailing_data(self):
        header = ihdr(1, 1)
        pixels = chunk(b"IDAT", zlib.compress(bytes(5)))
        end = chunk(b"IEND")
        for body in [header + pixels + chunk(b"tEXt", b"key\0value") + pixels + end,
                     header + chunk(b"ABCD") + pixels + end,
                     header + pixels + end + b"trailing"]:
            with self.subTest(body=body), self.assertRaises(CartError):
                decode_rgba_png(PNG_SIGNATURE + body)

    def test_ancillary_chunk_after_idat(self):
        image = (PNG_SIGNATURE + ihdr(1, 1) + chunk(b"IDAT", zlib.compress(bytes(5)))
                 + chunk(b"tEXt", b"key\0value") + chunk(b"IEND"))
        self.assertEqual(decode_rgba_png(image), (1, 1, bytes(4)))

    def test_dimensions_exceeding_decoder_capacity(self):
        with self.assertRaisesRegex(CartError, "capacity"):
            decode_rgba_png(png_from_raw(0x7FFFFFFF, 0x7FFFFFFF, b""))

    def test_invalid_dimensions(self):
        for width, height in [(0, 1), (1, 0), (0, 0), (0x80000000, 1), (1, 0xFFFFFFFF)]:
            with self.subTest(size=(width, height)), self.assertRaisesRegex(CartError, "dimensions"):
                decode_rgba_png(png_from_raw(width, height, b""))

    def test_cart_dimensions_before_inflation(self):
        image = png_from_raw(0x7FFFFFFF, 205, b"", compressed=b"not zlib")
        with patch("pico8_cart.zlib.decompressobj", side_effect=AssertionError("must not inflate")):
            with self.assertRaisesRegex(CartError, "expected 160x205"):
                payload_from_png(image)

    def test_unsupported_image_formats(self):
        for options in [dict(depth=16), dict(color=2), dict(interlace=1),
                        dict(compression=1), dict(filtering=1)]:
            with self.subTest(options=options), self.assertRaisesRegex(CartError, "RGBA"):
                decode_rgba_png(PNG_SIGNATURE + ihdr(1, 1, **options)
                                + chunk(b"IDAT", zlib.compress(bytes(5))) + chunk(b"IEND"))

    def test_filter_and_scanline_lengths(self):
        for raw in [b"\x05" + bytes(4), bytes(4), bytes(6), b""]:
            with self.subTest(raw=raw), self.assertRaises(CartError):
                decode_rgba_png(png_from_raw(1, 1, raw))

    def test_malformed_zlib_streams(self):
        encoded = zlib.compress(bytes(5))
        for stream in [b"invalid", encoded[:-1], encoded + b"junk", encoded + encoded]:
            with self.subTest(stream=stream), self.assertRaises(CartError):
                decode_rgba_png(png_from_raw(1, 1, b"", compressed=stream))

    def test_inflation_is_bounded_by_scanline_size(self):
        image = png_from_raw(1, 1, bytes(100000))
        with self.assertRaisesRegex(CartError, "data length"):
            decode_rgba_png(image)
