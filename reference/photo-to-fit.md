# Photo-to-fit: a photo of the spot + what it should hold -> a part that grips a range

Route: `forge mount ...` (lib/mount.py, geometry in lib/mountgen.py). Send every image with `SendUserFile` (no such tool: print the absolute path). **Read every PNG yourself before sending it** (labels on the right things? arrows on the tube?). Wrong: fix `analysis.json`, re-render, at most 2 re-renders. Known products are looked up, never measured: only the unknown thing (chair, desk, bar) is measured. Test only if the user says test. Voice: `reference/moldy.md` where it exists.

## State table
| state | agent does | sends | next |
|---|---|---|---|
| S1 PRODUCT | `forge mount product "<words>"`: 1 match use it; several: ask 1 question (matches + "other: tell me the model"); 0: find the maker's spec page, add it to `knowledge/objects.json` with `source` URL + read date; unfindable: ask the model once, then the payload is ASSUMED with `fix` | question only if needed | S2 |
| S2 ANALYZE | `forge mount init <name> <photos> --ask "<words>"`, Read `grid_1.jpg`, fill `analysis.json` | | S2a if `missing_views`, else S3 |
| S2a ASK PHOTO | one sentence per missing view (which side, from where). `forge mount init <name> --add <photo>`. Max 2 rounds, then pick `strap` and say why | text | S2 |
| S3 CARDS | `forge mount card <name>` + `measure-card <name>`, Read both | both PNGs + "I'd go <style>. Reply `A 32 B 18`. Say a style letter to switch." | S4 |
| S4 NUMBERS | `forge mount numbers <name> "<reply>"`; exit 2: ask the line it prints; `--confirm` when the user says it is right | flag line | S5 |
| S5 TEST? | ask exactly: "Should I do a test first (fit comb, short print) or straight to the full thing?" | text | test S6, full S8 |
| S6 COMB | `forge mount comb <name>`, `forge preflight` + `forge report mold3d/<name>/comb` | `comb/preview.png` if any, report, 3MF path | S7 |
| S7 RESULT | `forge mount result <name> "<reply>"`: a tooth clicked -> measured -> S8; all loose/tight -> new comb -> S6 | | |
| S8 BUILD | `forge mount build <name>` (exit 1 = fix, max 6 iterations), `forge preflight mold3d/<name>/<name>.stl`, `forge report mold3d/<name>`, render if Blender exists | preview/sheet, Print Report verbatim, 1 line on what is assumed, hardware | S9 |
"Just make it" at S3/S4: skip to S8; unmeasured numbers become ASSUMED with the prior (report stamped NOT FIT-CHECKED).

## analysis.json rules
Coordinates are 0..1 on the EXIF-corrected photo (x right, y down), read off `grid_N.jpg`. `photo` fields index `photos[]` from 0.
- `section`: `round` (tube/bar: clamp-round or strap), `edge` (slab with free space under it: hookover), `flat` (a face you may screw into: screw), `irregular` (strap).
- `load`: weight acts straight down from the payload centre. `mass_full_g` = empty + capacity in ml, or the device mass. If it may twist a round mount, say so on the card ("it may rotate").
- `obstacles`: anything that moves or is in the way within 60 mm (levers, buttons, cables, arm pivot, drawers), each with `keep_out_mm` (default 10); the payload offset grows until every keep-out is clear.
- `measure`: only the interface, max 3 labels, A first; each names `tool` (calipers/ruler/tape) and `precision_mm` (0.5 clamps, 1.0 edges/reach); `no_calipers`: `strip` (reply `A c<length>`) or `profile` (`forge photofit <photo> --no-bin`, then `numbers --profile outline.json`).
- `missing_views`: add one whenever a side the clamp touches is not visible or the section is a guess. Never build on a guessed section.
- `scale_ref`: any known-size thing in frame (the product, a card 85.6 mm, a US quarter 24.26 mm, 1 euro coin 23.25 mm), in the same plane as the measurement; `null` if none.
Reply formats: `A 32`, `A 32 B 18`, `3.2cm`, `1.25in`, `A c100.5` (strip circumference). Comb: `-1 clicked` / `0 fits` / `+1 snug` / `all loose ~2` / `all tight ~2`.

## Styles
| style | section | grips | hardware | prints |
|---|---|---|---|---|
| clamp-round | round | D-2.5 .. D+2.5 mm tube | 2 M4 bolts + nuts (length from the gap) | halves split-face down, cup upright |
| hookover | edge | A-2 .. A+1 mm thick | none | on its side, hook pulls along the layers |
| strap | round / irregular | A-5 .. A+40 mm | 20 mm strap or zip ties | saddle roof-up with a 45 deg peak |
| screw | flat | n/a | 2 #8 / M4 wood screws | plate upright, thickened for 4 MPa across layers |
Payloads: `cup` (ring from objects.json, +loose fit +1 mm, drain hole), `hook` (40 mm arm + 12 mm lip). Load check: PLA 10 MPa along / 4 MPa across the layers [R]; FAIL = build exit 1.
