# Format adapters

## Adapter contract

Treat each platform parser as a replaceable adapter. An adapter should declare:

- supported platform, region/revision assumptions, extensions, magic bytes and size constraints;
- whether it reads source, a cartridge image, a ROM, an executable, a disk image or an extracted directory;
- deterministic extraction outputs and their byte ranges or source sections;
- compression, character encoding, checksums, banks, memory maps and known variants;
- validation fixtures and unsupported cases;
- legal or access constraints specific to the platform or source service.

The platform-independent mechanism analysis begins after extraction. Do not embed engine-selection or remake guidance in an adapter.

## Available adapters

### PICO-8

**Status:** implemented and tested.

**Inputs:** `.p8`, `.p8.png`, `.p8.rom`.

**Scripts:**

- `scripts/pico8_cart.py`: parse, decompress, convert P8SCII, split ROM regions and write a manifest.
- `scripts/analyze_cart.py`: generate a lexical source/resource index.
- `scripts/create_analysis_case.py`: record provenance, rights, SHA-256 and static reports.

**References:**

- `references/pico8-cartridge-format.md`
- `references/pico8-technical-system.md`
- `references/pico8-sample-analyses.md`

**Limits:** static call graphs are approximate; runtime behavior, dynamic Lua dispatch and design intent still require source-flow or play verification.

## Adding another platform

1. Confirm the requested artifact can be lawfully inspected and retained.
2. Prefer official format documentation, open-source emulator implementations and author-published source.
3. Add a platform-named parser instead of widening an existing parser with unrelated heuristics.
4. Emit an unpacked directory plus a machine-readable manifest containing hashes, offsets, sizes and format/version facts.
5. Preserve unknown bytes and unsupported regions rather than silently discarding them.
6. Add small, redistributable or user-provided fixtures and test exact round-trip/extraction behavior where possible.
7. Add one platform reference documenting the runtime, file layout, tool usage and known limits.
8. Register the adapter in this file and add only the minimal routing instructions to `SKILL.md`.
