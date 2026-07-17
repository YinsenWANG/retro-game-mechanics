# Game Boy Advance cartridge adapter

Use this reference only for authorized local GBA ROM inspection. Do not bundle ROMs, BIOS files, extracted assets, translations, or patches in the Skill repository.

## Adapter scope

- Inputs: raw `.gba` or `.agb` cartridge images; accept `.bin` only when provenance identifies it as a raw GBA image.
- Size: at least the 192-byte header and no more than the 32 MiB cartridge ROM window.
- Output: metadata only—hashes, header fields, validation results, library markers, and a heuristic pointer index.
- Non-goals: emulation, disassembly, decompilation, decompression guessing, asset extraction, DRM bypass, ROM modification, or redistribution.

Run:

```bash
python3 scripts/gba_rom.py AUTHORIZED_GAME.gba --json
python3 scripts/gba_rom.py AUTHORIZED_GAME.gba --output gba-manifest.json
python3 scripts/gba_analyze.py AUTHORIZED_GAME.gba --output gba-static-analysis.json
```

## Header map

All offsets are file-relative and hexadecimal.

| Range | Meaning |
| --- | --- |
| `000-003` | ARM entry instruction, conventionally a branch |
| `004-09F` | Nintendo logo data; validate in controlled tooling but do not emit |
| `0A0-0AB` | Game title |
| `0AC-0AF` | Game code |
| `0B0-0B1` | Maker code |
| `0B2` | Fixed value, normally `96` |
| `0B3` | Main unit code |
| `0B4` | Device type |
| `0B5-0BB` | Reserved |
| `0BC` | Software version |
| `0BD` | Header complement checksum |
| `0BE-0BF` | Reserved |

Compute the complement byte as `(-sum(rom[0xA0:0xBD]) - 0x19) & 0xFF`. Treat a valid header as format evidence, not proof of authenticity, provenance, revision identity, or authorization.

## Runtime facts needed for later analysis

- CPU: ARM7TDMI, with ARM and Thumb instruction sets.
- Cartridge ROM is visible from `08000000`; wait-state mirrors also occur at `0A000000` and `0C000000`.
- Main memory regions include BIOS at `00000000`, EWRAM at `02000000`, IWRAM at `03000000`, I/O at `04000000`, palette at `05000000`, VRAM at `06000000`, OAM at `07000000`, and cartridge save space beginning at `0E000000`.
- Graphics can use tiled or bitmap display modes. A byte pattern alone is insufficient to label graphics, maps, palettes, audio, scripts, or compressed blocks.
- Save hardware is not declared by a canonical header field. Common SDK marker strings can support a hypothesis, but runtime bus behavior or emulator instrumentation is stronger evidence.

## Analysis escalation

After metadata inspection, identify code and data only with explicit evidence. Prefer symbols or map files from authorized source, emulator execution traces, known SDK signatures, and confirmed pointer tables. Record ROM offsets and runtime addresses separately. ARM/Thumb mode, overlays, copied-to-RAM code, compression, and indirect dispatch must remain unresolved until demonstrated.

### From-scratch static recovery

Use `scripts/gba_analyze.py` when analysis must derive from the ROM rather than a title-specific decompilation project. It recursively follows directly resolved ARM/Thumb branches from the entry point, records calls and basic control-flow edges, resolves literal-pool ROM pointers, and validates aligned BIOS LZ77 streams.

Treat its output as the first pass of an iterative recovery process:

1. Name functions by demonstrated callers, data access, side effects, and runtime traces—not by address proximity.
2. Add indirect targets only after resolving literal pools, jump tables, register values, or emulator traces.
3. Separate executable code, pointer tables, scripts, text, graphics, maps, audio, padding, and compressed data through cross-references and consumers.
4. Convert disassembly to pseudocode only when branches, flags, calling convention, widths, signedness, and side effects are supported.
5. Preserve unknown instructions and regions. Retail ROMs do not contain the original identifiers, comments, types, source layout, or author intent.

The built-in decoder deliberately covers a conservative ARM7TDMI subset and emits unknown opcodes as `.word` or `.hword`. For a comprehensive instruction decoder, use a separately installed, version-recorded engine such as Capstone or Ghidra and retain the raw ROM offsets alongside its output.

Technical baselines: [GBATEK specifications](https://www.akkit.org/info/gbatek.htm), [Tonc hardware overview](https://gbadev.net/tonc/hardware.html), and [mGBA scripting memory domains](https://mgba.io/docs/scripting.html).
