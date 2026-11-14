# verification-playbook.md — how to read Mold3D's evidence (numbers first, pictures second)

Core law (ModelRift benchmark): "Every defect that would have ruined a print was found by a number instead: a volume, an angle, an interference test." Renders work for massing, proportion and "the column is in the wrong place"; they fail for **wall thickness, clearance, and whether a boolean quietly deleted half your part.** Claude also cannot read an STL by itself — it "will tell you it can... it's just bullshitting you" (Dave Snider). Never describe a binary STL from memory; only from `verify.json` and the rendered PNGs.

## Per-iteration reading order (cost-aware: Pro plan)
1. `forge/bin/forge run ...` finishes. Read **`mold3d/<name>/REPORT.md` and `verify.json` first** (small, numeric).
2. Read **`mold3d/<name>/sheet.png` ONCE** (the contact sheet of all views). Do not open individual `views/*.png` unless the sheet leaves one question open (then open exactly that one).
3. Write the critique in <= 8 lines using the checklist below. Decide ONE change. Edit. Re-run.
Never judge from a single view (Snider: "Just because there's a box there, it doesn't mean it's visible"; ModelRift/cad-skill use 6 views).

## verify.json — each field, what a bad value means, the standard fix
| Field | Expect | If wrong -> meaning -> fix |
|---|---|---|
| bbox (x,y,z) | spec `bbox_mm` +/- `bbox_tol` | Off by a factor of 10/25.4/1000 = **units bug**. Off by a few mm = parameter not wired, or a cutter/boss pushed outside. Off in one axis only = **axis confusion** (rotate/`center`). Fix the parameter derivation; re-run. |
| bbox min Z | 0 | Part floating above or sunk below bed: re-seat on Z=0 (`Align.MIN` / translate by -min.z). |
| volume_mm3 | within spec range | **Much lower than expected = a union/cut silently dropped something** (the silent boolean). Much higher = a cutter was added instead of subtracted, or a duplicate body. Compare to the previous iteration's volume: each feature should move it by its expected amount (cutter volume, text volume ~ 20 mm3). |
| mass_g | volume x 1.24 g/cm3 x infill factor | Sanity only (PLA ~1.24 g/cm3). Slicer infill adds. |
| watertight | true | False = open shell/holes/non-manifold: voxel remesh (organic), weld + normals (bpy), or rebuild the offending boolean with EPS overlap. A part that is not watertight is NEVER sent to slice. |
| components | spec `components` (usually 1) | 2+ = **floating part** (text over a pocket gave 3 solids), a cutter that sliced the body in two, or intentionally separate parts. Print layouts of assemblies expect N. Print the bbox of each component to find the stray one. |
| fits bed | true (<= 220x220x250) | Scale, split, rotate to the diagonal, or say "Snapmaker". |
| bed contact (area/patch) | large flat patch | Tiny patch on a big part = will detach/fail (a helmet print died on this). Re-orient or add a base/brim-friendly flat face. |
| support % / overhang | <= spec `max_support_pct` | High = reorient so the largest face is on the bed; chamfer bottom edges; split overhangs; accept auto-support only if unavoidable. |
| min_wall_mm | >= spec (>= 1.2 hard floor, 2.0+ target) | Below spec = thicken the offending feature; locate it with a `--section z=` render at the height reported. Thin walls fail or look fragile; treat < 2.0 as a warning. |
| interference (assembly) | ~0 mm3, gap >= clearance | Overlap volume > 0 = parts collide: increase the clearance parameter or move the feature. Gap < spec = too tight. Gap >> spec = loose; check against fit-log. |

Gate rule: any of watertight, bed fit, components, bbox, min_wall failing = **not print-ready**, full stop; fix and re-run. Never say "READY" from a render alone. (The old linter said READY on a part with a deleted foot; only eyeballing caught it — audit REPORT.)

## Spotting the silent boolean delete (3 independent ways; use at least 2)
1. **Volume delta per step** (in the part script): `assert after.volume < before.volume - X` for cuts, `> ` for adds. Templates do it.
2. **Component/solids count** after every union (`len(p.solids())`).
3. **Section render**: `forge/bin/render <stl> <outdir> --section z=<mm>` at a height through the feature; the cut should show as a hole/pocket in the section. A missing feature = the boolean was dropped even if `verify` passed other checks (contingencies rails A-C; HN 47183039).
Also known: Manifold can certify a mesh with 4 non-manifold edges as NoError (ModelRift), so STL-level `verify` is mandatory even when the CAD kernel said "valid".

## Reading sheet.png (checklist; answer each with yes/no/unsure)
1. Does the silhouette match the intent in at least iso + front + side? (same object, right proportions)
2. Orientation: is the intended bed face down? Which way is up (compare iso vs iso_back; read the axis gizmo)?
3. Every feature in spec.md section 5 visible, in the right place, on the right face?
4. Anything floating, disconnected, or intersecting wrongly?
5. Cavities/pockets: only the SECTION view proves them (flat renders of cavities lie; the CPU rasterizer faked a dome on flat caps). Cutaway-aware reading: look for the section contour, not the shading.
6. Thin-looking walls or tall skinny features (compare against the rulers/grid; do not eyeball).
7. Rulers/annotations: do the annotated dimensions equal the spec numbers?
8. Text legible and raised/engraved the right way?
If a view is ambiguous, add a section or a debug marker (a coloured sphere/cube at a known coordinate) rather than guessing (Snider).
Oblique views, not flat top-down, are the default because Workbench top-down is flat (audit gotcha #4).

## Reference comparison
If the user gave a photo/reference: `bin/render <stl> <outdir> --ref ref.png` and compare silhouette and proportions only. "Fully autonomous generation is not the right workflow... yet; for spatial geometry the human-in-the-loop step matters" (Pantheon benchmark, ModelRift): show the user the sheet.png at milestones.

## Iteration discipline
- One change per iteration; keep every `iter_NN/` (never overwrite) so you can revert.
- Cap: 6 iterations per phase (skeleton / features / finish). On the 7th, STOP, state what keeps failing, re-plan or fall back (SKILL.md "boundaries"). ModelRift capped at 12 versions overall.
- Never repeat the same fix twice. If two iterations show the same failure, the diagnosis is wrong: print the numbers (bboxes of each sub-part), don't re-render.
- Each iteration's log line in REPORT.md: `iter N: changed X -> volume a->b, bbox ..., verdict`.
