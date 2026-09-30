import hashlib
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import gba_rom, lz77, temporary_directory
from gba_rom import GbaRomError, header_checksum, inspect_rom
from gba_analyze import (_lz77_block, analyze, decode_arm, decode_thumb,
                         discover_cfg, scan_lz77)


class GbaHeaderTests(unittest.TestCase):
    def inspect(self, data, name="synthetic.gba"):
        with temporary_directory() as directory:
            path = Path(directory) / name
            path.write_bytes(data)
            return inspect_rom(path)

    def test_header_fields_hash_and_explicit_limits(self):
        data = gba_rom()
        for suffix in ["gba", "agb", "bin", "GBA"]:
            with self.subTest(suffix=suffix):
                result = self.inspect(data, "synthetic." + suffix)
                header = result["header"]
                self.assertEqual(header["title"], "SYNTHETIC")
                self.assertEqual(header["game_code"], "TEST")
                self.assertEqual(header["maker_code"], "00")
                self.assertEqual(header["software_version"], 7)
                self.assertTrue(header["header_checksum_valid"])
                self.assertEqual(header["entry_point"]["target_rom_offset"], 0xC0)
                self.assertTrue(header["entry_point"]["target_in_file"])
                self.assertEqual(result["source"]["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(len(result["validation"]["warnings"]), 1)
                self.assertIn("logo", " ".join(result["limits"]))
                self.assertNotIn("logo", header)

    def test_checksum_and_fixed_byte_warnings(self):
        self.assertEqual(header_checksum(bytes(0xC0)), 0xE7)
        data = gba_rom()
        data[0xA0] ^= 1
        data[0xB2] = 0
        result = self.inspect(data)
        self.assertFalse(result["header"]["header_checksum_valid"])
        self.assertFalse(result["validation"]["fixed_value_valid"])
        self.assertEqual(len(result["validation"]["warnings"]), 3)
        result = self.inspect(gba_rom(0x10000))
        self.assertTrue(result["validation"]["conventional_power_of_two_size"])
        self.assertEqual(result["validation"]["warnings"], [])

    def test_header_size_and_extension_boundaries(self):
        for size in [0, 1, 0xBF]:
            with self.subTest(size=size), self.assertRaisesRegex(GbaRomError, "too small"):
                self.inspect(bytes(size))
        self.assertEqual(self.inspect(gba_rom()[:0xC0])["source"]["size"], 0xC0)
        with self.assertRaisesRegex(GbaRomError, "expected"):
            self.inspect(gba_rom(), "synthetic.txt")
        with patch.object(Path, "read_bytes", return_value=bytes(32 * 1024 * 1024 + 1)):
            with self.assertRaisesRegex(GbaRomError, "32 MiB"):
                inspect_rom(Path("synthetic.gba"))

    def test_entry_signed_and_out_of_file_targets(self):
        for word, target in [(0xEAFFFFFE, 0), (0xEAFFFFFC, -8), (0xEA0000FE, 0x400)]:
            data = gba_rom()
            struct.pack_into("<I", data, 0, word)
            entry = self.inspect(data)["header"]["entry_point"]
            with self.subTest(word=word):
                self.assertEqual(entry["target_rom_offset"], target)
                self.assertEqual(entry["target_in_file"], 0 <= target < len(data))
        data = gba_rom()
        struct.pack_into("<I", data, 0, 0xE3A00000)
        self.assertNotIn("target_rom_offset", self.inspect(data)["header"]["entry_point"])

    def test_markers_and_mirrored_aligned_pointer_candidates(self):
        data = gba_rom()
        data[0x100:0x10C] = b"SRAM_V123\0\0\0"
        data[0x120:0x12C] = b"SRAM_V456\0\0\0"
        data[0x140:0x14C] = b"SIIRTC_V001\0"
        for offset, value in [(0x160, 0x08000180), (0x164, 0x0A000180),
                              (0x168, 0x0C000180), (0x16C, 0x08000200),
                              (0x170, 0x0E000180), (0x1D1, 0x08000184)]:
            struct.pack_into("<I", data, offset, value)
        result = self.inspect(data)
        self.assertEqual(result["technology_markers"]["save"],
                         [{"marker": "SRAM_V123", "offset": 0x100},
                          {"marker": "SRAM_V456", "offset": 0x120}])
        self.assertEqual(result["technology_markers"]["peripherals"],
                         [{"marker": "SIIRTC_V001", "offset": 0x140}])
        self.assertEqual(result["pointer_index"]["aligned_rom_pointer_count"], 3)
        self.assertEqual(result["pointer_index"]["top_targets"],
                         [{"rom_offset": 0x180, "reference_count": 3}])


class GbaCodeTests(unittest.TestCase):
    def test_arm_branches_calls_and_unknown_word(self):
        for word, name, target, fallthrough in [(0xEAFFFFFE, "b", 0, False),
                                               (0xEB000000, "bl", 8, True),
                                               (0x1AFFFFFE, "bne", 0, True)]:
            ins = decode_arm(struct.pack("<I", word), 0)
            with self.subTest(word=word):
                self.assertEqual(ins.mnemonic, name)
                self.assertEqual(ins.targets, [(target, "call" if name == "bl" else "branch")])
                self.assertEqual(ins.fallthrough, fallthrough)
        ins = decode_arm(struct.pack("<I", 0xEE000000), 0)
        self.assertEqual(ins.as_dict()["raw"], "0xee000000")
        self.assertEqual(ins.mnemonic, ".word")
        self.assertEqual(decode_arm(struct.pack("<I", 0xE3A00480), 0).operands, "r0, #0x80000000")
        self.assertTrue(decode_arm(struct.pack("<I", 0xE12FFF1E), 0).terminates)

    def test_thumb_signed_branches_return_and_unknown_halfword(self):
        for half, name, target, stops in [(0xE7FE, "b", 0, True), (0xD1FE, "bne", 0, False)]:
            ins = decode_thumb(struct.pack("<H", half), 0)
            with self.subTest(half=half):
                self.assertEqual(ins.mnemonic, name)
                self.assertEqual(ins.targets, [(target, "branch")])
                self.assertEqual(ins.terminates, stops)
        self.assertTrue(decode_thumb(struct.pack("<H", 0x4770), 0).terminates)
        self.assertTrue(decode_thumb(struct.pack("<H", 0xBD01), 0).terminates)
        self.assertEqual(decode_thumb(struct.pack("<H", 0xB501), 0).operands, "{r0, lr}")
        ins = decode_thumb(struct.pack("<H", 0xDE00), 0)
        self.assertEqual(ins.mnemonic, ".hword")
        self.assertEqual(ins.as_dict()["raw"], "0xde00")

    def test_cfg_loops_calls_invalid_seeds_and_budget(self):
        data = struct.pack("<IIIII", 0xEA000000, 0, 0xEB000000, 0xE12FFF1E, 0xEAFFFFFE)
        result = discover_cfg(data, [(0, "arm"), (-4, "arm"), (2, "arm"), (20, "arm")], 20)
        self.assertEqual([ins["offset"] for ins in result["instructions"]], [0, 8, 12, 16])
        self.assertEqual(result["edges"],
                         [{"source_offset": 0, "target_offset": 8, "kind": "branch"},
                          {"source_offset": 8, "target_offset": 16, "kind": "call"},
                          {"source_offset": 16, "target_offset": 16, "kind": "branch"}])
        self.assertFalse(result["truncated"])
        limited = discover_cfg(data, [(0, "arm")], 2)
        self.assertEqual(limited["instruction_count"], 2)
        self.assertTrue(limited["truncated"])
        for limit in [0, -1]:
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "positive"):
                discover_cfg(data, [(0, "arm")], limit)

    def test_literal_pointer_target_and_mode_are_not_dereferenced_again(self):
        for mode in ["arm", "thumb"]:
            for low_bit, target_mode in [(0, "arm"), (1, "thumb")]:
                data = bytearray(32)
                if mode == "arm":
                    struct.pack_into("<II", data, 0, 0xE59F0000, 0xE12FFF1E)
                else:
                    struct.pack_into("<HH", data, 0, 0x4801, 0x4770)
                struct.pack_into("<I", data, 8, 0x08000010 | low_bit)
                # Target bytes happen to resemble another pointer. It must be ignored.
                struct.pack_into("<I", data, 16, 0x08000018)
                result = discover_cfg(data, [(0, mode)], 10)
                with self.subTest(mode=mode, low_bit=low_bit):
                    self.assertEqual(result["function_seeds"],
                                     [{"offset": 0, "address": "0x08000000", "mode": mode},
                                      {"offset": 16, "address": "0x08000010", "mode": target_mode}])
                    self.assertEqual(result["instruction_count"], 2)

    def test_end_to_end_analysis_keeps_evidence_limits(self):
        with temporary_directory() as directory:
            path = Path(directory) / "synthetic.gba"
            path.write_bytes(gba_rom())
            result = analyze(path, 20)
        self.assertEqual(result["control_flow"]["instructions"][0]["offset"], 0xC0)
        self.assertEqual(result["control_flow"]["instruction_count"], 1)
        self.assertEqual(result["bios_lz77_blocks"], [])
        self.assertTrue(result["evidence_limits"])


class Lz77Tests(unittest.TestCase):
    def test_literals_and_overlapping_backreference(self):
        for size, stream in [(3, b"\0ABC"), (6, b"\x40A\x20\0")]:
            data = lz77(size, stream)
            with self.subTest(stream=stream):
                self.assertEqual(_lz77_block(data, 0),
                                 {"offset": 0, "compressed_size": len(data), "decompressed_size": size})
                self.assertEqual(scan_lz77(data), [_lz77_block(data, 0)])

    def test_truncation_zero_size_and_invalid_distance(self):
        data = lz77(3, b"\0ABC")
        for prefix in range(len(data)):
            with self.subTest(prefix=prefix):
                self.assertIsNone(_lz77_block(data[:prefix], 0))
        for data in [lz77(0, b""), lz77(3, b"\x80\0\0"), lz77(4, b"\x40A\0\x01")]:
            with self.subTest(data=data):
                self.assertIsNone(_lz77_block(data, 0))

    def test_alignment_and_compressed_size_exclude_padding(self):
        block = lz77(1, b"\0A")
        data = bytes(4) + block + bytes(2)
        self.assertEqual(scan_lz77(data), [{"offset": 4, "compressed_size": 6, "decompressed_size": 1}])
        self.assertEqual(scan_lz77(b"\0" + block), [])
        self.assertEqual(scan_lz77(b"\0" + block, alignment=1)[0]["offset"], 1)
        for alignment in [0, -1]:
            with self.subTest(alignment=alignment), self.assertRaisesRegex(ValueError, "positive"):
                scan_lz77(data, alignment)
