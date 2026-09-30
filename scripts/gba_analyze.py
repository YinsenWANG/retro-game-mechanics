#!/usr/bin/env python3
"""Recover static code structure and BIOS-compressed blocks from an authorized GBA ROM.

This is a conservative discovery tool, not a source-code recovery claim. It uses
only the Python standard library and preserves undecoded instructions as data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from gba_rom import GbaRomError, inspect_rom


ROM_BASE = 0x08000000
COND = ("eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc",
        "hi", "ls", "ge", "lt", "gt", "le", "", "nv")


@dataclass
class Insn:
    offset: int
    size: int
    mode: str
    raw: int
    mnemonic: str
    operands: str = ""
    targets: list[tuple[int, str]] = field(default_factory=list)
    terminates: bool = False
    fallthrough: bool = True
    literal_target_mode: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "offset": self.offset, "address": f"0x{ROM_BASE + self.offset:08x}",
            "size": self.size, "mode": self.mode, "raw": f"0x{self.raw:0{self.size * 2}x}",
            "mnemonic": self.mnemonic, "operands": self.operands,
            "targets": [{"offset": x, "kind": kind} for x, kind in self.targets],
            "terminates": self.terminates,
        }


def _sign(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def decode_arm(data: bytes, offset: int) -> Insn:
    word = struct.unpack_from("<I", data, offset)[0]
    cond = COND[word >> 28]
    suffix = cond
    ins = Insn(offset, 4, "arm", word, ".word", f"0x{word:08x}")
    if (word & 0x0FFFFFF0) == 0x012FFF10:  # BX
        reg = word & 0xF
        return Insn(offset, 4, "arm", word, "bx" + suffix, f"r{reg}",
                    terminates=True, fallthrough=False)
    if (word & 0x0E000000) == 0x0A000000:  # B/BL
        link = bool(word & 0x01000000)
        target = offset + 8 + (_sign(word & 0xFFFFFF, 24) << 2)
        kind = "call" if link else "branch"
        unconditional = (word >> 28) == 0xE
        return Insn(offset, 4, "arm", word, ("bl" if link else "b") + suffix,
                    f"0x{ROM_BASE + target:08x}", [(target, kind)],
                    terminates=not link and unconditional,
                    fallthrough=link or not unconditional)
    if (word & 0x0F000000) == 0x0F000000:
        return Insn(offset, 4, "arm", word, "swi" + suffix, f"0x{word & 0xFFFFFF:x}")
    if (word & 0x0C000000) == 0x04000000:  # single data transfer
        load = bool(word & (1 << 20)); rn = (word >> 16) & 0xF; rd = (word >> 12) & 0xF
        up = bool(word & (1 << 23)); immediate = not bool(word & (1 << 25))
        if immediate:
            delta = word & 0xFFF
            op = "ldr" if load else "str"
            sign = "" if up else "-"
            targets: list[tuple[int, str]] = []
            operands = f"r{rd}, [r{rn}, #{sign}{delta}]"
            if rn == 15:
                address = (offset + 8 + (delta if up else -delta)) & ~3
                operands += f" ; ROM+0x{address:x}"
                if 0 <= address <= len(data) - 4:
                    value = struct.unpack_from("<I", data, address)[0]
                    operands += f" =0x{value:08x}"
                    if ROM_BASE <= (value & ~1) < ROM_BASE + len(data):
                        targets.append(((value & ~1) - ROM_BASE, "literal-pointer"))
            return Insn(offset, 4, "arm", word, op + suffix, operands, targets,
                        literal_target_mode="thumb" if targets and value & 1 else "arm")
    if (word & 0x0E000000) == 0x08000000:  # block transfer
        load = bool(word & (1 << 20)); rn = (word >> 16) & 0xF; regs = word & 0xFFFF
        names = [f"r{i}" for i in range(16) if regs & (1 << i)]
        op = "ldm" if load else "stm"
        return Insn(offset, 4, "arm", word, op + suffix, f"r{rn}!, {{{', '.join(names)}}}",
                    terminates=load and bool(regs & (1 << 15)),
                    fallthrough=not (load and bool(regs & (1 << 15))))
    if (word & 0x0C000000) == 0:  # common data-processing immediate/register form
        opcode = (word >> 21) & 0xF
        names = ("and", "eor", "sub", "rsb", "add", "adc", "sbc", "rsc",
                 "tst", "teq", "cmp", "cmn", "orr", "mov", "bic", "mvn")
        rn = (word >> 16) & 0xF; rd = (word >> 12) & 0xF
        if word & (1 << 25):
            imm = word & 0xFF; rot = ((word >> 8) & 0xF) * 2
            operand = ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm
            op2 = f"#0x{operand:x}"
        else:
            op2 = f"r{word & 0xF}"
        if opcode in (8, 9, 10, 11): operands = f"r{rn}, {op2}"
        elif opcode in (13, 15): operands = f"r{rd}, {op2}"
        else: operands = f"r{rd}, r{rn}, {op2}"
        return Insn(offset, 4, "arm", word, names[opcode] + suffix, operands)
    return ins


def decode_thumb(data: bytes, offset: int) -> Insn:
    half = struct.unpack_from("<H", data, offset)[0]
    ins = Insn(offset, 2, "thumb", half, ".hword", f"0x{half:04x}")
    if (half & 0xFF87) == 0x4700:  # BX/BLX register
        reg = (half >> 3) & 0xF
        return Insn(offset, 2, "thumb", half, "bx", f"r{reg}", terminates=True, fallthrough=False)
    if (half & 0xF800) == 0xE000:  # unconditional B
        target = offset + 4 + (_sign(half & 0x7FF, 11) << 1)
        return Insn(offset, 2, "thumb", half, "b", f"0x{ROM_BASE + target:08x}",
                    [(target, "branch")], terminates=True, fallthrough=False)
    if (half & 0xF000) == 0xD000 and (half & 0x0F00) < 0x0E00:
        cond = COND[(half >> 8) & 0xF]
        target = offset + 4 + (_sign(half & 0xFF, 8) << 1)
        return Insn(offset, 2, "thumb", half, "b" + cond, f"0x{ROM_BASE + target:08x}",
                    [(target, "branch")])
    if (half & 0xFF00) == 0xDF00:
        return Insn(offset, 2, "thumb", half, "swi", f"0x{half & 0xFF:x}")
    if (half & 0xF800) == 0x4800:  # literal LDR
        rd = (half >> 8) & 7; literal = ((offset + 4) & ~3) + ((half & 0xFF) << 2)
        operands = f"r{rd}, [pc, #{(half & 0xFF) << 2}] ; ROM+0x{literal:x}"
        targets: list[tuple[int, str]] = []
        if 0 <= literal <= len(data) - 4:
            value = struct.unpack_from("<I", data, literal)[0]
            operands += f" =0x{value:08x}"
            if ROM_BASE <= (value & ~1) < ROM_BASE + len(data):
                targets.append(((value & ~1) - ROM_BASE, "literal-pointer"))
        return Insn(offset, 2, "thumb", half, "ldr", operands, targets,
                    literal_target_mode="thumb" if targets and value & 1 else "arm")
    if (half & 0xF600) == 0xB400:  # PUSH/POP
        pop = bool(half & 0x0800); extra = bool(half & 0x0100)
        regs = [f"r{i}" for i in range(8) if half & (1 << i)]
        if extra: regs.append("pc" if pop else "lr")
        return Insn(offset, 2, "thumb", half, "pop" if pop else "push",
                    "{" + ", ".join(regs) + "}", terminates=pop and extra,
                    fallthrough=not (pop and extra))
    if (half & 0xE000) == 0x2000:
        op = (half >> 11) & 3; names = ("mov", "cmp", "add", "sub")
        return Insn(offset, 2, "thumb", half, names[op], f"r{(half >> 8) & 7}, #{half & 0xFF}")
    if (half & 0xF800) == 0x3000:
        return Insn(offset, 2, "thumb", half, "add", f"r{(half >> 8) & 7}, #{half & 0xFF}")
    if (half & 0xF800) == 0x3800:
        return Insn(offset, 2, "thumb", half, "sub", f"r{(half >> 8) & 7}, #{half & 0xFF}")
    return ins


def _valid_offset(data: bytes, offset: int, mode: str) -> bool:
    align = 4 if mode == "arm" else 2
    return 0 <= offset <= len(data) - align and offset % align == 0


def discover_cfg(data: bytes, seeds: list[tuple[int, str]], max_instructions: int) -> dict[str, object]:
    if max_instructions <= 0:
        raise ValueError("max_instructions must be positive")
    queue = deque(seeds)
    decoded: dict[tuple[int, str], Insn] = {}
    function_seeds: set[tuple[int, str]] = set(seeds)
    edges: set[tuple[int, int, str]] = set()
    while queue and len(decoded) < max_instructions:
        start, mode = queue.popleft()
        if not _valid_offset(data, start, mode): continue
        pos = start
        while _valid_offset(data, pos, mode) and len(decoded) < max_instructions:
            key = (pos, mode)
            if key in decoded: break
            ins = decode_arm(data, pos) if mode == "arm" else decode_thumb(data, pos)
            decoded[key] = ins
            for target, kind in ins.targets:
                if kind in {"branch", "call"} and _valid_offset(data, target, mode):
                    edges.add((pos, target, kind)); queue.append((target, mode))
                    if kind == "call": function_seeds.add((target, mode))
                elif kind == "literal-pointer":
                    target_mode = ins.literal_target_mode or mode
                    if _valid_offset(data, target, target_mode):
                        function_seeds.add((target, target_mode))
            if ins.terminates or not ins.fallthrough: break
            pos += ins.size
    ordered = [decoded[k].as_dict() for k in sorted(decoded)]
    return {
        "instruction_count": len(ordered),
        "truncated": len(decoded) >= max_instructions,
        "function_seeds": [{"offset": o, "address": f"0x{ROM_BASE + o:08x}", "mode": m}
                           for o, m in sorted(function_seeds)],
        "edges": [{"source_offset": a, "target_offset": b, "kind": k}
                  for a, b, k in sorted(edges)],
        "instructions": ordered,
        "warning": "Function seeds and CFG are conservative approximations; indirect calls and mode changes through registers need data-flow analysis.",
    }


def _lz77_block(data: bytes, start: int) -> dict[str, int] | None:
    if start + 4 > len(data) or data[start] != 0x10: return None
    output_size = int.from_bytes(data[start + 1:start + 4], "little")
    if not 1 <= output_size <= 64 * 1024 * 1024: return None
    pos = start + 4; produced = 0
    try:
        while produced < output_size:
            flags = data[pos]; pos += 1
            for bit in range(7, -1, -1):
                if produced >= output_size: break
                if flags & (1 << bit):
                    token = (data[pos] << 8) | data[pos + 1]; pos += 2
                    length = (token >> 12) + 3; distance = (token & 0xFFF) + 1
                    if distance > produced: return None
                    produced += length
                else:
                    pos += 1; produced += 1
                if pos > len(data): return None
    except IndexError:
        return None
    return {"offset": start, "compressed_size": pos - start, "decompressed_size": output_size}


def scan_lz77(data: bytes, alignment: int = 4) -> list[dict[str, int]]:
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    blocks = []
    for offset in range(0, len(data) - 4, alignment):
        block = _lz77_block(data, offset)
        if block is not None: blocks.append(block)
    return blocks


def analyze(path: Path, max_instructions: int) -> dict[str, object]:
    if max_instructions <= 0:
        raise ValueError("max_instructions must be positive")
    data = path.read_bytes()
    metadata = inspect_rom(path)
    entry = int(metadata["header"]["entry_point"].get("target_rom_offset", 0))  # type: ignore[index,union-attr]
    result = {
        "schema": "retro-game-mechanics/gba-static-analysis-v1",
        "source": {"filename": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        "metadata": metadata,
        "control_flow": discover_cfg(data, [(entry, "arm")], max_instructions),
        "bios_lz77_blocks": scan_lz77(data),
        "evidence_limits": [
            "Original source names, comments, types, build scripts, and author intent are not present in a retail ROM.",
            "Unknown instructions remain raw words/halfwords; no pseudocode is fabricated.",
            "Static analysis cannot prove indirect control flow, copied-to-RAM code, self-modification, or runtime state.",
            "Validated compression streams are structural candidates until consumers and decoded content are traced.",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-instructions", type=int, default=100000)
    args = parser.parse_args()
    try:
        result = analyze(args.rom, args.max_instructions)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output: args.output.write_text(encoded, encoding="utf-8")
        else: print(encoded, end="")
        return 0
    except (OSError, GbaRomError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
