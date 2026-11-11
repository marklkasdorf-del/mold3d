"""Print-in-place herringbone planetary fidget (bench 2026-10-17, now calibrated via fit.pip_gap).
Zr = Zs + 2Zp and (Zs + Zr) / N must be an integer (planets space evenly). Herringbone traps planets axially.
Motions: `mesh` (carrier fixed, one sun tooth: cheap exact check) and `spin` (ring held, planets orbit: animation).
"""
import math, os, sys
from build123d import *
from .core import Mech, Motion, Move

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit
import gears


def build(zs=15, zp=15, n=3, module=1.6, height=14.0, helix_deg=25, ring_wall=5.0, grips=24, hex_af=9.0, gap=None):
    zr = zs + 2 * zp
    assert (zs + zr) % n == 0, f"(Zs+Zr)/N must be an integer: ({zs}+{zr})/{n}"
    gears.set_params(module=module, height=height, helix_deg=helix_deg)
    gap = fit.get("pip_gap") if gap is None else gap
    C = gap / 1.8                    # per-flank offset; measured min gap ~= 1.8*C on this tooth form (bench)
    M = module
    rs, rp, rr = zs * M / 2, zp * M / 2, zr * M / 2
    a = rs + rp
    sun_f = offset(gears.gear_face(zs), -C, kind=Kind.INTERSECTION)
    sun = gears.herringbone(sun_f, rs, +1)
    sun -= extrude(RegularPolygon(hex_af / 2, 6, major_radius=False), height)
    parts = {"sun": sun}
    for i in range(n):
        phi = 2 * math.pi * i / n
        pf = offset(gears.gear_face(zp), -C, kind=Kind.INTERSECTION) - Circle(2.5)
        pf = pf.rotate(Axis.Z, math.degrees(phi * (1 + zs / zp)))
        parts[f"planet{i}"] = Pos(a * math.cos(phi), a * math.sin(phi), 0) * gears.herringbone(pf, rp, -1)
    ring_cut = offset(gears.gear_face(zr, internal=True), C, kind=Kind.ARC)
    ring_out = rr + 1.25 * M + ring_wall
    ring_f = Circle(ring_out) - ring_cut
    for k in range(grips):
        t = 2 * math.pi * k / grips
        ring_f -= Pos(ring_out * math.cos(t), ring_out * math.sin(t)) * Circle(1.6)
    parts["ring"] = gears.herringbone(ring_f, rr, -1)

    pitch = 360 / zs
    mesh = Motion("mesh", (0, pitch), [Move("sun", "rot")] +
                  [Move(f"planet{i}", "rot", pivot=(a * math.cos(2 * math.pi * i / n), a * math.sin(2 * math.pi * i / n), 0),
                        ratio=-zs / zp) for i in range(n)] + [Move("ring", "rot", ratio=-zs / zr)],
                  control=[Move("sun", "rot", amount=pitch / 2)], steps=7,
                  note="carrier fixed, one sun tooth pitch (the mesh repeats every tooth)")
    wc = zs / (zs + zr)              # ring held: carrier speed; planets spin rel. carrier, then orbit with it
    wp = -(1 - wc) * zs / zp
    spin_moves = [Move("sun", "rot")]
    for i in range(n):
        c = (a * math.cos(2 * math.pi * i / n), a * math.sin(2 * math.pi * i / n), 0)
        spin_moves += [Move(f"planet{i}", "rot", pivot=c, ratio=wp), Move(f"planet{i}", "rot", ratio=wc)]
    spin = Motion("spin", (0, 360), spin_moves, steps=3, note="ring held, sun turned: planets orbit (animation)")
    return Mech("planetary", parts, ["ring"], [mesh, spin],
                meta={"zs": zs, "zp": zp, "zr": zr, "module": M, "gap": gap, "C": round(C, 3),
                      "diameter": round(2 * ring_out, 1), "height": height})
