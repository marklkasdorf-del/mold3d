"""forge verify: numeric print-readiness checks on an STL (trimesh + numpy/scipy only).

No rtree/shapely/embree needed: wall thickness is brute-force numpy ray casting,
assembly fit is a numpy scanline voxelizer + exact point-triangle distances.
Every check returns a row {name, status: PASS|WARN|FAIL, value, detail}.
Defaults only FAIL on definitely-bad things (open mesh, inverted, floating bodies,
too big for bed, empty); soft limits (walls, supports) become hard when the spec sets them.
"""
import json, math, sys
import numpy as np
import trimesh

PLA_G_CM3 = 1.24
try:
    import printer
    DEFAULT_BED = list(printer.bed())      # knowledge/printer.json
except Exception:
    DEFAULT_BED = [220.0, 220.0, 250.0]


def row(name, status, value, detail=""):
    return {"name": name, "status": status, "value": value, "detail": detail}


# ---------------------------------------------------------------- geometry helpers
def load_mesh(path):
    m = trimesh.load(path, force="mesh", process=True)
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise ValueError(f"{path}: no triangles")
    return m


def tri_ray_first_hit(origins, dirs, tris, chunk_elems=6_000_000, return_idx=False):
    """Brute-force Moller-Trumbore. Returns nearest hit distance per ray (inf if none).
    origins/dirs (N,3); tris (F,3,3)."""
    v0 = tris[:, 0]; e1 = tris[:, 1] - v0; e2 = tris[:, 2] - v0
    F = len(tris)
    out = np.full(len(origins), np.inf)
    idx = np.zeros(len(origins), dtype=int)
    step = max(1, chunk_elems // max(F, 1))
    for s in range(0, len(origins), step):
        o = origins[s:s + step][:, None, :]; d = dirs[s:s + step][:, None, :]
        p = np.cross(d, e2[None])                      # (n,F,3)
        det = np.einsum("fk,nfk->nf", e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        t0 = o - v0[None]
        u = np.einsum("nfk,nfk->nf", t0, p) * inv
        q = np.cross(t0, e1[None])
        v = np.einsum("nfk,nfk->nf", d, q) * inv
        t = np.einsum("fk,nfk->nf", e2, q) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-5)
        tt = np.where(hit, t, np.inf)
        out[s:s + step] = tt.min(axis=1); idx[s:s + step] = tt.argmin(axis=1)
    return (out, idx) if return_idx else out


def pt_tri_dist(P, T):
    """Exact distance from points P (n,3) to triangles T (n,3,3), pairwise."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    n = np.cross(b - a, c - a)
    nn = np.linalg.norm(n, axis=1, keepdims=True); nn[nn == 0] = 1
    n = n / nn
    d_plane = np.einsum("ij,ij->i", P - a, n)
    proj = P - d_plane[:, None] * n
    # inside test by barycentric signs
    def side(p, q, r): return np.einsum("ij,ij->i", np.cross(q - p, r - p), n)
    s1 = side(a, b, proj); s2 = side(b, c, proj); s3 = side(c, a, proj)
    inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
    def seg(p, q, r):  # distance r -> segment pq
        pq = q - p; t = np.einsum("ij,ij->i", r - p, pq) / np.maximum(np.einsum("ij,ij->i", pq, pq), 1e-18)
        t = np.clip(t, 0, 1)
        return np.linalg.norm(r - (p + t[:, None] * pq), axis=1)
    d_edge = np.minimum(np.minimum(seg(a, b, P), seg(b, c, P)), seg(c, a, P))
    return np.where(inside, np.abs(d_plane), d_edge)


def voxel_inside(mesh, lo, hi, pitch):
    """Solid occupancy (bool grid) of `mesh` over box [lo,hi) via z-scanline winding fill.
    Voxel (i,j,k) centre = lo + (idx+0.5)*pitch. Exact-ish (no shell dilation)."""
    shape = np.maximum(np.ceil((hi - lo) / pitch).astype(int), 1)
    nx, ny, nz = shape
    diff = np.zeros((nx, ny, nz + 1), dtype=np.int16)
    jit = np.array([0.0137, 0.0071]) * pitch               # dodge shared-edge double hits
    tri = mesh.triangles
    nzn = mesh.face_normals[:, 2]
    keep = np.abs(nzn) > 1e-9                              # vertical faces never cross a z ray
    lo_xy, hi_xy = lo[:2], hi[:2]
    tmin = tri[:, :, :2].min(axis=1); tmax = tri[:, :, :2].max(axis=1)
    keep &= (tmax[:, 0] >= lo_xy[0]) & (tmin[:, 0] <= hi_xy[0]) & (tmax[:, 1] >= lo_xy[1]) & (tmin[:, 1] <= hi_xy[1])
    for f in np.nonzero(keep)[0]:
        t = tri[f]
        i0 = max(int(math.floor((t[:, 0].min() - lo[0] - jit[0]) / pitch - 0.5)), 0)
        i1 = min(int(math.ceil((t[:, 0].max() - lo[0] - jit[0]) / pitch - 0.5)), nx - 1)
        j0 = max(int(math.floor((t[:, 1].min() - lo[1] - jit[1]) / pitch - 0.5)), 0)
        j1 = min(int(math.ceil((t[:, 1].max() - lo[1] - jit[1]) / pitch - 0.5)), ny - 1)
        if i1 < i0 or j1 < j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
        px = lo[0] + (ii + 0.5) * pitch + jit[0]; py = lo[1] + (jj + 0.5) * pitch + jit[1]
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-14:
            continue
        w1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        w2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        w3 = 1 - w1 - w2
        m = (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
        if not m.any():
            continue
        z = w1[m] * az + w2[m] * bz + w3[m] * cz
        k = np.ceil((z - lo[2]) / pitch - 0.5).astype(int)   # first voxel centre >= z
        k = np.clip(k, 0, nz)
        s = 1 if nzn[f] < 0 else -1                          # ray going +z: enter on downward faces
        np.add.at(diff, (ii[m], jj[m], k), s)
    return np.cumsum(diff, axis=2)[:, :, :nz] > 0


# ---------------------------------------------------------------- single-part verify
def _wall_single(mesh, min_wall, seed=0):
    """Shape-diameter style on ONE connected body: from sampled surface points cast a ray along -normal;
    first hit distance = local wall thickness. Returns (dict, d_valid_array)."""
    area = float(mesh.area)
    F = len(mesh.faces)
    n = int(np.clip(area / 1.0, 1500, max(500, int(3e8 / max(F, 1)))))
    pts, fi = trimesh.sample.sample_surface(mesh, n, seed=seed)
    nor = mesh.face_normals[fi]
    org = pts - nor * 1e-3
    d, hit_i = tri_ray_first_hit(org, -nor, mesh.triangles, return_idx=True)
    # An ACUTE EDGE (e.g. a slot meeting a floor at 65 deg) gives tiny ray distances next to the edge although there is no thin WALL.
    # A real wall = the hit face roughly opposes the start face (n . n_hit < -0.5). Field test 2026-10-14 (air_stand) false FAIL.
    opposing = np.einsum("ij,ij->i", nor, mesh.face_normals[hit_i]) < -0.5
    good = np.isfinite(d) & opposing
    thin = (d < (min_wall - 1e-3)) & opposing
    res = {"samples": n, "thin_samples": int(thin.sum()), "thin_area_mm2": float(thin.sum() * area / n), "clusters": []}
    if thin.any():
        cell = np.floor(pts[thin] / 5.0).astype(int)           # cluster in 5 mm cells
        keys, inv = np.unique(cell, axis=0, return_inverse=True)
        for k in range(len(keys)):
            sel = inv == k
            p = pts[thin][sel]; dd = d[thin][sel]
            res["clusters"].append({"center_mm": [round(float(x), 1) for x in p.mean(0)],
                                    "min_thickness_mm": round(float(dd.min()), 2),
                                    "area_mm2": round(float(sel.sum() * area / n), 1)})
    return res, d[good]


def wall_thickness(mesh, min_wall, seed=0):
    """Wall thickness measured ONE CONNECTED BODY AT A TIME (idea from text-to-cad dfam-check): cast against a whole
    assembly, a ray can leave one body, cross the mating clearance and land on its neighbour, recording the fit gap as a wall.
    Returns min, p05 (a robust 'thin' signal when min is a sampling outlier), thin area and thin clusters."""
    bodies = [b for b in mesh.split(only_watertight=False) if len(b.faces) >= 4] or [mesh]
    total = {"samples": 0, "thin_samples": 0, "thin_area_mm2": 0.0, "clusters": [], "bodies": len(bodies)}
    ds = []
    for i, b in enumerate(bodies):
        r, dv = _wall_single(b, min_wall, seed + i)
        total["samples"] += r["samples"]; total["thin_samples"] += r["thin_samples"]
        total["thin_area_mm2"] += r["thin_area_mm2"]; total["clusters"] += r["clusters"]; ds.append(dv)
    dall = np.concatenate(ds) if ds else np.array([])
    total["min_mm"] = float(dall.min()) if len(dall) else None
    total["p05_mm"] = float(np.percentile(dall, 5)) if len(dall) else None
    total["clusters"].sort(key=lambda c: -c["area_mm2"]); total["clusters"] = total["clusters"][:8]
    return total


def overhang(mesh, zmin, angle=45.0):
    """Downward faces flatter than `angle` from horizontal, excluding faces on the bed plane."""
    nz = mesh.face_normals[:, 2]
    low = mesh.triangles[:, :, 2].max(axis=1) <= zmin + 0.05
    thresh = -math.sin(math.radians(angle))
    bad = (nz < thresh) & ~low
    a = mesh.area_faces
    levels = {}
    zc = mesh.triangles_center[:, 2]
    for z, ar in zip(np.round(zc[bad], 0), a[bad]):
        levels[z] = levels.get(z, 0) + ar
    top = sorted(levels.items(), key=lambda kv: -kv[1])[:3]
    return float(a[bad].sum()), [{"z_mm": float(z), "area_mm2": round(float(ar), 1)} for z, ar in top]


def verify(path, spec=None):
    spec = spec or {}
    rows = []
    m = load_mesh(path)
    ext = m.extents; mn, mx = m.bounds
    wt = bool(m.is_watertight)
    _, cnt = np.unique(m.edges_sorted, axis=0, return_counts=True)
    open_edges = int((cnt == 1).sum()); nonmanifold = int((cnt > 2).sum())
    wind = bool(m.is_winding_consistent)
    bodies = m.split(only_watertight=False)
    ncomp = len(bodies)
    vol = float(m.volume) if wt else float(abs(m.volume))
    info = {"file": str(path), "bbox_mm": [round(float(x), 3) for x in ext],
            "bounds_min": [round(float(x), 3) for x in mn], "faces": int(len(m.faces)),
            "volume_mm3": round(vol, 1), "mass_g_pla": round(vol / 1000 * PLA_G_CM3, 1),
            "surface_area_mm2": round(float(m.area), 1), "watertight": wt, "winding_consistent": wind,
            "components": ncomp}
    # --- topology
    must_wt = spec.get("must_be_watertight", True)
    rows.append(row("watertight", "PASS" if wt else ("FAIL" if must_wt else "WARN"), wt,
                    "" if wt else f"{open_edges} open + {nonmanifold} non-manifold edges; mesh has holes -> slicer may drop/garble features"))
    rows.append(row("winding", "PASS" if wind else "FAIL", wind, "" if wind else "inconsistent triangle winding (flipped faces)"))
    inverted = wt and m.volume < 0
    rows.append(row("normals_outward", "FAIL" if inverted else "PASS", not inverted, "volume is negative: mesh is inside-out" if inverted else ""))
    rows.append(row("non_empty", "PASS" if vol > 1.0 else "FAIL", round(vol, 1), "" if vol > 1.0 else "volume ~0: a boolean probably deleted the part"))
    want_c = spec.get("components", 1)
    rows.append(row("components", "PASS" if ncomp == want_c else "FAIL", ncomp,
                    f"expected {want_c}" + ("" if ncomp == want_c else " (floating/disconnected bodies; if intentional set spec components)")))
    small = [round(float(b.volume), 1) for b in bodies if abs(b.volume) < 5.0]
    if small and ncomp > 1:
        rows.append(row("tiny_bodies", "WARN", small, "bodies <5 mm3 are probably debris"))
    # --- bed
    bed = spec.get("bed", DEFAULT_BED)
    fits = all(e <= b + 1e-6 for e, b in zip(ext, bed))
    swap = (ext[1] <= bed[0] and ext[0] <= bed[1] and ext[2] <= bed[2])
    rows.append(row("bed_fit", "PASS" if fits else "FAIL", [round(float(x), 1) for x in ext],
                    f"bed {bed}" + ("" if fits else (" - fits if rotated 90deg about Z" if swap else " - too big: scale, split, or reorient"))))
    # --- units sanity (a metres/inches export reads as a speck and silently passes every other check)
    diag = float(np.linalg.norm(ext))
    info["bbox_diagonal_mm"] = round(diag, 2)
    if diag < 2.0:
        rows.append(row("units", "WARN", round(diag, 3), "bbox diagonal < 2 mm: the mesh is probably in metres or inches (1 STL unit must be 1 mm); rescale before trusting any number"))
    # --- bed contact
    zmin = float(mn[2])
    nz = m.face_normals[:, 2]
    onbed = (nz < -0.99) & (m.triangles[:, :, 2].max(axis=1) <= zmin + 0.05)
    contact = float(m.area_faces[onbed].sum())
    info["bed_contact_mm2"] = round(contact, 1)
    footprint = float(ext[0] * ext[1])
    status = "PASS" if contact >= 20 else "WARN"
    rows.append(row("bed_contact", status, round(contact, 1),
                    f"{contact / footprint * 100:.0f}% of bbox footprint on z-min" + ("" if status == "PASS" else "; <20 mm2 -> weak first layer/needs brim; consider flipping")))
    if abs(zmin) > 0.01:
        rows.append(row("z_min", "WARN", round(zmin, 3), "part not sitting at z=0 (slicer will drop it; fine for assemblies)"))
    # --- overhangs / supports
    oh_area, levels = overhang(m, zmin)
    pct = oh_area / max(float(m.area), 1e-9) * 100
    info["overhang_area_mm2"] = round(oh_area, 1); info["support_pct"] = round(pct, 1); info["overhang_levels"] = levels
    lim = spec.get("max_support_pct")
    st = "PASS" if pct <= (lim if lim is not None else 10) else ("FAIL" if lim is not None else "WARN")
    rows.append(row("supports", st, round(pct, 1), f"{oh_area:.0f} mm2 of surface is >45deg overhang (limit {lim if lim is not None else '10 (soft)'}%); worst z-levels {levels}"))
    # --- walls
    mw = spec.get("min_wall_mm")
    tw = wall_thickness(m, mw if mw is not None else 1.2)
    info["wall"] = tw
    thin_bad = tw["thin_area_mm2"] >= 1.0
    st = "PASS" if not thin_bad else ("FAIL" if mw is not None else "WARN")
    detail = (f"min seen {tw['min_mm']:.2f} mm, p05 {tw['p05_mm']:.2f} mm" if tw["min_mm"] is not None else "no inward hits") + (f", measured per body x{tw['bodies']}" if tw["bodies"] > 1 else "")
    if thin_bad:
        detail += f"; ~{tw['thin_area_mm2']:.0f} mm2 below {mw if mw is not None else 1.2} mm at " + "; ".join(
            f"{c['center_mm']} ({c['min_thickness_mm']}mm)" for c in tw["clusters"][:4])
    rows.append(row("min_wall", st, None if tw["min_mm"] is None else round(tw["min_mm"], 2), detail))
    # --- spec asserts
    if "bbox_mm" in spec:
        tol = spec.get("bbox_tol", 0.5)
        want = spec["bbox_mm"]
        ok = all(abs(a - b) <= tol for a, b in zip(ext, want))
        rows.append(row("spec_bbox", "PASS" if ok else "FAIL", [round(float(x), 2) for x in ext], f"want {want} +-{tol}"))
    if "volume_mm3" in spec:
        lo, hi = spec["volume_mm3"]
        ok = lo <= vol <= hi
        rows.append(row("spec_volume", "PASS" if ok else "FAIL", round(vol, 1), f"want [{lo}, {hi}]" + ("" if ok else " (a boolean may have dropped/duplicated geometry)")))
    status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else ("WARN" if any(r["status"] == "WARN" for r in rows) else "PASS")
    return {"status": status, "info": info, "checks": rows}


# ---------------------------------------------------------------- print orientation candidates
def orientations(path, bed=None, angle=45.0):
    """Rank the 6 axis-aligned ways to lay the part on the bed (idea from text-to-cad dfam-check `orientations`).
    Per candidate: overhang/support area (mm2 and % of surface), bed-contact patch, build height, bed fit.
    Recommendation = fits the bed, least support area, then biggest contact patch, then lowest height."""
    bed = bed or DEFAULT_BED
    m0 = load_mesh(path)
    rots = {"as_is (+Z up)": np.eye(4),
            "flip_180_x (upside down)": trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]),
            "rot_+90_x": trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]),
            "rot_-90_x": trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]),
            "rot_+90_y": trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]),
            "rot_-90_y": trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])}
    out = []
    for name, T in rots.items():
        m = m0.copy(); m.apply_transform(T)
        zmin = float(m.bounds[0][2])
        oh, _ = overhang(m, zmin, angle)
        onbed = (m.face_normals[:, 2] < -0.99) & (m.triangles[:, :, 2].max(axis=1) <= zmin + 0.05)
        ext = m.extents
        fits = bool(ext[0] <= bed[0] and ext[1] <= bed[1] and ext[2] <= bed[2]) or bool(ext[1] <= bed[0] and ext[0] <= bed[1] and ext[2] <= bed[2])
        out.append({"orientation": name, "support_area_mm2": round(oh, 1), "support_pct": round(oh / max(float(m.area), 1e-9) * 100, 1),
                    "bed_contact_mm2": round(float(m.area_faces[onbed].sum()), 1), "height_mm": round(float(ext[2]), 1), "fits_bed": fits})
    ok = [o for o in out if o["fits_bed"]]
    best = min(ok, key=lambda o: (round(o["support_area_mm2"], 0), -o["bed_contact_mm2"], o["height_mm"])) if ok else None
    return {"status": "PASS", "info": {"file": str(path), "angle_limit_deg": angle, "recommended": best["orientation"] if best else None,
            "note": "axis-aligned rotations only; support area = down-facing faces steeper-than-limit counted as in `verify`, bed plane excluded"},
            "candidates": out}


def format_orient(res):
    L = [f"ORIENTATIONS for {res['info']['file']}  (overhang limit {res['info']['angle_limit_deg']} deg)", "",
         f"  {'orientation':<26}{'support mm2':>12}{'support %':>10}{'bed mm2':>10}{'height':>8}  fits"]
    for o in res["candidates"]:
        star = " <- recommended" if o["orientation"] == res["info"]["recommended"] else ""
        L.append(f"  {o['orientation']:<26}{o['support_area_mm2']:>12}{o['support_pct']:>10}{o['bed_contact_mm2']:>10}{o['height_mm']:>8}  {'yes' if o['fits_bed'] else 'NO'}{star}")
    L += ["", "  note: " + res["info"]["note"], "  To use a non-current orientation, re-seat the part in its script (rotate, then translate so bbox.min.Z == 0)."]
    return "\n".join(L)


# ---------------------------------------------------------------- assembly fit
def assembly(path_a, path_b, clearance=0.2, move_a=(0, 0, 0), move_b=(0, 0, 0), allow_contact=True, tol=0.02):
    """Interference (exact solid overlap volume) + min gap between two mating parts."""
    a = load_mesh(path_a); b = load_mesh(path_b)
    a.apply_translation(move_a); b.apply_translation(move_b)
    rows = []
    # --- interference: voxel overlap inside intersection bbox
    lo = np.maximum(a.bounds[0], b.bounds[0]) - 0.5; hi = np.minimum(a.bounds[1], b.bounds[1]) + 0.5
    inter = {"volume_mm3": 0.0, "pitch": None, "bbox": None}
    if np.all(hi > lo):
        vol_box = float(np.prod(hi - lo))
        pitch = max(0.1, (vol_box / 2.5e7) ** (1 / 3))
        occ = voxel_inside(a, lo, hi, pitch) & voxel_inside(b, lo, hi, pitch)
        inter["pitch"] = round(pitch, 3)
        inter["volume_mm3"] = round(float(occ.sum() * pitch ** 3), 2)
        if occ.any():
            idx = np.argwhere(occ)
            inter["bbox"] = [[round(float(x), 1) for x in lo + idx.min(0) * pitch], [round(float(x), 1) for x in lo + (idx.max(0) + 1) * pitch]]
    ok = inter["volume_mm3"] <= 0.5
    rows.append(row("interference", "PASS" if ok else "FAIL", inter["volume_mm3"],
                    f"solid overlap mm3 (pitch {inter['pitch']})" + ("" if ok else f" at {inter['bbox']}: parts collide; add clearance or shrink the male part")))
    # --- gap: from sampled points of each part cast along the OUTWARD normal onto the other part.
    # (normal-direction clearance = what a printed gap/slip fit means; plain closest-distance would
    # just read ~0 at the edge of any seated contact patch). Contact (<tol) is reported separately.
    R = max(clearance * 6, 3.0)
    def one_way(src, dst):
        n = int(np.clip(src.area / 0.25, 2000, 60000))
        pts, fi = trimesh.sample.sample_surface(src, n, seed=1)
        nor = src.face_normals[fi]
        lo2, hi2 = dst.bounds[0] - R, dst.bounds[1] + R
        sel = np.all((pts >= lo2) & (pts <= hi2), axis=1)
        pts, nor = pts[sel], nor[sel]
        back = 0.05                                  # start slightly inside src so seated faces register as d~0
        d = tri_ray_first_hit(pts - nor * back, nor, dst.triangles) - back
        w = np.full(len(d), src.area / n)           # mm2 represented by each sample
        ok = d <= R
        return d[ok], w[ok]
    d1, w1 = one_way(a, b); d2, w2 = one_way(b, a)
    dall = np.concatenate([d1, d2]); wall_ = np.concatenate([w1, w2])
    seat = 0.0
    gap = None
    if len(dall) == 0:
        rows.append(row("min_gap", "PASS", f">{R:.1f}", "no surfaces face each other within search radius"))
    else:
        touching = dall < tol
        seat = float(wall_[touching].sum() / 2)      # both directions see the same patch
        nontouch = dall[~touching] if allow_contact else dall
        gap = float(nontouch.min()) if len(nontouch) else None
        if inter["volume_mm3"] > 0.5:
            rows.append(row("min_gap", "FAIL", round(float(dall.min()), 3), "parts overlap"))
        elif gap is None:
            rows.append(row("min_gap", "PASS", 0.0, "parts only touch (seated contact)"))
        else:
            okg = gap >= clearance - tol
            rows.append(row("min_gap", "PASS" if okg else "FAIL", round(gap, 3),
                            f"closest facing surfaces along normals; need >= {clearance} mm clearance" + ("" if okg else " -> too tight to print/assemble: enlarge by that clearance")))
        if allow_contact:
            rows.append(row("seated_contact_mm2", "PASS", round(seat, 1), "surface within 0.02 mm (lid resting on rim etc.), not counted as a fault"))
    status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    return {"status": status, "info": {"a": str(path_a), "b": str(path_b), "move_a": list(move_a), "move_b": list(move_b),
                                      "clearance": clearance, "interference": inter, "min_gap_mm": gap}, "checks": rows}


def format_text(res):
    out = [f"STATUS: {res['status']}"]
    for k, v in res["info"].items():
        if k in ("wall", "overhang_levels"):
            continue
        out.append(f"  {k}: {v}")
    out.append("")
    for r in res["checks"]:
        out.append(f"  [{r['status']:4}] {r['name']:<18} {str(r['value']):<22} {r['detail']}")
    return "\n".join(out)
