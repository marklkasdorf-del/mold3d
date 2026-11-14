#!/usr/bin/env python3
"""split: cut a model too big for your printer bed into bed-sized pieces with alignment pins + labels. venv: .venv-cad

    forge split model.stl [--bed X,Y,Z] [--scale 1.06] [--pins printed|filament|none] [--max-pieces 12]
Each cut: along the piece's longest axis, at the position (30-70%) with the SMALLEST cross-section (= least seam to
glue/sand), keeping both halves non-empty. Pins: up to 3 per seam, placed where the seam is thickest
(>= pin radius + 2 mm wall). printed = 4 mm pins (pins.stl, holes +slide_gap), filament = 1.75 mm filament
offcuts as pins (holes 1.95 mm). Pieces get engraved IDs on the CUT face (hidden once glued).
Thin shells (helmets) have no room for pins -> the seam gets 3 glue TABS on the inside instead.
Fit test per piece: any rotation (minimum-volume oriented box) must fit the bed box; print pose via preflight --orient.
"""
import argparse, json, math, os, sys
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forge_env
import meshkit as mk
import fit
import printer
from manifold3d import Manifold, JoinType


def fits(M, bed):
    t = mk.mf2tm(M)
    try:
        T, ext = trimesh.bounds.oriented_bounds(t)
    except Exception:
        ext = t.extents
    return all(a <= b + 1e-6 for a, b in zip(sorted(ext), sorted(bed))), sorted(ext)


def section(M, axis, at):
    """cross-section of M on the plane axis=at (returns CrossSection in plane coords)."""
    rot = {0: [0, -90, 0], 1: [90, 0, 0], 2: [0, 0, 0]}[axis]
    # Ry(-90): z' = x ; Rx(+90): z' = y ; so the slice height is +at for every axis (a -at here sliced empty air)
    return M.rotate(rot).slice(float(at))


def plane_frame(axis):
    """rotation (deg) used by section() and its inverse for placing things on the plane."""
    return {0: [0, -90, 0], 1: [90, 0, 0], 2: [0, 0, 0]}[axis]


def best_cut(M, axis):
    bb = M.bounding_box(); lo, hi = bb[axis], bb[axis + 3]
    best = None
    for f in np.linspace(0.3, 0.7, 17):
        at = lo + f * (hi - lo)
        a = section(M, axis, at).area()
        if a <= 0.5:
            continue
        score = a * (1 + 0.6 * abs(f - 0.5))          # prefer small seams, mildly prefer the middle
        if best is None or score < best[0]:
            best = (score, at, a)
    return best


def pin_points(cs, r_need, k=3):
    inner = cs.offset(-r_need, JoinType.Round)
    if inner.is_empty() or inner.area() < 0.5:
        return []
    pts = np.concatenate([np.asarray(p) for p in inner.to_polygons()])
    chosen = [pts[np.argmax(((pts - pts.mean(0)) ** 2).sum(1))]]
    while len(chosen) < k:
        d = np.min([((pts - c) ** 2).sum(1) for c in chosen], axis=0)
        i = int(np.argmax(d))
        if d[i] < (4 * r_need) ** 2:
            break
        chosen.append(pts[i])
    # pull points slightly inward from the offset boundary toward the inner centroid
    c0 = pts.mean(0)
    return [tuple(p + 0.15 * (c0 - p)) for p in chosen]


def to_world(axis, at, uv):
    """plane coords (from the rotated slice) -> world xyz."""
    u, v = uv
    if axis == 2:
        return np.array([u, v, at])
    if axis == 0:   # rotate [0,-90,0]: world (x,y,z) -> (-z, y, x)  => u=-z, v=y, slice height = x
        return np.array([at, v, -u])
    # axis 1: rotate [90,0,0]: (x,y,z) -> (x, -z, y) => u=x, v=-z, height=y ; section used -at -> careful
    return np.array([u, at, -v])


def run(src, out, bed=None, scale=1.0, pins="printed", max_pieces=12):
    bed = bed or tuple(b - 10 for b in printer.bed())
    M = mk.load_manifold(src)
    if scale != 1.0:
        M = M.scale([scale] * 3)
    lo = M.bounding_box(); M = M.translate([-lo[0], -lo[1], -lo[2]])
    pin_r = {"printed": 2.0 + fit.get("slide_gap") / 2, "filament": 0.975, "none": 0}[pins]
    depth = {"printed": 6.0, "filament": 8.0, "none": 0}[pins]
    queue = [("A", M)]; pieces = []; seams = []
    while queue:
        name, P = queue.pop(0)
        ok, ext = fits(P, bed)
        if ok or len(pieces) + len(queue) + 1 >= max_pieces:
            pieces.append((name, P, ext, ok)); continue
        bb = P.bounding_box(); exts = [bb[i + 3] - bb[i] for i in range(3)]
        axis = int(np.argmax(exts))
        bc = best_cut(P, axis)
        if bc is None:
            pieces.append((name, P, ext, False)); continue
        _, at, area = bc
        normal = [0.0, 0.0, 0.0]; normal[axis] = 1.0
        hi_half, lo_half = P.split_by_plane(normal, float(at))
        cs = section(P, axis, at)
        holes = []
        kind = "pins"
        if pins != "none":
            pts = pin_points(cs, pin_r + 2.0)
            for uv in pts:
                c = to_world(axis, at, uv)
                cyl = Manifold.cylinder(2 * depth, pin_r, pin_r, 48, True)
                rot = {0: [0, 90, 0], 1: [90, 0, 0], 2: [0, 0, 0]}[axis]
                cyl = cyl.rotate(rot).translate(c.tolist())
                hi_half -= cyl; lo_half -= cyl; holes.append([round(float(x), 2) for x in c])
            if not pts:
                kind = "glue-tabs"
        # engrave the seam number on BOTH mating faces (hidden after gluing; tells you which faces go together)
        sid = str(len(seams) + 1)
        room = cs.offset(-6.0, JoinType.Round)
        if not room.is_empty() and room.area() > 30:
            rp = np.concatenate([np.asarray(q) for q in room.to_polygons()])
            far = rp[np.argmax(np.min([((rp - np.array(h2[:2] if axis == 2 else (h2[0] if axis == 1 else -h2[2], h2[2] if axis == 1 else h2[1]))) ** 2).sum(1)
                                        for h2 in holes], axis=0))] if holes else rp.mean(0)
            far = far + 0.25 * (rp.mean(0) - far)
            try:
                from build123d import Text, extrude, Align, export_stl
                import tempfile
                txt = extrude(Text("S" + sid, font_size=7, font="Arial Black", align=(Align.CENTER, Align.CENTER)), 1.2)
                fd, tp = tempfile.mkstemp(suffix=".stl"); os.close(fd); export_stl(txt, tp)
                T = mk.tm2mf(trimesh.load(tp)); os.remove(tp)
                T = T.translate([float(far[0]), float(far[1]), -0.6])
                rot = {0: [0, 90, 0], 1: [-90, 0, 0], 2: [0, 0, 0]}[axis]
                c3 = to_world(axis, at, (0.0, 0.0))
                T = T.rotate(rot).translate([c3[0] if axis == 0 else 0.0, c3[1] if axis == 1 else 0.0, c3[2] if axis == 2 else 0.0])
                hi_half -= T; lo_half -= T
            except Exception as e:
                print("   (label skipped:", repr(e)[:80], ")")
        a_name, b_name = name + "1", name + "2"
        seams.append({"between": [a_name, b_name], "axis": "xyz"[axis], "at": round(float(at), 2), "seam_mm2": round(area, 1),
                      "type": kind, "pins": len(holes), "pin_centres": holes})
        queue += [(a_name, lo_half), (b_name, hi_half)]
    os.makedirs(out, exist_ok=True)
    rep = {"pieces": [], "seams": seams, "pins_total": sum(s["pins"] for s in seams), "pin_type": pins, "bed": bed}
    for name, P, ext, ok in pieces:
        p = os.path.join(out, f"piece_{name}.stl"); mk.save(P, p)
        rep["pieces"].append({"name": name, "file": os.path.basename(p), "fits": ok, "oriented_box_mm": [round(e, 1) for e in ext],
                              "volume_cm3": round(P.volume() / 1000, 1)})
    if pins == "printed" and rep["pins_total"]:
        L = 2 * depth - 1.0                                   # 0.5 mm shorter than the two holes: glue room
        pin = (Manifold.cylinder(0.5, 1.5, 2.0, 48) + Manifold.cylinder(L - 1.0, 2.0, 2.0, 48).translate([0, 0, 0.5])
               + Manifold.cylinder(0.5, 2.0, 1.5, 48).translate([0, 0, L - 0.5]))   # chamfered ends slide in
        pl = [pin.translate([(i % 6) * 7.0, (i // 6) * 7.0, 0]) for i in range(rep["pins_total"])]
        mk.save(Manifold.compose(pl), os.path.join(out, "pins.stl"))
    # exploded preview: push pieces apart from the centre
    scene = []
    allc = np.array([mk.mf2tm(P).bounds.mean(0) for _, P, _, _ in pieces])
    cen = allc.mean(0)
    for (name, P, _, _), c in zip(pieces, allc):
        d = c - cen; d = d / (np.linalg.norm(d) + 1e-9) * 15
        scene.append(mk.mf2tm(P.translate(d.tolist())))
    trimesh.util.concatenate(scene).export(os.path.join(out, "exploded.stl"))
    json.dump(rep, open(os.path.join(out, "split.json"), "w"), indent=1)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("--bed", default=None, help="x,y,z mm (default: printer.json bed minus 10 mm margin)"); ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--pins", default="printed", choices=["printed", "filament", "none"])
    ap.add_argument("--max-pieces", type=int, default=12); ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or os.path.join(forge_env.OUT, "split_" + os.path.splitext(os.path.basename(a.model))[0])
    rep = run(a.model, out, tuple(float(v) for v in a.bed.split(",")) if a.bed else None, a.scale, a.pins, a.max_pieces)
    print(f"{len(rep['pieces'])} pieces, {len(rep['seams'])} seams, {rep['pins_total']} {rep['pin_type']} pins -> {out}")
    for p in rep["pieces"]:
        print(f"   {p['name']:6s} fits={p['fits']}  box {p['oriented_box_mm']}  {p['volume_cm3']} cm3")
    for s in rep["seams"]:
        print(f"   seam {s['between']} on {s['axis']}={s['at']}: {s['seam_mm2']} mm2, {s['type']} ({s['pins']} pins)")
