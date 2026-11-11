# gotchas-b123d.md — build123d 0.11.0 (Python 3.12) idioms and traps

Interpreter: the CAD venv python (`.venv-cad/bin/python`) (3.12, build123d 0.11.0 + OCP + trimesh). Never `pip install cadquery` there: it fights over OCP versions.
Every snippet below was RUN in that venv on 2026-10-14 (results in comments). Re-verify after any build123d upgrade.
Why b123d: real solids (B-rep) can report their own volume/validity, unlike SCAD (ModelRift; HN 47183039 nszceta).

## 0. Skeleton every part uses
```python
from build123d import *
import os
p = Box(60, 40, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))   # bottom on Z=0, centred XY
export_stl(p, os.environ.get("FORGE_OUT_STL", "part.stl"), tolerance=0.01, angular_tolerance=0.1)
export_step(p, "part.step")      # STEP = exact B-rep; keep it for later edits
```
`export_stl` keyword names are `tolerance` and `angular_tolerance` (verified). Use 0.01 / 0.1 (cad-skill).

## 1. Two modes: pick ONE per file
- **Algebra mode** (`a + b`, `a - b`, `a & b`, `Pos(x,y,z) * shape`): preferred. Expressions return new shapes, easy to assert volumes between steps.
- **Builder mode** (`with BuildPart() as p: ...`, result in `p.part`): fine for sketch->extrude. Inside a builder, `mode=Mode.SUBTRACT` cuts, `Mode.ADD` fuses, `Mode.PRIVATE` makes without adding.
```python
with BuildPart() as p:
    Box(30, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
print(p.part.volume)     # 8214.60 = 9000 - pi*25*10 ... verified
```
Do not mix: a shape created inside a builder is auto-added; the same call in algebra mode just returns a shape.

## 2. Alignment and origin (the #1 source of misplaced geometry)
- **Primitives are CENTRED on the origin by default** (`Box(10,10,10)` spans -5..5 on all axes; `Cylinder(5,20)` axis = Z, spans z -10..10). Verified.
- Bottom on the bed: `align=(Align.CENTER, Align.CENTER, Align.MIN)` — then `bbox.min.Z == 0`.
- `Pos(x,y,z) * shape` translates. `Rot(rx,ry,rz) * shape` rotates (degrees, about the ORIGIN; build123d applies the three angles as one combined rotation: when in doubt, rotate one axis at a time and check the bbox). **Order matters:** `Pos(10,0,0) * Rot(0,0,90) * Box(10,2,2)` rotates first (about origin), then moves; verified bbox X 9..11, Y -5..5.
- `Cylinder(r, h, rotation=(90,0,0))` lies along Y (bbox 6 x 20 x 6 verified).
- Rotating about the origin of a bottom-aligned part swings it below Z=0. Re-seat after: `p = Pos(0,0,-p.bounding_box().min.Z) * p`.
- `Plane.XZ` has normal **-Y**, `Plane.YZ` normal +X, `Plane.XY` normal +Z (verified: z_dir (0,-1,0), (1,0,0), (0,0,1)). A sketch on `Plane.XZ` extruded +amount goes toward -Y.
- Sketch on a face: `with BuildSketch(p.faces().sort_by(Axis.Z)[-1]):` = top face. Extrude `amount=-5` goes INTO the part (use with `mode=Mode.SUBTRACT`).

## 3. Selecting edges/faces (never by hard-coded index)
```python
b = Box(20, 20, 20)
b.edges().filter_by(Axis.Z)                         # edges parallel to Z (vertical)      -> 4
b.edges().filter_by(Axis.X)                         # 4
b.edges().filter_by_position(Axis.Z, -0.01, 0.01)   # edges lying at z ~ 0 (bottom ring)   -> 4 on Z-MIN-aligned box
b.faces().sort_by(Axis.Z)[-1]                       # top face;  [0] = bottom
b.faces().filter_by(GeomType.PLANE)                 # planar faces -> 6
b.faces().group_by(Axis.Z)                          # groups by height (3 groups on a box: bottom/sides/top)
```
`filter_by_position` uses the part's current coordinates: select AFTER you've positioned the part.

## 4. Fillet / chamfer ordering (CadQuery/b123d fillet failures name no edge — flowful cad-skill)
1. Build the plain body. 2. **Fillet/chamfer BEFORE cutting cavities/holes** (fewer, simpler edges). 3. Largest radius first. 4. Bottom chamfer, vertical fillets.
```python
b = Box(60, 40, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
b = chamfer(b.edges().filter_by_position(Axis.Z, -0.1, 0.1), 1.0)   # bed-side ring: chamfer, not fillet
b = fillet(b.edges().filter_by(Axis.Z), 3)                          # vertical edges
```
- Too-big radius raises `ValueError: Failed creating a fillet with radius of 6, try a smaller value or use max_fillet()` (verified). Ask first: `shape.max_fillet(shape.edges())` (a Shape method, NOT a global; returned 4.94 on a 10 mm box).
- **Do not wrap fillets in try/except to quietly shrink the radius** (cad-skill). Fix the geometry or pick edges deliberately.
- Chamfer takes one length or two (asymmetric). Sanity: chamfer 2 on the 4 bottom edges of a 20x20x10 box removed 149.3 mm3 (4000 -> 3850.7, verified).

## 5. Hollowing: subtract, don't shell (cad-skill: shell "is fragile")
```python
outer = Box(20, 20, 20)
inner = Pos(0, 0, 2) * Box(16, 16, 20)          # open top: cavity runs past the top
hollow = outer - inner                           # volume 3392 (verified) = 8000 - 16*16*18
```
`offset(shape, amount=-2, openings=face)` also works (3392 verified) **but `openings` must be a face of THE SAME object instance.** Passing a face of a fresh `Box(...)` silently returned the solid inner box (volume 4096) — no error. That is a silent-no-op trap; prefer subtraction.

## 6. Booleans: assert the volume delta every time
```python
v0 = body.volume;  body = body - cutter
assert body.volume < v0 - 1.0, "cut did nothing"       # far-away cutter changes nothing: (Box - Pos(100,0,0)*Box) kept 8000 (verified)
```
- Overlap cutters past the surface by 0.01-0.1 mm (EPS) so no coplanar skin remains.
- `a & b` = intersection; `(box & lid).volume` is the interference number (500.0 for two 10 mm cubes offset 5, verified). Expect ~0 for a fit that should clear.
- **`a & b` can return `None` (not a 0-volume shape) when the shapes do not overlap at all** (seen 2026-10-14, phone dummy vs stand): write `x = a & b; ov = 0.0 if x is None else x.volume`.
- After `+` check `len(shape.solids())`. Text floated over a pocket gave **3 solids**, not 1 (verified): floating parts happen silently. Assert `== 1` (or the expected count).
- `p.is_valid` should be True; if False, rebuild with simpler ops.

## 7. Patterns and sketches
```python
with BuildPart() as q:
    Box(50, 50, 5)
    with GridLocations(30, 30, 2, 2): Hole(2.2)      # 4 holes, through the part (Hole default depth = through)
    with PolarLocations(10, 6): Cylinder(1, 5, mode=Mode.ADD)   # 6 pins on a 10 mm radius circle
```
Algebra equivalent: `body - [Pos(x,y,0)*Cylinder(1.5,30) for x in (-5,0,5)]` (subtracting a list works; verified).
`with Locations((10,10,5), (-10,-10,5)): Cylinder(...)` places copies at points (verified).
- Rounded-rect sketch -> extrude: `with BuildSketch(Plane.XY) as sk: Rectangle(40,30); fillet(sk.vertices(), 4)` then `extrude(amount=8)`.
- `revolve(axis=Axis.Z)` on a closed profile drawn in `Plane.XZ` (`BuildLine` + `Polyline(..., close=True)` + `make_face()`): volume 2853.6 verified.
- Taper: `extrude(amount=10, taper=10)` narrows the top (prefer to loft, which is fragile; cad-skill). Verified bbox 20x20x10.
- `CounterSinkHole(radius=2, counter_sink_radius=4, depth=6, counter_sink_angle=90)` works inside a BuildPart.
- `SlotOverall(30, 8)` + `extrude` = a stadium slot.

## 8. Text
```python
t = Text("AB", font_size=8, font_style=FontStyle.BOLD)       # a 2D face/compound
solid = extrude(Pos(0, 0, top_z) * t, amount=0.6)             # raised; subtract a slab for engraving
```
- Text becomes real geometry; **verify by volume delta** and `len(solids())` (letters on a hole = floating islands, verified 3 solids).
- Min stroke for FDM >= 0.8 mm: font_size >= ~7 mm bold.
- Text worked with the default font on this Mac (bbox 'HI' size 6 ~ 5x4.3 mm). If it ever errors or is blank, pass `font="Helvetica"` and check the volume delta.

## 9. Misc verified facts
- `import_stl(path)` returns a **Face** (shell), not a Solid. For edits of downloaded STLs use trimesh/Blender, or rebuild; do not expect boolean-ready solids from it.
- `mirror(shape, about=Plane.YZ)` mirrors across X=0 (verified). `scale(shape, 2)` multiplies volume x8.
- `shape.rotate(Axis.X, 90)` rotates about the given Axis (`Axis.X` passes through the WORLD origin, not the shape's centre) and returns a new shape; bbox of a 20 mm cube after 90 deg X = 20x20x20 (verified).
- `Compound([a, Pos(30,0,0)*b])` + `export_stl` = multi-body STL (2 solids, 8125 mm3 verified).
- `shape.is_inside((x,y,z))` / `shape.center()` for quick numeric probes. `shape.bounding_box()` has `.min .max .size .center()`.
- Print layout of multi-part files: lay parts flat side by side in ONE STL, but keep an assembled-pose STL for interference (see templates/assembly_lidbox_b123d.py).

## 10. Common errors
| Error / symptom | Cause | Fix |
|---|---|---|
| `Failed creating a fillet ... max_fillet()` | radius too big / bad edge set | `max_fillet`, smaller radius, fillet before cuts |
| `AttributeError: 'Location' object has no attribute 'origin'` | `Plane*Pos` gives a Location | use `.position` (verified) |
| `name 'max_fillet' is not defined` | it's a method | `b.max_fillet(b.edges())` |
| Volume unchanged after `-` | cutter missed (frame mistake) or opening face from other object | assert delta; print cutter bbox |
| More solids than expected | floating text/parts, cutter split body | `len(p.solids())`; print each solid's bbox |
| Part below the bed | rotated about origin | re-seat on Z=0 |
