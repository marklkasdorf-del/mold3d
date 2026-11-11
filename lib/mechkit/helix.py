"""Helix passthrough fidget ("impossible passthrough"): a twisted 3-lobe spiral spins down through a matching
twisted hole in a stand. NOTE (bench): the famous "spiral cone fidget" (Printables 927393) is a DIFFERENT toy
(finned cone through a slotted cone) -- look at reference images of both and ask which one is meant.
Prints: spiral knob-down (twist has no overhang), stand upside-down (plate on bed).
"""
import math, os, sys
from build123d import *
from .core import Mech, Motion, Move

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit


def star(r_out, r_in, n=3):
    pts = []
    for k in range(n * 16):
        t = 2 * math.pi * k / (n * 16)
        rr = r_in + (r_out - r_in) * (0.5 + 0.5 * math.cos(n * t)) ** 1.6
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return Polygon(*pts, align=None)


def build(L=110.0, turn_mm=90.0, r_lobe=21.0, r_core=9.0, plate=6.0, cone=(40.0, 31.0, 80.0), wall=2.4,
          knob=(30.0, 6.0), gap=None, windows=8):
    G = fit.get("loose_fit") if gap is None else gap          # sliding passthrough wants a loose fit
    rate = 360.0 / turn_mm
    rb, rt, ch = cone
    sec = star(r_lobe, r_core)

    def twisted(face, z0, h):
        face = face.faces()[0] if not isinstance(face, Face) else face
        f = face.rotate(Axis.Z, z0 * rate).moved(Location((0, 0, z0)))
        return Solid.extrude_linear_with_rotation(f, (0, 0, z0), (0, 0, h), h * rate)

    z0 = ch + 1.0
    spiral = twisted(sec, z0, L) + Pos(0, 0, z0 + L) * Cylinder(knob[0], knob[1], align=(Align.CENTER, Align.CENTER, Align.MIN))
    stand = Solid.make_cone(rb, rt, ch) - Solid.make_cone(rb - wall, rt - wall, ch - plate)
    stand -= twisted(offset(sec, G, kind=Kind.ARC), ch - plate - 0.5, plate + 1.0)
    for k in range(windows):
        stand -= Rot(0, 0, 360 * k / windows) * Pos(rb - 4, 0, ch * 0.42) * Rot(0, 90, 0) * Cylinder(9, 12)
    parts = {"stand": stand, "spiral": spiral}
    drop = Motion("drop", (0, L - 1.0), [Move("spiral", "helix", axis=(0, 0, -1), rate=rate)],
                  control=[Move("spiral", "trans", axis=(0, 0, -1), amount=turn_mm / 6)], steps=13,
                  note="spiral spins all the way down through the plate")
    return Mech("helix", parts, ["stand"], [drop],
                meta={"gap": G, "turn_mm": turn_mm, "print": "spiral knob-down; stand upside-down (mirror Z)",
                      "control_note": "control drop = 1/6 turn (60 deg): avoids the 3-lobe 120-deg symmetry no-op",
                      "gap_pose": ("drop", L / 2)})
