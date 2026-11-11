"""forge starter: build123d part (lane b123d).  Run: forge/bin/forge run part.py --spec spec.json --name mypart
Units: millimetres. Origin: bottom-centre of the part (bbox X/Y centred, Z from 0 up) so Z=0 IS the print bed.
Rules baked in: parameter block -> one function per feature -> assemble -> self-asserts -> export.
Example part: a rounded tray with a corner screw hole and a chamfered (not filleted) bottom edge. Replace the features.
"""
import os, sys
from build123d import *
from b123d_checks import assert_solid, overlap_volume, min_distance   # forge/lib is on PYTHONPATH under `forge run`

# ---------------- PARAMETERS (mm). Every number in the model derives from these. -------------
LENGTH      = 80.0   # X
WIDTH       = 50.0   # Y
HEIGHT      = 20.0   # Z (print height)
WALL        = 2.4    # >= 1.2 hard min, 2.0+ recommended; 2.4 = 6 perimeters at 0.4
FLOOR       = 2.4
CORNER_R    = 4.0    # vertical-edge fillet (fine: vertical edges need no support)
BOTTOM_CH   = 1.0    # chamfer on bed-side edges (NOT a fillet: fillets overhang <45deg at the bed)
HOLE_D      = 3.4    # M3 clearance = 3.0 + 0.4 (see reference/print-tolerances.md)
HOLE_INSET  = 8.0    # hole centre distance from each outer side
EPS         = 0.01   # cutter overshoot so booleans never leave coplanar skins

# ---------------- FEATURES: each returns a Part, built at the origin -------------------------
def body() -> Part:
    b = Box(LENGTH, WIDTH, HEIGHT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    b = fillet(b.edges().filter_by(Axis.Z), CORNER_R)                      # fillet before cutting
    b = chamfer(b.edges().filter_by_position(Axis.Z, -EPS, EPS), BOTTOM_CH)  # bottom edges only
    return b

def cavity() -> Part:
    iw, il = LENGTH - 2 * WALL, WIDTH - 2 * WALL
    c = Box(iw, il, HEIGHT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    c = fillet(c.edges().filter_by(Axis.Z), max(CORNER_R - WALL, 0.5))
    return Pos(0, 0, FLOOR) * c                                             # open top: cavity runs past HEIGHT

def screw_holes() -> list:
    x, y = LENGTH / 2 - HOLE_INSET, WIDTH / 2 - HOLE_INSET
    return [Pos(sx * x, sy * y, -EPS) * Cylinder(HOLE_D / 2, FLOOR + 2 * EPS, align=(Align.CENTER, Align.CENTER, Align.MIN))
            for sx in (-1, 1) for sy in (-1, 1)]

# ---------------- ASSEMBLE -------------------------------------------------------------------
def build() -> Part:
    p = body()
    v0 = p.volume
    p = p - cavity()
    assert p.volume < v0 - 1000, "cavity boolean did nothing (silent drop?)"      # subtract must remove volume
    v1 = p.volume
    p = p - screw_holes()
    assert p.volume < v1, "screw holes did nothing"
    return p

# ---------------- SELF-CHECKS (numbers, not looks) -------------------------------------------
def check(p: Part):
    bb = p.bounding_box()
    assert abs(bb.size.X - LENGTH) < 0.05 and abs(bb.size.Y - WIDTH) < 0.05 and abs(bb.size.Z - HEIGHT) < 0.05, bb.size
    assert abs(bb.min.Z) < 1e-6, "part must sit on Z=0"
    assert_solid(p, "part", solids=1)   # valid B-rep + 1 solid + positive signed volume + BRepAlgoAPI_Check

if __name__ == "__main__":
    part = build()
    check(part)
    out = os.environ.get("FORGE_OUT_STL", "part.stl")
    export_stl(part, out, tolerance=0.01, angular_tolerance=0.1)
    try:
        export_step(part, os.path.splitext(out)[0] + ".step")
    except Exception as e:  # STEP is a bonus, never fatal
        print("step export skipped:", e, file=sys.stderr)
    print(f"OK {out} vol={part.volume:.0f}mm3 bbox={tuple(round(v,2) for v in part.bounding_box().size)}")
