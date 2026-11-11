"""Fit Card: ONE print that measures your printer's real print-in-place gaps.

Row 1: six spinners (vertical pin, captured by a 45-deg cone cap) at gaps .15 .20 .25 .30 .35 .40 mm.
Row 2: three flat hinges (horizontal cone pins) at .25 .35 .45 mm -- horizontal pins sag, so they get their own number.
After printing: give each ring / flap one firm break-in twist, then flick it. Smallest number that moves FREELY
 -> `forge fit set pip_gap <that>` ; hinge row -> `forge fit set pip_vgap <that>`.
Everything prints flat, no supports (overhangs 45 deg, bridges < 5 mm).
"""
import math
from build123d import *
from .core import Mech, Motion, Move, zcyl, label, CEN

RP, RO, HR, CH, CAP_T = 3.0, 8.0, 4.0, 1.5, 1.2   # post r, ring outer r, ring h, cone-trap chamfer, cap plate
BUMP_R = 0.9
PITCH = 19.0
RAIL_W = 9.0
SQ2 = math.sqrt(2)


def cone_z0(g):
    """where the 45-deg cap cone meets the post so the cone sits exactly g (perpendicular) above the ring chamfer."""
    return HR - CH - g + g * SQ2


def spinner(g, ztop):
    ring = zcyl(RO, HR) - zcyl(RP + g, HR)
    inner_top = ring.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1].sort_by(SortBy.RADIUS)[0]
    ring = chamfer(inner_top, CH)
    for k in range(10):                                         # grip bumps for flicking
        t = 2 * math.pi * k / 10
        ring += zcyl(BUMP_R, HR, RO * math.cos(t), RO * math.sin(t))
    z0 = cone_z0(g)
    rcap = RP + g + CH
    zc = z0 + (rcap - RP)                                       # top of the cone
    post = zcyl(RP, ztop) + Pos(0, 0, z0) * Solid.make_cone(RP, rcap, rcap - RP) + zcyl(rcap, ztop - zc, z=zc)
    return post, ring


def hinge(g, w=16.0, leaf=10.0, t=2.4, rk=3.0, r_base=1.9, cone_l=1.4):
    """flat print-in-place hinge, axis along X at (y=0, z=rk). A = fixed leaf (-Y) with the two outer knuckles
    + cone sockets; B = flap (+Y) with the middle knuckle + cone pins. Folds B up and over A (+X rotation)."""
    kl = (w - 2 * g) / 3
    xa0, xa1 = -w / 2, -w / 2 + kl
    xb0, xb1 = xa1 + g, xa1 + g + kl
    xc0, xc1 = xb1 + g, w / 2

    def knuckle(x0, x1):
        return Pos((x0 + x1) / 2, 0, rk) * Rot(0, 90, 0) * Cylinder(rk, x1 - x0)

    def block(x0, x1, y0, y1, h):
        return Box(x1 - x0, y1 - y0, h, align=(Align.MIN, Align.MIN, Align.MIN)).moved(Location((x0, y0, 0)))

    A = knuckle(xa0, xa1) + knuckle(xc0, xc1)
    A += block(xa0, xa1, -(rk + g) - 0.01, rk, rk) + block(xc0, xc1, -(rk + g) - 0.01, rk, rk)
    A += block(-w / 2, w / 2, -leaf, -(rk + g), t)
    B = knuckle(xb0, xb1) + block(xb0, xb1, -rk, rk + g + 0.01, rk)
    B += block(-w / 2, w / 2, rk + g, leaf, t)
    for sgn, xf in ((1, xb1), (-1, xb0)):
        pl = Plane(origin=(xf, 0, rk), x_dir=(0, 1, 0), z_dir=(sgn, 0, 0))
        B += Solid.make_cone(r_base, r_base - cone_l, cone_l, pl)
        R = r_base + g * SQ2
        A -= Solid.make_cone(R, R - (cone_l + g), cone_l + g, pl)
    return A, B, rk


def build(gaps=(0.15, 0.20, 0.25, 0.30, 0.35, 0.40), hinge_gaps=(0.25, 0.35, 0.45)):
    parts, motions = {}, []
    n = len(gaps)
    half = (n - 1) * PITCH / 2
    zrail = max(cone_z0(g) + CH + g + CAP_T for g in gaps)      # common cap-top height
    y_rail = RO + BUMP_R + 1.0
    x_edge = half + RO + BUMP_R + 1.0 + 2.0                     # tie bars sit outside the last ring
    frame = Box(2 * (x_edge + 2.0), RAIL_W, zrail, align=(Align.CENTER, Align.MIN, Align.MIN)).moved(Location((0, y_rail, 0)))
    for i, g in enumerate(gaps):
        x = -half + i * PITCH
        post, ring = spinner(g, zrail)
        arm = Box(4.0, y_rail + 0.01, CAP_T, align=(Align.CENTER, Align.MIN, Align.MIN)).moved(Location((x, 0, zrail - CAP_T)))
        frame += Pos(x, 0, 0) * post + arm
        frame += Pos(x, y_rail + RAIL_W / 2, zrail) * label(f"{g:.2f}"[1:], size=5.5)
        k = f"ring{int(round(g * 100)):02d}"
        parts[k] = Pos(x, 0, 0) * ring
        motions.append(Motion(f"spin{k[4:]}", (0, 360), [Move(k, "rot", axis=(0, 0, 1), pivot=(x, 0, 0))],
                              control=[Move(k, "trans", axis=(0, 0, 1), amount=1.5)], steps=7,
                              note=f"spinner at gap {g:.2f}"))
    hy = -(RO + BUMP_R) - 3.0 - 10.0                            # hinge axis line (flaps point toward the rings)
    hx0 = -(len(hinge_gaps) - 1) * 26 / 2
    for i, g in enumerate(hinge_gaps):
        A, B, rk = hinge(g)
        x = hx0 + i * 26
        frame += Pos(x, hy, 0) * A
        k = f"flap{int(round(g * 100)):02d}"
        parts[k] = Pos(x, hy, 0) * B + Pos(x, hy + 6.8, 2.4) * label(f"{g:.2f}"[1:], size=5.0)
        motions.append(Motion(f"fold{k[4:]}", (0, 150), [Move(k, "rot", axis=(1, 0, 0), pivot=(x, hy, rk))],
                              control=[Move(k, "trans", axis=(1, 0, 0), amount=1.5)], steps=7,
                              note=f"hinge at gap {g:.2f}"))
    # hinge strip + two tie bars -> the frame is ONE piece; only rings and flaps move
    frame += Box(2 * (x_edge + 2.0), 6.0, 2.4, align=(Align.CENTER, Align.MAX, Align.MIN)).moved(Location((0, hy - 10.0 + 0.01, 0)))
    for sx in (-1, 1):
        frame += Box(4.0, y_rail - (hy - 16.0) + 1.0, 2.4, align=(Align.CENTER, Align.MIN, Align.MIN)).moved(Location((sx * x_edge, hy - 16.0, 0)))
    parts = {"frame": frame, **parts}
    return Mech("fitcard", parts, ["frame"], motions,
                meta={"gaps": list(gaps), "hinge_gaps": list(hinge_gaps),
                      "how": "one firm break-in twist each, then flick; smallest free number -> forge fit set pip_gap / pip_vgap"})
