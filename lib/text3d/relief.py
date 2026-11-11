#!/usr/bin/env python3
"""relief.py: top-view concept (RGBA cut-out) -> flat, domed, flat-bottomed creature body (the flexi-designer way).

    relief.py concept.png out.stl [--length 110] [--thick 9] [--edge 0.5] [--detail 0.6]

Why not image->3D here: Hunyuan reads a top view as a FRONT view, so a laid-down lizard comes out as a squashed blob.
Human flexi designers start from the OUTLINE; so does this:
  outline  = cut-out mask, biggest blob, holes filled, features < 2 mm opened away (they'd snap)
  dome     = rounded edges from the distance-to-outline (edge height = edge*thick, full height ~5 mm in)
  detail   = luminance high-pass (scales, eyes, ridges) adds +-detail mm on top
  base     = perfectly flat bottom (z=0) = real first layer, flexify-ready
"""
import argparse, json, math
import numpy as np
from PIL import Image
from scipy import ndimage
import trimesh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img"); ap.add_argument("out")
    ap.add_argument("--length", type=float, default=110.0); ap.add_argument("--thick", type=float, default=9.0)
    ap.add_argument("--edge", type=float, default=0.32, help="edge height as a fraction of thick (joint cores sit in the thick middle)")
    ap.add_argument("--detail", type=float, default=0.6); ap.add_argument("--res", type=float, default=0.25)
    a = ap.parse_args()
    im = Image.open(a.img).convert("RGBA")
    arr = np.asarray(im).astype(np.float32) / 255.0
    mask = arr[..., 3] > 0.5
    lab, n = ndimage.label(mask)
    if n == 0:
        raise SystemExit("empty mask")
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    mask = lab == (1 + int(np.argmax(sizes)))
    mask = ndimage.binary_fill_holes(mask)
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(float); c = pts.mean(0)
    w, v = np.linalg.eigh(np.cov((pts - c).T)); ax = v[:, np.argmax(w)]
    proj = (pts - c) @ ax
    px_len = proj.max() - proj.min()
    mm_per_px = a.length / px_len
    # resample to the working grid (res mm per cell), keep orientation; flexify aligns later
    scale = mm_per_px / a.res
    H, W = mask.shape
    newsize = (max(8, int(W * scale)), max(8, int(H * scale)))
    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(newsize, Image.LANCZOS)) > 127
    lum = np.asarray(Image.fromarray((arr[..., :3].mean(2) * 255).astype(np.uint8)).resize(newsize, Image.LANCZOS)).astype(np.float32) / 255
    r_open = max(1, int(round(1.0 / a.res)))                      # remove features thinner than ~2 mm
    m = ndimage.binary_opening(m, structure=np.ones((3, 3)), iterations=r_open)
    m = ndimage.binary_closing(m, structure=np.ones((3, 3)), iterations=r_open)
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1)); m = lab == (1 + int(np.argmax(sizes)))
    m = ndimage.binary_fill_holes(m)
    d = ndimage.distance_transform_edt(m) * a.res                  # mm to the outline (inside)
    d_out = ndimage.distance_transform_edt(~m) * a.res              # mm to the outline (outside)
    sd = ndimage.gaussian_filter(d - d_out, 1.2)                    # SMOOTH signed distance: sub-pixel walls, no stair-steps
    R = 6.0
    t = np.clip(d / R, 0, 1)
    dome = a.edge + (1 - a.edge) * (1 - (1 - t) ** 2)              # quarter-round edge profile
    h = a.thick * dome
    hp = lum - ndimage.gaussian_filter(lum, 6)                      # detail: high-pass luminance
    hp = np.clip(hp / (np.abs(hp).max() + 1e-6), -1, 1)
    h = h + a.detail * hp * np.clip(d / 2.0, 0, 1)                 # no detail right at the edge
    h = ndimage.gaussian_filter(h, 0.7)
    h[~m] = 0
    # height field -> watertight solid via marching cubes on (h(x,y) - z)
    nz = int(math.ceil((a.thick + a.detail + 1) / a.res)) + 2
    zs = (np.arange(nz) - 1) * a.res
    pad = 2
    hpad = np.pad(h, pad)
    mpad = np.pad(m, pad)
    # extend the height field past the outline (edge height) so the lateral boundary comes ONLY from the smooth sd
    h_ext = np.where(m, h, a.thick * a.edge)
    hpad = np.pad(h_ext, pad, mode="edge")
    sdpad = np.pad(sd, pad, constant_values=-5.0)
    field = np.minimum(hpad[None, :, :] - zs[:, None, None], sdpad[None, :, :])
    field = np.minimum(field, zs[:, None, None] + 0.0)              # z >= 0 : closed flat bottom
    from skimage import measure
    verts, faces, _, _ = measure.marching_cubes(field, 0.0)
    # verts are (z, y, x) in cell units
    z = (verts[:, 0] - 1) * a.res; y = (verts[:, 1] - pad) * a.res; x = (verts[:, 2] - pad) * a.res
    V = np.stack([x, -y, z], 1)
    mesh = trimesh.Trimesh(V, faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    # smooth FIRST, then snap the base: everything within 0.3 mm of the bottom goes to exactly z=0 (true first layer)
    trimesh.smoothing.filter_taubin(mesh, iterations=6)
    z = mesh.vertices[:, 2]; z0 = np.percentile(z, 0.5)
    mesh.vertices[:, 2] = np.where(z < z0 + 0.3, 0.0, z - z0)
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        mesh = max(parts, key=lambda p: abs(p.volume))
    mesh.apply_translation([-mesh.bounds.mean(0)[0], -mesh.bounds.mean(0)[1], 0])
    mesh.export(a.out)
    print(json.dumps({"out": a.out, "bbox": [round(float(v), 1) for v in mesh.extents], "faces": len(mesh.faces),
                      "watertight": bool(mesh.is_watertight), "mm_per_px": round(mm_per_px, 4)}))


if __name__ == "__main__":
    main()
