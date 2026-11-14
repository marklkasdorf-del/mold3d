# Fit table: real print-in-place gaps, by printer and material

Only real prints go here. A render never does. Every row has a source you can open.

**How to read it.** The gap is the designed clearance per side between two bodies printed in place.
*free* = moved by hand straight off the bed, *stiff* = moved with effort, *fused* = did not move.
The adopted value is the smallest gap that came free. Rotating joints on vertical pins (spinners) and
hinges on horizontal pins (which sag) are different numbers; Mold3D keeps them apart as `pip_gap` and `pip_vgap`.

## Measured gaps

| printer | material | joint | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 | 0.35 | 0.50 | adopted | source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Anycubic Kobra X | PLA | spinner, vertical pin | | fused | free | free | free | free | | **0.20** (`pip_gap`) | Mold3D Fit Card, 2026-11-13, supports off [1] |
| Anycubic Kobra X | PLA | hinge, horizontal pin | | | | fused | | folds | folds | **0.35** (`pip_vgap`) | Mold3D Fit Card, 2026-11-13, supports off [1] |
| Bambu Lab X1C | not stated | rotating pin | fused | fused | stiff | free | loose | loose | loose | **0.25** (0.20 still turns) | Fab Academy 2025, Singapore group test [2] |
| Prusa MK4 | not stated | rotating pin | fused | fused | fused | free | loose | loose | loose | **0.25** | Fab Academy 2025, Singapore group test [2] |
| Bambu Lab X1C | PLA-HD | rotating pin | fused | | stiff | | free | | | **0.30** (0.20 stiff) | Fab Academy 2026, León student test [3] |

General guidance without a named printer: "leaving a 0.2 mm to 0.3 mm gap between the pin and the barrel is the sweet spot";
0.2 mm on a well-calibrated FDM printer "will give you a tight, smooth hinge with no wobble" [4].

## What the table says so far
- Nothing has come free below 0.20 mm on any printer in this table. Mold3D's preflight NO-GO for gaps under 0.8 x `pip_gap` matches that.
- 0.20 is the edge: free on a Kobra X, stiff on an X1C, fused on an MK4. 0.25 to 0.30 worked everywhere.
- Hinges on horizontal pins need more than spinners (0.35 vs 0.20 on the same printer, same day): the pin's underside sags into the gap.
- The shipped default (`pip_gap` 0.30, `pip_vgap` 0.30) is therefore safe but loose on a Kobra X; print the Fit Card and `forge fit set` to tighten it.

## Add your printer
1. `forge mech build fitcard` (about an hour, ~16 g), print it with supports OFF.
2. Twist each spinner and fold each hinge. Note the smallest gap that moves freely.
3. `forge fit set pip_gap <mm> --from "Fit Card <date> <printer> <material>"` and the same for `pip_vgap`.
4. Add a row above (printer, material, what you saw at each gap, the date). A photo in the pull request is welcome.
Two prints that disagree both stay in the table; the newer one wins until a third settles it.

## Sources
1. Mold3D Fit Card print on an Anycubic Kobra X, 2026-11-13 (the repo's README, "What is not proven yet"): spinners at 0.20 mm and wider broke free, 0.15 mm fused; hinges at 0.35 mm and wider folded, 0.25 mm fused.
2. Fab Academy 2025, Singapore lab, group assignment week 5 (clearance test on a Bambu Lab X1C and an Original Prusa MK4; gaps 0.5 to 0.1 mm): https://fabacademy.org/2025/labs/singapore/group.assignments/wk05_group.html . Quoted: "The optimal clearance was 0.25mm"; "we need to leave at least 0.2mm clearance in order to have joints that do not fuse together"; X1C at 0.2 mm "Ok but stiffer than 0.25", MK4 at 0.2 mm "Completely fused".
3. Fab Academy 2026, León lab, student machine notes for the Bambu Lab X1 Carbon (PLA-HD, 0.4 mm nozzle): https://fabacademy.org/2026/labs/leon/students/beni-alvarez/machines/bambu_x1.html . Quoted: "The 0.3 mm clearance moves freely"; "the 0.2 mm clearance had some difficulty and moves, although somewhat stiffly"; "The 0.1 mm clearance does not move".
4. Snapmaker blog, "3D printed hinges": https://blog.snapmaker.com/blog/3d-printed-hinges/ (no printer or material named).
