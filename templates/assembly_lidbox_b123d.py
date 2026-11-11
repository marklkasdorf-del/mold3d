"""forge starter: two-part assembly (box + lip lid) in build123d.  forge/bin/forge run assembly_lidbox_b123d.py --name lidbox
Writes (next to $FORGE_OUT_STL):  <stem>.stl           = PRINT LAYOUT (box + lid side by side, lid flipped flat on the bed; 2 components)
                                  <stem>_box.stl, <stem>_lid_assembled.stl = ASSEMBLED POSE for the interference check:
    forge/bin/verify <stem>_box.stl --assembly <stem>_box.stl <stem>_lid_assembled.stl --clearance 0.2
Fit-critical interface = the lid lip inside the box opening. LIP_CLEAR is THE number to tune from knowledge/fit-log.md.
Origin: each part bottom-centre, Z=0 = bed. Units mm.
"""
import os
from build123d import *

# ---------------- PARAMETERS -----------------------------------------------------------------
L, W, H     = 70.0, 45.0, 28.0    # outer box
WALL        = 2.4
FLOOR       = 2.4
R           = 4.0                 # vertical corner radius
LID_T       = 2.4                 # lid plate thickness
LIP_H       = 4.0                 # lip depth into the box
LIP_WALL    = 1.6                 # lip ring thickness
LIP_CLEAR   = 0.30                # radial gap lip<->box inner wall (research default; replace from fit-log.md)
EPS         = 0.01

IN_L, IN_W = L - 2 * WALL, W - 2 * WALL          # box inner opening

def _rbox(l, w, h, r):
    b = Box(l, w, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return fillet(b.edges().filter_by(Axis.Z), r)

def make_box() -> Part:
    outer = _rbox(L, W, H, R)
    outer = chamfer(outer.edges().filter_by_position(Axis.Z, -EPS, EPS), 1.0)
    cav = Pos(0, 0, FLOOR) * _rbox(IN_L, IN_W, H, max(R - WALL, 0.5))
    p = outer - cav
    assert p.volume < outer.volume - 1000, "box cavity dropped"
    return p

def make_lid() -> Part:
    """Built in PRINT orientation: plate on the bed (Z 0..LID_T), lip pointing UP (+Z). Needs no supports."""
    plate = _rbox(L, W, LID_T, R)
    plate = chamfer(plate.edges().filter_by_position(Axis.Z, -EPS, EPS), 0.8)
    lo_l, lo_w = IN_L - 2 * LIP_CLEAR, IN_W - 2 * LIP_CLEAR        # lip outer = opening minus clearance each side
    lip_outer = Pos(0, 0, LID_T - EPS) * _rbox(lo_l, lo_w, LIP_H + EPS, max(R - WALL - LIP_CLEAR, 0.5))
    lip_inner = Pos(0, 0, LID_T - EPS) * _rbox(lo_l - 2 * LIP_WALL, lo_w - 2 * LIP_WALL, LIP_H + 2 * EPS, 0.5)
    lid = plate + (lip_outer - lip_inner)
    assert len(lid.solids()) == 1, "lid lip not fused to plate"
    return lid

def lid_assembled(lid: Part) -> Part:
    """Flip the lid (lip down) and drop it onto the box rim: plate underside at Z=H."""
    return Pos(0, 0, H + LID_T) * (Rot(180, 0, 0) * lid)           # Rot X180 maps z -> -z, so plate top lands at H+LID_T

if __name__ == "__main__":
    box, lid = make_box(), make_lid()
    out = os.environ.get("FORGE_OUT_STL", "lidbox.stl")
    stem = os.path.splitext(out)[0]
    # assembled pose + interference number (should be ~0 mm3, lip must not overlap walls)
    la = lid_assembled(lid)
    _x = box & la
    ov = 0.0 if _x is None else _x.volume          # `&` returns None when nothing overlaps
    print(f"interference volume box&lid = {ov:.3f} mm3 (must be ~0)")
    assert ov < 1.0, "lid lip collides with box walls"
    assert abs(la.bounding_box().max.Z - (H + LID_T)) < 0.05 and la.bounding_box().min.Z < H, "lid not seated on rim"
    export_stl(box, stem + "_box.stl", tolerance=0.01, angular_tolerance=0.1)
    export_stl(la, stem + "_lid_assembled.stl", tolerance=0.01, angular_tolerance=0.1)
    layout = Compound([box, Pos(0, W + 10, 0) * lid])               # side by side on the bed, both flat
    export_stl(layout, out, tolerance=0.01, angular_tolerance=0.1)
    print(f"OK {out} (print layout) + _box/_lid_assembled for fit check")
