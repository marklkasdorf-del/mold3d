#!/usr/bin/env python3
"""remix: upgrade ANY model (Printables downloads, AI figures, your own) in one command. venv: .venv-cad

  forge remix in.stl text "HELLO" [--side front|back|left|right|top] [--at U,V] [--size 10] [--height 0.8] [--engrave]
  forge remix in.stl keychain [--side left|right|front|back] [--hole 5]
  forge remix in.stl magnets [--side bottom|back|...] [--count 2] [--magnet 10x2]
  forge remix in.stl thicken [--min 2.0]
  forge remix in.stl fit-head [--circ 547] [--pad 5]       (helmets / masks: scale the INSIDE to your head)
  forge remix in.stl flat [--cut 0.6]  |  mirror [--axis x]  |  scale (--factor F | --height H)
Every op writes <in>_<op>.stl (or --out) and prints what changed (size, volume, genus) so it can be checked.

text: letters follow curved surfaces exactly. Emboss = text prism n (model shifted +h along the face normal);
engrave = model - (text prism n skin of depth d facing that side). Keep text inside one face.
"""
import argparse, json, math, os, sys, tempfile
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import meshkit as mk
import fit
from manifold3d import Manifold

SIDES = {  # outward normal, text right (x), text up (y): right-handed with z = normal
    "front": ((0, -1, 0), (1, 0, 0), (0, 0, 1)), "back": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)), "right": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "top": ((0, 0, 1), (1, 0, 0), (0, 1, 0)), "bottom": ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
}


def load(path):
    M = mk.load_manifold(path)
    return Manifold.compose([q for q in M.decompose() if q.volume() > 0.5])


def text_prism(txt, size, length=200.0, font="Arial Black"):
    from build123d import Text, extrude, Align, export_stl, Pos
    try:
        sk = Text(txt, font_size=size, font=font, align=(Align.CENTER, Align.CENTER))
    except Exception:
        sk = Text(txt, font_size=size, align=(Align.CENTER, Align.CENTER))
    s = Pos(0, 0, -length / 2) * extrude(sk, length)
    fd, p = tempfile.mkstemp(suffix=".stl"); os.close(fd)
    export_stl(s, p, tolerance=0.02, angular_tolerance=0.1)
    T = mk.tm2mf(trimesh.load(p)); os.remove(p)
    return T


def frame(origin, x, y, z):
    R = np.stack([np.array(x, float), np.array(y, float), np.array(z, float)], axis=1)
    return np.hstack([R, np.array(origin, float).reshape(3, 1)])


def surface_point(M, side, at=(0.0, 0.0)):
    """ray from outside along -normal through the face centre (+ offset at=(u,v) in text axes) -> hit point."""
    n, x, y = (np.array(v, float) for v in SIDES[side])
    t = mk.mf2tm(M)
    c = t.bounds.mean(0)
    # project the centre onto the face plane, offset in text axes
    start = c + x * at[0] + y * at[1] + n * (np.linalg.norm(t.extents) + 10)
    loc, idx, _ = t.ray.intersects_location([start], [-n], multiple_hits=False)
    if len(loc) == 0:
        raise SystemExit(f"no surface on the {side} side at offset {at}: move --at")
    return loc[0], n, x, y


def auto_spot(M, side, txt, size):
    """find where text fits on that side: ray-cast a grid -> footprint image -> the point deepest inside it (distance
    transform), text turned along the local long axis (a boomerang arm), size shrunk until the text box fits."""
    from scipy import ndimage
    n, x, y = (np.array(v, float) for v in SIDES[side])
    t = mk.mf2tm(M)
    c = t.bounds.mean(0); ext = np.linalg.norm(t.extents)
    U = np.arange(-ext / 2, ext / 2, 0.5); V = np.arange(-ext / 2, ext / 2, 0.5)
    uu, vv = np.meshgrid(U, V, indexing="ij")
    starts = c[None, :] + uu.ravel()[:, None] * x + vv.ravel()[:, None] * y + n * (ext + 10)
    loc, idx, _ = t.ray.intersects_location(starts, np.tile(-n, (len(starts), 1)), multiple_hits=False)
    hit = np.zeros(len(starts), bool); hit[idx] = True
    depth = np.full(len(starts), np.nan); depth[idx] = loc @ n
    img = hit.reshape(uu.shape)
    # only the outermost "plateau": hits within 1.5 mm of the most common top height (flat face, not the far side)
    dimg = depth.reshape(uu.shape)
    top = np.nanpercentile(dimg[img], 90) if img.any() else 0
    flat = img & (np.abs(dimg - top) < 1.5)
    dist = ndimage.distance_transform_edt(flat) * 0.5
    i, j = np.unravel_index(np.argmax(dist), dist.shape)
    r = float(dist[i, j])
    # local direction: PCA of the flat pixels within 3r
    ii, jj = np.nonzero(flat)
    sel = (ii - i) ** 2 + (jj - j) ** 2 <= (6 * r / 0.5) ** 2
    pts = np.stack([U[ii[sel]], V[jj[sel]]], 1)
    ang = 0.0
    if len(pts) > 10:
        w, vec = np.linalg.eigh(np.cov((pts - pts.mean(0)).T))
        d = vec[:, np.argmax(w)]
        if d[0] < 0: d = -d
        ang = math.degrees(math.atan2(d[1], d[0]))
    return (float(U[i]), float(V[j])), ang, r


def op_text(M, a):
    at = tuple(float(v) for v in a.at.split(","))
    ang = a.rot
    if a.at == "0,0":
        try:
            surface_point(M, a.side, at)
            spot_ok = True
        except SystemExit:
            spot_ok = False
        if not spot_ok or a.auto:
            at, ang_auto, r = auto_spot(M, a.side, a.text, a.size)
            ang = ang_auto if a.rot == 0 else a.rot
            # shrink until the text's long side fits the flat spot (Arial Black ~0.75*size per letter)
            fit_len = 2 * r * 0.95 + 4 * r          # elongated spot: allow along the long axis
            est = 0.75 * a.size * len(a.text)
            if est > fit_len:
                a.size = max(4.5, a.size * fit_len / est)
    p, n, x, y = surface_point(M, a.side, at)
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    x2 = ca * x + sa * y; y2 = -sa * x + ca * y            # rotate the text frame about the normal
    T = text_prism(a.text, a.size).transform(frame(p, x2, y2, n))
    if a.engrave:
        skin = M - M.translate((-n * a.height).tolist())
        out = M - (T ^ skin)
    else:
        out = M + (T ^ M.translate((n * a.height).tolist()))
    return out, {"surface_point": [round(float(v), 2) for v in p], "mode": "engrave" if a.engrave else "emboss",
                 "depth_or_height": a.height, "size": round(a.size, 1), "rotation_deg": round(ang, 1)}


def op_keychain(M, a):
    n = np.array(SIDES[a.side][0], float)
    t = mk.mf2tm(M)
    sec = M.slice(0.3)
    pts = np.concatenate([np.asarray(q) for q in sec.to_polygons()]) if not sec.is_empty() else t.vertices[:, :2]
    d2 = n[:2]
    i = int(np.argmax(pts @ d2)); ex = pts[i]
    hole_r = a.hole / 2; R = hole_r + 3.0
    hmax = float(t.extents[2])
    th = float(min(4.0, max(2.4, hmax)))
    c = ex + d2 * (R - 2.0)                                  # disc overlaps the model by 2 mm
    if np.linalg.norm(c - ex) < hole_r + 1.2 + 0:            # keep the hole itself outside the model footprint
        c = ex + d2 * (hole_r + 1.4)
    disc = mk.cyl(R, 0, th, x=float(c[0]), y=float(c[1]), seg=64)
    hole_c = c + d2 * 0.6
    hole = mk.cyl(hole_r, -1, th + 1, x=float(hole_c[0]), y=float(hole_c[1]), seg=48)
    out = (M + disc) - hole
    return out, {"loop_centre": [round(float(v), 1) for v in hole_c], "hole_mm": a.hole, "thickness": th,
                 "genus_before": M.genus(), "genus_after": out.genus()}


def op_magnets(M, a):
    dia, h = (float(v) for v in a.magnet.lower().split("x"))
    g = fit.get("press_fit")
    side = a.side
    n = np.array(SIDES[side][0], float)
    t = mk.mf2tm(M)
    # the flat face on that side: faces whose normal ~= n, take the biggest planar cluster
    fn = t.face_normals; sel = (fn @ n) > 0.98
    if not sel.any():
        raise SystemExit(f"no flat face on the {side} side")
    depth_vals = t.triangles_center[sel] @ n
    plane = depth_vals.max()                                  # outermost flat face on that side
    on = sel.copy(); on[sel] = np.abs(depth_vals - plane) < 0.05
    # place magnets on that face: sample the face polygon, keep points >= magnet radius + 2 from its edge
    x, y = (np.array(v, float) for v in SIDES[side][1:])
    # sample the face AREA evenly (a flat face can be just 2 big triangles: their centres say nothing about its shape)
    sub = t.submesh([np.nonzero(on)[0]], append=True)
    cen, _ = trimesh.sample.sample_surface_even(sub, int(min(60000, max(3000, sub.area * 4))), seed=0)
    u, v = cen @ x, cen @ y
    U = np.linspace(u.min(), u.max(), 40); V = np.linspace(v.min(), v.max(), 40)
    from scipy.spatial import cKDTree
    tri2d = cKDTree(np.stack([u, v], 1))
    cand = [(uu, vv) for uu in U for vv in V if tri2d.query([uu, vv])[0] < 1.5]
    r_need = dia / 2 + fit.get("min_wall") + 1.6     # +1.6 = the sampling tolerance below, so the real wall stays >= min_wall
    # keep candidates far from the face boundary (distance to the nearest non-face sample)
    good = [c for c in cand if all(tri2d.query([c[0] + r_need * math.cos(k), c[1] + r_need * math.sin(k)])[0] < 1.6
                                   for k in np.linspace(0, 2 * math.pi, 12, endpoint=False))]
    if not good:
        raise SystemExit("face too small for that magnet")
    good = np.array(good)
    picks = [good[np.argmax(((good - good.mean(0)) ** 2).sum(1))]]
    while len(picks) < a.count:
        dd = np.min([((good - q) ** 2).sum(1) for q in picks], axis=0)
        j = int(np.argmax(dd))
        if dd[j] < (dia + 3) ** 2:
            break
        picks.append(good[j])
    out = M
    centres = []
    for uu, vv in picks:
        c3 = x * uu + y * vv + n * plane
        pocket = Manifold.cylinder(h + 0.2 + 0.05, dia / 2 + g, dia / 2 + g, 64)
        # orient cylinder axis along -n (into the part) starting 0.05 outside the face
        z = -n; xx = x; yy = np.cross(z, xx)
        pocket = pocket.transform(frame(c3 + n * 0.05, xx, yy, z))
        out = out - pocket
        centres.append([round(float(q), 1) for q in c3])
    return out, {"magnets": centres, "pocket": f"{dia + 2 * g:.2f} x {h + 0.2:.1f} mm (press-fit, add a drop of CA)"}


def op_thicken(M, a):
    """make every wall at least --min thick, leaving thick parts and surfaces alone.
    Medial approach: D = distance to the surface; ridge voxels of D are the wall's centre surface; where 2*D < min the
    wall is thin -> add a smooth Euclidean ball of radius min/2 around those centre voxels (one pass).
    (v1 dilated 'thin' voxels found by opening: surface roughness counted as thin, every pass grew lumps.)"""
    from scipy import ndimage
    from skimage import measure
    t = mk.mf2tm(M)
    p = a.pitch or max(0.15, min(0.35, max(t.extents) / 450))
    v = t.voxelized(p); V = ndimage.binary_fill_holes(v.matrix)
    pad = int(math.ceil(a.min / p)) + 3
    V = np.pad(V, pad)
    target = a.min + 0.4                                          # margin: voxels + smoothing shave ~0.2-0.3 mm
    D = ndimage.distance_transform_edt(V) * p                     # mm to the nearest surface (0 outside)
    ridge = (D > 0) & (ndimage.maximum_filter(D, size=3) <= D + 1e-6)
    thin_axis = ridge & (2 * D < target)
    Dt = ndimage.distance_transform_edt(~thin_axis) * p
    W = V | (Dt <= target / 2)
    f = ndimage.gaussian_filter(W.astype(np.float32), 0.6)
    verts, faces, _, _ = measure.marching_cubes(f, 0.5)
    verts = (verts - pad) * p + v.transform[:3, 3]
    out_t = trimesh.Trimesh(verts, faces[:, ::-1], process=True)
    if out_t.volume < 0:
        out_t.invert()
    trimesh.smoothing.filter_taubin(out_t, iterations=6)
    out = mk.tm2mf(out_t)
    out = Manifold.compose([q for q in out.decompose() if q.volume() > 0.5])
    return out, {"thin_axis_voxels": int(thin_axis.sum()), "pitch": round(p, 3),
                 "note": "voxel rebuild: details finer than ~1 voxel soften; check the result in a section view"}


def op_fit_head(M, a):
    """smallest scale where a padded HEAD fits inside the helmet everywhere at once (3D interference, not one slice).
    Head proxy = ellipsoid W x L x H (default 160 x 190 x 225, from --circ via the ellipse ratio) grown by --pad, centred on
    the cavity, crown just under the cavity ceiling. Binary search on scale until head  helmet volume < 1 mm3.
    (v1 measured the widest inner slice -> on a full helmet that's the roomy jaw: said 87% when 106% fit.)"""
    t = mk.mf2tm(M)
    z0, z1 = float(t.bounds[0][2]), float(t.bounds[1][2])
    holes = []
    for z in np.linspace(z0 + 0.05 * (z1 - z0), z1 - 0.02 * (z1 - z0), 90):
        for poly in M.slice(float(z)).to_polygons():
            P = np.asarray(poly)
            ar = 0.5 * (P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]).sum()
            if ar < -500:                                     # a real cavity loop (clockwise, > 5 cm2)
                holes.append((float(z), -ar, P.mean(0)))
    if not holes:
        raise SystemExit("no inner cavity found: is this a hollow helmet/mask standing opening-down?")
    ceil = max(h[0] for h in holes)
    big = max(holes, key=lambda h: h[1])
    cx, cy = float(big[2][0]), float(big[2][1])
    # head size: ellipse with the 160:190 width:length ratio scaled to the given circumference (Ramanujan)
    ra, rb = 80.0, 95.0
    per = math.pi * (3 * (ra + rb) - math.sqrt((3 * ra + rb) * (ra + 3 * rb)))
    k = a.circ / per; ra *= k; rb *= k
    rc = a.head_h / 2
    head = Manifold.sphere(1.0, 96).scale([ra + a.pad, rb + a.pad, rc + a.pad])
    def interference(sc):
        Ms = M.scale([sc, sc, sc])
        hz = ceil * sc - a.pad - rc                     # crown (plus pad) just under the scaled ceiling
        Hd = head.translate([cx * sc, cy * sc, hz])
        return mk.inter_vol(Ms, Hd)
    lo_s, hi_s = 0.6, 1.8
    if interference(hi_s) > 1.0:
        raise SystemExit("even at 180% the head proxy hits the helmet: check orientation (opening down, face -Y)")
    for _ in range(22):
        mid = (lo_s + hi_s) / 2
        if interference(mid) > 1.0:
            lo_s = mid
        else:
            hi_s = mid
    s_fit = hi_s
    out = M.scale([s_fit] * 3)
    return out, {"scale": round(s_fit, 4), "scale_pct": round(100 * s_fit, 1), "head_mm": [round(2 * ra, 1), round(2 * rb, 1), a.head_h],
                 "pad_mm": a.pad, "cavity_ceiling_z": round(ceil, 1),
                 "note": "padded head touches no plastic at this scale; print 1-2% larger for comfort foam"}


def op_flat(M, a):
    lo = M.bounding_box()[2]
    out = M.trim_by_plane([0, 0, 1], float(lo + a.cut)).translate([0, 0, -float(lo + a.cut)])
    return out, {"cut_mm": a.cut, "contact_mm2": round(out.slice(0.1).area(), 1)}


def op_mirror(M, a):
    ax = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[a.axis]
    return M.mirror(ax), {"axis": a.axis}


def op_scale(M, a):
    if a.height:
        h = M.bounding_box()[5] - M.bounding_box()[2]
        f = a.height / h
    else:
        f = a.factor
    return M.scale([f, f, f]), {"factor": round(f, 4)}


OPS = {"text": op_text, "keychain": op_keychain, "magnets": op_magnets, "thicken": op_thicken, "fit-head": op_fit_head,
       "flat": op_flat, "mirror": op_mirror, "scale": op_scale}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("op", choices=list(OPS)); ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--out"); ap.add_argument("--side", default=None); ap.add_argument("--at", default="0,0")
    ap.add_argument("--size", type=float, default=10.0); ap.add_argument("--height", type=float, default=None)
    ap.add_argument("--engrave", action="store_true"); ap.add_argument("--hole", type=float, default=5.0)
    ap.add_argument("--count", type=int, default=2); ap.add_argument("--magnet", default="10x2")
    ap.add_argument("--min", type=float, default=2.0); ap.add_argument("--pitch", type=float, default=0.0)
    ap.add_argument("--circ", type=float, default=547.0); ap.add_argument("--pad", type=float, default=5.0)
    ap.add_argument("--head-h", type=float, default=225.0)
    ap.add_argument("--cut", type=float, default=0.6); ap.add_argument("--axis", default="x")
    ap.add_argument("--factor", type=float, default=1.0)
    ap.add_argument("--rot", type=float, default=0.0, help="text rotation about the face normal (deg)")
    ap.add_argument("--auto", action="store_true", help="text: auto-place on the widest flat spot even if the centre hits")
    a = ap.parse_args()
    defaults = {"text": "top", "keychain": "left", "magnets": "bottom"}
    a.side = a.side or defaults.get(a.op, "top")
    if a.height is None:
        a.height = 0.8 if a.op == "text" else None
    M = load(a.model)
    out, info = OPS[a.op](M, a)
    dst = a.out or os.path.splitext(a.model)[0] + f"_{a.op}.stl"
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    mk.save(out, dst)
    b0, b1 = M.bounding_box(), out.bounding_box()
    info.update({"out": dst, "bbox_before": [round(b0[i + 3] - b0[i], 1) for i in range(3)],
                 "bbox_after": [round(b1[i + 3] - b1[i], 1) for i in range(3)],
                 "volume_before_cm3": round(M.volume() / 1000, 2), "volume_after_cm3": round(out.volume() / 1000, 2)})
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
