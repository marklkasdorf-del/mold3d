#!/usr/bin/env python3
"""quickview: a picture of a model with NO Blender (numpy + PIL + trimesh only). Works in any sandbox.

    forge view <stl> [more.stl@2 ...] [--out preview.png] [--title T] [--json]

Painter's algorithm, orthographic, back-face culled, Lambert shaded, 2x supersampled. Not pretty-render quality:
it exists so every design ends with a picture on the phone even when Blender can't start. Blender sheets still win when they work.
Colour slots: 1 warm grey, 2 orange, 3 blue, 4 green (the filament slots of the 3MF).
"""
import argparse, json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (246, 241, 231)
INK = (70, 62, 50)
SLOT = {1: (226, 214, 196), 2: (232, 120, 52), 3: (60, 120, 200), 4: (70, 160, 90)}
MAX_FACES = 80000
_L = np.array([0.4, -0.6, 1.0]); _L = _L / np.linalg.norm(_L)
VIEWS = {"iso": ((1.0, -1.0, 0.8), (0, 0, 1)), "top": ((0, 0, 1.0), (0, 1, 0)),
         "front": ((0, -1.0, 0), (0, 0, 1)), "side": ((1.0, 0, 0), (0, 0, 1))}


def _decimate(meshes):
    """list of (V, F, rgb) with the total face count capped at MAX_FACES (decimated proportionally)."""
    total = sum(len(m.faces) for m, _ in meshes)
    out = []
    for m, rgb in meshes:
        V, F = np.asarray(m.vertices, float), np.asarray(m.faces, int)
        if total > MAX_FACES and len(F) > 200:
            tgt = max(100, int(len(F) * MAX_FACES / total))
            try:
                import fast_simplification
                V2, F2 = fast_simplification.simplify(V.astype(np.float32), F.astype(np.int32), target_reduction=1.0 - tgt / len(F))
                if len(F2):
                    V, F = np.asarray(V2, float), np.asarray(F2, int)
            except Exception:
                pass                                              # non-manifold etc: draw every face (slower, still correct)
        out.append((V, F, rgb))
    return out


def _bounds(parts):
    lo = np.min([V.min(0) for V, _, _ in parts], axis=0); hi = np.max([V.max(0) for V, _, _ in parts], axis=0)
    return lo, hi


def _draw(parts, view, size, bg, lo, hi):
    S = 2
    v, up = (np.array(x, float) for x in VIEWS[view]); v /= np.linalg.norm(v)
    r = np.cross(up, v); r /= np.linalg.norm(r)
    u = np.cross(v, r)
    ctr = (lo + hi) / 2
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) - ctr
    sx, sy = corners @ r, corners @ u
    ext = max(sx.max() - sx.min(), sy.max() - sy.min(), 1e-6)
    w, h = size if isinstance(size, tuple) else (size, size)
    scale = min(w, h) * S / (ext * 1.12)
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
    img = Image.new("RGB", (w * S, h * S), bg); dr = ImageDraw.Draw(img)
    polys, depths, cols = [], [], []
    for V, F, rgb in parts:
        P = V - ctr
        tri = P[F]                                                # (n,3,3)
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(n, axis=1); ok = ln > 1e-12
        n = n / np.where(ok, ln, 1)[:, None]
        keep = ok & (n @ v > 1e-6)                                # back-face cull
        if not keep.any():
            continue
        tri, n = tri[keep], n[keep]
        px = (tri @ r - cx) * scale + w * S / 2
        py = h * S / 2 - (tri @ u - cy) * scale
        polys.append(np.stack([px, py], -1)); depths.append((tri @ v).mean(1))
        sh = 0.35 + 0.65 * np.maximum(0, n @ _L)
        cols.append(np.clip(np.array(rgb, float)[None, :] * sh[:, None], 0, 255).astype(np.uint8))
    if polys:
        poly = np.concatenate(polys); dep = np.concatenate(depths); col = np.concatenate(cols)
        order = np.argsort(dep, kind="stable")                    # far -> near
        for i in order:
            c = tuple(int(q) for q in col[i])
            dr.polygon([tuple(p) for p in poly[i]], fill=c, outline=c)
    return img.resize((w, h), Image.LANCZOS)


def render_view(meshes, view, size=400, bg=BG):
    """meshes = [(trimesh.Trimesh, (r,g,b)), ...]; view in iso|top|front|side -> PIL.Image (size x size, or a (w,h) tuple)."""
    parts = _decimate(meshes)
    lo, hi = _bounds(parts)
    return _draw(parts, view, size, bg, lo, hi)


def _font(px):
    try:
        return ImageFont.load_default(size=px)
    except Exception:
        return ImageFont.load_default()


def sheet(meshes, out_png, title, dims_mm=None):
    """1200x900 PNG: hero iso on the left, top/front/side stacked on the right, a title strip under the hero."""
    parts = _decimate(meshes)
    lo, hi = _bounds(parts)
    if dims_mm is None:
        dims_mm = [float(x) for x in (hi - lo)]
    canvas = Image.new("RGB", (1200, 900), BG); dr = ImageDraw.Draw(canvas)
    canvas.paste(_draw(parts, "iso", (800, 800), BG, lo, hi), (0, 0))
    f = _font(16)
    for i, vw in enumerate(("top", "front", "side")):
        canvas.paste(_draw(parts, vw, (400, 290), BG, lo, hi), (800, i * 290))
        dr.text((810, i * 290 + 8), vw, fill=INK, font=f)
    dr.line([(800, 0), (800, 870)], fill=(220, 212, 196), width=2)
    dims = " x ".join(f"{v:.1f}".rstrip("0").rstrip(".") for v in dims_mm)
    dr.text((24, 830), f"{title}  ·  {dims} mm", fill=INK, font=_font(28))
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    canvas.save(out_png, optimize=True)
    return out_png


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stls", nargs="+", help="model.stl [other.stl@2 ...]  (@N = filament colour slot)")
    ap.add_argument("--out"); ap.add_argument("--title"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    import trimesh
    t0 = time.time(); meshes = []
    for i, s in enumerate(a.stls):
        path, _, slot = s.partition("@")
        if not os.path.isfile(path):
            sys.exit(f"forge view: no such file {path}")
        m = trimesh.load(path, force="mesh")
        meshes.append((m, SLOT.get(int(slot) if slot.isdigit() else 1, SLOT[1])))
    first = os.path.abspath(a.stls[0].partition("@")[0])
    out = os.path.abspath(a.out) if a.out else os.path.splitext(first)[0] + "_view.png"
    title = a.title or os.path.splitext(os.path.basename(first))[0]
    sheet(meshes, out, title)
    info = {"png": out, "w": 1200, "h": 900, "faces": int(sum(len(m.faces) for m, _ in meshes)), "seconds": round(time.time() - t0, 2)}
    print(json.dumps(info) if a.json else f"quick view -> {out}")


if __name__ == "__main__":
    main()
