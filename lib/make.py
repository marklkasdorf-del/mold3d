#!/usr/bin/env python3
"""make: generators for things you actually need, from YOUR numbers. venv: .venv-cad. All clearances come from fit.json.

  forge make box W D H [--lid slide|press] [--divs 2x1] [--label "PODS"] [--snap] [--round 3]   (inner size, mm)
  forge make keychain "HELLO" [--size 12] [--hole 4.5] [--colors 1|2]
  forge make sign "MY SHOP" [--w 140 --h 40] [--holes 2] [--border] [--colors 1|2]
  forge make holder (--outline outline.json | --dims WxDxH) [--mount screws|tape|desk] [--depth 20]
  forge make stand [--device "iPhone Air" | --dims WxT] [--angle 65] [--case 2] [--cable]
  forge make lithophane photo.jpg [--width 100] [--frame]
  forge make devices                        (list the device library: knowledge/devices.json)
Boxes are checked like mechanisms: a slide lid must slide all the way out clear AND jam if you try to lift it.
Output: ./mold3d/make/<thing>/ with STLs already in their PRINT pose + a one-line recipe.
"""
import argparse, difflib, json, math, os, re, sys
from build123d import *

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forge_env
import fit
FORGE = os.path.dirname(HERE)
OUT = os.path.join(forge_env.OUT, "make")
DEV = os.path.join(FORGE, "knowledge", "devices.json")
WALL = 2.0                     # minimum wall (mm)
FONT = "Arial Black"


_FONT_WARNED = []


def T(txt, size, align=(Align.CENTER, Align.CENTER)):
    try:
        return Text(txt, font_size=size, font=FONT, align=align)
    except Exception:
        if not _FONT_WARNED:
            _FONT_WARNED.append(1)
            print(f'make: font "{FONT}" not found, using the default font', file=sys.stderr)
        return Text(txt, font_size=size, align=align)


def parse_dims(s, n):
    """'70x8' / '60X30*20' / '60×30x20' -> n floats, or a plain ValueError with an example."""
    ex = "--dims 70x8 (W x T)" if n == 2 else "--dims 60x30x20 (W x D x H)"
    parts = [q for q in re.split(r"[xX*\u00d7]", str(s).replace(" ", "")) if q != ""]
    try:
        v = [float(q) for q in parts]
    except ValueError:
        v = []
    if len(v) != n:
        raise ValueError(f"--dims {s!r} needs {n} numbers in mm, e.g. {ex}")
    return v


def ov(a, b):
    r = a & b
    return r.volume if r is not None else 0.0


def save(name, parts, recipe, info=None, pieces=None):
    d = os.path.join(OUT, name); os.makedirs(d, exist_ok=True)
    files, steps = [], []
    for k, s in parts.items():
        f = os.path.join(d, f"{k}.stl"); export_stl(s, f, tolerance=0.01, angular_tolerance=0.08); files.append(f)
        if k != "assembled":                                      # exact CAD file next to the STL, for editing
            try:
                export_step(s, f[:-4] + ".step"); steps.append(f[:-4] + ".step")
            except Exception as e:
                print(f"make: could not write {k}.step ({e})", file=sys.stderr)
    info = info or {}
    if pieces is None:
        pieces = [{"name": k, "parts": [[k, k, 1]]} for k in parts if k != "assembled"]
    for pc in pieces:
        pc["parts"] = [[pn, os.path.join(d, f"{fk}.stl"), sl] for pn, fk, sl in pc["parts"]]
    info.update({"files": files, "step_files": steps, "pieces": pieces, "recipe": recipe})
    json.dump(info, open(os.path.join(d, "make.json"), "w"), indent=1)
    print(json.dumps(info, indent=1))
    return d


# ------------------------------------------------------------------ box
def box(W, D, H, lid="slide", divs="1x1", label="", snap=False, r=3.0, wall=WALL, floor=2.0):
    ow, od = W + 2 * wall, D + 2 * wall
    if lid == "slide":
        gl, lt, gd = fit.get("slide_gap"), 1.8, 1.4               # gap, lid thickness, groove depth into the wall
        top_band = lt + 2 * gl + 1.6                              # wall above the groove keeps the lid in
        oh = floor + H + top_band
        body = extrude(RectangleRounded(ow, od, r), oh)
        body -= Pos(0, 0, floor) * extrude(RectangleRounded(W, D, max(0.5, r - wall)), oh)
        gz = floor + H                                            # groove bottom
        groove = Pos(0, wall / 2 + 0.01, gz + lt / 2 + gl) * Box(W + 2 * gd, D + wall + 0.02, lt + 2 * gl)
        body -= groove
        body -= Pos(0, -od / 2 + wall / 2, gz + (oh - gz) / 2 + 0.01) * Box(W + 2 * gd, wall + 0.2, oh - gz + 0.02)   # open front
        lid_w, lid_d = W + 2 * gd - 2 * gl, D + wall - gl
        lid_s = Pos(0, -wall / 2 + gl / 2, 0) * extrude(RectangleRounded(lid_w, lid_d, 1.0), lt)
        lid_s -= Pos(0, -lid_d / 2 + 8, lt) * Cylinder(6, 1.4, align=(Align.CENTER, Align.CENTER, Align.CENTER))   # thumb dimple
        if label:
            lid_s += Pos(0, 4, lt) * extrude(T(label, min(14, lid_w / max(3, len(label)) * 1.4)), 0.8)
        lid_pose = Pos(0, wall / 2 + 0.01 - (wall / 2 - gl / 2), gz + gl) * lid_s       # assembled pose for the check
        parts_assembled = {"box": body, "lid": lid_pose}
    else:                                                         # press-on lid with a lip
        g = fit.get("snug_fit")
        oh = floor + H
        body = extrude(RectangleRounded(ow, od, r), oh)
        body -= Pos(0, 0, floor) * extrude(RectangleRounded(W, D, max(0.5, r - wall)), oh)
        lip_h, lt = 5.0, 2.4
        lid_s = extrude(RectangleRounded(ow, od, r), lt)
        lip = extrude(RectangleRounded(W - 2 * g, D - 2 * g, max(0.5, r - wall - g)), lip_h) - \
            extrude(RectangleRounded(W - 2 * g - 2 * WALL, D - 2 * g - 2 * WALL, max(0.3, r - 2 * wall)), lip_h)
        lid_s += Pos(0, 0, -lip_h) * lip
        if snap:                                                  # detent: 0.35 mm bumps on the lip + matching groove
            for sx in (-1, 1):
                lid_s += Pos(sx * (W / 2 - g), 0, -lip_h / 2) * Box(0.7, D * 0.4, 1.2)
                body -= Pos(sx * (W / 2), 0, oh - lip_h / 2) * Box(0.9, D * 0.4 + 0.6, 1.6)
        if label:
            lid_s -= Pos(0, 0, lt - 0.6) * extrude(T(label, min(16, ow / max(3, len(label)) * 1.5)), 1.0)   # engraved (prints on the bed)
        lid_pose = Pos(0, 0, oh) * lid_s
        parts_assembled = {"box": body, "lid": lid_pose}
    nx, ny = (int(v) for v in divs.lower().split("x"))
    for i in range(1, nx):
        x = -W / 2 + i * W / nx
        body += Pos(x, 0, floor) * Box(WALL, D, H - 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for j in range(1, ny):
        y = -D / 2 + j * D / ny
        body += Pos(0, y, floor) * Box(W, WALL, H - 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    parts_assembled["box"] = body
    # ---- checks (the box is a mechanism)
    chk = {"static_overlap_mm3": round(ov(parts_assembled["box"], parts_assembled["lid"]), 3)}
    if lid == "slide":
        worst = 0.0
        for k in range(9):
            dy = -(D + wall) * k / 8                              # slide out through the open front
            worst = max(worst, ov(parts_assembled["box"], Pos(0, dy, 0) * parts_assembled["lid"]))
        lift = ov(parts_assembled["box"], Pos(0, 0, 1.5) * parts_assembled["lid"])
        chk.update({"slide_out_worst_mm3": round(worst, 3), "lift_jams": lift > 1.0})
        lid_print = lid_s                                         # flat, label up
    else:
        chk["lip_gap_per_side_mm"] = g
        lid_print = Rot(180, 0, 0) * lid_s                        # plate on the bed, lip up (engraved label on the bed face)
        lid_print = Pos(0, 0, -lid_print.bounding_box().min.Z) * lid_print
    ok = chk["static_overlap_mm3"] < 0.01 and (lid != "slide" or (chk["slide_out_worst_mm3"] < 0.01 and chk["lift_jams"]))
    chk["ok"] = ok
    name = f"box_{int(W)}x{int(D)}x{int(H)}_{lid}"
    recipe = (f"box opening up, lid {'flat label up' if lid == 'slide' else 'plate down, lip up'}; no supports; "
              f"walls {wall} mm; {'slide gap ' + str(fit.get('slide_gap')) if lid == 'slide' else 'snug ' + str(fit.get('snug_fit'))} mm per side")
    return save(name, {"box": parts_assembled["box"], "lid": lid_print, "assembled": Compound([parts_assembled["box"], parts_assembled["lid"]])},
                recipe, {"check": chk, "outer_mm": [round(ow, 1), round(od, 1), round(parts_assembled['box'].bounding_box().size.Z, 1)]})


# ------------------------------------------------------------------ keychain / sign
def _poly_wire(w, step=0.2):
    n = max(48, int(w.length / step))
    return Wire.make_polygon([w.position_at(i / n) for i in range(n)], close=True)


def default_colors():
    """2 when the active printer profile has more than one filament slot (printer.json "filament_slots"), else 1."""
    try:
        import printer
        return 2 if int(printer.load().get("filament_slots", 1)) > 1 else 1
    except Exception:
        return 1


def _two_colour(name, base, text, recipe, info):
    info = dict(info, expect={"visible_from_top": ["text"]})
    return save(name + "_2c", {"base": base, "text": text}, recipe, info,
                pieces=[{"name": name.split("_")[0], "parts": [["base", "base", 1], ["text", "text", 2]]}])


def keychain(text, size=12.0, hole=4.5, plate_t=3.0, text_h=1.4, margin=3.0, colors=1):
    sk = T(text, size)
    plate2d = offset(sk, margin, kind=Kind.ARC)
    fs = plate2d.faces()
    if len(fs) > 1:                                               # per-letter offsets overlap: fuse them into one plate outline
        fs = fs[0].fuse(*fs[1:]).clean().faces()
    # re-draw the outline as a fine polygon (0.2 mm): the raw offset curves do not survive a STEP round trip
    plate2d = Sketch(Compound([Face(_poly_wire(f.outer_wire()), [_poly_wire(w) for w in f.inner_wires()]) for f in fs]))
    bb = plate2d.bounding_box()
    ring_c = (bb.min.X - hole / 2 - 0.6, (bb.min.Y + bb.max.Y) / 2)
    ring = Pos(*ring_c) * Circle(hole / 2 + 3.0)
    base = extrude(plate2d + ring, plate_t)
    base -= Pos(*ring_c, 0) * Cylinder(hole / 2, plate_t * 3, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    raised = Pos(0, 0, plate_t) * extrude(sk, text_h)
    name = f"keychain_{''.join(c for c in text if c.isalnum())[:16]}"
    if colors == 2:
        k = base + raised
        sz = k.bounding_box().size
        return _two_colour(name, base, raised, "flat, no supports; text prints on filament slot 2 (no pause needed)",
                           {"size_mm": [round(v, 1) for v in (sz.X, sz.Y, sz.Z)], "colors": 2})
    k = base + raised
    return save(name, {"keychain": k},
                f"flat, no supports; tip: pause at {plate_t:.1f} mm and swap filament for 2-colour letters",
                {"size_mm": [round(v, 1) for v in (k.bounding_box().size.X, k.bounding_box().size.Y, k.bounding_box().size.Z)],
                 "pause_height_mm": plate_t})


def sign(text, w=140.0, h=40.0, holes=2, border=True, t=3.0, colors=1):
    p = extrude(RectangleRounded(w, h, 4), t)
    raised = None
    if border:
        raised = Pos(0, 0, t) * extrude(RectangleRounded(w - 3, h - 3, 3) - RectangleRounded(w - 7, h - 7, 2), 1.2)
    size = min(h * 0.45, (w - 14 - (24 if holes else 0)) / max(3, len(text)) * 1.45)
    letters = Pos(0, 0, t) * extrude(T(text, size), 1.2)
    raised = letters if raised is None else raised + letters
    if holes:
        for sx in (-1, 1)[:holes] if holes <= 2 else (-1, 1):
            x = sx * (w / 2 - 9)
            p -= Pos(x, 0, 0) * Cylinder(1.9, 3 * t, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            p -= Pos(x, 0, t - 1.8) * Cone(1.9, 3.8, 1.8, align=(Align.CENTER, Align.CENTER, Align.MIN))   # countersink (#6 / M3.5)
    name = f"sign_{''.join(c for c in text if c.isalnum())[:16]}"
    if colors == 2:
        return _two_colour(name, p, raised, "flat, no supports; #6 or M3.5 countersunk screws; text and border print on filament slot 2 (no pause needed)",
                           {"size_mm": [w, h, t + 1.2], "colors": 2})
    return save(name, {"sign": p + raised},
                "flat, no supports; #6 or M3.5 countersunk screws; pause at 3.0 mm for 2-colour text",
                {"size_mm": [w, h, t + 1.2], "pause_height_mm": t})


# ------------------------------------------------------------------ holder / stand
def holder(outline=None, dims=None, mount="screws", depth=None, wall=2.4):
    g = fit.get("loose_fit")
    if outline:
        o = json.load(open(outline))
        pts = [tuple(map(float, q)) for q in o["outline_mm"]]
        obj = Polygon(*pts, align=None)
        depth = depth or o.get("depth", 15.0)
    else:
        Wd, Dd, Hd = parse_dims(dims, 3)
        obj = RectangleRounded(Wd, Dd, min(3, Wd / 4, Dd / 4)); depth = depth or Hd * 0.6
    pocket = offset(obj, g, kind=Kind.ARC)
    outer = offset(obj, g + wall, kind=Kind.ARC)
    floor = 2.4
    hold = extrude(outer, floor + depth) - Pos(0, 0, floor) * extrude(pocket, depth + 1)
    bb = hold.bounding_box()
    hold -= Pos(0, bb.min.Y, floor + depth) * Box(min(24, bb.size.X * 0.4), 4 * wall, depth * 1.2, align=(Align.CENTER, Align.CENTER, Align.CENTER))  # thumb slot
    if mount == "screws":
        plate = Pos(0, bb.max.Y + 1.5, 0) * Box(bb.size.X + 16, 3.0, floor + depth + 18, align=(Align.CENTER, Align.MIN, Align.MIN))
        hold += plate
        for sx in (-1, 1):
            x = sx * (bb.size.X / 2 + 3.5)
            z = floor + depth + 9
            hole = Pos(x, bb.max.Y + 1.5, z) * Rot(-90, 0, 0) * Cylinder(2.0, 10, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            cs = Pos(x, bb.max.Y + 1.5 + 0.01, z) * Rot(90, 0, 0) * Cone(4.0, 2.0, 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
            hold -= hole; hold -= cs
        recipe = "print floor-down as modeled (back plate stands vertical), no supports; 2 countersunk screws into the wall"
    elif mount == "tape":
        recipe = "floor-down, no supports; stick a 3M strip on the flat bottom"
    else:
        hold += Pos(0, 0, 0) * extrude(offset(outer, 8, kind=Kind.ARC), 2.4) if False else Box(0.001, 0.001, 0.001)
        recipe = "floor-down, no supports"
    return save(f"holder_{mount}", {"holder": hold}, recipe, {"pocket_gap_mm": g, "depth_mm": depth})


def devices():
    if not os.path.exists(DEV):
        json.dump({"iPhone Air": {"w": 74.7, "h": 156.2, "t": 5.64, "source": "tech inventory (Apple spec)"}}, open(DEV, "w"), indent=1)
    return json.load(open(DEV))


def stand(device=None, dims=None, angle=65.0, case=2.0, cable=True):
    if device:
        devs = devices()
        low = {k.lower(): k for k in devs}
        d = devs.get(low.get(device.lower(), device))
        if not d:
            close = difflib.get_close_matches(device, list(devs), n=3, cutoff=0.4)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            raise SystemExit(f"unknown device {device!r}.{hint} known: {', '.join(devs)}. Add one: forge make devices add NAME WxHxT")
        w, t = d["w"], d["t"]
    else:
        w, t = parse_dims(dims, 2)
    slot = t + 2 * case + 1.0                                     # case on both faces + 1 mm play
    W = max(60.0, w * 0.75)
    base_d, base_t = 85.0, 5.0
    a = math.radians(angle)
    back_len = 95.0
    base = Box(W, base_d, base_t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lip = Pos(0, -base_d / 2 + 6, base_t) * Box(W, 4.0, 9.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # back support: a slab leaning back at `angle` from horizontal, its front face = where the phone rests
    slab = Box(W, 5.0, back_len, align=(Align.CENTER, Align.MIN, Align.MIN))
    slab = Pos(0, -base_d / 2 + 8 + slot, base_t) * Rot(-(90 - angle), 0, 0) * slab
    s = base + lip + slab
    # gusset under the slab for strength
    s += Pos(0, -base_d / 2 + 8 + slot + 2.5, base_t) * Rot(-(90 - angle), 0, 0) * Box(5.0, 40, 40, align=(Align.CENTER, Align.MIN, Align.MIN))
    if cable:
        s -= Pos(0, -base_d / 2 + 6, base_t + 2) * Box(12, 12, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    s = s & Box(400, 400, 400, align=(Align.CENTER, Align.CENTER, Align.MIN))       # nothing below the bed
    return save(f"stand_{(device or 'custom').replace(' ', '')}_{int(angle)}deg", {"stand": s},
                "as modeled, no supports (slab leans <= 45 deg past vertical); PLA+",
                {"slot_mm": round(slot, 2), "angle_deg": angle, "device": device or dims})


def lithophane(img, width=100.0, t_min=0.8, t_max=3.2, frame=True, px=0.2):
    import numpy as np
    import trimesh
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(img)).convert("L")
    W = int(width / px); H = int(im.height * W / im.width)
    a = np.asarray(im.resize((W, H), Image.LANCZOS)).astype(np.float32) / 255.0
    th = t_min + (1.0 - a) * (t_max - t_min)                       # dark = thick
    if frame:
        f = int(3.0 / px)
        th = np.pad(th, f, constant_values=t_max + 0.8)
    Hh, Ww = th.shape
    ys, xs = np.mgrid[0:Hh, 0:Ww]
    top = np.stack([xs * px, (Hh - 1 - ys) * px, th], -1).reshape(-1, 3)
    bot = top.copy(); bot[:, 2] = 0
    V = np.concatenate([top, bot])
    idx = np.arange(Hh * Ww).reshape(Hh, Ww)
    q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    F = [np.stack([q[:, 0], q[:, 2], q[:, 1]], 1), np.stack([q[:, 0], q[:, 3], q[:, 2]], 1)]
    off = Hh * Ww
    F += [np.stack([q[:, 0] + off, q[:, 1] + off, q[:, 2] + off], 1), np.stack([q[:, 0] + off, q[:, 2] + off, q[:, 3] + off], 1)]
    def edge(a_, b_):
        return [np.stack([a_[:-1], b_[:-1], a_[1:]], 1), np.stack([a_[1:], b_[:-1], b_[1:]], 1)]
    for e in (idx[0, :], idx[:, -1], idx[-1, ::-1], idx[::-1, 0]):
        F += edge(e + off, e) if True else []
    mesh = trimesh.Trimesh(V, np.concatenate(F), process=True)
    trimesh.repair.fix_normals(mesh)
    # print it STANDING (vertical lithophanes print cleanest): rotate so the plate stands on its bottom edge
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    mesh.apply_translation(-mesh.bounds[0])
    d = os.path.join(OUT, "lithophane_" + os.path.splitext(os.path.basename(img))[0]); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "lithophane.stl"); mesh.export(f)
    info = {"files": [f], "size_mm": [round(float(v), 1) for v in mesh.extents], "watertight": bool(mesh.is_watertight),
            "recipe": "print STANDING on its edge as exported, no supports, white PLA; light it from behind"}
    json.dump(info, open(os.path.join(d, "make.json"), "w"), indent=1); print(json.dumps(info, indent=1))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["box", "keychain", "sign", "holder", "stand", "lithophane", "devices"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--lid", default="slide"); ap.add_argument("--divs", default="1x1"); ap.add_argument("--label", default="")
    ap.add_argument("--snap", action="store_true"); ap.add_argument("--round", type=float, default=3.0)
    ap.add_argument("--size", type=float, default=12.0); ap.add_argument("--hole", type=float, default=4.5)
    ap.add_argument("--w", type=float, default=140.0); ap.add_argument("--h", type=float, default=40.0)
    ap.add_argument("--holes", type=int, default=2); ap.add_argument("--colors", type=int, choices=[1, 2], default=None, help="keychain/sign: 2 = base + text as separate filament slots (default 2 on a multicolour printer profile)"); ap.add_argument("--border", action="store_true")
    ap.add_argument("--outline"); ap.add_argument("--dims"); ap.add_argument("--mount", default="screws")
    ap.add_argument("--depth", type=float); ap.add_argument("--device"); ap.add_argument("--angle", type=float, default=65.0)
    ap.add_argument("--case", type=float, default=2.0); ap.add_argument("--no-cable", action="store_true")
    ap.add_argument("--width", type=float, default=100.0); ap.add_argument("--frame", action="store_true")
    a = ap.parse_args()
    usage = {"box": "forge make box W D H [--lid slide|press]", "keychain": 'forge make keychain "TEXT"', "sign": 'forge make sign "TEXT"',
             "holder": "forge make holder --dims 60x30x20", "stand": 'forge make stand --device "iPhone Air"',
             "lithophane": "forge make lithophane photo.jpg", "devices": "forge make devices"}[a.what]

    def num(v):
        try:
            return float(v)
        except ValueError:
            ap.exit(2, f'forge make {a.what}: "{v}" is not a number (mm)\n')
    if a.what == "box" and len(a.args) < 3:
        ap.exit(2, "forge make box needs W D H (inside size, mm), e.g. forge make box 80 60 40\n")
    if a.what in ("keychain", "sign") and not a.args:
        ap.exit(2, f'forge make {a.what} needs the text, e.g. forge make {a.what} "MARK"\n')
    if a.what == "lithophane" and (not a.args or not os.path.isfile(a.args[0])):
        ap.exit(2, "forge make lithophane needs a photo, e.g. forge make lithophane me.jpg\n")
    try:
        if a.what == "box":
            W, D, H = (num(v) for v in a.args[:3]); box(W, D, H, a.lid, a.divs, a.label, a.snap, a.round)
        elif a.what == "keychain":
            keychain(a.args[0], a.size, a.hole, colors=a.colors or default_colors())
        elif a.what == "sign":
            sign(a.args[0], a.w, a.h, a.holes, a.border, colors=a.colors or default_colors())
        elif a.what == "holder":
            holder(a.outline, a.dims, a.mount, a.depth)
        elif a.what == "stand":
            stand(a.device, a.dims, a.angle, a.case, not a.no_cable)
        elif a.what == "lithophane":
            lithophane(a.args[0], a.width, frame=a.frame)
        elif a.what == "devices":
            if a.args[:1] == ["add"]:
                name, dims = a.args[1], a.args[2]; w, h, t = (float(v) for v in dims.lower().split("x"))
                d = devices(); d[name] = {"w": w, "h": h, "t": t, "source": "added by user"}; json.dump(d, open(DEV, "w"), indent=1)
            print(json.dumps(devices(), indent=1))

    except (ValueError, KeyError, IndexError) as e:
        ap.exit(2, f"forge make {a.what}: {e}\nusage: {usage}\n")

if __name__ == "__main__":
    main()
