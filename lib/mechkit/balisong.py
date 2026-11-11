"""Print-in-place balisong (butterfly knife) trainer, blunt blade. Bench v2 + calibrated gaps.
Kinematic rule that makes it work: pivots at PY >= (bar_inner + bar_w)/2, so each handle's whole swept volume stays on
its own side of y=0 -> the handles can never hit each other (v1 with wider bars crashed at 180 deg until PY moved).
Capture: cone pin (wide at the bed) in a matching cone hole -> handle can't lift; the bed stops it dropping.
"""
import math, os, sys
from build123d import *
from .core import Mech, Motion, Move, zcyl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit


def build(gap=None, vgap=None, T=3.2, FL=2.4, BW=20.0, BL=85.0, BAR_W=7.0, HB=11.0, BAR_X1=95.0):
    G = fit.get("pip_gap") if gap is None else gap
    VG = fit.get("pip_vgap") if vgap is None else vgap
    PR0, PR1 = 2.6, 1.6
    TANG_R = PR0 + G + 1.8
    BAR_Y0 = BW / 2 + G
    PY = max(9.0, (BAR_Y0 + BAR_W) / 2 + 0.15)
    BAR_X0 = 5.4
    H = T + VG + FL

    blade = extrude(Rectangle(BL - BAR_X0 + 1, BW, align=(Align.MIN, Align.CENTER)).moved(Location((BAR_X0 - 5, 0))), T)
    blade = (blade - Pos(BL - 6 + 50, 0, T / 2) * Box(100, 40, T + 1)) + Pos(BL - 6, 0, 0) * zcyl(BW / 2, T)
    for s in (1, -1):
        blade += Pos(0, s * PY, 0) * zcyl(TANG_R, T)
    blade += Box(TANG_R * 2, 2 * PY, T, align=(Align.CENTER, Align.CENTER, Align.MIN))
    Gn = G / math.cos(math.atan((PR0 - PR1) / T))     # radial offset that gives a true PERPENDICULAR gap G on the cone
    for s in (1, -1):
        blade -= Pos(0, s * PY, 0) * Solid.make_cone(PR0 + Gn, PR1 + Gn, T)
    blade -= Pos(45, 0, 0) * zcyl(4, T)
    blade -= Pos(62, 0, 0) * zcyl(3, T)

    def handle(s):
        bar = Box(BAR_X1 - BAR_X0, BAR_W, HB, align=(Align.MIN, Align.MIN, Align.MIN)).moved(Location((BAR_X0, BAR_Y0, 0)))
        bar = fillet(bar.edges().filter_by(Axis.X).group_by(Axis.Y)[-1], 2.5)
        bar = fillet(bar.edges().filter_by(Axis.Z).group_by(Axis.X)[-1], 3.0)
        for k in range(4):
            bar -= Pos(30 + k * 15, BAR_Y0 + BAR_W / 2, HB / 2) * Rot(0, 0, 45) * Box(3.4, 3.4, HB + 1)
        flange = Box(12, BAR_Y0 + BAR_W - 1.0, FL, align=(Align.MIN, Align.MIN, Align.MIN)).moved(Location((0, 1.0, T + VG)))
        flange += Pos(0, PY, T + VG) * Cylinder(PY - 1.4, FL, align=(Align.CENTER, Align.CENTER, Align.MIN))
        pin = Pos(0, PY, 0) * Solid.make_cone(PR0, PR1, T) + zcyl(PR1, VG + 0.5, 0, PY, T)
        h = bar + flange + pin + Pos(0, PY, H) * Cylinder(3.6, 1.2, align=(Align.CENTER, Align.CENTER, Align.MIN))
        return h.mirror(Plane.XZ) if s < 0 else h

    parts = {"blade": blade, "handleA": handle(1), "handleB": handle(-1)}
    flip = Motion("flip", (0, 180), [Move("handleA", "rot", pivot=(0, PY, 0)),
                                     Move("handleB", "rot", pivot=(0, -PY, 0), ratio=-1)],
                  control=[Move("handleA", "trans", axis=(0, 0, 1), amount=1.5)], steps=13,
                  note="both handles swing open 180 deg (blade held)")
    return Mech("balisong", parts, ["blade"], [flip],
                meta={"gap": G, "vgap": VG, "pivot_y": round(PY, 2), "length": BAR_X1 + TANG_R})
