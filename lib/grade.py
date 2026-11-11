#!/usr/bin/env python3
"""Score an attempt STL against a ground-truth STL (the real manufacturer/standard STEP from step.parts).

usage: grade.py <attempt.stl> <gt.stl> [--n 200000] [--json out.json]

Pose-free: both meshes are centred on their bbox centre, then all 24 axis-aligned rotations
(+ mirror) of the attempt are tried; the best volume-IoU pose is reported.
Metrics:
  iou        volume intersection-over-union (Monte Carlo, n points)   -> the headline score
  chamfer    mean surface-to-surface distance, both ways (mm)
  h95        95th percentile surface distance (mm): "how far off are the worst bits"
  bbox_err   per-axis bbox size error (mm), sorted dims
  vol_err    attempt volume vs GT volume (%)
"""
import argparse, itertools, json, sys
import numpy as np, trimesh
from scipy.spatial import cKDTree

ap = argparse.ArgumentParser()
ap.add_argument("attempt"); ap.add_argument("gt")
ap.add_argument("--n", type=int, default=200000)
ap.add_argument("--json")
a = ap.parse_args()

def load(p):
    m = trimesh.load(p, force="mesh")
    if not m.is_watertight:  # STEP tessellation seams: weld + patch so inside/outside tests work
        m.merge_vertices(digits_vertex=4); trimesh.repair.fill_holes(m); trimesh.repair.fix_normals(m)
    m.apply_translation(-m.bounds.mean(axis=0))
    return m

A, G = load(a.attempt), load(a.gt)
rng = np.random.default_rng(0)

def rotations():
    seen = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for i, (p, s) in enumerate(zip(perm, signs)): R[i, p] = s
            seen.append(R)  # includes det=-1 (mirrors): fine for symmetric parts, flagged below
    return seen

def vox(m, pitch):
    v = m.voxelized(pitch).fill()
    return set(map(tuple, np.round(v.points / pitch).astype(int)))

def iou(Am, Gm, n):  # voxel IoU on a shared world grid; n -> grid resolution (~n^(1/3) cells per axis... capped)
    pitch = max(Gm.extents) / (60 if n <= 20000 else 140)
    a, g = vox(Am, pitch), vox(Gm, pitch)
    return len(a & g) / len(a | g)

# coarse pose search on bbox-shape match, then IoU on the best few
gd = G.extents
cands = []
for R in rotations():
    T = np.eye(4); T[:3, :3] = R
    ext = np.abs(R @ A.extents)
    cands.append((np.abs(ext - gd).sum(), T))
cands.sort(key=lambda c: c[0])
best = None
for _, T in cands[:12]:
    Am = A.copy(); Am.apply_transform(T)
    s = iou(Am, G, 20000)
    if best is None or s > best[0]: best = (s, T)
Am = A.copy(); Am.apply_transform(best[1])
score = iou(Am, G, a.n)

pa, _ = trimesh.sample.sample_surface(Am, 30000, seed=1)
pg, _ = trimesh.sample.sample_surface(G, 30000, seed=2)
d1, _ = cKDTree(pg).query(pa); d2, _ = cKDTree(pa).query(pg)
d = np.concatenate([d1, d2])
out = {
    "iou": round(float(score), 4),
    "chamfer_mm": round(float(d.mean()), 3),
    "h95_mm": round(float(np.percentile(d, 95)), 3),
    "bbox_attempt": [round(x, 2) for x in sorted(Am.extents)],
    "bbox_gt": [round(x, 2) for x in sorted(G.extents)],
    "vol_attempt": round(float(Am.volume), 1), "vol_gt": round(float(G.volume), 1),
    "vol_err_pct": round(100 * (Am.volume - G.volume) / G.volume, 1),
    "watertight": [bool(A.is_watertight), bool(G.is_watertight)],
    "mirrored_pose": bool(np.linalg.det(best[1][:3, :3]) < 0),
}
print(json.dumps(out, indent=1))
if a.json: open(a.json, "w").write(json.dumps(out, indent=1))
