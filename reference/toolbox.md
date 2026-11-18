# Mold3D toolbox and file map

Evidence columns are the author's runs (2026-10). `forge --help` lists every command with a one-line description.

Lead with these tools on the USER's files and numbers; MechKit showpieces are the engine underneath, not the product.

| cmd | what | evidence (author's runs, 2026-10) |
|---|---|---|
| `remix <stl> text "X"` | raised/engraved text that follows curves (shift-along-normal trick); auto-places on the widest flat spot, turned along it | boomerang arm (auto, -13 deg), a faceplate engrave |
| `remix <stl> fit-head [--circ 547]` | smallest scale where a padded 3D head proxy touches no plastic | a movie-prop helmet -> 106.6% (printed at 106% and fit) |
| `remix <stl> thicken --min 2` | walls under min thickened around their medial surface; thick parts untouched | a helmet part: layers with walls < 1.2 mm went 9 -> 1 |
| `remix <stl> keychain / magnets / flat / mirror / scale` | ring tab with through-hole (genus +1); magnet pockets with >= 2 mm walls; flat bed face | a boomerang, a 40 mm block |
| `make box W D H --lid slide|press [--divs] [--label]` | boxes; slide lid motion-checked (slides out clear + lift jams) | both pass |
| `make keychain|sign|stand|holder|lithophane` | name keychains (2-colour pause height), signs, device stands (knowledge/devices.json), photo-outline holders, lithophanes | rendered + checked |
| `plate <stl> --fill --slice` | bed packing + per-item cost | 33 keychains, 4 h 50, 2.6 g each |
| `mech list/build/test` | MechKit: fitcard, gyro, planetary, balisong, helix; Mech API for new ones | all pass; gaps = design gap +-0.01 |
| `fit show/set` | the one clearance table (`knowledge/fit.json`) | read by every generator |
| `flexify model.stl` | any creature -> print-in-place flexi (lap joints on cone pins, self-healing joint placement) | SDF gecko 7 joints +-22 deg, 3 s |
| `sculpt` | SDF organic lane (gecko recipe in lib/sculpt.py) | watertight in 3 s |
| `text3d "idea" [--base N] [--flexi] [--helmet]` | local text->concept->Hunyuan3D->printable figure + preflight + slice; `--helmet` = wearable 2-piece helmet | 4 figures ~3.5 min each; helmet v2 looks 5.3% vs egg 0.9% (the real prop scored 13.5%), 34.5 h / 742 g |
| `verify stl [--spec spec.json]` | every spec requirement (size, walls, components, named `checks`: hole / empty_at / solid_at / fits, fit sources) as PASS/FAIL in plain words, "N of N green"; `--raw` for the numbers table | 21/21 known answers on the suite fixture |
| `preflight stl [--slice/--orient/--heat]`, `heat` | failure prediction: knife-edge contact, mid-air islands, bridges vs cantilevers, thin walls, fused PIP gaps, auto-support traps, tip-over |
| `report <dir|stl> [--json]` | the Print Report: verdict, moving parts, gaps [V]/[R], time/grams, plain-English watch-fors, files; collects 3MF + preview + report.json | fitcard: GO, 9 movers clear |
| `export stl [--supports on/off/auto] [--out f.3mf]` | 3MF carrying the supports checkbox into Orca/Bambu/AnkerMake/Prusa slicers; `_SUPPORTS-OFF`/`-ON` in the name | 4/4 known cases correct |
| `export --piece NAME=a.stl@1,b.stl@2 [--piece ...] [--expect JSON]` | every piece on one plate as a Bambu/Orca project 3MF, colour parts on filament slots, supports per piece; reads itself back with `contents` | suite: 2 pieces / 2 slots read back |
| `contents f.3mf [--expect JSON]` | what is really in a 3MF: pieces, parts, filament slots, supports, and where each part shows (top / bed face only / buried); `--expect` mismatch = exit 1, do not send | caught both click fidget v7 delivery mistakes |
| `looks stl --target "x"` | recognizability score (CLIP, clean renders) | ranked all 3 bench pairs like a human |
| `split stl [--scale]` | bed-sized pieces, smallest seams, pins + engraved seam IDs, pins.stl | 290 mm dragon -> 6 pieces, 2 s |
| `photofit mat` / `photofit photo.jpg` | Calibration Mat (ArUco) -> exact outline -> Gridfinity pocket bin | 72x24 test: -0.12/-0.25 mm |
| `gridfinity bin/base` | Gridfinity to spec | 0.93 IoU vs a community 1x1x6 bin (measured from the real file) |
| `ar stl [--parts dir]` | USDZ (iPhone/Vision Pro AR, real size) + GLB (Quest) | 48.4 x 11 mm survives the conversion |
| `showcase dir|stl` | verified-motion video + GIF + listing kit | 10 videos rendered |
| `grade`, `movecheck`, `parts-find`, `step2stl`, `topo` | benchmark + real parts + addressable faces | bench/ |


## File map
`lib/`: remix.py, make.py, plate.py, mechkit/{core,fitcard,gyro,planetary,balisong,helix,hinge,cli}.py, flexify.py, sculpt.py, meshkit.py, preflight.py, export3mf.py, contents3mf.py, report.py, heat_render.py, looks.py, split.py, photofit.py, gridfinity.py, ar.py, showcase.py + showcase_bpy.py, fit.py, gears.py, motion.py, grade.py, movecheck.py, text3d/{text3d.sh,concept.py,figure_post.py,relief.py}, text3d/hy3d_run.py (+ your Hunyuan3D-2 checkout in text3d/Hunyuan3D-2). `knowledge/`: fit.json, fit-log.md, lessons.md, benchmark-2026-10-17.md, mechkit.md, mechkit-tests.json, printer.json (+ printers/), devices.json. `bench/`: benchmark notes + the blind attempt scripts. `tests/`: run_all.sh (smoke), run_suite.sh (known-answer suite). Outputs: `./mold3d/<name>/` in the folder you run forge from (`$MOLD3D_OUT` overrides).

## Routing quality notes
text3d figures read clearly but fine detail is soft at 60 mm and they need supports; flexi-from-text is chunky (use an SDF body or a sculpt); never hand-model a helmet or character (blobs): use FIND+REMIX or TEXT3D.
