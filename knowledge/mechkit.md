# MechKit — verified print-in-place mechanisms (built 2026-10-17)
Modules (`forge mech list`): fitcard, gyro, planetary, balisong, helix, hinge (template). Scoreboard: mechkit-tests.json.
API (`lib/mechkit/core.py`): `Mech(name, parts{name: Shape}, fixed[...], motions[Motion])`;
`Motion(name, drive=(a,b), moves=[Move(part, "rot"|"trans"|"helix", axis, pivot, ratio, rate)], control=[Move(..., amount=)])`.
`selftest(m)`: static overlaps, per-pose sweep (steps), control checked ALONG ITS PATH (must exceed 1 mm3), exact gaps
(trimesh at angular tol 0.05). `export(m, dir)`: parts/*.stl + <name>.stl + mech.json (drives the showcase animation).
New mechanism: copy `templates/mech_template.py` -> lib/mechkit/<name>.py, add to cli.py REGISTRY, `forge mech build <name>`.

Numbers that work (all at fit.pip_gap = 0.30 until the Fit Card says otherwise):
| mechanism | key geometry | measured |
|---|---|---|
| fitcard | spinners: post r3, ring r8 h4, 45deg cap cone, z0 = HR - CH - g + g*sqrt2 | gaps = .15...40 exactly; 58 min, 16 g |
| gyro | spherical zones, t 3.5, core r9, pins rb1.8 L1.5 (true 45deg), stepped dome tops 11 -> 8.6 | 0.296-0.298; 44 min, 15 g |
| planetary | Zs15 Zp15x3 Zr45 m1.6, herringbone 25deg, flank offset C = gap/1.8 | 0.298-0.309; 2 h 57, 35 g |
| balisong | PY >= (bar_inner+bar_w)/2, cone pin r2.6->1.6, hole offset gap/cos(cone angle) | 0.300; 51 min, 16 g |
| helix | 3-lobe star, 1 turn / 90 mm, hole = section offset (gap) twisted at the same rate | passthrough 0.279; control = 1/6 turn |
| hinge | Fit Card hinge, cone pins r1.9 L1.4, sockets +gap*sqrt2 | 0.300 |
Flexify joints (lib/flexify.py) reuse the same physics: lap joint, disc r=0.36*width, cone pin r0 = max(1.6, 0.42Ra),
r1 = r0 - 0.7, z-split 0.45 h, V-notch theta 25 -> swing +-22. Needs ~3.5 mm height and 6 mm width at the joint core.
