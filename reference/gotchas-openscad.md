# gotchas-openscad.md — OpenSCAD (2026.06.12 snapshot, Manifold) + BOSL2

Binary: `openscad` on PATH (or `OPENSCAD=...`). On Apple Silicon some Homebrew builds abort inside agent sandboxes ("Incompatible processor ... neon"): run outside the sandbox. BOSL2: install into your OpenSCAD libraries folder (`include <BOSL2/std.scad>`).
Command: `openscad --backend=Manifold -o out.stl part.scad` (Manifold = fast; the `forge run` wrapper does this).

## When SCAD is the right lane
Trivial blocks/plates/holes, 1-3 features, or when a BOSL2 primitive does the whole job (gears, threads, screws). Beyond that choose build123d: SCAD "complexity balloons" for functional parts (dofm, HN 49676577) and it cannot query its own volume (ModelRift). Counter-view (roel_v/Mashimo): variables in SCAD are enough for printed parts. Our rule: SCAD only if it fits in ~60 lines.

## Silent failures (the SCAD-specific killers)
- OpenSCAD gave "no errors and no warnings across roughly 45 invocations while producing deleted posts, misplaced slots, and a corrupted export" (ModelRift). **Always run `forge/bin/verify` with a spec: volume + bbox + components.** SCAD cannot assert.
- Manifold can certify a part with non-manifold edges as NoError (ModelRift). The exported STL needs its own audit (verify does it).
- Echo the numbers you care about: `echo(vol_note="inner", w=IN_W);` and read them from stderr.

## Coordinate / orientation traps (contingencies, HN 47183039: "forgetting axis orientations after multiple layers of rotate(), center=true presence ignored")
- `cube([x,y,z])` starts at the origin corner; `cube(..., center=true)` centres on ALL axes. `cylinder()` starts at z=0 going up; `center=true` centres on z. Prefer BOSL2 `cuboid([x,y,z], anchor=BOTTOM)` / `cyl(d=, h=, anchor=BOTTOM)`: the anchor is explicit.
- Avoid nested `rotate()`. Rotate once, or use BOSL2 `orient=`/`xrot()/yrot()/zrot()`. Check after rotation: bbox via the verify tool.
- Transform order reads bottom-up: `translate(a) rotate(b) cube()` rotates first, then moves.

## Epsilon / z-fighting
- Cutters must overshoot every face they pierce by `EPS = 0.01`..0.1: `translate([0,0,-EPS]) cylinder(h=H+2*EPS, ...)`. Coplanar faces leave zero-thickness skins or a film (gerdesj, HN 45140921: "failed to allow for closing the geometry properly ie adding a tiny epsilon").
- For unions, overlap the pieces by >= 0.01 so they fuse instead of touching on a shared face ("shared faces causing rendering issues", contingencies).

## Resolution
Set `$fn` globally (`$fn = 64;`) or `$fa=2; $fs=0.4;`. Default is coarse, so rounded edges look blocky (KrFttd5D1cw). Holes meant for screws: even `$fn` multiples of 4 so the flats align.

## Debug modifiers (YouTube KrFttd5D1cw)
`#obj` highlights (transparent red) — use on cutters in `difference()` to see where they landed. `!obj` renders ONLY that object. `%obj` ghosts it. `*obj` disables it. Remove before the final run (they don't export but they hide mistakes in previews).

## BOSL2 traps (verified in this install)
- `cuboid()` asserts **"Cannot specify nonzero value for both chamfer and rounding"** (hit while writing the template). For a rounded body with a chamfered bottom: `hull()` a `linear_extrude` of `rect(..., rounding=r)` on top of a slightly smaller rect at z=0 (see templates/part_scad.scad).
- `cuboid(rounding=r, edges="Z")` rounds vertical edges only. Edge specifiers: `"Z"`, `TOP`, `BOTTOM`, `[TOP,"Z"]`, `except=`.
- Library names are easy to hallucinate (gerdesj HN 45140921 "hallucinated functions (BOSL)"). If unsure, grep: `grep -rn "module cuboid\|function cuboid" <your OpenSCAD libraries>/BOSL2/`.
- Threads: `include <BOSL2/threading.scad>`; make a 5-minute thread coupon before trusting one (rasterizer cannot see thread detail).

## Fillets and chamfers
CSG has no real fillet. Use BOSL2 rounding args, `offset_sweep`, or `minkowski()` (slow). If you need many fillets on a functional part, switch to build123d (gotchas-b123d.md).

## Live loop (optional)
OpenSCAD auto-reloads when the .scad changes (fortran77, HN 47475417), but headless forge runs don't need the GUI.
