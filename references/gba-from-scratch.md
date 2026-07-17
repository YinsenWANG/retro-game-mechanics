# From-scratch GBA reverse-analysis workflow

Use this workflow when no authorized source or symbol map is available. It produces candidate relationships for review, not a falsely precise decompilation.

```bash
python3 scripts/gba_rom.py GAME.gba --output gba-manifest.json
python3 scripts/gba_analyze.py GAME.gba --output gba-static-analysis.json
```

Stages:

1. Preserve the original and record SHA-256, header, revision clues, and permission scope.
2. Treat the 192-byte header and conventional entry branch as the only initial anchors.
3. Recursively follow directly resolved ARM/Thumb branches from proven code anchors; stop at indirect branches, jump tables, overlays, literal pools, and copied-to-RAM code.
4. Record literal-pool pointers and aligned ROM pointers separately. Cluster targets, then classify them only after examining consumers and alignment.
5. Validate GBA BIOS LZ77 streams (`0x10`) structurally. Do not treat every `0x10` byte as compression or label decoded output without a consumer.
6. Separate executable code, pointer tables, scripts, text, graphics, maps, audio, padding, and unknown regions through cross-references and runtime traces.
7. Convert disassembly to pseudocode only when branches, flags, calling convention, widths, signedness, and side effects are supported.
8. Connect recovered functions and tables to input, state transitions, entity lifecycles, physics, collision, resources, progression, and feedback. Record offsets and confidence for every claim.
9. Validate dynamic behavior with emulator tracing, memory watches, frame stepping, or controlled play. Keep static candidates and play observations separate.

A commercial ROM contains machine code and data, not the original C source, names, comments, or build files. From-scratch output can include disassembly, reconstructed pseudocode, recovered constants, data schemas, and a behavior model. Name recovery and semantics remain hypotheses unless confirmed by repeated control/data evidence or runtime behavior.

Do not use a parser from another console, guess compression from a magic byte, treat every ROM pointer as a function, or copy extracted copyrighted assets into the Skill. Preserve unresolved regions and list the runtime experiment needed to resolve them.
