#!/usr/bin/env python3
"""Print-in-place / moving-part checks, identical for human and Max models.
usage: movecheck.py <model.stl|3mf> [--json out.json]
Reports: bodies, pairwise min gap (mm) between bodies, interpenetration, overhang area %, bbox, volume.
A print-in-place joint on a 0.4 mm nozzle wants gaps ~0.3-0.5 mm: <0.25 fuses, >0.8 rattles.
"""
import sys, json, argparse, itertools
import numpy as np, trimesh

ap = argparse.ArgumentParser(); ap.add_argument("model"); ap.add_argument("--json"); a = ap.parse_args()
m = trimesh.load(a.model, force="mesh")
m.apply_translation([0, 0, -m.bounds[0][2]])
bodies = [b for b in m.split(only_watertight=False) if b.volume > 1.0 or b.area > 20]
bodies.sort(key=lambda b: -abs(b.volume))

def gap(A, B, n=8000):
    """min distance from A's surface to B's surface, and how many A points sit inside B."""
    pa, _ = trimesh.sample.sample_surface_even(A, n, seed=1)
    if len(B.faces) > 60000:  # dense human meshes: B's vertices are ~0.1mm apart -> KD-tree is exact enough + fast
        from scipy.spatial import cKDTree
        d, _ = cKDTree(B.vertices).query(pa)
        gap.close = (d < 0.2).sum()
        return float(d.min()), 0
    _, d, _ = trimesh.proximity.closest_point(B, pa)
    inside = B.contains(pa) if B.is_watertight else np.zeros(len(pa), bool)
    gap.close = ((d < 0.2) | inside).sum()
    return float(d[~inside].min()) if (~inside).any() else 0.0, int(inside.sum())

pairs = []
for (i, A), (j, B) in itertools.combinations(enumerate(bodies), 2):
    if not (np.all(A.bounds[0] - 1 < B.bounds[1]) and np.all(B.bounds[0] - 1 < A.bounds[1])):
        continue  # bboxes 1mm apart -> not a joint
    g1, in1 = gap(A, B); c1 = gap.close; g2, in2 = gap(B, A); c2 = gap.close
    # fuse_risk_mm2: surface area (both sides) closer than 0.2 mm -> will likely weld on a typical FDM printer
    fr = c1 / 8000 * A.area + c2 / 8000 * B.area
    pairs.append({"a": i, "b": j, "min_gap_mm": round(min(g1, g2), 3), "penetrating_pts": in1 + in2, "fuse_risk_mm2": round(float(fr), 1)})

n = m.face_normals; z = m.triangles_center[:, 2]
down = (n[:, 2] < -np.cos(np.radians(45))) & (z > 0.3)
out = {
    "file": a.model.split("/")[-1], "bodies": len(bodies),
    "body_vols": [round(float(b.volume), 1) for b in bodies],
    "joints": pairs,
    "tightest_gap_mm": min([p["min_gap_mm"] for p in pairs], default=None),
    "fuse_risk_mm2": round(sum(p["fuse_risk_mm2"] for p in pairs if p["min_gap_mm"] < 5), 1),
    "overhang_area_pct": round(100 * m.area_faces[down].sum() / m.area, 1),
    "bbox_mm": [round(x, 1) for x in m.extents], "volume_cm3": round(m.volume / 1000, 1),
    "watertight": bool(m.is_watertight),
}
print(json.dumps(out, indent=1))
if a.json: open(a.json, "w").write(json.dumps(out, indent=1))
