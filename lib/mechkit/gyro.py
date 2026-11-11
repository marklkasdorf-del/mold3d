"""Print-in-place gyroscope fidget (nested gimbal rings).

Trick that makes it collision-proof BY CONSTRUCTION: every ring is a SPHERICAL ZONE (inner + outer faces are
concentric spheres, cut flat top/bottom). Turning a ring about any axis through the centre maps its spherical faces
onto themselves, so the gap to its neighbours stays exactly `g` at every angle. Rings are joined by pairs of 45-deg
cone pins on alternating X / Y axes; the pins are the only thing that stops the wrong motion (control test).
Prints flat as one plate, no supports: sphere slopes at the cut planes stay < 45 deg (checked in build()).
"""
import math, sys, os
from build123d import *
from .core import Mech, Motion, Move, CEN

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit

SQ2 = math.sqrt(2)


def zone(r_out, r_in, c, top):
    """spherical-zone ring: concentric spheres about (0,0,c), cut flat at z=0 (bed) and z=top.
    Heights may differ per ring: the gap depends only on the sphere radii, so a taller inner ring still can't hit."""
    s = Pos(0, 0, c) * Sphere(r_out)
    if r_in > 0:
        s -= Pos(0, 0, c) * Sphere(r_in)
    slab = Box(4 * r_out, 4 * r_out, top, align=CEN)
    return s & slab


def build(n_rings=4, core_r=9.0, t=3.5, c=4.5, tops=None, g=None, rb=1.8, L=1.5, engrave="MAX", grips=14):
    """c = sphere-centre height (= pin height). tops = top height per body (core first); default = stepped dome."""
    g = fit.get("pip_gap") if g is None else g
    tops = tops or [11.0 - 0.6 * i for i in range(n_rings + 1)]
    radii = [(0.0, core_r)]
    r = core_r
    for i in range(n_rings):
        r_in = r + g
        r = r_in + t
        radii.append((r_in, r))
    for (r_in, r_out), top in zip(radii, tops):     # printability: overhang of each sphere at the cut planes
        a_bot = math.degrees(math.asin(min(1.0, c / r_out)))             # outer face below centre faces down
        a_top = math.degrees(math.asin(min(1.0, (top - c) / r_in))) if r_in > 0 else 0.0   # inner face above centre
        assert a_bot <= 45.0 and a_top <= 45.0, f"ring r={r_out:.1f}: overhang {max(a_bot, a_top):.0f} deg > 45"
    bodies = [zone(ro, ri, c, top) for (ri, ro), top in zip(radii, tops)]
    cc = (0, 0, c)
    axes = [(1, 0, 0) if i % 2 == 0 else (0, 1, 0) for i in range(n_rings)]   # pivot axis between body i and i+1
    assert rb - L > 0.1, "pin tip must stay a true 45-deg cone (rb > L), or pin/socket stop being parallel"
    for i in range(n_rings):
        a = axes[i]
        R_in_outer = radii[i + 1][0]
        for sgn in (1, -1):
            d = tuple(sgn * v for v in a)
            base_pt = tuple(cc[k] + d[k] * (R_in_outer + 0.4) for k in range(3))
            pl = Plane(origin=base_pt, z_dir=tuple(-v for v in d))
            bodies[i + 1] = bodies[i + 1] + Solid.make_cone(rb, rb - L, L, pl)
            bodies[i] = bodies[i] - Solid.make_cone(rb + g * SQ2, rb + g * SQ2 - (L + g), L + g, pl)
    if engrave:                                      # engraved (never raised: raised text would poke out of the shell)
        try:
            txt = Text(engrave, font_size=5.2, font="Arial Black", align=(Align.CENTER, Align.CENTER))
        except Exception:
            txt = Text(engrave, font_size=5.2, align=(Align.CENTER, Align.CENTER))
        bodies[0] = bodies[0] - Pos(0, 0, tops[0] - 0.6) * extrude(txt, 1.0)
    if grips:                                        # scallops on the outer ring for thumb grip
        R = radii[-1][1]
        for k in range(grips):
            ang = 2 * math.pi * k / grips + math.pi / grips
            bodies[-1] = bodies[-1] - Pos(R * math.cos(ang), R * math.sin(ang), 0) * Cylinder(1.6, 2 * tops[-1], align=CEN)
    names = ["core"] + [f"ring{i + 1}" for i in range(n_rings)]
    parts = dict(zip(names, bodies))
    motions = []
    for i in range(n_rings):
        inner = names[: i + 1]                     # body i and everything inside it turn together
        perp = (0, 1, 0) if axes[i][0] else (1, 0, 0)
        motions.append(Motion(f"spin_{names[i]}", (0, 360),
                              [Move(n, "rot", axis=axes[i], pivot=cc) for n in inner],
                              control=[Move(n, "rot", axis=perp, pivot=cc, amount=25) for n in inner],
                              steps=9, note=f"{names[i]} (+inner) about {'X' if axes[i][0] else 'Y'}"))
    # all rings tumbling at once (showcase + a harder self-test). Inner rotations FIRST, outer last: each outer rotation
    # then carries the already-rotated inner bodies, which is exactly how nested gimbals compose.
    gm = []
    for i in range(n_rings):
        for nm in names[: i + 1]:
            gm.append(Move(nm, "rot", axis=axes[i], pivot=cc, ratio=[2.0, 1.5, 1.0, 0.75, 0.5][i % 5]))
    motions.append(Motion("gimbal", (0, 360), gm, steps=5, note="every ring tumbling at once"))
    return Mech("gyro", parts, [names[-1]], motions,
                meta={"gap": g, "diameter": round(2 * radii[-1][1], 1), "height": max(tops), "pivot_z": c,
                      "why": "spherical zones: gap is constant at every angle"})
