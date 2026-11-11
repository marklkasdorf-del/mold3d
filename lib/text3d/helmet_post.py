#!/usr/bin/env python3
"""helmet_post.py: AI helmet mesh -> WEARABLE multi-piece helmet sized to a head you specify. venv: .venv-cad

    helmet_post.py raw.glb OUTDIR [--head 160,190] [--wall 3.0] [--pad 5] [--face 0.38] [--rot x+90]
1 neck finder: narrowest cross-section in the lower half = the neck; everything below (shoulders) goes
2 scale so the INSIDE fits the head: inner >= head + 2*pad at the widest level (default 160 x 190 mm; pass --head W,L)
3 hollow: voxel solid -> erode by wall -> shell, cavity opened at the neck
4 split the faceplate off at y = front + face*depth (front piece comes off to put it on)
5 four magnet bosses on the seam (10x2 mm disc magnets, pockets 10.4 x 2.2 each side, glue in, test polarity first)
6 every piece must fit the printer bed (knowledge/printer.json) in some orientation -> report + preflight
"""
import argparse, json, math, os, sys
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import meshkit as mk
import fit
from manifold3d import Manifold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("out")
    ap.add_argument("--head", default="160,190"); ap.add_argument("--wall", type=float, default=3.0)
    ap.add_argument("--pad", type=float, default=5.0); ap.add_argument("--face", type=float, default=0.38)
    ap.add_argument("--rot", default="x+90"); ap.add_argument("--pitch", type=float, default=0.7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    head_w, head_l = (float(v) for v in a.head.split(","))
    t = trimesh.load(a.raw, force="mesh")
    if a.rot == "x+90":
        t.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    t.apply_translation(-t.bounds[0])
    # rough watertight solid first (raw AI meshes are leaky) so slicing/areas are meaningful
    pitch0 = max(t.extents) / 220
    from scipy import ndimage
    from skimage import measure
    v = t.voxelized(pitch0); mat = ndimage.binary_fill_holes(v.matrix)
    H = mat.shape[2]
    areas = mat.sum(axis=(0, 1)).astype(float)
    lo, hi = int(0.12 * H), int(0.62 * H)
    neck = lo + int(np.argmin(ndimage.uniform_filter1d(areas[lo:hi], 5)))
    neck_z = neck * pitch0 + v.transform[2, 3]
    # 2 scale from the widest level ABOVE the neck
    above = mat[:, :, neck:]
    widest = neck + int(np.argmax(above.sum(axis=(0, 1))))
    sl = mat[:, :, widest]
    xs, ys = np.nonzero(sl)
    W0, L0 = (xs.max() - xs.min() + 1) * pitch0, (ys.max() - ys.min() + 1) * pitch0
    need_w, need_l = head_w + 2 * (a.pad + a.wall), head_l + 2 * (a.pad + a.wall)
    s = max(need_w / W0, need_l / L0)
    t.apply_scale(s); t.apply_translation(-t.bounds[0])
    neck_z = (neck_z - v.transform[2, 3]) * s
    # 3 hollow at final scale
    p = a.pitch
    v = t.voxelized(p)
    solid = ndimage.binary_fill_holes(v.matrix)
    kz = int(round(neck_z / p))
    solid[:, :, :max(0, kz)] = False                                   # shoulders gone
    it = int(round(a.wall / p))
    inner = ndimage.binary_erosion(solid, iterations=it)
    inner[:, :, :kz + it + 1] = solid[:, :, :kz + it + 1]              # cavity reaches the neck cut -> open bottom
    shell = solid & ~inner
    shell[:, :, :kz + 1] = False
    # AI helmets are solid heads on a skinny neck stump, so the cavity starts ABOVE solid neck layers (sealed).
    # Open it like a real helmet: take the cavity outline where it first gets wide and punch it down through the bottom.
    cav_area = inner.sum(axis=(0, 1)).astype(float)
    zmax = int(np.argmax(cav_area))
    z_open = next((z for z in range(kz, zmax + 1) if cav_area[z] >= 0.6 * cav_area[zmax]), zmax)
    hole = ndimage.binary_erosion(inner[:, :, z_open], iterations=1)
    for z in range(0, z_open):
        shell[:, :, z] &= ~hole
    pad = 3
    f = ndimage.gaussian_filter(np.pad(shell, pad).astype(np.float32), 0.9)
    verts, faces, _, _ = measure.marching_cubes(f, 0.5)
    verts = (verts - pad) * p + v.transform[:3, 3]
    m = trimesh.Trimesh(verts, faces[:, ::-1], process=True)
    if m.volume < 0:
        m.invert()
    parts = m.split(only_watertight=False)
    m = max(parts, key=lambda q: abs(q.volume))
    trimesh.smoothing.filter_taubin(m, iterations=10)
    if len(m.faces) > 600000:
        import fast_simplification
        vv, ff = fast_simplification.simplify(m.vertices, m.faces, 1 - 600000 / len(m.faces)); m = trimesh.Trimesh(vv, ff)
    m.apply_translation([-m.bounds.mean(0)[0], -m.bounds.mean(0)[1], -m.bounds[0][2]])
    # inner fit check at the widest level
    zc = (widest - neck) * pitch0 * s
    inner_sec = inner[:, :, min(inner.shape[2] - 1, kz + int(round(zc / p)))]
    ix, iy = np.nonzero(inner_sec)
    fit_w, fit_l = ((ix.max() - ix.min() + 1) * p, (iy.max() - iy.min() + 1) * p) if len(ix) else (0, 0)
    M = mk.tm2mf(mk.repair(m) if not m.is_watertight else m)
    M = Manifold.compose([q for q in M.decompose() if q.volume() > 50])
    # 4 faceplate split (face points -Y after the x+90 rotation)
    bb = M.bounding_box(); y0, y1 = bb[1], bb[4]
    ys_ = y0 + a.face * (y1 - y0)
    back, front = M.split_by_plane([0, 1, 0], float(ys_))
    # 5 magnet bosses + pockets on the seam ring (4 points: upper-left/right, lower-left/right of the ring)
    ring = M.rotate([90, 0, 0]).slice(float(ys_))                     # plane y = ys_ (Rx(90): z' = y)
    P = np.concatenate([np.asarray(q) for q in ring.to_polygons()]) if not ring.is_empty() else np.zeros((0, 2))
    mags = []
    if len(P):
        cx, cz = P[:, 0].mean(), (-P[:, 1]).mean()
        cand = {}
        for q in P:
            x, z = q[0], -q[1]
            key = ("L" if x < cx else "R") + ("U" if z > cz else "D")
            score = abs(x - cx) * 0.6 + abs(z - cz)
            if key not in cand or score > cand[key][0]:
                cand[key] = (score, x, z)
        g = fit.get("press_fit")
        for key, (_, x, z) in cand.items():
            d = np.array([cx - x, cz - z]); d = d / (np.linalg.norm(d) + 1e-9)
            bx, bz = x + d[0] * (a.wall + 4.0), z + d[1] * (a.wall + 4.0)   # boss centre just inside the wall
            boss = Manifold.cylinder(12.0, 7.0, 7.0, 48, True).rotate([90, 0, 0]).translate([bx, ys_, bz])
            boss = boss ^ mk.box(bb[0] - 5, bb[1] - 5, max(bb[2], float(neck_z) * 0 + bb[2]) - 5, bb[3] + 5, bb[4] + 5, bb[5] + 5)
            pock = Manifold.cylinder(2.2, 5.2 + g, 5.2 + g, 48).rotate([90, 0, 0])
            back = back + (boss ^ mk.box(bb[0] - 5, ys_, bb[2] - 5, bb[3] + 5, ys_ + 6, bb[5] + 5))
            front = front + (boss ^ mk.box(bb[0] - 5, ys_ - 6, bb[2] - 5, bb[3] + 5, ys_, bb[5] + 5))
            back = back - pock.translate([bx, ys_ + 2.2, bz])                  # pocket into the back half
            front = front - pock.translate([bx, ys_, bz])                      # pocket into the face half
            mags.append([round(float(bx), 1), round(float(ys_), 1), round(float(bz), 1)])
    rep = {"scale": round(s, 3), "neck_cut_z": round(float(neck_z), 1), "inner_fit_mm": [round(fit_w, 1), round(fit_l, 1)],
           "head_mm": [head_w, head_l], "wall_mm": a.wall, "magnets": mags, "pieces": {}}
    import split as sp
    import printer
    for nm, piece in (("shell", back), ("faceplate", front)):
        piece = Manifold.compose([q for q in piece.decompose() if q.volume() > 50])
        path = os.path.join(a.out, f"helmet_{nm}.stl"); mk.save(piece, path)
        ok, ext = sp.fits(piece, printer.bed())
        rep["pieces"][nm] = {"file": path, "fits_bed": ok, "oriented_box_mm": [round(e, 1) for e in ext], "volume_cm3": round(piece.volume() / 1000, 1)}
    mk.save(back + front, os.path.join(a.out, "helmet_assembled.stl"))
    json.dump(rep, open(os.path.join(a.out, "helmet.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
