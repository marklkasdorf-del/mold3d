---
name: mold3d
version: 2.2.0
user-invocable: true
description: Idea-to-printable-3D-model studio for FDM printers. Use when asked to "model / design / make me a <thing> to print", "3D model this", "CAD this", "custom mount/case/holder/adapter/lid/bracket", "fidget", "print-in-place", "something that moves", "flexi <animal>", "figure / statue / mascot of <x>", "text to 3D", "gridfinity", "insert for my <thing>", "split this for my bed", "will this print", "calibrate my printer", "see it in AR", "put my name on", "add a keychain loop", "add magnets", "fix thin walls", "scale to my head", "make me a box", "keychains", "sign", "phone stand", "lithophane", "mold 3d", "/mold3d", or "forge". Code-CAD (build123d/OpenSCAD/bpy) + MechKit verified mechanisms + local text-to-3D + flexify + preflight failure prediction; hands a verified STL to your slicer.
triggers: [mold 3d, /mold3d, forge, model this for 3d printing, design a part to print, make me a custom, 3d model this, cad this, idea to print, print in place, fidget, flexi, text to 3d, gridfinity, will this print, check an stl]
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch]
---

# Mold3D: idea -> verified, printable part

The ask: whatever the user typed after /mold3d. `FORGE` = this skill's directory (e.g. `~/.claude/skills/mold3d`). One CLI: `$FORGE/bin/forge <cmd>`; `forge --help` lists every command. Paths you give forge are relative to the current folder. **Designs are written to `./mold3d/<name>/`** in the folder you run from (`$MOLD3D_OUT` overrides). Details: `reference/toolbox.md` (commands, file map), `reference/mech-rules.md`, `reference/gotchas-forge.md`, `reference/questions.md`.

Envs: `$FORGE/.venv-cad` (`FORGE_CAD_PY`); optional `$FORGE/.venv-ai` (`FORGE_AI_PY`) for `text3d`/`looks`. Printer: `knowledge/printer.json`. Forge ends at a verified STL/3MF plus a verdict; slicing is the user's slicer. Specified parts hit 0.96 IoU, guessed ones 0.41: look numbers up, never recall them.

## Rules that never bend
1. **Numbers first, pictures second.** No claim about geometry unless it comes from a tool's output (verify/selftest/preflight/grade JSON) or a render you read this iteration. Never describe an STL from memory.
2. **No silent guesses.** Custom parts get `spec.md` + `spec.json` with numeric success criteria first. A missing fit number is looked up, asked (see Questionnaire), or marked ASSUMED.
3. **One change per iteration**, keep every `iter_NN/`, max 6 per phase, then re-plan.
4. **Anything that moves ships with a passing self-test** (sweep clear + must-jam control + measured gaps).
5. **Every print gets `forge preflight` before the slice; its verdict decides supports.** NO-GO = fix geometry/orientation first. Print-in-place / multi-body parts also get `forge export <stl>`: hand over the 3MF, not the STL (a slicer's auto supports fill the gaps and weld the parts; an STL can't carry "supports off").
6. **Sandboxes:** Blender, OpenSCAD and GPU torch can crash inside agent sandboxes that hide the GPU (Blender exits 139). If a step segfaults, run it outside the sandbox. Pure python (build123d, manifold3d, trimesh) runs anywhere.
7. **Report milestones in one line each** (route, first render, blocker) and say what the user must decide. Send key images and AR files when the channel supports files.
8. Never start a print or spend money without the user's explicit OK. Respect downloaded-model licenses (CC BY-NC = no selling).
9. Say "verified in geometry", never "perfect"; "verified on plastic" only after a real print.
10. One sheet read per iteration, deterministic tools over re-asking, no subagent fan-outs for CAD.

## First use
No `$FORGE/.venv-cad`? Run `bash $FORGE/install.sh` first. Run `forge doctor` only on first use or after an error (it is cached for 24 h; `--fresh` re-checks). Then once: `cat $FORGE/knowledge/{lessons.md,printer.json}; forge fit show`. If `pip_gap` is still `[R]` (research default), mention once that the Fit Card (`forge mech build fitcard`, ~1 h, ~16 g) calibrates every moving part.

## Route (first match wins; tell the user the route in one line)
| The ask | Route | Tools |
|---|---|---|
| change a DOWNLOAD (text, keychain loop, magnets, thicker walls, scale to a head, flat bottom, mirror) | REMIX | `forge remix <stl> text|keychain|magnets|thicken|fit-head|flat|mirror|scale` |
| practical thing from the user's numbers (box, keychain, sign, stand, holder, lithophane) | MAKE | `forge make box|keychain|sign|stand|holder|lithophane` |
| many copies in one print | PLATE | `forge plate <stl...> --fill` |
| a famous existing thing (prop, toy, popular device case) | FIND on a model site, then REMIX | web search, `forge split` |
| original wearable helmet | TEXT3D --helmet | `forge text3d "<style> helmet" --helmet` |
| something that moves (fidget, hinge, gears, gyro, clicker) | MECHKIT, else the Mech API | `forge mech list/build` |
| a flexi animal | SDF body or sculpt, then FLEXIFY | `forge sculpt`, `forge flexify` |
| figure / mascot / creature | TEXT3D (~3.5 min) or find | `forge text3d "<idea>"` |
| custom-fit functional part (mount, holder, adapter, case) | MODEL (phases below) | `forge run`, `forge parts-find` |
| drawer insert / exact pocket | GRIDFINITY + PHOTOFIT | `forge gridfinity`, `forge photofit` |
| too big for the bed | SPLIT | `forge split` |
| "will this print / why did it fail" | PREFLIGHT | `forge preflight`, `forge heat` |
| show off / sell | SHOWCASE + AR | `forge showcase`, `forge ar` |

## Fast lane vs custom lane
**Fast lane** (REMIX, MAKE, MECHKIT, GRIDFINITY, PLATE, SPLIT): build now with stated defaults, finish with the Print Report, then ask "want it different?". Missing fit numbers: draft with defaults first, then ask (see Questionnaire).
**Custom lane** (MODEL): follow phases 1-5.

## Questionnaire (vague requests)
**Draft first, then ask:** for a vague request, build a quick rough draft with sensible defaults and show it (first render + one line on what you assumed), THEN ask. If the request lacks a number the part depends on (what it attaches to, size, screw size, device model): look it up first (`parts-find`, `knowledge/devices.json`, datasheet, `photofit`). What is still missing: ask 1-3 multiple-choice questions, each with smart defaults ("M3", "standard <device> size (I'll look it up)", "I'll measure it"; the user can type Other). In Claude Code use the AskUserQuestion tool; in Codex or when it is unavailable, send a short numbered list with defaults marked. Ask only about numbers that change whether it FITS or WORKS, never color, fillets or other safe defaults. If the user says "just make it", proceed with defaults, list them under `"assumed"` in `spec.json`, and the Print Report shows an Assumed row. Format and examples: `reference/questions.md`.

## Phase 1: BRIEF (custom parts)
1. Collect what the user already told you (device model, measurements, photos).
2. **Reference pass** for anything with a name: look at 6-9 reference images or top designs; write "## Form" in spec.md (proportions, 2-3 signature features, variant).
3. Dimensions: look up, never recall: `forge parts-find "<part>" [--download]` + `forge step2stl`, datasheets, web search. Cite sources in spec.md. An owned object that can't be looked up: `forge photofit mat`, print at 100%, photo, outline within ~0.3 mm.
4. Questionnaire for what is left. Write `mold3d/<name>/spec.md` + `spec.json` (templates/); mark estimates on fit interfaces `estimate` or `assumed`.

## Phase 2: LANE + PLAN
b123d (default: functional, dimensioned, fit-critical; `templates/part_b123d.py`), scad (trivial or BOSL2), sdf (`lib/sculpt.py`, organic), mesh (`lib/meshkit.py`: edit downloads, big booleans, flexify, split), bpy (renders, text art). Plan in comments at the top of the part file: features as functions, a parameter block in mm, clearances from `fit.get("pip_gap"/"slide_gap"/"hole_comp"...)` (never hard-code 0.3 or hole sizes), origin bottom-centre on Z=0, print orientation designed in (largest flat face down, overhangs <= 45 deg, bridges < 18 mm, walls >= 2.0).

## Phase 3: BUILD IN SMALL STEPS
One change, then `forge run part.py --lane <lane> --spec spec.json --name <name>`, read verify.json/REPORT.md (did volume/bbox change as expected? no change = dropped boolean), read sheet.png once, critique, next change. Moving parts use the Mech API (`reference/mech-rules.md`). Run `forge preflight` in the loop for anything with overhangs.
- **Looks Score** (only if `forge doctor` shows the AI env): for named objects, `forge looks <stl> --target "<thing>"` on clean renders; < 30% means iterate FORM, not mechanics.
- Never judge from one view. Overlap cutters 0.05 mm (coplanar faces weld pins). Export with angular_tolerance 0.05. Check must-jam controls along the whole path. Cap 6 iterations, then re-plan or route to FIND.
- Finish when verify passes every spec key, selftest passes (movers), preflight is GO/GO+SUPPORTS, and the visual checklist is yes.

## Phase 4: FIT
Print-in-place gaps come from `fit.json`; calibration steps in `reference/mech-rules.md`. For mating parts or parts around the user's object, run an assembled-pose check with a dummy of the object. Threads, snap-fits and press-fits get a coupon first.

## Phase 5: PRINT PREP + HAND-OFF
1. `forge preflight <stl> [--orient]` gives the verdict and supports decision; `forge heat <stl>` shows it.
2. **Supports = preflight's call:** GO -> off; GO+SUPPORTS -> on/auto; NO-GO -> fix first (knife-edge contact, fused gaps, doesn't fit -> `forge split`). "SUPPORTS: OFF (required)" = auto-support trap: supports must stay OFF or they weld the gap. If NO-GO because it needs supports AND supports would weld, fix the geometry (chamfer flat undersides to 45 deg, re-orient) before exporting.
3. **Print-in-place / multi-body: `forge preflight <stl>` then `forge export <stl>`** (name ends `_SUPPORTS-OFF.3mf` or `_SUPPORTS-ON.3mf`). Tell the user: open this file, check the Support box matches the filename, change nothing else. Single-body parts can go as the STL.
4. Slice in the user's slicer with that supports decision. Optional `slicer_cmd` in `knowledge/printer.json` adds time and grams to the report.
5. Never start a print without the user's OK ("Bed clear? Starting <name>, ~<time>, <g> g.").

## Finish every design with the Print Report
Last step of every finished design: `$FORGE/bin/forge report mold3d/<name>` (or a plain `<file>.stl`). It collects the print-ready 3MF (supports decision baked in), `preview.png` (if a render exists or Blender is installed) and `report.json`, and prints the table below filled from tool output. Show it verbatim in chat with one sentence above it and nothing else; if you re-fill it from `report.json`, keep this shape, drop rows whose data is absent, and invent nothing:

```
**MOLD3D PRINT REPORT** · <name> · <W x D x H mm> · <printer>
| | |
|---|---|
| Verdict | ✅ GO / ⚠️ GO + supports / ❌ NO-GO — supports ON/OFF |
| Moving parts | <n>, all clear through full motion |
| Gaps | <mm> (calibrated on your printer / default — print the Fit Card) |
| Assumed | <numbers nobody confirmed> (only when `assumed` is set) |
| Print | ~<time> · <grams> g |
| Watch for | <top 1-2 issues in plain English> |
| Files | `<path>.3mf` (print this) |
```
- Issues are plain English ("first-layer gap under 0.35" becomes "tight gap near the bed may fuse"); never paste preflight jargon or numbers you did not get from the report.
- No `Print` row unless a slicer hook is set (grams are never estimated from volume). No `Moving parts` / `Gaps` rows for static parts.
- NO-GO: no 3MF is written; fix the geometry and re-run `forge report`. Send `preview.png` when the channel supports files. If the notes say previews are off, there is no Blender: say so in one line, everything else still works.
- The 3MF filename keeps the `_SUPPORTS-OFF` / `_SUPPORTS-ON` suffix: tell the user to open that file and check the Support box matches.
- Done = the file path, this report, a picture, and one line on what was assumed.

## Phase 6: FEEDBACK
After a print ask "What was off? (fit / looks / strength / print quality / nothing)". Gaps -> `forge fit set ...` + `knowledge/fit-log.md`; lessons -> `knowledge/lessons.md`. Skill or tool changes -> `tests/run_suite.sh`.

## STOP-AND-CHECK (before each render and before "done")
- [ ] axis/centre/units (bbox vs spec, mm) - [ ] every boolean has a volume delta - [ ] no floating parts (components == spec)
- [ ] walls >= 2.0 - [ ] movers: selftest PASS, controls jam, gaps ~= fit.pip_gap - [ ] preflight GO/GO+SUPPORTS
- [ ] named object: reference pass done, Looks >= 30% (if AI env) - [ ] fit numbers sourced or listed as ASSUMED - [ ] claimed with numbers

## Boundaries
Reliable: functional parts with real numbers, print-in-place mechanisms, looked-up standard parts, Gridfinity, photo-fit pockets, flexify. Soft: text->3D detail. Unreliable: hand-modeled organic/iconic forms, threads, linkages with > 5 moving parts.
Switch route when: 6 iterations without passing; same failure twice after a re-plan; no dimensions obtainable (photofit or coupon first).
