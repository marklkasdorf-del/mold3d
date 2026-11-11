"""meshkit.py: shared mesh plumbing (trimesh <-> manifold3d), repair, exact gaps/volumes. venv: .venv-cad

    import meshkit as mk
    M = mk.load_manifold("x.stl")          # repaired, watertight, ready for booleans
    mk.inter_vol(A, B); mk.gap(A, B)       # exact overlap volume / min clearance (manifold3d)
    mk.save(M, "y.stl")
manifold3d booleans are exact + robust on big meshes (OCC chokes on 100k-tri sculpts; this doesn't).
"""
import numpy as np
import trimesh
from manifold3d import Manifold, Mesh, CrossSection


def tm2mf(t: trimesh.Trimesh) -> Manifold:
    t = t.copy()
    t.merge_vertices()
    m = Manifold(Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
    if m.status().name != "NoError" or m.is_empty():
        raise ValueError(f"mesh is not manifold ({m.status().name}); run mk.repair() first")
    return m


def mf2tm(m: Manifold) -> trimesh.Trimesh:
    me = m.to_mesh()
    return trimesh.Trimesh(np.asarray(me.vert_properties)[:, :3], np.asarray(me.tri_verts), process=False)


def repair(t: trimesh.Trimesh, pitch=None, max_cells=320):
    """make any mesh (holes, self-intersections, multi-shell) one watertight solid: try cheap fixes, else voxel remesh."""
    t = t.copy()
    t.merge_vertices()
    trimesh.repair.fill_holes(t); trimesh.repair.fix_normals(t)
    if t.is_watertight and t.is_volume:
        try:
            tm2mf(t); return t
        except Exception:
            pass
    pitch = pitch or max(t.extents) / max_cells
    v = t.voxelized(pitch).fill()
    from skimage import measure
    mat = np.pad(v.matrix.astype(np.float32), 2)
    from scipy.ndimage import gaussian_filter
    mat = gaussian_filter(mat, 0.8)
    verts, faces, _, _ = measure.marching_cubes(mat, 0.5)
    verts = (verts - 2) * pitch + v.transform[:3, 3]
    out = trimesh.Trimesh(verts, faces[:, ::-1])
    if out.volume < 0:
        out.invert()
    return out


def load_manifold(path, repair_if_needed=True):
    t = trimesh.load(path, force="mesh")
    try:
        return tm2mf(t)
    except Exception:
        if not repair_if_needed:
            raise
        return tm2mf(repair(t))


def save(m, path):
    (mf2tm(m) if isinstance(m, Manifold) else m).export(path)


def vol(m: Manifold) -> float:
    return float(m.volume())


def inter_vol(a: Manifold, b: Manifold) -> float:
    return float((a ^ b).volume())


def gap(a: Manifold, b: Manifold, search=3.0) -> float:
    """exact min surface distance (mm) if < search, else search."""
    return float(a.min_gap(b, search))


def box(x0, y0, z0, x1, y1, z1) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl(r, z0, z1, x=0.0, y=0.0, r_top=None, seg=96) -> Manifold:
    return Manifold.cylinder(z1 - z0, r, r if r_top is None else r_top, seg).translate([x, y, z0])


def prism(points_xy, z0, z1) -> Manifold:
    """extrude a 2D outline. Winding is fixed here: manifold treats a CLOCKWISE contour as a hole (empty solid)."""
    p = np.asarray(points_xy, float)
    area = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    if area < 0:
        p = p[::-1]
    return CrossSection([p.tolist()]).extrude(z1 - z0).translate([0, 0, z0])


def rot_z(m: Manifold, deg, cx=0.0, cy=0.0) -> Manifold:
    return m.translate([-cx, -cy, 0]).rotate([0, 0, deg]).translate([cx, cy, 0])


def frame_matrix(origin, x_dir):
    """4x3 affine for manifold.transform: local XY frame (x_dir in the XY plane) -> world."""
    x = np.array([x_dir[0], x_dir[1], 0.0]); x /= np.linalg.norm(x)
    y = np.array([-x[1], x[0], 0.0]); z = np.array([0, 0, 1.0])
    R = np.stack([x, y, z], axis=1)
    return np.hstack([R, np.array(origin, float).reshape(3, 1)])


def heights_on_disc(t: trimesh.Trimesh, cx, cy, r, n=9):
    """top surface heights sampled on a disc (rays from above) -> (min, max). None if a ray misses."""
    pts = []
    for i in range(n):
        for j in range(n):
            u, v = -1 + 2 * i / (n - 1), -1 + 2 * j / (n - 1)
            if u * u + v * v <= 1:
                pts.append((cx + u * r, cy + v * r))
    o = np.array([[x, y, t.bounds[1][2] + 10] for x, y in pts])
    d = np.tile([0, 0, -1.0], (len(o), 1))
    loc, idx, _ = t.ray.intersects_location(o, d, multiple_hits=False)
    if len(idx) < len(o):
        return None
    return float(loc[:, 2].min()), float(loc[:, 2].max())
