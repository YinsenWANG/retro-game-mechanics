# Retro Game Mechanics

`retro-game-mechanics` is a portable Agent Skill for studying how classic games actually work and turning that understanding into useful creative input for new game development. It can be used with Cherry Studio, Claude Code, Codex, OpenCode, and other clients that support the Agent Skills format.

Many newer models are already very good at writing game code. The harder and more valuable problem is often elsewhere: a game needs a strong idea, a compelling core loop, readable rules, meaningful choices, and mechanisms that create memorable situations. Code can implement those things, but it does not invent their quality by itself.

This skill helps an agent investigate old games as evidence-rich design systems. It traces controls, state machines, entities, physics, collision, resources, level structure, pacing, feedback, and the interactions that make a compact game engaging. The result is a mechanics dossier that can give a new game creator concrete inspiration without copying the original game's expressive assets or pretending that a list of features is the same as good design.

## Compatible clients

The skill is client-agnostic. Install or link this directory according to the conventions of your Agent Skills-compatible tool, then invoke `retro-game-mechanics` from:

- Cherry Studio
- Claude Code
- Codex
- OpenCode
- Other tools that support the Agent Skills directory and `SKILL.md` convention

## What it supports

- Authorized local game packages, ROM-like files, source trees, and creator-published material
- PICO-8 cartridges (`.p8`, `.p8.png`, `.p8.rom`)
- Game Boy Advance ROM metadata and from-scratch static recovery (`.gba`, `.agb`)
- Evidence-separated mechanics dossiers covering runtime structure and player experience

The GBA workflow starts from the ROM itself: it validates the cartridge header, follows conservative ARM/Thumb control-flow candidates, indexes ROM pointers and literal pools, validates BIOS LZ77 candidates, and records what still requires runtime tracing. It does not substitute a title-specific decompilation project, and it does not claim to recover the original C source, names, comments, or author intent from a retail ROM.

## Quick start

```bash
# PICO-8
python3 scripts/pico8_cart.py GAME.p8.png --json
python3 scripts/analyze_cart.py GAME.p8.png --format markdown --output static-analysis.md

# GBA
python3 scripts/gba_rom.py GAME.gba --output gba-manifest.json
python3 scripts/gba_analyze.py GAME.gba --output gba-static-analysis.json
```

Read the relevant references before analyzing an artifact:

- [Rights and sources](references/rights-and-sources.md)
- [Format adapters](references/format-adapters.md)
- [From-scratch GBA recovery](references/gba-from-scratch.md)
- [Mechanics extraction model](references/mechanism-extraction.md)
- [Output contract](references/workflow-and-output.md)

## Evidence and boundaries

The skill keeps **facts**, **source/binary observations**, **play observations**, **design inferences**, and **unknowns** separate. Public availability or emulator compatibility is not treated as permission to acquire or redistribute a game. Original ROMs and extracted copyrighted assets are not bundled in this repository.

The goal is to understand the original game deeply enough that a later creative or technical agent can make independent decisions. This skill ends with that understanding; it does not prescribe a remake, engine, architecture, or feature roadmap.

## Validation

From the repository root, run the synthetic regression suite using only Python's
standard library:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

On systems where Python is named `python`, use `python -m unittest discover -s tests -v`.
No installed Agent Skill, emulator, ROM, BIOS, network access, or external Python
package is needed. Fixtures generate original bytes and clean up temporary files
inside the checkout.

Coverage includes PNG filters, CRC/chunk structure and bounded inflation;
P8SCII and legacy/pxa code decoding; GBA headers, pointer/marker heuristics,
ARM/Thumb control-flow candidates and BIOS LZ77 structure; and successful and
malformed-input CLI runs. Malformed inputs return exit status 2 with an `error:`
message on stderr. CI runs the same suite on Linux, macOS, and Windows.

These are synthetic parser regressions, not emulator or real-cartridge
compatibility certification. The PNG adapter accepts non-interlaced 8-bit RGBA
cartridges at 160×205 and checks that size before inflation. Text cartridges
must have a PICO-8 header and valid UTF-8. GBA headers and compression candidates
do not establish authenticity or runtime use, and the instruction decoder and
CFG remain conservative approximations.
