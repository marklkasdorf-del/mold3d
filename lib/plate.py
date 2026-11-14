#!/usr/bin/env python3
"""plate: pack parts onto the printer bed for ONE print job (batches to sell, or a whole project at once). venv: .venv-cad

    forge plate a.stl [b.stl ...] [--copies 6] [--fill] [--gap 4] [--slice]
--copies N : N of each part.   --fill : as many of the (first) part as fit.   --slice : slicer hook -> time, grams,
             and per-item cost (shop brain). Parts keep their print pose (flat side down); only rotate about Z.
Packing: each part is turned about Z to its smallest footprint, then shelf-packed largest-first into the usable bed area
(5 mm margin). Writes mold3d/plate/<name>/plate.stl + plate.png (top view).
"""
import argparse, json, math, os, subprocess, sys
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
FORGE = os.path.dirname(HERE)
import printer, forge_env
_B = printer.bed()
BEDX, BEDY = _B[0] - 10.0, _B[1] - 10.0     # usable area = bed minus a 5 mm margin per side


def footprint(t):
    """rotation about Z (deg) giving the smallest bbox footprint, and that bbox (w, h)."""
    pts = t.vertices[:, :2]
    from scipy.spatial import ConvexHull
    hull = pts[ConvexHull(pts).vertices]
    best = None
    for a in np.arange(0, 180, 3):
        r = math.radians(a); R = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])
        q = hull @ R.T; w, h = q.max(0) - q.min(0)
        if best is None or w * h < best[0]:
            best = (w * h, a, w, h)
    return best[1], best[2], best[3]


def shelf_pack(rects, gap):
    """rects: list of (id, w, h). Returns placements {id: (x, y, rotated)} for those that fit (largest first)."""
    order = sorted(rects, key=lambda r: -max(r[1], r[2]))
    x = y = shelf_h = 0.0
    out = {}
    for rid, w, h in order:
        if w < h:                                                 # lay long side along X
            w, h, rot = h, w, True
        else:
            rot = False
        if w > BEDX or h > BEDY:
            continue
        if x + w > BEDX:
            x, y, shelf_h = 0.0, y + shelf_h + gap, 0.0
        if y + h > BEDY:
            continue
        out[rid] = (x, y, rot, w, h)
        x += w + gap; shelf_h = max(shelf_h, h)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="+"); ap.add_argument("--copies", type=int, default=1)
    ap.add_argument("--fill", action="store_true"); ap.add_argument("--gap", type=float, default=4.0)
    ap.add_argument("--slice", action="store_true"); ap.add_argument("--name")
    a = ap.parse_args()
    meshes = []
    for p in a.parts:
        t = trimesh.load(p, force="mesh"); t.apply_translation([0, 0, -t.bounds[0][2]])
        ang, w, h = footprint(t)
        t.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ang), [0, 0, 1]))
        t.apply_translation([-t.bounds[0][0], -t.bounds[0][1], 0])
        meshes.append((os.path.basename(p), t, w, h))
    n = 400 if a.fill else a.copies
    rects = []
    src = meshes[:1] if a.fill else meshes
    for i, (nm, t, w, h) in enumerate(src):
        for c in range(n):
            rects.append(((i, c), w, h))
    place = shelf_pack(rects, a.gap)
    plate = []
    for (i, c), (x, y, rot, w, h) in place.items():
        t = src[i][1].copy()
        if rot:
            t.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 0, 1]))
            t.apply_translation([-t.bounds[0][0], -t.bounds[0][1], 0])
        t.apply_translation([x + 5, y + 5, 0])
        plate.append(t)
    if not plate:
        raise SystemExit("nothing fits the bed (part bigger than the usable bed area?) -> forge split it")
    allm = trimesh.util.concatenate(plate)
    allm.apply_translation([-_B[0] / 2, -_B[1] / 2, 0])                       # bed centre at the origin
    name = a.name or os.path.splitext(os.path.basename(a.parts[0]))[0] + (f"_x{len(plate)}")
    d = os.path.join(forge_env.OUT, "plate", name); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "plate.stl"); allm.export(f)
    # top-view preview
    from PIL import Image, ImageDraw
    S = 3
    im = Image.new("RGB", (int(_B[0] * S), int(_B[1] * S)), (231, 220, 198)); dr = ImageDraw.Draw(im)
    for k in range(0, int(max(_B[0], _B[1])) + 1, 10):
        c = (199, 185, 153) if k % 50 == 0 else (214, 202, 176)
        dr.line([(k * S, 0), (k * S, _B[1] * S)], fill=c); dr.line([(0, k * S), (_B[0] * S, k * S)], fill=c)
    for t in plate:
        sec = t.section(plane_origin=[0, 0, 0.2], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        p2, _ = sec.to_2D() if hasattr(sec, "to_2D") else sec.to_planar()
        for poly in p2.polygons_full:
            xy = np.asarray(poly.exterior.coords)
            # to_planar recentres; use the 3D section vertices instead for exact placement
        for ent in sec.discrete:
            pts = [((px) * S, (_B[1] - py) * S) for px, py in ent[:, :2] + 0]
            if len(pts) > 2:
                dr.polygon(pts, fill=(120, 116, 108), outline=(58, 54, 49))
    im.save(os.path.join(d, "plate.png"))
    info = {"plate": f, "items": len(plate), "preview": os.path.join(d, "plate.png"),
            "bbox_mm": [round(float(v), 1) for v in allm.extents]}
    if a.slice:
        t, g = printer.slice_stats(f, "off")
        if t: info["time"] = t
        if g: info["grams"] = g
        if not t and not g: info["note"] = "no slicer hook configured (printer.json slicer_cmd / FORGE_SLICER_CMD)"
        if "grams" in info:
            info["per_item_g"] = round(info["grams"] / len(plate), 2)
            info["per_item_filament_usd"] = round(info["grams"] / len(plate) / 1000 * 20, 2)
    json.dump(info, open(os.path.join(d, "plate.json"), "w"), indent=1)
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
