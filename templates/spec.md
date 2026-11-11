# <part name> — spec   (forge Phase 1 BRIEF; written BEFORE any modeling)

## 1. What it is, in one line
<e.g. "Lid-and-box for a 3x AAA battery pack with a USB-C cable pass-through">

## 2. Why / who / where
- Used by: <me / sells / gift>   Use: <desk, bag, outdoors, 100g load...>   Taste notes: <sturdy, clean, no monograms unless asked>

## 3. Real-world measurements (every number: value, HOW obtained, confidence)
| Thing | Value (mm) | Source (caliper / datasheet URL / photo-with-ruler) | Confidence |
|---|---|---|---|
| e.g. pod body diameter | 38.0 | caliper, <who> <date> | measured |
| e.g. USB-C plug width | 8.3 | USB-IF spec | datasheet |
Anything with confidence "estimate" gets a TEST COUPON before the full part (Phase 4).

## 4. Fit interfaces (each gets a clearance from reference/print-tolerances.md + a coupon)
| Interface | Type (slip / snug / press / loose) | Clearance (mm) | Coupon needed? |
|---|---|---|---|

## 5. Features (each becomes ONE function in the part file)
1. <body: outer 80x50x20, wall 2.4, floor 2.4>
2. <cutout: USB-C 9.0x3.4 at x=…, centred on face -Y>
3. …

## 6. Print plan
- Orientation: <flat face on bed = …>   Supports: <none; overhangs ≤45°>   Material: PLA   Printer: <name, bed, nozzle - see knowledge/printer.json>
- Hard walls: ≥ 2.4 mm structural, ≥ 1.2 mm never less

## 7. Success criteria (mirror of spec.json — NUMBERS only)
- bbox 80 x 50 x 20 mm ± 0.3 | volume 19000–20500 mm3 | 1 component | watertight | min wall ≥ 1.6 | support ≤ 10 % | fits bed
- Visual: <list of 3–6 things the sheet.png MUST show, e.g. "cutout visible on -Y face", "no floating pieces">

## 8. Out of scope (protects existing work)
- <e.g. do not change wall thickness while adding the cutout>

## 9. Reference images (fetched via web search, saved to out/<name>/ref/)
- <path or URL + what to compare>
