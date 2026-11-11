"""sculpt.py: the ORGANIC lane. Signed-distance-field modeling with smooth blends -> watertight mesh.

Why: B-rep CAD (build123d) makes eggs and boxes; organic forms need SMOOTH UNIONS (shapes melt into each other like
clay). fogleman/sdf gives that: union(a, b, k=3) blends with a 3 mm fillet-like radius. Output is always watertight
(marching cubes), ready for manifold3d booleans, flexify, preflight and the slicer.

    from sculpt import *
    f = union(ellipsoid((17, 8, 6)).translate((8, 0, 3)), sphere(5).translate((30, 0, 3)), k=4)
    f = intersection(f, slab(z0=0))           # flat bed face
    t = to_mesh(f, step=0.25)                 # trimesh
Recipes: gecko() below. Rules: keep everything in mm; flat base via slab(z0=0); thin features >= 1.6 mm;
smooth k 2-5 mm reads organic, k 0 reads mechanical; step 0.2-0.3 for prints (0.5 for previews).
"""
import numpy as np
import trimesh
from sdf import *   # noqa: F401,F403  (sphere, ellipsoid, capsule, capped_cone, union, intersection, slab, ...)
from sdf import union, intersection, difference, slab, sphere, ellipsoid, capsule, capped_cone


def to_mesh(f, step=0.25, verbose=False):
    pts = f.generate(step=step, verbose=verbose)
    pts = np.asarray(pts, dtype=np.float64)
    faces = np.arange(len(pts)).reshape(-1, 3)
    t = trimesh.Trimesh(pts, faces, process=True)
    t.merge_vertices()
    trimesh.repair.fix_normals(t)
    return t


def gecko(length_scale=1.0, k=2.5):
    """flat-bottomed gecko ~115 mm long, head at +X. Designed as a flexify test body (wide torso, long tail)."""
    s = length_scale
    body = ellipsoid(np.array((17, 8.5, 6.5)) * s).translate(np.array((8, 0, 3)) * s)
    head = ellipsoid(np.array((9, 7.5, 5.5)) * s).translate(np.array((32, 0, 3.2)) * s)
    snout = ellipsoid(np.array((6.5, 5.2, 3.9)) * s).translate(np.array((39, 0, 2.7)) * s)
    tail = capped_cone(np.array((-6, 0, 3.0)) * s, np.array((-62, 0, 1.9)) * s, 6.2 * s, 2.7 * s)   # thick enough to joint + print
    parts = [body, head, snout, tail]
    for sy in (1, -1):
        for (x0, x1, fx) in ((18, 25, 1), (-1, -8, -1)):          # front legs angle forward, back legs back
            a = np.array((x0, sy * 6.5, 2.2)) * s
            b = np.array((x1, sy * 18.5, 1.6)) * s
            parts.append(capsule(a, b, 2.4 * s))
            foot = ellipsoid(np.array((3.6, 3.6, 1.7)) * s).translate(b)
            parts.append(foot)
            for ang in (-40, 0, 40):                                # three toes splayed outward
                th = np.radians(ang) + (np.pi / 2 if sy > 0 else -np.pi / 2) * 0.5 + (0 if fx > 0 else 0)
                d = np.array((np.cos(th) * fx * 0.6 + 0.4 * fx, sy * abs(np.sin(th)) + 0.3 * sy, 0.0))
                d = d / np.linalg.norm(d)
                parts.append(capsule(b, b + d * 4.2 * s, 1.1 * s))
    for sy in (1, -1):
        parts.append(sphere(2.3 * s).translate(np.array((34, sy * 4.4, 6.4)) * s))   # eyes
    for i, x in enumerate(np.linspace(-12, 22, 8)):                                  # back ridge bumps
        parts.append(sphere((1.7 - 0.05 * i) * s).translate(np.array((x, 0, 8.6 - 0.04 * abs(x - 8))) * s))
    f = union(*parts, k=k * s)
    return intersection(f, slab(z0=0))


if __name__ == "__main__":
    import sys, os
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "gecko", "gecko.stl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t = to_mesh(gecko(), step=0.25)
    t.export(out)
    print(out, "faces", len(t.faces), "watertight", t.is_watertight, "bbox", [round(v, 1) for v in t.extents])
