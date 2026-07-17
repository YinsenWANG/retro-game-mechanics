#!/usr/bin/env python3
"""Generate a reproducible static-analysis brief for a local PICO-8 cart."""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from pico8_cart import CartError, Cartridge, read_cartridge


API_GROUPS = {
    "system": {"load", "save", "run", "stop", "flip", "time", "t", "stat", "extcmd", "printh", "menuitem"},
    "graphics": {"cls", "camera", "circ", "circfill", "clip", "color", "cursor", "fillp", "line", "oval", "ovalfill", "pal", "palt", "pget", "print", "pset", "rect", "rectfill", "sget", "spr", "sset", "sspr"},
    "input": {"btn", "btnp", "key", "keyp"},
    "audio": {"music", "sfx"},
    "map": {"map", "mget", "mset", "fget", "fset", "tline"},
    "memory": {"cartdata", "dget", "dset", "memcpy", "memset", "peek", "peek2", "peek4", "poke", "poke2", "poke4", "reload", "cstore"},
    "math_table": {"abs", "add", "all", "atan2", "band", "bnot", "bor", "bxor", "ceil", "cos", "count", "del", "deli", "flr", "foreach", "lshr", "max", "mid", "min", "pack", "rnd", "rotl", "rotr", "sgn", "shl", "shr", "sin", "sqrt", "srand", "sub", "unpack"},
}
ALL_APIS = set().union(*API_GROUPS.values())

CALL_RE = re.compile(r"(?<![\w.])([a-z_][\w.]*)\s*\(", re.I)
FUNCTION_RES = (
    re.compile(r"^\s*(?:local\s+)?function\s+([a-z_][\w.]*)\s*\(", re.I),
    re.compile(r"^\s*(?:local\s+)?([a-z_][\w.]*)\s*=\s*function\s*\(", re.I),
)
TABLE_ASSIGN_RE = re.compile(r"^\s*(?:local\s+)?([a-z_][\w.]*)\s*=\s*\{", re.I)
GLOBAL_ASSIGN_RE = re.compile(r"^\s*([a-z_][\w.]*)\s*(?:[+\-*/.]?=)", re.I)


def strip_comments_and_strings(code: str) -> str:
    code = re.sub(r"--\[\[.*?\]\]", " ", code, flags=re.S)
    code = re.sub(r"--[^\n]*", "", code)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    code = re.sub(r"'(?:\\.|[^'\\])*'", "''", code)
    return code


def find_functions(code: str) -> list[dict[str, object]]:
    lines = code.splitlines()
    starts: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, 1):
        for pattern in FUNCTION_RES:
            match = pattern.search(line)
            if match:
                starts.append((line_no, match.group(1)))
                break
    function_names = {name for _, name in starts}
    results = []
    for index, (line_no, name) in enumerate(starts):
        end_line = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        body = "\n".join(lines[line_no - 1 : end_line])
        calls = [match.group(1) for match in CALL_RE.finditer(strip_comments_and_strings(body))]
        results.append(
            {
                "name": name,
                "line": line_no,
                "calls_custom": sorted({call for call in calls if call in function_names and call != name}),
                "calls_api": dict(collections.Counter(call for call in calls if call in ALL_APIS).most_common()),
            }
        )
    return results


def hex_nibbles(text: str) -> list[int]:
    return [int(ch, 16) for ch in text.lower() if ch in "0123456789abcdef"]


def p8_asset_summary(cart: Cartridge) -> dict[str, object]:
    result: dict[str, object] = {}
    if cart.source_format == "p8":
        gfx = hex_nibbles(cart.sections.get("gfx", ""))
        result["gfx_nonzero_pixels"] = sum(value != 0 for value in gfx)
        result["gfx_nonempty_8x8_cells_estimate"] = sum(
            any(gfx[(row + y) * 128 + col : (row + y) * 128 + col + 8] for y in range(8))
            for row in range(0, min(128, len(gfx) // 128), 8)
            for col in range(0, 128, 8)
        ) if len(gfx) >= 128 * 128 else None
        map_bytes = bytes.fromhex("".join(ch for ch in cart.sections.get("map", "") if ch.lower() in "0123456789abcdef")) if cart.sections.get("map") else b""
        result["map_bytes"] = len(map_bytes)
        result["map_nonzero_tiles"] = sum(value != 0 for value in map_bytes)
        gff = bytes.fromhex("".join(ch for ch in cart.sections.get("gff", "") if ch.lower() in "0123456789abcdef")) if cart.sections.get("gff") else b""
        result["flag_bytes"] = len(gff)
        result["flagged_sprites"] = sum(value != 0 for value in gff)
        result["sfx_rows"] = sum(bool(line.strip()) for line in cart.sections.get("sfx", "").splitlines())
        result["music_rows"] = sum(bool(line.strip()) for line in cart.sections.get("music", "").splitlines())
    elif cart.rom is not None:
        rom = cart.rom
        gfx = rom[0x0000:0x2000]
        result["gfx_nonzero_nibbles"] = sum(bool(value & 0x0F) + bool(value >> 4) for value in gfx)
        result["map_nonzero_tiles"] = sum(value != 0 for value in rom[0x2000:0x3000])
        result["flagged_sprites"] = sum(value != 0 for value in rom[0x3000:0x3100])
        result["music_patterns_nonempty_estimate"] = sum(
            any(value != 0x41 + channel for channel, value in enumerate(rom[0x3100 + row * 4 : 0x3104 + row * 4]))
            for row in range(64)
        )
        result["sfx_nonempty_estimate"] = sum(
            any(rom[0x3200 + row * 68 : 0x3240 + row * 68])
            for row in range(64)
        )
    return result


def analyze(cart: Cartridge, source: str) -> dict[str, object]:
    clean = strip_comments_and_strings(cart.code)
    calls = [match.group(1) for match in CALL_RE.finditer(clean)]
    api_counts = collections.Counter(call for call in calls if call in ALL_APIS)
    functions = find_functions(cart.code)
    tables = sorted({match.group(1) for line in cart.code.splitlines() if (match := TABLE_ASSIGN_RE.search(line))})
    globals_seen = sorted({match.group(1) for line in cart.code.splitlines() if (match := GLOBAL_ASSIGN_RE.search(line))})
    callbacks = [name for name in ("_init", "_update", "_update60", "_draw") if re.search(rf"\b{name}\s*=\s*function|\bfunction\s+{name}\s*\(", clean)]
    return {
        "source": source,
        "format": cart.source_format,
        "version": cart.version,
        "code": {
            "characters": len(cart.code),
            "lines": cart.code.count("\n") + bool(cart.code),
            "callbacks": callbacks,
            "function_count": len(functions),
            "functions": functions,
            "table_candidates": tables,
            "global_state_candidates": globals_seen,
            "api_calls": dict(api_counts.most_common()),
            "api_groups": {
                group: sum(api_counts[name] for name in names) for group, names in API_GROUPS.items()
            },
        },
        "assets": p8_asset_summary(cart),
        "caveats": [
            "Call graph edges are lexical approximations, not runtime traces.",
            "Compressed/minified naming can hide semantic roles.",
            "Design intent and why-it-is-fun claims require play evidence or cautious inference.",
        ],
    }


def markdown_report(result: dict[str, object]) -> str:
    code = result["code"]
    assets = result["assets"]
    lines = [
        f"# Static cartridge analysis: {Path(str(result['source'])).name}",
        "",
        "## Facts from the file",
        "",
        f"- Format: `{result['format']}`; version: `{result['version']}`",
        f"- Code: {code['characters']} characters, {code['lines']} lines, {code['function_count']} named functions",
        f"- Lifecycle callbacks: {', '.join(code['callbacks']) or 'none detected'}",
        f"- Table candidates: {', '.join(code['table_candidates'][:20]) or 'none detected'}",
        "",
        "### API profile",
        "",
    ]
    for group, count in code["api_groups"].items():
        lines.append(f"- {group}: {count}")
    lines.extend(["", "### Asset profile", ""])
    for key, value in assets.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "### Approximate function relationships", ""])
    for function in code["functions"]:
        custom = ", ".join(function["calls_custom"]) or "—"
        lines.append(f"- `{function['name']}` (line {function['line']}) → {custom}")
    lines.extend(
        [
            "",
            "## Analyst completion required",
            "",
            "Complete the report with play evidence, controls and action grammar, core and secondary loops, states, entities, collision/physics, resources, progression, feedback, failure/retry, content generation, system couplings, and evidence-backed explanations of player experience. Label every claim as fact, source observation, play observation, design inference, or unknown.",
            "",
            "## Caveats",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["caveats"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cartridge", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(read_cartridge(args.cartridge), str(args.cartridge))
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else markdown_report(result)
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, CartError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
