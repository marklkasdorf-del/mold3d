---
name: max-model
version: 2.1.0
user-invocable: true
description: Idea-to-printable-3D-model studio for FDM printers. Use when asked to "model / design / make me a <thing> to print", "3D model this", "CAD this", "custom mount/case/holder/adapter/lid/bracket", "fidget", "print-in-place", "something that moves", "flexi <animal>", "figure / statue / mascot of <x>", "text to 3D", "gridfinity", "insert for my <thing>", "split this for my bed", "will this print", "calibrate my printer", "see it in AR", "put my name on", "add a keychain loop", "add magnets", "fix thin walls", "scale to my head", "make me a box", "keychains", "sign", "phone stand", "lithophane", "max model", "/max-model", or "forge". Code-CAD (build123d/OpenSCAD/bpy) + MechKit verified mechanisms + local text-to-3D + flexify + preflight failure prediction; hands a verified STL to your slicer.
triggers:
  - max model
  - /max-model
  - forge
  - model this for 3d printing
  - design a part to print
  - make me a custom
  - 3d model this
  - cad this
  - idea to print
  - print in place
  - fidget
  - flexi
  - text to 3d
  - gridfinity
  - will this print
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebSearch
  - WebFetch
  - Agent
---

# max-model: idea -> verified, printable part

The ask: whatever the user typed after /max-model (or the thing they described).
`FORGE` = this skill's directory (e.g. `~/.claude/skills/max-model`); every path below is relative to it. One CLI: `$FORGE/bin/forge <cmd>` (list at the bottom).
Environments (see README): CAD venv `$FORGE/.venv-cad` (build123d, trimesh, manifold3d, usd-core, opencv, sdf; override `FORGE_CAD_PY`), optional AI venv `$FORGE/.venv-ai` (torch, diffusers, CLIP; override `FORGE_AI_PY`) for `text3d` and `looks`.
Printer: `knowledge/printer.json` (bed, nozzle, layer; examples in `knowledge/printers/`). Slicing is the user's slicer of choice: forge ends at a verified STL plus a preflight verdict (supports on/off). An optional `slicer_cmd` hook lets forge report print time and grams.

**What the 2026-10-17 benchmark showed (`knowledge/benchmark-2026-10-17.md`):** exact parts from a full spec reach 0.96 voxel IoU vs the real STEP for fully specified parts, but only 0.41-0.82 where details were guessed; print-in-place mechanisms passed motion sweeps on the first build with zero fused gaps (not yet validated by real prints on the author's printer); LOOKS of iconic/organic things are the weak spot when modeled by hand (a hand-modeled helmet came out as an egg). The text3d / looks / remix pipelines exist to cover that weak spot with tools instead of willpower: reference pass + Looks Score, local text->3D for organic figures, flexify on top of sculpts, find-and-remix for iconic props.

## Rules that never bend
1. **Numbers first, pictures second.** No claim about geometry unless it comes from a tool's output (verify/selftest/preflight/grade JSON) or a render you read this iteration. Never describe an STL from memory.
2. **Spec before model** for custom parts: `spec.md` + `spec.json` with numeric success criteria first.
3. **One change per iteration**, keep every `iter_NN/`, max 6 per phase, then re-plan.
4. **Anything that moves ships with a passing self-test** (sweep clear + must-jam control + measured gaps). No exceptions; it is the reason mechanisms are the strength of this skill.
5. **Every print gets `forge preflight` before the slice**, and its verdict decides supports. NO-GO = fix geometry/orientation first.
6. **Environment:** Blender, OpenSCAD and GPU torch (text3d, looks) can crash inside some agent sandboxes that hide the GPU (Blender exits 139). If a step segfaults, run it outside the sandbox. Pure python (build123d, manifold3d, trimesh) runs anywhere.
7. **Report milestones briefly** (route chosen, first render, print-ready with time/grams/verdict, blocker): one line each, say what the user must decide. Send key images (sheet.png, poster.png) and AR files when the channel supports files.
8. Never start a print or spend money without the user's explicit OK. Downloaded models: respect the license (CC BY-NC = no selling).

## Session start (30 seconds)
```
ls $FORGE/knowledge/; cat $FORGE/knowledge/{fit-log.md,lessons.md,printer.json}; $FORGE/bin/forge fit show
$FORGE/bin/forge doctor                # red line -> fix it or report it before modeling
```
If `forge fit show` says pip_gap is still `[R]` (research default, not measured on this printer): mention once that the **Fit Card** (`forge mech build fitcard`, about an hour, ~16 g) calibrates every moving part, and offer to print it.

---

## PHASE 0 — ROUTE (pick the pipeline, not the hammer)
First match wins. Tell the user the route in one line.

| He wants | Route | Tools |
|---|---|---|
| change a DOWNLOAD: name/text on it, keychain loop, magnets, thicker walls, scale to a head size, flat bottom, mirror | **REMIX** (download, then upgrade) | `forge remix <stl> text|keychain|magnets|thicken|fit-head|flat|mirror|scale` |
| a practical thing from the user's numbers: box (slide/press lid), name keychain, sign, phone stand, holder for an object, lithophane | **MAKE** (generators; clearances from fit.json; boxes are motion-checked) | `forge make box|keychain|sign|stand|holder|lithophane` (+ `photofit` for outlines) |
| many copies / a whole project in one print (selling) | **PLATE** (packs the bed, per-item cost) | `forge plate <stl...> --fill|--copies N --slice` |
| a famous existing thing (a movie helmet, prop, popular toy, case for a popular device) | **FIND** (search a model site such as Printables/Thingiverse yourself), then **REMIX** (scale, split, magnets, fit) | web search, `forge split`, `forge preflight --orient` |
| an ORIGINAL wearable helmet ("a helmet nobody else has") | **TEXT3D --helmet**: neck cut, sized to a head you specify (default 160x190 + pad), 3 mm shell, faceplate + 4 magnet bosses, seam-down slices | `forge text3d "<style> helmet" --helmet` |
| something that **moves** (fidget, hinge, gears, gyro, balisong, passthrough, clicker) | **MECHKIT** if a module fits, else model it with the Mech API | `forge mech list/build`, `lib/mechkit/core.py` |
| a **flexi** animal | design an SDF body (`lib/sculpt.py`) or take a sculpt (a model site/text3d) -> **FLEXIFY** | `forge flexify`, `forge sculpt` |
| a **figure / mascot / creature / statue** | **TEXT3D** (local, free, ~3.5 min) or find; offer both | `forge text3d "<idea>" [--base NAME]` |
| a custom-fit functional part (mount, holder, adapter, case for the user's object) | **MODEL** (phases 1-6 below) | build123d lane, `forge run`, `forge parts-find` |
| organise drawers / an insert for an object | **GRIDFINITY** (+ **PHOTOFIT** for an exact pocket) | `forge gridfinity`, `forge photofit` |
| too big for the bed | **SPLIT** with pins + seam labels | `forge split` |
| "will this print / why did it fail" | **PREFLIGHT** (+ heatmap) | `forge preflight`, `forge heat` |
| show it off / sell it | **SHOWCASE** + **AR** | `forge showcase`, `forge ar` |

Honest quality notes for routing (measured by the author, 2026-10-17): text3d figures read clearly (axolotl, dragon, ghost mascot, shark) but fine detail is soft at 60 mm and they need supports; flexi-from-text via relief is chunky (thin legs merge) -> prefer an SDF-designed body or a human sculpt for flexis; hand-modeled organic shapes still look like blobs -> never hand-model a helmet/character, use FIND+REMIX or TEXT3D.

## PHASE 1 — BRIEF (custom parts): spec with numbers
1. Anything the user already told you about the exact object (device model, measurements, photos).
1b. **REFERENCE PASS** for anything with a name: search for 6-9 reference images / top-rated designs of the real thing, LOOK at them; write "## Form" in spec.md (proportions, 2-3 signature features, which variant). Skipping this made the bench balisong a flat stick and the spiral fidget the wrong toy.
2. Dimensions: look them up, never recall (bench: recalled pulley 0.41 IoU). `forge parts-find "<part>" [--download]` + `forge step2stl`; datasheets via web fetch; web search for reference images. Cite sources in spec.md. For an object the user owns that cannot be looked up: **PHOTOFIT** (`forge photofit mat` -> print the Calibration Mat at 100% -> photo -> outline within ~0.3 mm) beats asking for caliper numbers.
3. Ask the user only what can't be found: ONE message, <= 4 questions, each with a default.
4. Write `out/<name>/spec.md` + `spec.json` (templates/). Estimates on fit interfaces are marked `estimate`.
5. Post "spec ready: <one line> -- OK to build?"; proceed on low-risk silence with stated defaults.

## PHASE 2 — LANE + PLAN
| Lane | Use for |
|---|---|
| **b123d** (default) | functional/dimensioned/fit-critical parts, enclosures, MechKit modules |
| **scad** | trivial parts or one BOSL2 primitive (threads) |
| **sdf** (`lib/sculpt.py`) | organic bodies you design yourself: smooth unions, flat base, always watertight (gecko recipe) |
| **mesh** (`lib/meshkit.py`, manifold3d) | editing downloads/AI meshes, big booleans, flexify, split (OCC chokes on 100k-tri sculpts) |
| **bpy** | renders, voxel remesh, text-heavy art |
Plan in comments at the top of the part file: features as functions, parameter block in mm, clearances from `fit.get("pip_gap"/"slide_gap"/...)` (never hard-code 0.3), origin bottom-centre on Z=0, print orientation designed in (largest flat face down, overhangs <= 45, bridges < 18, walls >= 2.0), build order, assert list.

## PHASE 3 — BUILD IN SMALL STEPS
Per iteration: one change -> `forge run part.py --lane <lane> --spec spec.json --name <name>` -> read verify.json/REPORT.md (did volume/bbox change by what the change should cause? no change = dropped boolean) -> read sheet.png once -> critique -> next change.
- **Moving parts = the Mech API** (`lib/mechkit/core.py`): `Mech(name, parts, fixed, [Motion(name, drive, [Move...], control=[...])])` -> `selftest()` sweeps every pose, runs the must-jam control **along its whole path**, measures gaps exactly. Collision-proof by construction beats checking: arcs/spheres centred on the pivot keep the gap constant (gyro, flexi joints); keep each mover's swept volume on its own side of a plane (balisong pivots). Gears: `lib/gears.py`. **Measured, not declared**: `forge mech ratio <name> [--motion M --driven PART --driver PART]` poses the mechanism, frees the output and bisects for the contact-free interval -> measured ratio + backlash (`ratio.json`, exit 3 if it disagrees with the declared ratio). Cycloidal reducer: `forge mech build cyclo11` (`lib/cycloid.py` exact profile + undercut check). Studio renders: `forge showcase <dir> --style studio --still hero|cutaway|exploded`, `--ghost`, `--annotate`.
- **Preflight in the loop** for anything with overhangs: `forge preflight out/<name>/<name>.stl`.
- **Named objects: Looks Score** after the mechanics pass: `forge looks out/<name>/<name>.stl --target "<thing>"` (CLIP on clean renders; validated: it ranked human > v2 > v1 balisong). < 30% = iterate FORM (proportions, signature features), not mechanics. Compare v1 vs v2 with it instead of guessing.
- Hard rules: never judge from one view; overlap cutters 0.05 mm (coplanar faces leave zero-thickness skins that WELD pins: measured gap 0.0 instead of 0.3); same failure twice -> print sub-part numbers and re-diagnose; cap 6 iterations then re-plan or route to FIND.
Finish when verify passes every spec key, selftest passes (movers), preflight is GO/GO+SUPPORTS, visual checklist all yes.

## PHASE 4 — FIT
- **Calibration first:** print-in-place gaps come from `fit.json`. Until pip_gap is [V], every PIP design carries a preflight CAUTION. The Fit Card measures pip_gap (spinners .15-.40) and pip_vgap (hinges .25-.45) in one print: after it, ask "smallest number that spins freely after a firm twist?" -> `forge fit set pip_gap <n> --from "fitcard <date>"` (and pip_vgap). Every MechKit/flexify/gridfinity build reads it automatically.
- Mating parts / parts around the user's object: assembled-pose check `bin/verify --assembly a.stl b.stl --clearance <fit> --move-b=x,y,z`; dummy of the object from photofit/parts-find.
- Coupon only for an interface type the Fit Card doesn't cover (threads, snap-fits, press-fits) or estimated dimensions: <= 10 min, 3 variants, raised labels.

## PHASE 5 — PRINT PREP + HAND-OFF
1. `forge preflight <stl> [--slice]` -> verdict + supports decision. Organic/tilted parts: `forge preflight <stl> --orient` (tries tilts; one helmet wanted ~20 deg). `forge heat <stl>` makes the red/yellow support heatmap to show him.
2. Supports = preflight's call: GO -> off; GO+SUPPORTS -> on/auto; NO-GO -> fix first (knife-edge contact, fused gaps, doesn't fit -> `forge split`).
3. Slice in YOUR slicer of choice with the supports decision from step 2 and your normal profile; forge never changes slicer settings. (Optional: set `slicer_cmd` in `knowledge/printer.json` so `preflight --slice` / `plate --slice` report time and grams.)
4. Show the user: sheet or showcase poster + time/grams (if the hook is set) + verdict + one-line recipe. Offer `forge ar <stl>` (USDZ: opens as a real-size preview on iPhone/Vision Pro; GLB for Quest) when size/fit is the question.
5. Never start a print without the user's OK: "Bed clear? Starting <name>, ~<time>, <g> g."
6. Report "<name> print-ready: <time>, <g> g, <verdict>." Selling? `forge showcase <dir>` writes mp4/gif + listing.md (cost, suggested price, license reminder).

## PHASE 6 — FEEDBACK + LEARN
1. One line after it prints: "What was off? (fit / looks / strength / print quality / nothing)". Read any photo.
2. Gaps -> `forge fit set ...` (+ a row in fit-log.md). Other numbers -> fit-log.md / print-tolerances.md [V].
3. 1-3 lines in `knowledge/lessons.md` (date · project · lesson · phase). New technique -> `knowledge/<topic>.md` (<= 40 lines, runnable snippet).
4. Leave `part.py` + spec re-runnable. Offer one adjacent idea (shop brain) without starting it.
5. Any skill/tool change -> `tests/run_suite.sh` (known-answer checks) and, for capability claims, the bench (`forge grade`, `forge looks`) -- prove it got better.

---

## The toolbox (`forge <cmd>`)
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
| `preflight stl [--slice/--orient/--heat]`, `heat` | failure prediction: knife-edge contact, mid-air islands, bridges vs cantilevers, thin walls, fused PIP gaps, tip-over | 4/4 known cases correct |
| `looks stl --target "x"` | recognizability score (CLIP, clean renders) | ranked all 3 bench pairs like a human |
| `split stl [--scale]` | bed-sized pieces, smallest seams, pins + engraved seam IDs, pins.stl | 290 mm dragon -> 6 pieces, 2 s |
| `photofit mat` / `photofit photo.jpg` | Calibration Mat (ArUco) -> exact outline -> Gridfinity pocket bin | 72x24 test: -0.12/-0.25 mm |
| `gridfinity bin/base` | Gridfinity to spec | 0.93 IoU vs a community 1x1x6 bin (measured from the real file) |
| `ar stl [--parts dir]` | USDZ (iPhone/Vision Pro AR, real size) + GLB (Quest) | 48.4 x 11 mm survives the conversion |
| `showcase dir|stl` | verified-motion video + GIF + listing kit | 10 videos rendered |
| `grade`, `movecheck`, `parts-find`, `step2stl`, `topo` | benchmark + real parts + addressable faces | bench/ |

## Gotchas learned building this (each one cost real time once)
- manifold3d: a CLOCKWISE outline extrudes to an EMPTY solid (meshkit.prism fixes winding). `min_gap` is exact; use it.
- Cutters that share a face with the target leave a zero-thickness skin (pin welded, gap 0.0): extend cutters 0.05 mm past both faces, slope preserved.
- build123d `Polygon(*pts)` needs TUPLES; JSON lists became a zero-area sliver.
- Must-jam controls must be checked along the PATH: a gimbal ring tilted 25 deg about the wrong axis is clear of its pins, but jams at 10 deg.
- Export with angular_tolerance 0.05: coarse facets on big curves ate 0.06 mm of a 0.3 mm gap (the printer gets the facets).
- 45-deg cone pins/sockets must stay true 45 deg (rb > L): a clamped tip made pin and socket non-parallel (gap 0.21 instead of 0.30). Non-45 cones: offset radially by gap/cos(angle).
- Twisted (helical) surfaces: an in-plane offset g gives only g*cos(helix angle) of real gap.
- PCA axis sign is arbitrary: never flip a model 180 deg just because eigh said so.
- Taubin-smooth ONLY uniform voxel meshes; it melted a plinth cylinder into a splash.
- Image->3D from a TOP view is read as a front view (blob). Flat things (flexis, reliefs) come from the outline (`text3d/relief.py`), not Hunyuan.
- CLIP judges annotated CAD views badly (grid/text confuse it); always score clean renders.
- AI helmets are solid heads on a skinny neck stump: the hollowed cavity is SEALED above the neck -> punch the cavity outline down through the bottom (helmet_post does). Figure prompts say "full body" -> helmets need their own helmet-only prompt.
- Big hollow shells: slice in the pose preflight --orient picks (seam on the bed), never in the assembled pose (faceplate slice FAILED floating there; rim-down shell = 540 g of support).
- Artifacts don't serve .bin: ship geometry as base64 JSON.
- Head fit is a 3D question: the widest inner slice of a full helmet is the roomy jaw (v1 said 87% when 106% fit). Use the padded head proxy + interference search.
- Thin-wall fixing by "opening" treats surface roughness as thin and grows lumps each pass; thicken around the MEDIAL surface instead (distance-transform ridge), one pass, target min + 0.4.
- Flat-face analysis must sample the face AREA: a big flat face can be 2 triangles (magnet placement saw nothing).
- Auto-placing text: the bbox centre of a boomerang is empty air; ray-cast a grid and use the deepest point of the footprint.

## STOP-AND-CHECK (before each render and before "done")
- [ ] Axis/centre/units (bbox vs spec; mm everywhere) - [ ] every boolean has a volume delta - [ ] no floating parts (components == spec; flexify reports floating/slivers)
- [ ] walls >= 2.0 (preflight walls) - [ ] movers: selftest PASS, controls jam, gaps ~= fit.pip_gap - [ ] preflight GO/GO+SUPPORTS - [ ] named object: reference pass done, Looks >= 30%
- [ ] fit: Fit Card [V] or coupon - [ ] scope: revision stays narrow - [ ] done = all of the above, claimed with numbers, never "perfect".

## Boundaries
Reliable: functional parts with real numbers; print-in-place mechanisms from a clear motion; exact standard parts when looked up; Gridfinity; photo-fit pockets; text->3D figurines (soft detail); flexify on any body thick enough (~3.5 mm at the joints).
Unreliable: hand-modeled organic/iconic forms (FIND or TEXT3D instead), flexi from photo-style concepts (chunky), threads (BOSL2 + coupon), complex linkages (> 5 moving parts: find first).
Give up and switch when: 6 iterations without passing; same failure twice after a re-plan; no dimensions obtainable (photofit or coupon first); a tool is red in `forge doctor` (report it).

## Cost
Habits that keep usage low: one sheet read per iteration, small scripts, deterministic tools over re-asking. No subagent fan-outs for CAD.

## File map
`lib/`: remix.py, make.py, plate.py, mechkit/{core,fitcard,gyro,planetary,balisong,helix,hinge,cli}.py, flexify.py, sculpt.py, meshkit.py, preflight.py, heat_render.py, looks.py, split.py, photofit.py, gridfinity.py, ar.py, showcase.py + showcase_bpy.py, fit.py, gears.py, motion.py, grade.py, movecheck.py, text3d/{text3d.sh,concept.py,figure_post.py,relief.py}, text3d/hy3d_run.py (+ your Hunyuan3D-2 checkout in text3d/Hunyuan3D-2). `knowledge/`: fit.json, fit-log.md, lessons.md, benchmark-2026-10-17.md, mechkit.md, mechkit-tests.json, printer.json (+ printers/), devices.json. `bench/`: benchmark notes + the blind attempt scripts. `tests/`: run_all.sh (smoke), run_suite.sh (known-answer suite). Outputs: `out/<name>/`.
