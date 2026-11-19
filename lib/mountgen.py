"""mountgen: geometry + load math for `forge mount` (photo-to-fit). Pure functions, no CLI. build123d, mm.

  clamp_params(A)            -> the ranged V-block clamp numbers (D_lo, D_hi, c, G(d), bolt length, range text)
  load_check(...)            -> bending stress vs the house PLA allowables [R]
  build(analysis)            -> {"pieces": [...], "mount": {...}, "checks": [...], "dummy": ...}  (every piece in print pose, Z=0 bed)
  comb(analysis, label, centre) -> the fit comb (3 teeth at centre -1 / 0 / +1)

Four interface styles (clamp-round, hookover, strap, screw) x two payloads (cup, hook). Clearances only from fit.get().
Print-pose rule: a pose is "along layers" when |stress_axis . Z| <= 0.26 (15 deg); generators choose such poses.
"""
import math, os
from build123d import *
import fit

SQ2 = math.sqrt(2.0)
ALONG = {"x": 10.0, "alt": 4.0}          # PLA allowable bending stress, MPa, along / across the layers [R] (house values)
W_CLAMP = 24.0                            # clamp length along the tube
FL = 5.0                                  # flange thickness
NUT_DEPTH = 3.4
TAB = 2.4                                 # the cup piece's tab that rides on the upper flange (inside the bolt stack)
ARM_H = 12.0                              # cup arm height
T_HOOK = 4.0                              # hookover / hook profile thickness
POSE_TOL = 0.26


def _g(key):
    return fit.get(key)


# ------------------------------------------------------------------ pure math
def G(d, d_lo):
    """gap between the two split faces when the clamp closes on a tube of diameter d (0 at D_lo)."""
    return math.sqrt(max(d * d - d_lo * d_lo, 0.0))


def clamp_params(A, r=2.5, tab=0.0):
    d_lo, d_hi = A - r, A + r
    ri = d_hi / 2.0
    c = math.sqrt(ri * ri - (d_lo / 2.0) ** 2)
    need = G(d_hi, d_lo) + 2 * FL + tab + 3.2 + 1.0
    bolt = next((L for L in (20, 25, 30, 35, 40, 50, 60, 70, 80) if L >= need), None)
    if bolt is None:
        raise ValueError(f"a {A:g} mm tube needs a bolt longer than 80 mm: use the strap style")
    return {"A": A, "r": r, "D_lo": d_lo, "D_hi": d_hi, "Ri": ri, "c": c, "G_lo": 0.0, "G_A": G(A, d_lo), "G_hi": G(d_hi, d_lo),
            "bolt_mm": bolt, "need_mm": need, "range_mm": [d_lo, d_hi], "range_text": f"Grips {d_lo:g}–{d_hi:g} mm tube"}


def load_check(mass_g, factor, L, b, h, along_layers):
    F = mass_g / 1000.0 * 9.81 * factor
    sigma = 6.0 * F * L / (b * h * h)
    allow = ALONG["x"] if along_layers else ALONG["alt"]
    return {"mass_g": mass_g, "F_N": round(F, 2), "sigma_mpa": round(sigma, 2), "allow_mpa": allow,
            "along_layers": bool(along_layers), "ok": bool(sigma <= allow), "L_mm": round(L, 1), "b_mm": b, "h_mm": h}


def along_layers_pose(stress_axis):
    """the pose rule: the main bending stress runs (within 15 deg) in the layer plane."""
    n = math.sqrt(sum(v * v for v in stress_axis)) or 1.0
    return abs(stress_axis[2]) / n <= POSE_TOL


def screw_thickness(M, b):
    """plate thickness for a bending moment M (N.mm) on width b at the 4 MPa across-the-layers allowable; min 4."""
    return max(4.0, math.ceil(math.sqrt(6.0 * M / (b * ALONG["alt"])) * 2.0 - 1e-9) / 2.0)


def cup_dims(p):
    """ring sizes from the payload's datasheet numbers (+ the loose fit and 1.0 mm)."""
    lf = _g("loose_fit")
    body = p.get("body_d") or p.get("base_d")
    base = p.get("base_d") or body
    id_b = base + 2 * lf + 1.0
    id_t = body + 2 * lf + 1.0
    depth = min(0.4 * float(p.get("height") or 175.0), 70.0)
    wall = 2.4
    return {"id_bottom": id_b, "id_top": id_t, "depth": depth, "wall": wall, "floor": 3.0,
            "ro_max": max(id_b, id_t) / 2 + wall, "handle_w": p.get("handle_w")}


# ------------------------------------------------------------------ shape helpers
def cyl_y(r, length):
    return Rot(90, 0, 0) * Cylinder(r, length)


def prism_y(pts, length):
    """extrude a polygon given in (x, z) along Y, centred on y=0."""
    with BuildSketch(Plane.XZ) as sk:
        Polygon(*pts, align=None)
    return extrude(sk.sketch, length / 2.0, both=True)


def prism_z(pts, height, z0=0.0):
    """extrude a polygon given in (x, y) along Z from z0."""
    with BuildSketch(Plane.XY.offset(z0)) as sk:
        Polygon(*pts, align=None)
    return extrude(sk.sketch, height)


def teardrop_bore(rb, length):
    """a horizontal bore (axis Y) of radius rb with its roof above 45 deg replaced by a 45 deg peak (prints without supports)."""
    a = rb / SQ2
    kite = prism_y([(-a, a), (0, rb * SQ2), (a, a), (0, 0)], length)
    return cyl_y(rb, length) + kite


def hole_z(x, y, d, z0, z1):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, z1 - z0)


def hex_trap(x, y, across_flats, z_top, depth):
    r = across_flats / math.sqrt(3.0)          # circumradius
    with BuildSketch(Plane.XY.offset(z_top - depth)) as sk:
        with Locations((x, y)):
            RegularPolygon(r, 6)
    return extrude(sk.sketch, depth + 0.05)


def frustum(r0, r1, h, align=(Align.CENTER, Align.CENTER, Align.MIN)):
    """cone from radius r0 (bottom) to r1 (top); a plain cylinder when they match."""
    if abs(r0 - r1) < 1e-6:
        return Cylinder(r0, h, align=align)
    return Cone(r0, r1, h, align=align)


def fuse(*solids):
    out = solids[0]
    for s in solids[1:]:
        out = out + s
    return out


# ------------------------------------------------------------------ payloads
def cup_solid(p, xc, arm_x0, W, extra=None):
    """upright cup ring (floor on the bed) at (xc, 0) with an arm block from arm_x0 to the ring centre. Local frame: bed z=0."""
    d = cup_dims(p)
    h = d["floor"] + d["depth"]
    outer = Pos(xc, 0, 0) * frustum(d["id_bottom"] / 2 + d["wall"], d["id_top"] / 2 + d["wall"], h)
    arm = Pos((arm_x0 + xc) / 2, 0, ARM_H / 2) * Box(xc - arm_x0, W, ARM_H)
    body = outer + arm
    if extra is not None:
        body = body + extra
    k = (d["depth"] + 1.0) / d["depth"]
    r_top = d["id_bottom"] / 2 + (d["id_top"] / 2 - d["id_bottom"] / 2) * k
    body = body - Pos(xc, 0, d["floor"]) * frustum(d["id_bottom"] / 2, r_top, d["depth"] + 1.0)
    body = body - Pos(xc, 0, d["floor"] / 2) * Cylinder(4.0, d["floor"] + 0.2)                 # drain hole, 8 mm
    if d["handle_w"]:
        sw = float(d["handle_w"]) + 4.0
        body = body - Pos(xc, d["ro_max"] / 2 + 1.0, d["floor"] + d["depth"] / 2 + 0.5) * Box(sw, d["ro_max"] + 2.0, d["depth"] + 1.0)
    return body, d


def cup_checks(xc, d):
    """known-answer probes in the cup piece's local frame."""
    zmid = d["floor"] + d["depth"] / 2.0
    rid = d["id_bottom"] / 2.0 + (d["id_top"] - d["id_bottom"]) / 4.0       # radius at mid-depth
    return [("cup is hollow just inside the ring", "empty_at", [xc + rid - 0.1, 0, zmid]),
            ("cup wall is solid at mid-wall", "solid_at", [xc + rid + d["wall"] / 2.0, 0, zmid]),
            ("drain hole is open", "empty_at", [xc, 0, d["floor"] / 2.0]),
            ("cup floor is solid", "solid_at", [xc + rid, 0, d["floor"] / 2.0])]


def offset_x(clear_from, p_dims, obstacles):
    """ring centre x: ring OD clear of the interface by 3 mm and of every obstacle keep-out (max, not sum)."""
    keep = max([3.0] + [float(o.get("keep_out_mm", 10.0)) for o in (obstacles or [])])
    return clear_from + keep + p_dims["ro_max"], keep


# ------------------------------------------------------------------ interface 1: clamp-round (+ cup)
def clamp_half(cp, lower):
    rb = cp["D_lo"] / 2.0
    ro = rb * SQ2 + 3.0
    t = max(FL, NUT_DEPTH + 2.2) if lower else FL            # the nut trap must leave a >= 2 mm floor (2.2 so tessellation never reads 1.99)
    hole_d = 4.0 + 2 * _g("hole_comp")
    xb = ro + 6.0
    x_end = xb + 6.5
    dome = cyl_y(ro, W_CLAMP) & Pos(0, 0, ro / 2) * Box(2 * ro + 2, W_CLAMP + 2, ro)
    body = dome
    for sx in (-1, 1):
        cx = sx * ((ro - 1.0) + x_end) / 2.0
        body = body + Pos(cx, 0, t / 2) * Box(x_end - (ro - 1.0), W_CLAMP, t)
    body = body - teardrop_bore(rb, W_CLAMP + 2.0)
    s = 7.0 + 2 * _g("snug_fit")
    for sx in (-1, 1):
        body = body - hole_z(sx * xb, 0, hole_d, -0.05, t + 0.05)
        if lower:
            body = body - hex_trap(sx * xb, 0, s, t, NUT_DEPTH)
    return body, {"ro": ro, "xb": xb, "x_end": x_end, "t": t, "rb": rb}


def build_clamp(analysis, cp, pay, obstacles, W=W_CLAMP):
    lower, gl = clamp_half(cp, True)
    upper, gu = clamp_half(cp, False)
    ro, xb, x_end = gl["ro"], gl["xb"], gl["x_end"]
    pieces = [{"name": "clamp_lower", "solid": lower, "asm": Pos(0, 0, -cp["G_A"] / 2) * Rot(0, 180, 0), "checks": [], "role": "interface"},
              {"name": "clamp_upper", "solid": upper, "asm": Pos(0, 0, cp["G_A"] / 2), "checks": [], "role": "interface"}]
    info = {"arm_x_bolt": xb, "tab": TAB}
    if pay["kind"] == "cup":
        dims = cup_dims(pay)
        xc, keep = offset_x(x_end, dims, obstacles)
        arm_x0 = xb + 5.0
        hole_d = 4.0 + 2 * _g("hole_comp")
        tab = Pos((ro - 0.5 + arm_x0 + 1.0) / 2, 0, TAB / 2) * Box(arm_x0 + 1.0 - (ro - 0.5), W, TAB)
        solid, d = cup_solid(pay, xc, arm_x0, W, extra=tab)
        solid = solid - hole_z(xb, 0, hole_d + 0.4, -0.05, TAB + 0.05)
        pieces.append({"name": "cup_arm", "solid": solid, "asm": Pos(0, 0, cp["G_A"] / 2 + FL), "checks": cup_checks(xc, d), "role": "payload"})
        info.update({"xc": xc, "keep_mm": keep, "L": xc - xb, "b": W, "h": ARM_H, "stress_axis": [1, 0, 0], "offset_m": xc / 1000.0})
    else:
        raise ValueError("clamp-round carries a cup; for a hook use a hookover style on a desk edge")
    return pieces, info, {"ro": ro, "xb": xb}


# ------------------------------------------------------------------ interface 2: hookover (+ hook)
def build_hookover(analysis, pay, A, B):
    t = T_HOOK
    B = max(float(B or 30.0), 22.0)
    gap = A + 1.0
    W = max(20.0, float(pay.get("band_w", 40.0)) + 4.0) if pay["kind"] == "hook" else 20.0
    u_in = B - 2.0
    vb = -gap - t                                                  # underside of the bottom bar
    rects = [(-t, u_in, 0, t),                                     # top bar
             (-t, 0, vb, t),                                       # outer leg
             (-t, 15.0, vb, vb + t)]                               # inner lip under the edge
    lip_len = 40.0 if pay["kind"] == "hook" else 0.0
    if pay["kind"] == "hook":
        rects.append((-t - lip_len, -t, vb, vb + t))               # hook arm (40 mm)
        rects.append((-t - lip_len, -t - lip_len + t, vb, vb + t + 12.0))   # 12 mm upturned lip
    with BuildSketch(Plane.XY) as sk:
        for (u0, u1, v0, v1) in rects:
            with Locations(((u0 + u1) / 2, (v0 + v1) / 2)):
                Rectangle(u1 - u0, v1 - v0)
        # flex finger: 1.6 thick, 18 long, hangs from the top bar's inner end, tip 3.0 mm into the gap
        with BuildLine() as ln:
            Polyline((u_in, 0.05), (u_in - 18.0, -3.0), (u_in - 18.0, -3.0 - 1.6), (u_in, -1.6), (u_in, 0.05))
        make_face()
        if pay["kind"] == "hook":                                  # saddle: rounded inside corner where the band rests
            rf = min(15.0, 12.0) * 0.6
            ucx = -t - lip_len + t + rf
            with Locations((ucx, vb + t + rf)):
                Rectangle(rf, rf, align=(Align.MAX, Align.MAX), mode=Mode.ADD)
            with Locations((ucx, vb + t + rf)):
                Circle(rf, mode=Mode.SUBTRACT)
    solid = extrude(sk.sketch, W)
    umin = -t - lip_len
    vmin = vb
    mid_u = 6.0
    chk = [("the gap is open under the bar", "empty_at", [mid_u, -(A - 2.2), W / 2.0]),
           ("the bar is solid", "solid_at", [u_in / 2.0, t / 2.0, W / 2.0])]
    piece = {"name": "hookover", "solid": solid, "asm": None, "checks": chk, "role": "interface+payload"}
    info = {"A": A, "B": B, "W": W, "gap": gap, "range_mm": [A - 2.0, A + 1.0], "range_text": f"Grips desks {A - 2:g}–{A + 1:g} mm thick",
            "stress_axis": [1, 0, 0], "L": lip_len + t if lip_len else 20.0, "b": W, "h": t, "umin": umin, "vmin": vmin}
    return [piece], info


# ------------------------------------------------------------------ interface 3: strap (+ cup)
def build_strap(analysis, pay, A, obstacles):
    rs = A / 2.0 + _g("loose_fit")
    ys = 30.0
    xh = rs + 11.5
    ztop = rs * SQ2 + 4.0
    block = Pos(0, 0, ztop / 2) * Box(2 * xh, ys, ztop)
    block = block - teardrop_bore(rs, ys + 2.0)
    for sx in (-1, 1):
        block = block - Pos(sx * (rs + 4.0 + 1.75), 0, ztop / 2) * Box(3.5, 22.0, ztop + 1.0)
    pieces_info = {"A": A, "range_mm": [A - 5.0, A + 40.0], "range_text": f"Grips {A - 5:g}–{A + 40:g} mm tube with a 20 mm strap (strap length)"}
    chk = []
    if pay["kind"] != "cup":
        raise ValueError("strap carries a cup in this build")
    dims = cup_dims(pay)
    xc, keep = offset_x(xh, dims, obstacles)
    solid, d = cup_solid(pay, xc, xh - 1.0, 24.0, extra=block)
    chk = cup_checks(xc, d)
    pieces_info.update({"xc": xc, "keep_mm": keep, "L": xc - xh / 2.0, "b": 24.0, "h": ARM_H, "stress_axis": [1, 0, 0], "offset_m": xc / 1000.0})
    return [{"name": "strap_saddle_cup", "solid": solid, "asm": None, "checks": chk, "role": "interface+payload"}], pieces_info


# ------------------------------------------------------------------ interface 4: screw (+ cup)
def build_screw(analysis, pay, obstacles, mass_g, factor):
    if pay["kind"] != "cup":
        raise ValueError("screw plate carries a cup in this build")
    dims = cup_dims(pay)
    wp, hp = 44.0, 76.0
    plate_x = 0.0
    xc, keep = offset_x(0.0, dims, obstacles)
    L = xc
    M = mass_g / 1000.0 * 9.81 * factor * L
    t = screw_thickness(M, wp)
    plate = Pos(-t / 2, 0, hp / 2) * Box(t, wp, hp)
    for z in (hp / 2 - 20.0, hp / 2 + 20.0):
        plate = plate - Pos(-t / 2, 0, z) * Rot(0, 90, 0) * Cylinder(2.0, t + 1.0)
        plate = plate - Pos(0.01, 0, z) * Rot(0, 90, 0) * Cone(2.0, 4.0, 2.0, align=(Align.CENTER, Align.CENTER, Align.MAX))
    solid, d = cup_solid(pay, xc, -0.5, wp, extra=plate)
    info = {"plate_t": t, "xc": xc, "keep_mm": keep, "L": L, "b": wp, "h": t, "M_Nmm": M, "stress_axis": [0, 0, 1], "offset_m": xc / 1000.0,
            "range_mm": None, "range_text": None}
    return [{"name": "screw_plate_cup", "solid": solid, "asm": None, "checks": cup_checks(xc, d), "role": "interface+payload"}], info


# ------------------------------------------------------------------ plate layout + build
def bbox_of(s):
    b = s.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def layout(pieces, bed_x, gap=10.0):
    """shelf-pack the pieces on one plate (10 mm gaps), every piece with its bbox min at z=0. Records piece["offset"] = (dx, dy)."""
    order = sorted(range(len(pieces)), key=lambda i: -(bbox_of(pieces[i]["solid"])[4] - bbox_of(pieces[i]["solid"])[1]))
    x = y = row_h = 0.0
    maxw = bed_x - 2 * gap
    for i in order:
        p = pieces[i]
        x0, y0, z0, x1, y1, z1 = bbox_of(p["solid"])
        w, h = x1 - x0, y1 - y0
        if x > 0 and x + w > maxw:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        dx, dy, dz = x - x0, y - y0, -z0
        p["offset"] = (dx, dy, dz)
        p["plate"] = Pos(dx, dy, dz) * p["solid"]
        x += w + gap
        row_h = max(row_h, h)
    return pieces


def style_for(analysis):
    return analysis.get("style")


def resolve_payload(analysis):
    p = dict(analysis.get("payload") or {})
    p.setdefault("kind", "cup")
    return p


def number(analysis, label, default=None):
    n = (analysis.get("numbers") or {}).get(label)
    if n and n.get("mm") is not None:
        return float(n["mm"]), n.get("source", "user")
    pr = ((analysis.get("interface") or {}).get("prior_mm") or {}).get(label)
    if pr is not None:
        return float(pr), "ASSUMED"
    if default is not None:
        return float(default), "ASSUMED"
    return None, None


def build(analysis, bed_x=220.0):
    """-> dict(pieces, mount, fit, checks, dummy). Raises ValueError("needs: ...") when a needed number is missing."""
    style = style_for(analysis)
    pay = resolve_payload(analysis)
    obstacles = analysis.get("obstacles") or []
    mass = float(pay.get("mass_full_g") or 500.0)
    factor = float((analysis.get("load") or {}).get("factor", 3.0))
    A, srcA = number(analysis, "A")
    if A is None:
        raise ValueError("needs: A (the interface size). Reply like: A 32")
    fitn = {}
    dummy = None
    if style == "clamp-round":
        cp = clamp_params(A, tab=TAB)
        pieces, info, gm = build_clamp(analysis, cp, pay, obstacles)
        hardware = f"2× M4×{cp['bolt_mm']} bolts + 2× M4 nuts"
        range_text, range_mm = cp["range_text"], cp["range_mm"]
        pad = info["offset_m"] * mass / 1000.0 * 9.81 > 0.3
        if pad:
            hardware += "; a 1 mm rubber strip in the bore stops it rotating under the full cup"
        note_pose = "Both clamp halves print split-face down and the cup prints upright; the arm bends along the layers."
        dummy = {"d": cp["D_lo"], "length": W_CLAMP + 6.0}
        extra = {"bolt_mm": cp["bolt_mm"], "G_A": round(cp["G_A"], 2), "c": round(cp["c"], 3), "pad_recommended": pad}
    elif style == "hookover":
        B, srcB = number(analysis, "B", 30.0)
        pieces, info = build_hookover(analysis, pay, A, B)
        hardware = ""
        range_text, range_mm = info["range_text"], info["range_mm"]
        note_pose = "It prints on its side so the hook pulls along the layers, not between them."
        extra = {"min_wall_mm": 1.5}                      # the flex finger is 1.6 mm on purpose
        fitn["reach on top B"] = {"mm": B, "source": srcB}
    elif style == "strap":
        pieces, info = build_strap(analysis, pay, A, obstacles)
        hardware = "a 20 mm hook-and-loop strap or 2 zip ties"
        range_text, range_mm = info["range_text"], info["range_mm"]
        note_pose = "The saddle prints roof-up on its side with a 45 degree peak, the cup upright; no supports."
        extra = {}
    elif style == "screw":
        pieces, info = build_screw(analysis, pay, obstacles, mass, factor)
        hardware = "2 #8 or M4 wood screws"
        range_text = range_mm = None
        note_pose = f"The plate stands upright so the cup prints upright; plate thickened to {info['plate_t']:g} mm for the across-the-layers allowable."
        extra = {}
    else:
        raise ValueError(f"unknown style {style!r}")
    along = along_layers_pose(info["stress_axis"]) if style != "screw" else False
    ld = load_check(mass, factor, info["L"], info["b"], info["h"], along)
    layout(pieces, bed_x)
    mount = {"style": style, "range_text": range_text, "range_mm": range_mm, "hardware": hardware, "load": ld,
             "pieces": [{"name": p["name"], "role": p["role"], "plate_offset": [round(v, 3) for v in p["offset"]]} for p in pieces],
             "print_pose": note_pose, "stress_axis": info["stress_axis"]}
    mount.update(extra)
    if style == "screw":
        mount["plate_t"] = info["plate_t"]
        mount["load"]["thickened_to"] = info["plate_t"]
    fitn["interface size A"] = {"mm": A, "source": srcA}
    return {"pieces": pieces, "mount": mount, "fit": fitn, "dummy": dummy, "info": info, "payload": pay}


# ------------------------------------------------------------------ fit comb
def comb(analysis, label, centre):
    """3 teeth at centre -1 / 0 / +1 on a spine. round: C-rings (bore = value, 2.0 wall, 8 tall, 90 deg opening at the bottom);
    edge: U-slots (width = value, 10 deep). Returns (solid, checks, names)."""
    style = analysis.get("style")
    section = (analysis.get("interface") or {}).get("section")
    vals = [centre - 1.0, centre, centre + 1.0]
    labels = ["-1", "0", "+1"]
    H, wall = 8.0, 2.0
    if section in ("round", "irregular") and style != "hookover":
        rmax = (max(vals) / 2.0) + wall
        pitch = 2 * rmax + 2.0
        xs = [-pitch, 0.0, pitch]
        body = None
        checks = []
        for x, v in zip(xs, vals):
            ring = Pos(x, 0, H / 2) * Cylinder(v / 2 + wall, H) - Pos(x, 0, H / 2) * Cylinder(v / 2, H + 1.0)
            k = v / 2 + wall + 2.0
            ring = ring - prism_z([(x, 0), (x - k, -k), (x + k, -k)], H + 1.0, -0.5)          # 90 deg opening at the front
            body = ring if body is None else body + ring
        ysp = min(vals) / 2 + wall - 1.0
        SP_H, SP_D = 3.0, 5.0                                                                  # low spine: carries the 6 mm labels
        body = body + Pos(0, ysp + SP_D / 2, SP_H / 2) * Box(2 * pitch + 12.0, SP_D, SP_H)
        for x, lab in zip(xs, labels):
            body = body + Pos(x, ysp + SP_D / 2, SP_H) * extrude(_label(lab, 6.0), 0.6)
        for x, v, lab in zip(xs, vals, labels):
            checks.append((f"tooth {lab}: bore is open", "empty_at", [x + v / 2 - 0.1, 0, 4.0]))
            checks.append((f"tooth {lab}: wall is solid", "solid_at", [x + v / 2 + 1.0, 0, 4.0]))
    else:
        w_blk, d_blk = 30.0, 22.0
        pitch = w_blk + 6.0
        xs = [-pitch, 0.0, pitch]
        body = None
        checks = []
        for x, v, lab in zip(xs, vals, labels):
            blk = Pos(x, 0, H / 2) * Box(w_blk, d_blk, H) - Pos(x, -d_blk / 2 + 5.0 - 0.01, H / 2) * Box(v, 10.0 + 0.02, H + 1.0)
            body = blk if body is None else body + blk
            body = body + Pos(x, d_blk / 2 - 5.0, H) * extrude(_label(lab, 6.0), 0.6)
            checks.append((f"tooth {lab}: slot is open", "empty_at", [x, -d_blk / 2 + 5.0, 4.0]))
            checks.append((f"tooth {lab}: wall is solid", "solid_at", [x + v / 2 + 2.0, -d_blk / 2 + 5.0, 4.0]))
        body = body + Pos(0, d_blk / 2 - 2.0, H / 2) * Box(2 * pitch + w_blk, 4.0, H)
    return body, checks, list(zip(labels, vals))


def _label(txt, size):
    for font in ("Arial Black", None):
        try:
            return Text(txt, font_size=size, font=font) if font else Text(txt, font_size=size)
        except Exception:
            continue
    raise RuntimeError("no font for the comb labels")


def export(shape, path):
    export_stl(shape, path, tolerance=0.01, angular_tolerance=0.05)
