# Mold3D vs humans — 3D modeling benchmark, 2026-10-17
Author's own run (n=1 per item, one model: Claude). Treat as a worked case study, not a rigorous study. Ground-truth STEP files (from step.parts) and community champion (Printables) models are not redistributed here; re-fetch them with `forge parts-find` / the model site.
Files: `bench/` (the blind attempt scripts; gt/ and scores/ not included). Re-run after any skill change.

## Round A — accuracy: standard parts, blind, vs the real STEP (step.parts), `forge grade` (voxel IoU, pose-free)
| part | IoU | mean err | miss |
|---|---|---|---|
| 608ZZ bearing | 0.971 | 0.13 mm | — |
| ISO 4762 M5x16 | 0.959 | 0.11 mm | — |
| ISO 4032 M8 nut | 0.817 | 0.26 mm | height 6.8 vs 6.5, bore |
| 2020 B-slot6 | 0.765 | 0.46 mm | slot internals guessed |
| NEMA17 L40 | 0.770 | 1.98 mm | shaft way too long |
| GT2 20T pulley | 0.407 | 1.24 mm | invented a hub |
=> fully specified = human level. Recalled/guessed details = misses. Fix: `forge parts-find` / datasheet, never memory.

## Round B — things that move, vs the community champion (Printables) (same checks: `forge movecheck` + motion sweep)
| item | human (likes/makes) | human gaps | Skill gaps | Skill motion | looks |
|---|---|---|---|---|---|
| balisong | #846554 4.6k/275 | 0.25 mm, fuse 0 | 0.29 mm, fuse 0 | sweep 0-180 CLEAR, 1st build | human wins (v1 flat stick; v2 after ref pass closer, still behind) |
| planetary spinner | #898004 48/4, 3.0 stars | 0.04 mm, fuse-risk 225 mm2 | 0.36 mm, fuse 0 | tooth-pitch sweep CLEAR | ~tie |
| spiral fidget | #927393 6.5k/524 | (2-piece) | 0.4 mm | helix passthrough CLEAR + control jams | wrong toy: built passthrough, theirs = finned cone through slotted cone |
| superhero helmet | popular community helmet | — | 3 pcs, 0.6 split, magnets | n/a | human by a mile (mine = egg) |

## What humans have that the skill did not
1. They LOOK at the object first (proportions, signature features). -> added Phase 1b REFERENCE PASS (`forge refs`).
2. Sculpting skill for organic forms. -> not fixable with code-CAD; route = find + remix.
3. Real prints behind popular models (hundreds of makes). -> the edge must be verification: sweep + control + gap check before plastic.
## What the skill has that they don't
Exact numbers, motion verified before printing, zero-fuse gaps by construction, instant parametric resize to your body/objects, minutes not hours.

## Upgrades shipped (skill v1.2.0)
`lib/motion.py` (sweep + negative control), `lib/gears.py` (involute/herringbone/planetary), `lib/movecheck.py`, `lib/grade.py`,
CLI `forge movecheck|grade|refs`, SKILL.md: evidence-based routing, mandatory reference pass, moving-parts step 5b, side-by-side 5c.
Proof: balisong v2 widened bars -> sweep caught the handle crash at 180 deg -> pivot rule fixed it before any plastic.
## Still unproven (needs real prints)
Gaps 0.29-0.36 never printed (neither mechanism gaps nor the Fit Card); human champions use 0.25. Print the Fit Card + the planetary before trusting any gap.

## Mold3D 2.0 results (same day, evening)
- Gridfinity from memory of the spec 0.74 IoU -> after measuring a community Gridfinity 1x1x6 bin: **0.93** (lesson repeated: measure, don't recall).
- Looks Score (CLIP on clean renders) ranked every pair like a human: balisong human 60% > v2 42% > v1 28%; planetary 98% vs 99%;
  real helmet 13.5% vs egg 0.9%. Annotated CAD views gave nonsense (14% for the human balisong) -> always clean renders.
- Text->3D (local LCM-Dreamshaper + Hunyuan3D-2mini + figure_post): axolotl, baby dragon, ghost mascot, shark, ~3.5 min each, all GO+SUPPORTS.
- Flexify: SDF gecko 7 joints, all +-22 deg clear, pins capture, 0.30 gaps, 33 min / 7.4 g. Relief lizards from text concepts pass too but look chunky.
- Photofit synthetic test: 72 x 24 mm object through tilt + shadow + uneven light + noise: -0.12 / -0.25 mm.
- Still unproven until real plastic: every gap. The Fit Card (58 min, 16 g) is the first print.
