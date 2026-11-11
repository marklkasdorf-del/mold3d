#!/usr/bin/env python3
"""figure_post.py: raw AI mesh (Hunyuan3D / TripoSR / any download) -> print-ready figure. venv: .venv-cad

    figure_post.py raw.glb out.stl [--height 60] [--rot x+90|none] [--base "NAME"] [--thicken 0.0]
                   [--flat 10]   (flat = lay it down and squash to N mm tall: flexi / relief mode)
Steps: orient Z-up -> scale -> voxel remesh (ONE watertight solid, internal junk gone) -> gaussian smooth
(no voxel terracing) -> optional thicken (uniform dilate, for fragile fins/ears) -> flat base cut (real first
layer, not a point) -> optional display plinth with raised name -> decimate -> report.
"""
import argparse, json, math, os, sys
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import meshkit as mk
from manifold3d import Manifold


def voxel_remesh(t, pitch, blur=1.0, dilate_mm=0.0):
    from scipy import ndimage
    from skimage import measure
    v = t.voxelized(pitch)
    mat = v.matrix.copy()
    mat = ndimage.binary_fill_holes(mat)                      # solid inside (kills internal shells)
    pad = 4 + int(math.ceil(dilate_mm / pitch))
    mat = np.pad(mat, pad)
    if dilate_mm > 0:
        it = int(round(dilate_mm / pitch))
        mat = ndimage.binary_dilation(mat, iterations=it)
    field = ndimage.gaussian_filter(mat.astype(np.float32), blur)
    verts, faces, _, _ = measure.marching_cubes(field, 0.5)
    origin = v.transform[:3, 3]
    verts = (verts - pad) * pitch + origin
    out = trimesh.Trimesh(verts, faces[:, ::-1], process=True)
    if out.volume < 0:
        out.invert()
    # largest body only
    parts = out.split(only_watertight=False)
    if len(parts) > 1:
        out = max(parts, key=lambda p: abs(p.volume))
    return out


def flat_base(M, min_contact=80.0, max_frac=0.12):
    lo = M.bounding_box()
    z0, z1 = lo[2], lo[5]
    h = z1 - z0
    best = 0.0
    for cut in np.linspace(0, max_frac * h, 25):
        a = M.slice(float(z0 + cut + 0.05)).area()
        best = cut
        if a >= min_contact:
            break
    if best > 0:
        M = M.trim_by_plane([0, 0, 1], float(z0 + best))
    return M.translate([0, 0, -float(z0 + best)]), float(best)


def plinth(M, name, margin=4.0, h=5.0):
    from build123d import Text, extrude, Align, Cylinder, Pos, export_stl
    lo = M.bounding_box()
    H = lo[5] - lo[2]
    # size the plinth from the WHOLE lower third (AI figures often come with their own flared rock/pedestal)
    pts = []
    for z in np.linspace(0.1, 0.35 * H, 12):
        for poly in M.slice(float(z)).to_polygons():
            pts.append(np.asarray(poly))
    P = np.concatenate(pts)
    cx, cy = (P[:, 0].min() + P[:, 0].max()) / 2, (P[:, 1].min() + P[:, 1].max()) / 2
    r = float(np.max(np.hypot(P[:, 0] - cx, P[:, 1] - cy))) + margin
    r = max(r, 14.0)
    base = mk.cyl(r, 0, h, x=cx, y=cy, seg=128)
    base = base - mk.cyl(r + 1, 0, 0.8, x=cx, y=cy, seg=128) + mk.cyl(r - 0.8, 0, 0.8, x=cx, y=cy, r_top=r, seg=128)  # 45deg bed chamfer
    out = base + M.translate([0, 0, h - 0.4])                  # sink the figure 0.4 mm into the plinth
    if name:
        import tempfile
        try:
            txt = Text(name, font_size=min(6.0, 1.6 * r / max(3, len(name))), font="Arial Black", align=(Align.CENTER, Align.CENTER))
        except Exception:
            txt = Text(name, font_size=5.0, align=(Align.CENTER, Align.CENTER))
        solid = extrude(txt, 1.4)
        fd, p = tempfile.mkstemp(suffix=".stl"); os.close(fd)
        export_stl(solid, p)
        tt = trimesh.load(p); os.remove(p)
        # text on the plinth's front edge (-Y), standing on the rim like a badge: lay it on the top surface front band
        tt.apply_translation([cx, cy - r + 3.6, h - 0.01])
        try:
            out = out + mk.tm2mf(tt)
        except Exception:
            pass
    return out, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("out")
    ap.add_argument("--height", type=float, default=60.0, help="final height (figure) or length (flat mode), mm")
    ap.add_argument("--rot", default="x+90", help="x+90 for glTF (Y-up) meshes from Hunyuan/Tripo; none if already Z-up")
    ap.add_argument("--base", default=None, help="add a round display plinth with this raised name")
    ap.add_argument("--thicken", type=float, default=0.0, help="uniform dilate in mm (fragile fins/ears)")
    ap.add_argument("--flat", type=float, default=0.0, help="flexi/relief mode: lay down (camera axis -> up), squash to N mm")
    ap.add_argument("--pitch", type=float, default=0.0)
    a = ap.parse_args()
    t = trimesh.load(a.raw, force="mesh")
    if a.rot == "x+90":
        t.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))   # Y-up -> Z-up, face -> -Y
    if a.flat > 0:
        # image->3D from a TOP view: the camera looked along -Y after the rotation above -> make that axis Z
        t.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    t.apply_translation(-t.bounds[0])
    if a.flat > 0:
        L = max(t.extents[0], t.extents[1])
        s = a.height / L
        t.apply_scale(s)
        t.apply_scale([1, 1, a.flat / t.extents[2]])
    else:
        t.apply_scale(a.height / t.extents[2])
    pitch = a.pitch or max(0.18, min(0.35, max(t.extents) / 300))
    rm = voxel_remesh(t, pitch, blur=1.0, dilate_mm=a.thicken)
    # smooth ONLY the voxel figure (uniform tiny triangles): kills contour lines, keeps volume. Never smooth after the
    # plinth/text are added -- Taubin melts long sharp triangles (a cylinder became a flat splash, 2026-10-17).
    trimesh.smoothing.filter_taubin(rm, lamb=0.5, nu=-0.53, iterations=12)
    M = mk.tm2mf(rm)
    M, cut = flat_base(M)
    r_base = None
    if a.base is not None:
        M, r_base = plinth(M, a.base)
    out = mk.mf2tm(M)
    if len(out.faces) > 400000:
        import fast_simplification
        v, f = fast_simplification.simplify(out.vertices, out.faces, 1 - 380000 / len(out.faces))
        out = trimesh.Trimesh(v, f)
    out.export(a.out)
    info = {"out": a.out, "bbox": [round(float(x), 1) for x in out.extents], "faces": len(out.faces),
            "watertight": bool(out.is_watertight), "base_cut_mm": round(cut, 2), "pitch": pitch,
            "volume_cm3": round(float(out.volume) / 1000, 2), "plinth_r": r_base}
    print(json.dumps(info))


if __name__ == "__main__":
    main()
