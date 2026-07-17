---
name: retro-game-mechanics
description: Unpack and analyze authorized retro games, fantasy-console cartridges, ROM-like packages, source trees, and game links. Reconstruct the original game's runtime and asset structure, controls, states, entities, physics, collision, AI, resources, progression, content generation, feedback, pacing, core loops, distinctive mechanics, and evidence-backed reasons the game works. Use for lawful game-package extraction, source and data inspection, comprehensive gameplay-mechanics dossiers, or explaining why a compact classic game is compelling. Includes a deterministic PICO-8 adapter for .p8, .p8.png, and .p8.rom; add other platform adapters without changing the platform-independent analysis method. This skill ends with understanding the original game and does not prescribe a new game's design or implementation.
---

# Retro Game Mechanics

Produce a comprehensive, evidence-backed account of how the original game works and why its mechanics create its experience. Give the next agent enough accurate information to make independent creative or technical decisions.

## Scope and autonomy

- Inspect authorized local artifacts, use a matching bundled adapter when available, and choose the analysis order and depth that fit the game.
- Stop this Skill's work at the completed original-game mechanics dossier. Do not prescribe a remake, engine, architecture, art style, feature roadmap, or implementation plan.
- If a broader request includes creation, finish and delimit the mechanics dossier first; handle later work with general judgment rather than a recipe from this Skill.
- Prefer completeness over arbitrary item limits. Omit generic introductions, repeated caveats, and speculative development advice before omitting rules or evidence.

## Resolve rights before acquisition

Read `references/rights-and-sources.md` before acquiring or unpacking a third-party game.

Record the title, author or publisher, platform, source, revision, retrieval date, license or permission basis, and cryptographic hash. Treat public availability, emulator compatibility, or visible source as insufficient permission to download, retain, modify, or redistribute.

When permission is unclear, do not acquire the artifact. Analyze only lawfully available public information or ask for an authorized local copy, and state which source-derived conclusions remain unavailable.

## Select a format adapter

Read `references/format-adapters.md` and identify the artifact before running a parser.

- Use only an adapter that explicitly supports the detected platform and file variant.
- Preserve the original artifact; unpack into a new directory and record hashes.
- Do not guess encryption, compression, bank layout, pointer formats, opcodes, or asset encodings from an unrelated platform.
- If no adapter exists, inventory the artifact and authoritative format documentation, then perform only the analysis supported by available evidence. Implement a new adapter only when the user asks to extend this Skill.

### PICO-8 adapter

For `.p8`, `.p8.png`, and `.p8.rom`, read `references/pico8-cartridge-format.md` and `references/pico8-technical-system.md`.

```bash
python3 scripts/pico8_cart.py GAME.p8.png --json
python3 scripts/pico8_cart.py GAME.p8.png --extract-dir unpacked-cart
python3 scripts/analyze_cart.py GAME.p8.png --format markdown --output static-analysis.md
```

Create an auditable case when provenance matters:

```bash
python3 scripts/create_analysis_case.py GAME.p8.png CASE_DIR \
  --title "TITLE" --author "AUTHOR" --source-url "URL" \
  --license "LICENSE" --permission-basis "PERMISSION BASIS"
```

Do not copy the original artifact into a case unless retention is permitted.

### Game Boy Advance adapter

For an authorized raw `.gba` or `.agb` cartridge image, read `references/gba-cartridge-format.md` and `references/gba-from-scratch.md` before inspection.

```bash
python3 scripts/gba_rom.py GAME.gba --json
python3 scripts/gba_rom.py GAME.gba --output gba-manifest.json
python3 scripts/gba_analyze.py GAME.gba --output gba-static-analysis.json
```

Use the result as the first pass of a from-ROM recovery workflow, not as a title-specific source substitute. Do not infer code/data boundaries, compression, assets, save hardware, ARM/Thumb state, or gameplay behavior from header fields or string markers alone. Clearly separate decoded instructions, reconstructed pseudocode, hypotheses, and runtime observations. The adapter intentionally does not copy ROM bytes or extract copyrighted assets.

## Interpret rather than merely index

Treat parser output as discovery evidence, not the final analysis:

- Reconstruct the real entry points, update and render order, timing, input edges, state dispatch, entity lifecycle, collision order, data flow, and persistence.
- Connect code and data regions to runtime meaning: graphics, maps, flags, spawn data, animation, sound, music, UI, scripts, tables, and compressed content.
- Verify dynamic dispatch, generated behavior, indirect calls, bank switching, overlays, self-modifying data, or platform-specific runtime behavior when relevant.
- Mark static call relationships and decompiler output as approximate until confirmed by source flow, runtime tracing, or play observation.
- Report malformed, unsupported, version-dependent, or unresolved behavior instead of guessing.

## Meet the mechanics-dossier success criteria

Read `references/mechanism-extraction.md` for the platform-independent coverage model and report template. Explain, when present:

1. Provenance, platform, revision, permission scope, artifact hashes, and evidence limits.
2. Package/ROM structure, compression, memory or bank layout, entry points, modules, key functions, data tables, and important control/data relationships.
3. Player goals, complete controls, action timing, hidden affordances, and advanced techniques.
4. Global and player states, entities, AI, physics, collision, combat, resources, scoring, win/loss, and persistence.
5. Level organization, content tables, randomization, procedural generation, difficulty growth, unlocks, and replay variation.
6. Core and secondary loops, short/medium/long pacing, risk/reward, failure/retry cadence, and mastery curve.
7. Graphics, animation, camera, audio, UI, hit-stop, shake, particles, and feedback that makes rules legible.
8. Distinctive mechanisms, dependencies, interactions, resulting situations, edge cases, and evidence-backed reasons they are engaging.
9. Author statements versus source or binary observations, regional/version conflicts, uncertainties, and runtime validation needs.

Do not force every game into the same number of mechanics. Expand the systems that carry the actual design complexity.

## Keep evidence types separate

Label important claims as:

- **[事实]** authoritative documentation, creator statements, license text, or reproducible metadata.
- **[源码/二进制观察]** behavior supported by authorized source, disassembly, data, constants, memory, or control flow.
- **[游玩观察]** behavior observed in a specified version, platform, emulator, hardware run, or recording.
- **[设计推断·高/中/低]** an inferred purpose or player effect supported by evidence.
- **[未知]** information the available evidence cannot establish.

Never present inferred intent as a creator statement. Preserve conflicts between manuals, releases, source, binary behavior, ports, and observed play.

## Deliver the analysis

Use `references/workflow-and-output.md` for the output contract and JSON schema. For PICO-8, use `references/pico8-sample-analyses.md` as evidence-label examples, not as a depth limit.

Return the mechanics dossier itself, not a plan to analyze later. Include concrete state names, addresses, function or symbol names, constants, formulas, data layouts, and relationships when they materially explain behavior, without unnecessarily reproducing copyrighted source or assets.
