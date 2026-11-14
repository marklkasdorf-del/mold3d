# spec.json as a test: named requirements, PASS/FAIL in plain words

`forge verify <stl> --spec spec.json` runs every requirement and prints each as one line a maker can read.
`forge run --spec` does the same on every build, and `forge report` shows the total as `Checks: N of N green`.
Done = all green. A failed check means the part is not what was asked for, whatever the render looks like.

## The 3-line fast lane
Simple parts (a box, a sign, a bracket) need only this; everything else is optional:
```json
{"bbox_mm": [80, 50, 20], "components": 1, "min_wall_mm": 2.0}
```
Those three plus the always-on checks (closed mesh, outward normals, has volume, fits the bed, bed contact, overhang %)
give a line each. `forge verify part.stl` with no spec still runs the always-on ones.

## Built-in keys
| key | check | plain line it prints |
|---|---|---|
| `bbox_mm: [x, y, z]`, `bbox_tol` (0.5) | size within tolerance | `Size 80.0 x 50.0 x 20.0 mm, wanted 80 x 50 x 20 within 0.3` |
| `components: 1` | number of separate bodies | `One solid piece` / `2 separate pieces, expected 1: something is floating` |
| `min_wall_mm: 2.0` | thinnest wall (FAIL below; without the key, 1.2 mm is a WARN) | `Thinnest wall 2.40 mm (minimum 2)` |
| `volume_mm3: [lo, hi]` | volume range (catches a dropped boolean) | `Volume 19420 mm3, wanted 19000 to 20500` |
| `max_support_pct: 10` | overhang share (FAIL above; without the key, 10 % is a WARN) | `Overhangs: 3% of the surface needs support (limit 10)` |
| `bed: [x, y, z]` | overrides the printer profile's bed | `Fits the bed (80 x 50 x 20 mm on 220 x 220 x 250)` |
| `must_be_watertight: true` | closed mesh (FAIL; `false` makes it a WARN) | `Mesh is closed (no holes in the surface)` |
| `fit: {...}` | every fit number has a source (see `reference/questions.md`) | `All 3 fit numbers have a real source` / `NOT FIT-CHECKED: ...` |

## Named checks: `"checks": {"<requirement>": {<type>}}`
The key is the requirement in your words; it becomes the first half of the printed line.

| type | means | example |
|---|---|---|
| `hole` | a through-hole of diameter `d` (±`tol`, default 0.2) whose axis passes through `at`; `axis` x/y/z (default z), `along` = where on the axis to probe (default mid-part). Measured with 24 radial rays. | `{"hole": {"at": [32, 17], "d": 3.4, "tol": 0.2}}` -> `hole for the M3 screw: measured 3.41 mm at (32, 17), wanted 3.4 ±0.2` |
| `empty_at` | the point must be open space (a cutout, a channel, the inside of a pocket) | `{"empty_at": [0, -25, 10]}` -> `USB-C cutout is open: open at (0, -25, 10)` |
| `solid_at` | the point must be inside plastic (a floor, a boss, a wall that must exist) | `{"solid_at": [0, 0, 1.2]}` -> `floor is solid under the pod: solid at (0, 0, 1.2)` |
| `fits` | an object dummy STL (`forge step2stl`, `forge photofit`, a cylinder you export), moved into place with `move`, must not collide and must have `clearance` all round | `{"fits": "pod_dummy.stl", "clearance": 0.3, "move": [0, 0, 2.4]}` -> `pod drops in with clearance: 0.31 mm clearance around the object, wanted ≥ 0.3` |
| `height_mm`, `width_mm`, `depth_mm` | one extent inside `[lo, hi]` (Z, X, Y) | `{"height_mm": [40, 42]}` -> `tall enough for the pod: height 41.0 mm, wanted 40 to 42` |
| `mass_g` | PLA mass estimate inside `[lo, hi]` | `{"mass_g": [15, 21]}` |

Rules the checker keeps:
- A check type it does not know, a dummy file it cannot find, or a check that throws is a **FAIL**, never a silent pass.
- `hole` fails with `no hole at (x, y): the part is solid there` when there is no hole, `nothing around (x, y)` when it is open space, and says `it does not go all the way through` for a blind hole.
- Coordinates are the STL's: origin bottom-centre, Z up (the templates build that way).
- `fits` paths are relative to the spec's folder.

## Reading the output
```
CHECKS for tray.stl: 7 of 8 green (FAIL: fix the red lines before calling it done)
  PASS  Mesh is closed (no holes in the surface)
  PASS  One solid piece
  PASS  Fits the bed (80 x 50 x 20 mm on 220 x 220 x 250)
  PASS  Size 80.0 x 50.0 x 20.0 mm, wanted 80 x 50 x 20 within 0.3
  PASS  Thinnest wall 2.40 mm (minimum 2)
  FAIL  hole for the M3 screw: measured 3.00 mm at (32, 17), wanted 3.4 ±0.2
  PASS  Overhangs: 0% of the surface needs support (soft limit 10)
  WARN  NOT FIT-CHECKED: tube diameter is assumed. Fix: ask one question: what is the tube diameter? (default 25 mm)
```
Exit code 1 on any FAIL. `--raw` prints the engineering table (name / value / detail), `--json` the full result
(`checks[*].plain` holds the sentences, `summary.green` / `summary.total` the count).
`forge report` exits 4 when a check fails, so an agent cannot hand over a part that misses its spec.
