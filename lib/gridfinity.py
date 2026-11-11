#!/usr/bin/env python3
"""gridfinity.py: Gridfinity bins + baseplates from the spec (Zack Freedman's open standard). venv: .venv-cad

    forge gridfinity bin 2 1 3 [--magnets] [--divs 2] [--label] [--cutout outline.json --depth 12]
    forge gridfinity base 4 3
Spec (verified 2026-10-17 against Printables 282691 by grading, see bench): grid 42 mm, bin 41.5 (0.25 clearance),
height unit 7 mm. Foot profile bottom->top: 35.6 r0.8 -> (0.8 @45) 37.2 r1.6 -> (1.8 vertical) -> (2.15 @45) 41.5 r3.75.
Baseplate pocket = that profile grown 0.25/side: 36.3 r1.15 -> 37.7 r1.85 -> 42 r4.0 (4.65 tall, open "lite" bottom).
Magnets 6.5 x 2.4 mm at +-13 mm. A --cutout pocket (from photofit) is sunk into the bin floor with fit.loose_fit.
"""
import argparse, json, math, os, sys
from build123d import *

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fit

GRID, BIN, HU = 42.0, 41.5, 7.0
FOOT = [(0.0, 35.6, 0.8), (0.8, 37.2, 1.6), (2.6, 37.2, 1.6), (4.75, 41.5, 3.75)]
POCKET = [(0.0, 36.3, 1.15), (0.7, 37.7, 1.85), (2.5, 37.7, 1.85), (4.65, 42.0, 4.0)]
WALL = 0.95                 # measured on Printables 282691 (gridfinity-rebuilt default)
FLOOR_TOP = HU              # interior floor at one full unit (7 mm)
LIP = 3.75                  # measured: lip rises 3.75 above nz*7


def rrect_face(w, d, r, z, cx=0.0, cy=0.0):
    return (Plane.XY.offset(z) * Pos(cx, cy) * RectangleRounded(w, d, r)).faces()[0]


def profile_solid(prof, cx=0.0, cy=0.0, grow=0.0, w_extra=0.0, d_extra=0.0):
    """loft through (z, size, radius) stations; straight segments are lofted pairwise so the edges stay crisp."""
    out = None
    for (z0, s0, r0), (z1, s1, r1) in zip(prof, prof[1:]):
        f0 = rrect_face(s0 + 2 * grow + w_extra, s0 + 2 * grow + d_extra, r0 + grow, z0, cx, cy)
        f1 = rrect_face(s1 + 2 * grow + w_extra, s1 + 2 * grow + d_extra, r1 + grow, z1, cx, cy)
        seg = loft([f0, f1])
        out = seg if out is None else out + seg
    return out


def bin_(nx=1, ny=1, nz=3, magnets=False, divs=1, label=False, cutout=None, depth=None, lip=True):
    W, D = GRID * nx - 0.5, GRID * ny - 0.5
    H = HU * nz
    feet = None
    for i in range(nx):
        for j in range(ny):
            cx, cy = (i - (nx - 1) / 2) * GRID, (j - (ny - 1) / 2) * GRID
            f = profile_solid(FOOT, cx, cy)
            if magnets:
                for sx in (-13, 13):
                    for sy in (-13, 13):
                        f -= Pos(cx + sx, cy + sy, 0) * Cylinder(3.25, 2.4, align=(Align.CENTER, Align.CENTER, Align.MIN))
                        f -= Pos(cx + sx, cy + sy, 2.39) * Cylinder(1.5, 3.2, align=(Align.CENTER, Align.CENTER, Align.MIN))
            feet = f if feet is None else feet + f
    body = Pos(0, 0, 4.75) * extrude(RectangleRounded(W, D, 3.75), H - 4.75 + (LIP if lip else 0))
    iw, idp, ir = W - 2 * WALL, D - 2 * WALL, 3.75 - WALL
    ex, ey = GRID * (nx - 1), GRID * (ny - 1)
    if lip:
        # measured lip (inner widths for 1x1): support chamfer 39.6 -> 37.3 ending at H, ledge, vertical 37.7, flare to 40.2
        st = [(H - 1.15, 39.6, ir), (H, 37.3, 1.6), (H + 0.6, 37.7, 1.8), (H + 2.6, 37.7, 1.8), (H + LIP + 0.01, 40.3, 3.1)]
        cav_low = Pos(0, 0, FLOOR_TOP) * extrude(RectangleRounded(iw, idp, ir), H - 1.15 - FLOOR_TOP + 0.001)
        cav_lip = profile_solid([(z, sz, r) for z, sz, r in st], w_extra=ex, d_extra=ey)
        cav = cav_low + cav_lip
    else:
        cav = Pos(0, 0, FLOOR_TOP) * extrude(RectangleRounded(iw, idp, ir), H)
    b = feet + body - cav
    if divs > 1:
        for k in range(1, divs):
            x = -W / 2 + WALL + k * (W - 2 * WALL) / divs
            b += Pos(x, 0, FLOOR_TOP) * Box(1.2, D - 2 * WALL, H - FLOOR_TOP - 0.6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if label:
        b += Pos(0, D / 2 - WALL - 6, H - 0.6) * Rot(-0, 0, 0) * Box(W - 2 * WALL, 12, 1.2, align=(Align.CENTER, Align.CENTER, Align.MAX))
    if cutout:
        pts = [tuple(map(float, q)) for q in cutout["outline_mm"]]   # TUPLES: build123d reads [x, y] lists as vectors
        g = fit.get("loose_fit")
        dep = depth or cutout.get("depth", 10.0)
        sk = offset(Polygon(*pts, align=None), g, kind=Kind.ARC)
        fill = Pos(0, 0, 4.75) * extrude(RectangleRounded(W - 2 * WALL + 0.02, D - 2 * WALL + 0.02, 3.75 - WALL), H - 4.75)
        b += fill                                                     # solid insert...
        b -= Pos(0, 0, H - dep) * extrude(sk, dep + 10)               # ...with the object's exact pocket
        if cutout.get("finger_notch", True):                          # notch at the pocket's +X edge to lift it out
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            nx_ = min(max(xs) + g, W / 2 - WALL - 7.0 - 0.8)        # notch stays inside the wall
            b -= Pos(nx_, (min(ys) + max(ys)) / 2, H) * Cylinder(7, 2 * dep * 0.75, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    return b


def baseplate(nx=3, ny=3):
    W, D = GRID * nx, GRID * ny
    plate = extrude(RectangleRounded(W, D, 4.0), 4.65)
    for i in range(nx):
        for j in range(ny):
            cx, cy = (i - (nx - 1) / 2) * GRID, (j - (ny - 1) / 2) * GRID
            plate -= profile_solid(POCKET, cx, cy)
    return plate


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["bin", "base"]); ap.add_argument("dims", nargs="+", type=int)
    ap.add_argument("--magnets", action="store_true"); ap.add_argument("--divs", type=int, default=1)
    ap.add_argument("--label", action="store_true"); ap.add_argument("--no-lip", action="store_true")
    ap.add_argument("--cutout"); ap.add_argument("--depth", type=float); ap.add_argument("--out")
    a = ap.parse_args()
    if a.kind == "bin":
        nx, ny, nz = (a.dims + [1, 1, 3])[:3] if len(a.dims) >= 3 else (a.dims + [1, 3])[:3]
        cut = json.load(open(a.cutout)) if a.cutout else None
        s = bin_(nx, ny, nz, a.magnets, a.divs, a.label, cut, a.depth, not a.no_lip)
        name = a.out or os.path.join(os.path.dirname(HERE), "out", "gridfinity", f"bin_{nx}x{ny}x{nz}{'_cut' if cut else ''}.stl")
    else:
        nx, ny = (a.dims + [a.dims[0]])[:2]
        s = baseplate(nx, ny)
        name = a.out or os.path.join(os.path.dirname(HERE), "out", "gridfinity", f"base_{nx}x{ny}.stl")
    os.makedirs(os.path.dirname(name), exist_ok=True)
    export_stl(s, name, tolerance=0.01, angular_tolerance=0.1)
    bb = s.bounding_box().size
    print(json.dumps({"out": name, "bbox": [round(bb.X, 2), round(bb.Y, 2), round(bb.Z, 2)], "volume_cm3": round(s.volume / 1000, 2),
                      "valid": s.is_valid}))


if __name__ == "__main__":
    main()
