# Input, analysis coverage and output contract

## Accepted inputs

- An authorized cartridge, ROM-like package, executable, disk image, source tree or extracted game directory.
- A creator repository, official release page, manual, game page or recording with verifiable provenance.
- A game title alone, when the task begins with source and rights discovery rather than artifact acquisition.

Public availability or emulator support does not establish permission to download, unpack, retain or redistribute an artifact.

## Analysis phases

These phases specify coverage, not a rigid reasoning script. Choose an order that respects evidence dependencies.

1. **Provenance and rights**: record platform, release/revision, region, creator, source, permission, date and hashes.
2. **Identification and adapter routing**: verify magic bytes, container variant, size and platform before parsing.
3. **Unpacking and inventory**: preserve the original, extract into a new directory, record offsets/sections and identify code, graphics, maps, audio, text and metadata.
4. **Runtime skeleton**: identify entry points, state dispatch, update/render order, timing, input, persistence and important code/data flow.
5. **Behavior model**: reconstruct actions, states, entities, AI, physics, collision, combat, resources, scoring, win/loss and retry.
6. **Content model**: reconstruct levels, tables, generation, randomization, difficulty, rewards, unlocks and long-term loops.
7. **Experience model**: explain loops, pacing, feedback, readability, mechanism coupling, edge cases and mastery space.
8. **Evidence synthesis**: separate facts, source/binary observations, play observations, design inferences and unknowns; preserve release conflicts.

## PICO-8 tool example

```bash
python3 scripts/pico8_cart.py path/to/game.p8.png --json
python3 scripts/pico8_cart.py path/to/game.p8.png --extract-dir unpacked-cart
python3 scripts/analyze_cart.py path/to/game.p8.png --format markdown --output static-analysis.md
```

The PICO-8 extraction directory contains `code.p8lua`, `gfx.bin`, `map.bin`, `gff.bin`, `music.bin`, `sfx.bin`, an available `trailer.bin`, and `manifest.json`. Text `.p8` inputs preserve their source sections. Existing output directories are not overwritten.

## Output contract

### 1. Provenance and evidence boundary

- Game, creator/publisher, platform, release, region, revision, source, hashes and verification date.
- License or permission scope and prohibited actions.
- Whether evidence came from source, binary inspection, manual, play, recording, emulator or hardware.
- Missing evidence and the conclusions it prevents.

### 2. Artifact and runtime structure

- Container/ROM format, compression, banks or memory regions, executable/code form and extracted resources.
- Entry points, callbacks or loops, modules, symbols/functions, state machinery, data tables and control/data relationships.
- Graphics, maps, text, sound and music layout plus their runtime roles.
- Decompiler, disassembler or static-analysis uncertainty.

### 3. Original-game mechanics dossier

Use `mechanism-extraction.md` to explain:

- player goals, full controls, action grammar, core loop and secondary loops;
- states, entities, AI, movement, physics, collision, combat and resources;
- scoring, win/loss, failure, retry, level structure, generation, difficulty, rewards and unlocks;
- graphics, animation, camera, audio, music and UI feedback;
- distinctive mechanisms, dependencies, typical situations, edge cases and mastery space;
- why the rules work, with evidence, counterfactuals and confidence.

### 4. Conflicts and validation needs

- manual/creator claims that differ from the inspected release;
- regional, revision, port, emulator or hardware differences;
- questions requiring runtime tracing, instrumentation, frame stepping or another artifact;
- design intent that cannot be established from current evidence.

## Recommended JSON structure

```json
{
  "provenance": {
    "title": "",
    "creator": "",
    "platform": "",
    "release": "",
    "region": "",
    "revision": "",
    "source_url": "",
    "hashes": {},
    "license": "",
    "permission_scope": ""
  },
  "artifact": {
    "format": "",
    "version": null,
    "memory_or_banks": {},
    "code": {},
    "assets": {},
    "unpacked_files": []
  },
  "runtime": {
    "entry_points": [],
    "states": [],
    "entities": [],
    "control_and_data_flow": []
  },
  "mechanics": {
    "goals": [],
    "controls": [],
    "action_grammar": [],
    "rules": [],
    "loops": [],
    "progression": {},
    "feedback": [],
    "system_couplings": []
  },
  "evidence": [
    {
      "kind": "fact|source_or_binary_observation|play_observation|design_inference|unknown",
      "claim": "",
      "support": "",
      "confidence": "high|medium|low|null"
    }
  ],
  "conflicts": [],
  "runtime_validation_needed": []
}
```

## Stop and degrade safely

- If provenance is unclear, stop acquisition and use only lawful public evidence.
- If the format is unsupported, preserve the artifact and report identification facts; do not run the PICO-8 parser or guess a layout.
- If static control flow is unreliable, mark candidate relationships and specify runtime validation.
- If releases conflict, show each source, version and plausible explanation rather than choosing one silently.
