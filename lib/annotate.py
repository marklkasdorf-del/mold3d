"""Annotate raw Blender renders with things an LLM (or human) needs to judge scale/orientation:
bed-plane mm grid with numbered ticks, bbox wireframe with X/Y/Z dims, scale bar, axis gizmo
(X red, Y green, Z blue), view name header. Pure PIL, projects with the exact camera basis from cams.json.
usage: annotate.py <outdir> [--title T] [--ref ref.png] [--summary summary.txt]"""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PAPER = (238, 234, 224)
INK = (30, 30, 36)
AX = {"x": (214, 40, 40), "y": (30, 150, 60), "z": (40, 90, 220)}


def font(sz, bold=False):
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz, index=1 if (bold and p.endswith(".ttc")) else 0)
            except Exception:
                pass
    return ImageFont.load_default()


def nice(v):
    """round v (mm) to 1/2/5 x 10^n"""
    e = 10 ** math.floor(math.log10(v)); f = v / e
    return e * (1 if f < 1.5 else 2 if f < 3.5 else 5 if f < 7.5 else 10)


class Cam:
    def __init__(self, c):
        self.r = np.array(c["right"]); self.u = np.array(c["up"]); self.d = np.array(c["dir"])
        self.o = np.array(c["ortho_center"]); self.s = c["px_per_mm"]; self.W = c["W"]; self.H = c["H"]

    def px(self, p):
        q = np.asarray(p, float) - self.o
        return (self.W / 2 + q @ self.r * self.s, self.H / 2 - q @ self.u * self.s)


def text(dr, xy, s, f, fill=INK, bg=True, anchor="la"):
    if bg:
        bb = dr.textbbox(xy, s, font=f, anchor=anchor)
        dr.rectangle((bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1), fill=PAPER + (200,))
    dr.text(xy, s, font=f, fill=fill, anchor=anchor)


def annotate_view(raw_path, cam, meta, out_path, label):
    cm = Cam(cam)
    W, H = cm.W, cm.H
    bmin = np.array(meta["bbox_min"]); bmax = np.array(meta["bbox_max"]); dims = bmax - bmin
    img = Image.new("RGBA", (W, H), PAPER + (255,))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    f9, f11, f13 = font(11), font(13), font(15, True)
    elev = math.degrees(math.asin(-cm.d[2])) if False else math.degrees(math.asin(abs(cm.d[2])))
    looking_down = cm.d[2] > 0.15          # camera above -> bed plane visible beneath the part
    # ---- bed grid (drawn BELOW the object)
    if looking_down:
        step = nice(max(dims[0], dims[1], 10) / 6)
        x0 = math.floor((bmin[0] - step) / step) * step; x1 = math.ceil((bmax[0] + step) / step) * step
        y0 = math.floor((bmin[1] - step) / step) * step; y1 = math.ceil((bmax[1] + step) / step) * step
        z = bmin[2]
        gx = np.arange(x0, x1 + 1e-6, step); gy = np.arange(y0, y1 + 1e-6, step)
        gcol = (120, 125, 140, 150)
        for x in gx:
            dr.line([cm.px((x, y0, z)), cm.px((x, y1, z))], fill=gcol if abs(x) > 1e-9 else AX["y"] + (220,), width=1)
        for y in gy:
            dr.line([cm.px((x0, y, z)), cm.px((x1, y, z))], fill=gcol if abs(y) > 1e-9 else AX["x"] + (220,), width=1)
        lab = lambda v: f"{v:g}"
        for x in gx[::max(1, len(gx) // 6)]:
            px, py = cm.px((x, y0, z)); text(dr, (px, py + 3), lab(x), f9, AX["x"], bg=False, anchor="ma")
        for y in gy[::max(1, len(gy) // 6)]:
            px, py = cm.px((x0, y, z)); text(dr, (px - 4, py), lab(y), f9, AX["y"], bg=False, anchor="rm")
        meta_grid = f"grid {step:g} mm"
    else:
        meta_grid = "no bed grid (edge-on)"
    img = Image.alpha_composite(img, ov)
    raw = Image.open(raw_path).convert("RGBA")
    img = Image.alpha_composite(img, raw)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    # ---- bbox wireframe + dims on the 3 edges meeting at the corner nearest the camera
    cs = {(i, j, k): np.array([bmin[0] if i == 0 else bmax[0], bmin[1] if j == 0 else bmax[1], bmin[2] if k == 0 else bmax[2]])
          for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    for (i, j, k), p in cs.items():
        for a in range(3):
            idx = [i, j, k]
            if idx[a] == 0:
                idx[a] = 1
                dr.line([cm.px(p), cm.px(cs[tuple(idx)])], fill=(60, 70, 90, 110), width=1)
    near = max(cs, key=lambda c: float(cs[c] @ cm.d))
    for a, nm in enumerate("xyz"):
        idx = list(near); idx[a] = 1 - idx[a]
        p, q = cs[near], cs[tuple(idx)]
        (x0_, y0_), (x1_, y1_) = cm.px(p), cm.px(q)
        if math.hypot(x1_ - x0_, y1_ - y0_) < 28:
            continue
        dr.line([(x0_, y0_), (x1_, y1_)], fill=AX[nm] + (230,), width=2)
        text(dr, ((x0_ + x1_) / 2, (y0_ + y1_) / 2), f"{nm.upper()} {dims[a]:.1f}", f11, AX[nm], anchor="mm")
    # ---- scale bar bottom-left
    L = nice(W * 0.22 / cm.s); Lpx = L * cm.s
    bx, by = 18, H - 22
    dr.line([(bx, by), (bx + Lpx, by)], fill=INK + (255,), width=3)
    for t in range(0, 5):
        xx = bx + Lpx * t / 4
        dr.line([(xx, by - (9 if t % 4 == 0 else 5)), (xx, by)], fill=INK + (255,), width=2)
    text(dr, (bx + Lpx / 2, by - 12), f"{L:g} mm", f11, anchor="ms")
    # ---- axis gizmo bottom-right
    gx0, gy0, gl = W - 62, H - 30, 36
    for a, nm in enumerate("xyz"):
        v = np.zeros(3); v[a] = 1
        vx, vy = float(v @ cm.r), -float(v @ cm.u)
        n = math.hypot(vx, vy)
        if n < 0.08:   # axis points at/away from the camera
            text(dr, (gx0, gy0), nm.upper() + ("*" if v @ cm.d > 0 else "."), f13, AX[nm], bg=False, anchor="mm")
            continue
        ex, ey = gx0 + vx * gl, gy0 + vy * gl
        dr.line([(gx0, gy0), (ex, ey)], fill=AX[nm] + (255,), width=3)
        text(dr, (ex + vx * 9, ey + vy * 9), nm.upper(), f13, AX[nm], bg=False, anchor="mm")
    # ---- header / footer text
    text(dr, (8, 6), label.upper(), f13)
    text(dr, (8, 26), f"bbox {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm   {meta_grid}", f11)
    if meta.get("section"):
        s = meta["section"]
        text(dr, (W - 8, 6), f"CUT {s['axis']}={s['value']:g} mm (orange = cut face)", f11, (200, 70, 0), anchor="ra")
    img = Image.alpha_composite(img, ov).convert("RGB")
    img.save(out_path)
    return img


def make_sheet(imgs, out, cols=3, summary=None, title=""):
    w, h = imgs[0].size
    tiles = list(imgs)
    if summary:
        t = Image.new("RGB", (w, h), (252, 250, 245)); d = ImageDraw.Draw(t)
        y = 10
        for line in summary:
            col = INK
            if line.startswith("[FAIL"): col = (190, 30, 30)
            elif line.startswith("[WARN"): col = (190, 120, 0)
            elif line.startswith("[PASS"): col = (30, 120, 50)
            d.text((10, y), line[:int(w / 7.4)], font=font(13), fill=col); y += 19
            if y > h - 20: break
        tiles.append(t)
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * w, (i // cols) * h))
        ImageDraw.Draw(sheet).rectangle(((i % cols) * w, (i // cols) * h, (i % cols) * w + w - 1, (i // cols) * h + h - 1), outline=(150, 150, 150))
    sheet.save(out)


def main():
    outdir = sys.argv[1]
    ref = summary = None
    a = sys.argv[2:]
    for i, x in enumerate(a):
        if x == "--ref": ref = a[i + 1]
        if x == "--summary": summary = open(a[i + 1]).read().splitlines()
    meta = json.load(open(os.path.join(outdir, "cams.json")))
    vdir = os.path.join(outdir, "views"); os.makedirs(vdir, exist_ok=True)
    imgs = []
    for name, cam in meta["views"].items():
        raw = os.path.join(outdir, f"raw_{name}.png")
        imgs.append(annotate_view(raw, cam, meta, os.path.join(vdir, f"{name}.png"), name.replace("_", " ")))
        os.remove(raw)
    if ref:
        r = Image.open(ref).convert("RGB"); h = imgs[0].size[1]
        r = r.resize((int(r.size[0] * h / r.size[1]), h))
        pick = [imgs[0]] + ([imgs[4]] if len(imgs) > 4 else [])
        W = r.size[0] + sum(p.size[0] for p in pick)
        comp = Image.new("RGB", (W, h), (255, 255, 255)); comp.paste(r, (0, 0)); x = r.size[0]
        for p in pick: comp.paste(p, (x, 0)); x += p.size[0]
        ImageDraw.Draw(comp).text((8, h - 20), "REFERENCE (left) vs RENDER", font=font(13), fill=(190, 30, 30))
        if W > 2400: comp = comp.resize((2400, int(h * 2400 / W)))
        comp.save(os.path.join(vdir, "compare_ref.png"))
    make_sheet(imgs, os.path.join(outdir, "sheet.png"), summary=summary)
    os.remove(os.path.join(outdir, "cams.json")) if False else None
    print("ANNOTATED", [os.path.basename(p) for p in sorted(os.listdir(vdir))])


main()
