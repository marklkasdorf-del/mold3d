# print-tolerances.md — numbers for designing FDM parts (0.4 mm nozzle, PLA)

Reference setup: 0.4 mm nozzle, 220x220x250 bed (edit knowledge/printer.json), PLA, a stock 0.2 mm layer profile. The skill assumes you do not tune slicer settings per part, so **wall thickness, rib size and clearance must be put in the geometry, not fixed in the slicer.**

## Provenance tags (read this before trusting any number)
- **[R]** research-derived: flowful cad-skill SKILL.md table (GitHub flowful-ai/cad-skill) and the 2026-10-14 forum/YouTube sweep. Generic FDM, NOT measured on your printer.
- **[K]** general FDM maker knowledge (not in the research files, not verified here). Use as a starting guess only.
- **[V]** verified on your printer by a real print. **None ship with the repo.** The first fit-critical prints create them (protocol at the bottom).
Rule: a [V] number always overrides [R]/[K]. Anything not [V] on a fit-critical interface gets a test coupon (SKILL.md phase 4).

## Walls, features, spans
| Feature | Min | Default | Notes |
|---|---|---|---|
| Wall thickness | 1.2 [R] | **2.0 non-structural, 2.4 structural** [R] | Thin walls feel fragile. Use multiples of 0.4: 1.2 / 1.6 / 2.0 / 2.4 |
| Floor / lid plate | 1.2 [R] | 2.0-2.4 | Bottom layers also get squashed (elephant foot) |
| Smallest feature (pin, rib width) | 0.4 [R] (= nozzle) | 0.8 [R] (= 2 lines) | Anything under 0.8 prints unreliably/fuzzy |
| Raised text/emboss | stroke >= 0.8 [K] | height 0.6-1.0 [K] | Engraved text depth >= 0.6 [K]; font bold; verify text is real geometry (volume delta) |
| Bridge span | — | **< 20 mm** [R] | Longer: add a mid support, or arch/teardrop the roof |
| Overhang angle | — | **<= 45 deg from vertical** [R] | Steeper needs supports. Use chamfers (45 deg) instead of fillets on bed-side edges [R] |
| Horizontal hole (axis parallel to bed) | — | make it a teardrop/diamond, apex up [K] | A round horizontal hole sags at the top |
| Vertical hole | — | prints ~0.1-0.2 undersize [K] | Add to nominal; ream if critical |
| Layer height assumption | — | 0.2 mm [R] | Make Z dimensions multiples of 0.2 when exact height matters [K] |
| Max bed size | 220 x 220 x 250 | design to <= 210 x 210 x 240 [K] | leaves brim/skirt margin |
| Corner radius vertical edges | — | 2-6 mm fine [K] | vertical fillets need no support; bottom/horizontal ones do |

## Clearances (gap per side between mating parts)
| Fit | Gap | Source / use |
|---|---|---|
| Press / interference | **-0.10 to -0.15** (interference) | [R] cad-skill; only for tiny parts, expect to need sanding |
| Snug / friction-slip | **0.15 - 0.20** | [K] starting guess; lid lips that should hold lightly |
| Slip fit (hole around a shaft/screw, lid lip) | **0.20 min, 0.30 recommended** | [R] cad-skill "hole clearance" |
| Loose / sliding / moving | 0.40 - 0.50 | [K] |
| Print-in-place gap (moving joint) | 0.4 - 0.6 [K]; **no first-hand LLM reports exist [R gap]** | always coupon first |
| Screw clearance hole M3 | 3.2 - 3.4 mm dia | [K] (3.0 + 0.2..0.4) |
| Screw clearance hole M4 | 4.3 - 4.5 | [K] |
| M3 heat-set insert hole | 4.0 - 4.2 (insert OD ~4.6-5.0; check the insert datasheet) | [K] |
| M3 self-tap into plastic | 2.6 - 2.8 | [K] |
| Magnet pocket | magnet dia + 0.2..0.3, depth + 0.2 | [K] |
| Card/phone/device pocket | device dim + 0.4 per side | [K] |

**Gap is per side. A lid lip's outer size = opening - 2 x gap.** Define `CLEAR` once in the parameter block and derive both parts from it (templates do this).

## Material adjustments to the table above
| Material | Adjustment | Source |
|---|---|---|
| PLA / PLA+ | none, use table | — |
| PETG | clearance **+0.1 mm** | [R] cad-skill |
| TPU | clearance about **0.5 mm** | [R] cad-skill |
| ABS/ASA | shrinks 0.5-0.7 %; scale up critical dims | [R] cad-skill |
| Anything | "When in doubt, print a small test piece first." | [R] cad-skill |

## Orientation rules that decide whether it prints
1. Largest flat face on the bed (Z=0). Model with the bed face at Z=0 so `bbox.min.Z == 0`. [R]
2. Bottom-edge chamfer 0.6-1.0 mm instead of fillet. [R] Also hides elephant foot.
3. Layer lines are the weak axis: put tension/bending loads in the XY plane, not across layers. [K]
4. Lids print plate-down with the lip pointing up. Boxes print open-top up.
5. Cantilevered/thin tall features: print so their long axis lies in XY, or add a gusset.

## Test coupons (10 minutes each) — what to print BEFORE the real part
Coupon = only the mating feature, with the exact clearance candidates side by side, labelled with engraved numbers.
- **Lip/lid coupon:** 3 short lid-lip + box-corner pairs at gap 0.15 / 0.25 / 0.35 (<= 30x30x10 each).
- **Hole/peg coupon:** a 12 mm plate with 4 holes (nominal+0.1/0.2/0.3/0.4) and a matching peg set, or the real screw/part.
- **Pocket coupon (print with the pocket channel vertical, floor on the bed; raised labels):** a 3 mm slice of the device pocket (same outline, 3 mm tall) at 2 clearances; drop the real device in.
Choose the tightest gap that goes together by hand without force; that is the number you log.

## fit-log update protocol ([V] numbers)
Goal: turn [R]/[K] guesses into [V] numbers on THIS printer.
1. After any coupon or real fit print, ask the user in one line: "did it fit — too tight / snug / loose?" (or read their photo).
2. Append ONE row to `knowledge/fit-log.md` (create with the header if absent):
   `| date | printer/material | interface | design gap (mm) | result (tight/snug/loose/fail) | adopted value | part/print id |`
   Example: `| 2026-10-20 | my-printer PLA grey | lid lip/box | 0.30 | snug | 0.30 | lidbox |`
3. If the result changes a default, edit the table above: replace the tag with **[V]** and cite the date, e.g. `0.30 [V 2026-10-20]`. Never delete the older [R] number; strike it out.
4. At the start of every max-model session read `knowledge/fit-log.md` first and use [V] values for all new parameter blocks.
5. If two prints disagree, keep both rows and prefer the newer; investigate (wet filament, first-layer squash, orientation) before changing a default.
