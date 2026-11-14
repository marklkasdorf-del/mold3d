#!/usr/bin/env python3
"""preflight: predict print failures BEFORE plastic (mini layer slicer on manifold3d). Model must be in PRINT pose.

    forge preflight model.stl [--slice] [--json out.json] [--heat]       (--heat needs Blender)

Checks (each one is a real failure seen while building and benchmarking this skill):
  contact    bed contact area + shape; knife-edge patch = peels (a helmet print once died on a 9x1 mm sliver)
  tip        centre of mass vs contact hull; tall + narrow = wobble/knock-over
  islands    a region that STARTS IN MID-AIR (no layer under it) = spaghetti unless supported
  overhang   area past overhang_deg per layer; unsupported spans anchored on 2+ sides and < bridge_mm = OK bridge; more than
             overhang_area_mm2 of the rest = supports
  walls      walls < min_wall_mm (won't print) and < fit.min_wall (house minimum); per layer, opening by offset
  pip        print-in-place: separate bodies closer than fit.pip_gap; first-layer gaps < first_layer_fuse_mm fuse (elephant foot)
  traps      AUTO-SUPPORT TRAPS: flat-ish undersides (slope from horizontal < support_angle) that sit < support_trap_gap over a
             DIFFERENT body; a slicer's "auto supports" would fill that gap and weld the parts (CYCLO-11's first print died of this)
  bed        fits the printer bed
Every threshold (bridge_mm, overhang_deg, min_wall_mm, first_layer_fuse_mm, support_angle, support_trap_gap, layer, bed) comes from the
printer profile (knowledge/printer.json; `forge printer` shows each with its source) and is written to the JSON under "limits".
Verdict: GO / CAUTION / GO+SUPPORTS (prints fine with the supports box ticked) / NO-GO (no checkbox saves it),
with plain-English reasons + fixes (geometry, orientation, supports on/off; never slicer tuning).
Traps => the report says "SUPPORTS: OFF (required)"; `forge export model.stl` carries that into a 3MF the slicer obeys.
"""
import argparse, json, math, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import meshkit as mk
import fit
from manifold3d import CrossSection, JoinType

import printer


def _polys(cs):
    return [np.asarray(p) for p in cs.to_polygons()]


def _shapely(cs):
    from shapely.geometry import Polygon, MultiPolygon
    polys = []
    for p in cs.to_polygons():
        p = np.asarray(p)
        if len(p) >= 3:
            polys.append(Polygon(p).buffer(0))
    if not polys:
        return Polygon()
    out = polys[0]
    for q in polys[1:]:
        out = out.symmetric_difference(q)           # even-odd: a hole stays a hole (a plate with a bore is not a solid disc)
    return out


def _span(u, anchors):
    """bridge span = 2 x the farthest any unsupported point is from its nearest anchor (bridge30 -> 30, roof 10x10 -> 10,
    a one-sided cantilever 25 mm long -> 50: correctly NOT a bridge)."""
    from shapely.ops import unary_union
    su = _shapely(u)
    if su.is_empty or not anchors:
        return 1e9
    an = unary_union([_shapely(a) for a in anchors])
    x0, y0, x1, y1 = su.bounds
    from shapely.geometry import Point
    best = 0.0
    n = 14
    for i in range(n + 1):
        for j in range(n + 1):
            p = Point(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n)
            if su.contains(p):
                best = max(best, p.distance(an))
    return 2 * best


def support_traps(t, angle=None, max_gap=None, samples_per_mm2=1.0, cap=30000):
    """auto-support traps: downward faces NOT on the bed whose slope from horizontal is < angle (slicers auto-support those),
    raycast straight down to the next solid; if that solid is a DIFFERENT body closer than max_gap, supports would fill the gap.
    -> list of dicts (one per body pair): area_mm2, gap_min/mean_mm, xy, z, bodies [upper, lower]. Pure trimesh (rtree ray engine)."""
    import trimesh
    angle = float(printer.get("support_angle") if angle is None else angle)
    max_gap = float(printer.get("support_trap_gap") if max_gap is None else max_gap)
    n = t.face_normals
    fz = t.vertices[t.faces][:, :, 2]
    sel = np.where((-n[:, 2] > math.cos(math.radians(angle))) & (fz.min(axis=1) > 0.05))[0]      # downward, flat-ish, off the bed
    if not len(sel) or len(t.faces) == 0:
        return []
    label = trimesh.graph.connected_component_labels(t.face_adjacency, node_count=len(t.faces))
    sub = t.submesh([sel], append=True)
    npts = int(min(cap, max(200, sub.area * samples_per_mm2)))
    pts, fi = trimesh.sample.sample_surface(sub, npts, seed=0)
    src = label[sel[fi]]
    w = sub.area / len(pts)                                           # each sample stands for this much underside area
    org = pts - np.array([0, 0, 0.01])
    loc, ir, it = t.ray.intersects_location(org, np.tile([0.0, 0.0, -1.0], (len(pts), 1)), multiple_hits=False)
    dst = label[it]
    gap = pts[ir, 2] - loc[:, 2]
    hit = (dst != src[ir]) & (gap < max_gap) & (gap > 0.0)
    out = {}
    for k in np.where(hit)[0]:
        out.setdefault((int(src[ir[k]]), int(dst[k])), []).append(k)
    res = []
    for (a, b), ks in out.items():
        ks = np.array(ks)
        p = pts[ir[ks]]
        def nm(c):
            bb = t.submesh([np.where(label == c)[0]], append=True).bounds
            return f"body {c} (z {bb[0][2]:.1f}-{bb[1][2]:.1f}, {bb[1][0] - bb[0][0]:.0f} mm wide)"
        res.append({"upper": nm(a), "lower": nm(b), "area_mm2": round(float(len(ks) * w), 1), "gap_min_mm": round(float(gap[ks].min()), 2),
                    "gap_mean_mm": round(float(gap[ks].mean()), 2), "xy": [round(float(p[:, 0].mean()), 1), round(float(p[:, 1].mean()), 1)],
                    "z": round(float(p[:, 2].mean()), 1), "samples": int(len(ks))})
    res.sort(key=lambda r: -r["area_mm2"])
    return res


def analyse(path, do_slice=False, allow_tight=False):
    LIM = printer.limits()
    LAYER = LIM["layer"]; BED = LIM["bed"]
    BRIDGE, OVERHANG, MINWALL, FUSE, OH_AREA = LIM["bridge_mm"], LIM["overhang_deg"], LIM["min_wall_mm"], LIM["first_layer_fuse_mm"], LIM["overhang_area_mm2"]
    HOUSE_WALL = fit.get("min_wall")                       # the recommended wall for generated parts (fit table), 2.0 by default
    M = mk.load_manifold(path)
    lo = M.bounding_box()
    x0, y0, z0, x1, y1, z1 = lo
    if abs(z0) > 0.05:
        M = M.translate([0, 0, -z0]); z1 -= z0; z0 = 0.0
    t = mk.mf2tm(M)
    R = {"file": os.path.basename(path), "bbox_mm": [round(x1 - x0, 1), round(y1 - y0, 1), round(z1, 1)],
         "volume_cm3": round(M.volume() / 1000, 2), "issues": [], "notes": [], "limits": LIM, "printer": printer.load().get("name")}

    def issue(level, code, msg, fix=None, **kw):
        R["issues"].append({"level": level, "code": code, "msg": msg, "fix": fix, **kw})

    # ---- bed fit
    ex = sorted([x1 - x0, y1 - y0])
    if ex[1] > BED[1] or z1 > BED[2]:
        issue("NO-GO", "bed", f"does not fit the bed ({R['bbox_mm']} vs {BED[0]:g}x{BED[1]:g}x{BED[2]:g})", "split it (forge split) or scale down")

    # ---- layers
    zs = np.arange(LAYER / 2, z1, LAYER)
    layers = [M.slice(float(z)) for z in zs]
    first = layers[0]
    A0 = first.area()
    R["contact_mm2"] = round(A0, 1)
    sh0 = _shapely(first)
    hull = sh0.convex_hull
    if not hull.is_empty:
        mrr = hull.minimum_rotated_rectangle
        xs, ys = mrr.exterior.coords.xy
        e = sorted({round(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]), 2) for i in range(4)})
        w_min, w_max = e[0], e[-1]
        R["contact_patch_mm"] = [w_min, w_max]
        if A0 < 25 or (w_min < 5 and w_max > 4 * w_min and z1 > 15):
            issue("NO-GO", "contact", f"bed contact is a knife edge: {A0:.0f} mm2, patch {w_min:.1f} x {w_max:.1f} mm "
                  f"for a {z1:.0f} mm tall part -> it peels or snaps off mid-print",
                  "re-orient onto a bigger flat face (forge verify --orient) or add a flat base / brim ears")
        elif A0 < 0.06 * (x1 - x0) * (y1 - y0) and z1 > 40:
            issue("CAUTION", "contact", f"small footprint ({A0:.0f} mm2) for a {z1:.0f} mm tall part",
                  "enable supports in your slicer or re-orient; keep the window closed (draft lifts PLA)")
    # ---- tip-over
    try:
        cm = t.center_mass
        from shapely.geometry import Point
        p = Point(cm[0], cm[1])
        inside = hull.contains(p)
        margin = hull.exterior.distance(p) if inside else -hull.exterior.distance(p)
        R["center_of_mass"] = [round(float(v), 1) for v in cm]
        R["com_margin_mm"] = round(float(margin), 1)
        if not inside and z1 > 10:
            lvl = "NO-GO" if abs(margin) > 0.25 * z1 else "CAUTION"
            issue(lvl, "tip", f"centre of mass is {abs(margin):.1f} mm OUTSIDE the contact patch -> leverage peels it off the bed",
                  "re-orient, or tick supports under the overhanging mass")
        elif margin < 3 and z1 > 3 * max(1.0, R.get("contact_patch_mm", [1])[0]):
            issue("CAUTION", "tip", f"tall and narrow: centre of mass only {margin:.1f} mm inside the patch", "brim or re-orient")
    except Exception as e:
        R["notes"].append(f"tip check skipped: {e!r}"[:120])

    # ---- islands + overhangs (layer by layer)
    allow = LAYER * math.tan(math.radians(OVERHANG))       # how far a layer may step out over the one below
    floating, over_area, bridges, worst = [], 0.0, [], []
    for k in range(1, len(layers)):
        cur, prev = layers[k], layers[k - 1]
        if cur.is_empty():
            continue
        prev_g = prev.offset(allow, JoinType.Round)
        for isl in cur.decompose():
            a = isl.area()
            if a < 0.4:
                continue
            if (isl ^ prev).area() < 0.05:
                c = isl.bounds()
                floating.append({"z": round(float(zs[k]), 2), "xy": [round((c[0] + c[2]) / 2, 1), round((c[1] + c[3]) / 2, 1)],
                                 "area": round(a, 1)})
                continue
            un = isl - prev_g
            ua = un.area()
            if ua < 0.5:
                continue
            for u in un.decompose():
                if u.area() < 0.5:
                    continue
                anchors = [q for q in (u.offset(0.3, JoinType.Round) ^ prev).decompose() if q.area() > 0.05]
                span = _span(u, anchors)
                if len(anchors) >= 2 and span < BRIDGE:
                    bridges.append(span)
                else:
                    over_area += u.area() * LAYER / LAYER
                    worst.append((u.area(), float(zs[k])))
    R["floating_islands"] = floating[:20]
    R["overhang_unsupported_mm2"] = round(over_area, 1)
    R["bridges"] = {"count": len(bridges), "max_span_mm": round(max(bridges), 1) if bridges else 0}
    if floating:
        # merge islands that start at similar places (one feature = many layers)
        zlist = sorted({f["z"] for f in floating})
        issue("SUPPORTS", "islands",
              f"{len(floating)} region(s) start in MID-AIR (first at z={zlist[0]} mm, e.g. at xy {floating[0]['xy']}) "
              f"-> spaghetti without supports", "tick supports (--supports on) or re-orient so it grows from the bed")
    if over_area > OH_AREA:
        worst.sort(reverse=True)
        issue("SUPPORTS", "overhang", f"{over_area:.0f} mm2 of overhang past {OVERHANG:g} deg that isn't a short bridge (< {BRIDGE:g} mm) "
              f"(worst layer z={worst[0][1]:.1f}) -> droops/fails without supports",
              f"tick supports (--supports auto), or chamfer the underside to {OVERHANG:g} deg")
    elif over_area > OH_AREA / 4:
        R["notes"].append(f"{over_area:.0f} mm2 of mild overhang (droopy underside, usually fine; supports asked above {OH_AREA:g} mm2)")

    # ---- thin walls (every 4th layer)
    thin12, thin20 = [], []
    for k in range(0, len(layers), 4):
        cs = layers[k]
        if cs.is_empty():
            continue
        for r, bucket in ((MINWALL / 2, thin12), (HOUSE_WALL / 2, thin20)):
            opened = cs.offset(-r, JoinType.Round).offset(r, JoinType.Round)
            thin = cs - opened
            big = [q for q in thin.decompose() if q.area() > 1.2]
            if big:
                bucket.append((float(zs[k]), round(sum(q.area() for q in big), 1)))
    R["walls_under_1p2"] = thin12[:15]
    R["walls_under_2p0_layers"] = len(thin20)
    tot12 = sum(a for _, a in thin12)
    if thin12 and (len(thin12) >= 3 or tot12 > 10):
        issue("CAUTION", "walls", f"walls thinner than {MINWALL:g} mm on {len(thin12)} sampled layers (from z={thin12[0][0]:.1f}) "
              f"-> gaps or missing walls", f"thicken to >= {HOUSE_WALL:g} (house minimum) or accept for text/labels", kind="unprintable")
    elif thin12:
        R["notes"].append(f"tiny thin spots (<{MINWALL:g} mm) on {len(thin12)} layer(s), {tot12:.1f} mm2: edges/text, usually fine")
    elif len(thin20) > max(3, 0.2 * (len(layers) / 4)):
        issue("CAUTION", "walls", f"walls under {HOUSE_WALL:g} mm on {len(thin20)} sampled layers",
              f"thicken to {HOUSE_WALL:g}-{HOUSE_WALL + 0.4:g} mm", kind="fragile")

    # ---- print-in-place / multi-body
    bodies = [q for q in M.decompose() if q.volume() > 0.5]
    R["bodies"] = len(bodies)
    g = fit.get("pip_gap")
    if 1 < len(bodies) <= 40:
        tight = []
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                d = bodies[i].min_gap(bodies[j], 1.0)
                if d < 1.0:
                    tight.append(round(d, 3))
        R["pip_min_gap"] = min(tight) if tight else None
        if tight and min(tight) < 0.8 * g and not allow_tight:
            issue("NO-GO", "pip", f"moving parts only {min(tight):.2f} mm apart (calibrated pip_gap {g}) -> they fuse",
                  f"open the gap to >= {g} mm")
        # first-layer fuse risk
        isl0 = [q for q in first.decompose() if q.area() > 0.3]
        fuse = 0
        for i in range(len(isl0)):
            for j in range(i + 1, len(isl0)):
                if (isl0[i].offset(FUSE / 2, JoinType.Round) ^ isl0[j].offset(FUSE / 2, JoinType.Round)).area() > 0.01:
                    fuse += 1
        if fuse and fit.tag("pip_gap") == "[R]" and not allow_tight:
            issue("CAUTION", "pip", f"{fuse} first-layer gap(s) under {FUSE:g} mm: elephant foot may weld them "
                  f"(pip_gap {g} is still a research default)",
                  "print the Fit Card once (forge mech build fitcard) -> forge fit set pip_gap <smallest free>")
        elif fuse and allow_tight:
            R["notes"].append(f"{fuse} first-layer gaps under {FUSE:g} mm: intended (calibration print)")
        elif fuse:
            R["notes"].append(f"{fuse} first-layer gaps at the calibrated pip_gap {g} [V] (Fit Card proved they break free)")

    # ---- auto-support traps (needs the body split above)
    R["support_angle_deg"] = float(printer.get("support_angle")); LIM["support_angle"] = R["support_angle_deg"]   # --support-angle override
    R["support_traps"] = []
    if len(bodies) > 1:
        try:
            R["support_traps"] = support_traps(t)
        except Exception as e:
            R["notes"].append(f"support-trap check skipped: {e!r}"[:120])
    for tr in R["support_traps"]:
        issue("TRAP", "traps", f"auto supports would fill the {tr['gap_min_mm']:.2f} mm gap between {tr['upper']} and {tr['lower']} "
              f"(flat underside, {tr['area_mm2']:.0f} mm2, around xy {tr['xy']}, z={tr['z']}) and weld them -> supports must be OFF",
              "untick supports / print the `forge export` 3MF; or make that underside steeper than "
              f"{R['support_angle_deg']:g} deg from horizontal (chamfer to 45)")

    # ---- slice (real time / grams via the slicer hook)
    if do_slice:
        t, g = printer.slice_stats(path, "off" if R["support_traps"] else "on" if (floating or over_area > OH_AREA) else "off", timeout=1800)
        if t: R["print_time"] = t
        if g: R["grams"] = g
        if not t and not g:
            R["notes"].append("no slicer hook configured (printer.json slicer_cmd / FORGE_SLICER_CMD): slice the STL in your own slicer")

    lv = [i["level"] for i in R["issues"]]
    if "TRAP" in lv and "SUPPORTS" in lv:
        issue("NO-GO", "traps", "this part NEEDS supports (mid-air islands / steep overhangs) but supports would weld the print-in-place gaps "
              "-> no checkbox saves it", "re-orient so nothing needs support, chamfer the flat undersides to 45 deg, or print the bodies separately")
        lv = [i["level"] for i in R["issues"]]
    R["verdict"] = ("NO-GO" if "NO-GO" in lv else "GO+SUPPORTS" if "SUPPORTS" in lv else
                    "CAUTION" if "CAUTION" in lv else "GO")
    R["supports"] = "on" if "SUPPORTS" in lv else "off"
    R["supports_text"] = ("SUPPORTS: OFF (required) - auto supports would weld " + f"{sum(t_['area_mm2'] for t_ in R['support_traps']):.0f} mm2 of "
                          f"{len(R['support_traps'])} gap region(s)") if "TRAP" in lv and "SUPPORTS" not in lv and R["verdict"] != "NO-GO" else \
        "SUPPORTS: ON (needed)" if R["supports"] == "on" else "SUPPORTS: off (not needed)"
    return R, M


def orient_search(path, step=15, top=3):
    """try tilts about X and Y (step deg) + the 6 axis lays; score = contact (big good) - overhang (bad) - height.
    Organic parts often want an odd tilt (a helmet printed best tilted 20 deg on the back of the head)."""
    import trimesh
    BED = printer.bed()
    t0 = mk.mf2tm(mk.load_manifold(path))
    cands = []
    angs = list(range(-90, 91, step)) + [180]
    for ax in angs:
        for ay in range(-90, 91, step):
            T = trimesh.transformations.euler_matrix(math.radians(ax), math.radians(ay), 0, "sxyz")
            t = t0.copy(); t.apply_transform(T)
            t.apply_translation(-t.bounds[0])
            ext = t.extents
            fits = sorted(ext[:2])[1] <= BED[1] and ext[2] <= BED[2] and sorted(ext[:2])[0] <= BED[0]
            n, a, z = t.face_normals, t.area_faces, t.triangles_center[:, 2]
            contact = a[(n[:, 2] < -0.97) & (z < 0.3)].sum()
            over = a[(n[:, 2] < -math.cos(math.radians(45))) & (z > 0.6)].sum()
            score = (min(contact, 3000) ** 0.5) * 8 - over * 0.05 - ext[2] * 0.3 - (0 if fits else 1e6)
            cands.append({"rot_x": ax, "rot_y": ay, "contact_mm2": round(float(contact), 0), "overhang_mm2": round(float(over), 0),
                          "height": round(float(ext[2]), 1), "fits": bool(fits), "score": round(float(score), 1)})
    cands.sort(key=lambda c: -c["score"])
    out, seen = [], []
    for c in cands:                                  # keep distinct poses
        if all(abs(c["rot_x"] - d["rot_x"]) + abs(c["rot_y"] - d["rot_y"]) > 2 * step for d in seen):
            out.append(c); seen.append(c)
        if len(out) >= top:
            break
    return out


def heat_colors(M):
    import trimesh
    """per-vertex colour: overhang angle (green ok -> yellow 45 -> red flat ceiling); bed faces blue."""
    t = mk.mf2tm(M)
    n = t.face_normals
    z = t.triangles_center[:, 2]
    down = -n[:, 2]
    ang = np.degrees(np.arccos(np.clip(down, -1, 1)))    # 0 = facing straight down
    col = np.zeros((len(n), 4), np.uint8); col[:, 3] = 255
    for i, (a, d, zc) in enumerate(zip(ang, down, z)):
        if zc < 0.15 and d > 0.9:
            col[i, :3] = (70, 120, 230)                  # bed contact
        elif d <= 0.0 or a >= 55:
            col[i, :3] = (205, 210, 200)                 # fine
        elif a >= 45:
            col[i, :3] = (245, 200, 60)                  # borderline
        else:
            col[i, :3] = (230, 60, 50)                   # needs support
    # Blender's PLY importer reads VERTEX colours only: give every face its own 3 vertices, colour them exactly
    t2 = trimesh.Trimesh(t.vertices[t.faces].reshape(-1, 3), np.arange(len(t.faces) * 3).reshape(-1, 3), process=False)
    t2.visual.vertex_colors = np.repeat(col, 3, axis=0)
    return t2


def report(R):
    icon = R["verdict"]
    print(f"[{icon}] {R['file']}  bbox {R['bbox_mm']} mm  vol {R['volume_cm3']} cm3  contact {R.get('contact_mm2')} mm2 "
          f"patch {R.get('contact_patch_mm')}  bodies {R.get('bodies')}")
    print(f"   {R['supports_text']}")
    L = R.get("limits", {})
    if L:
        print(f"   limits   {R.get('printer')}: bridge < {L['bridge_mm']:g} mm, overhang {L['overhang_deg']:g} deg, wall >= {L['min_wall_mm']:g} mm, "
              f"first-layer fuse < {L['first_layer_fuse_mm']:g} mm, auto-support < {L['support_angle']:g} deg  (forge printer: sources)")
    for i in R["issues"]:
        print(f"   {i['level']:8s} {i['code']:9s} {i['msg']}")
        if i.get("fix"):
            print(f"            fix: {i['fix']}")
    for n in R["notes"]:
        print(f"   note     {n}")
    if "print_time" in R:
        print(f"   slice    {R['print_time']}, {R.get('grams')} g")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("--slice", action="store_true"); ap.add_argument("--json")
    ap.add_argument("--heat", help="write a risk-coloured PLY here (render with forge heat)")
    ap.add_argument("--allow-tight", action="store_true", help="calibration prints (Fit Card): tight gaps are intended")
    ap.add_argument("--support-angle", type=float, help="slicer auto-support threshold, deg from horizontal (default: the printer profile's support_angle)")
    ap.add_argument("--orient", action="store_true", help="search tilts for the best print pose (organic parts)")
    a = ap.parse_args()
    if a.orient:
        for c in orient_search(a.model):
            print(f"   pose rot_x={c['rot_x']:4d} rot_y={c['rot_y']:4d}: contact {c['contact_mm2']:6.0f} mm2, overhang "
                  f"{c['overhang_mm2']:6.0f} mm2, height {c['height']:5.1f}, fits {c['fits']}  score {c['score']}")
        sys.exit(0)
    if a.support_angle is not None:
        os.environ["FORGE_SUPPORT_ANGLE"] = str(a.support_angle)
    R, M = analyse(a.model, a.slice, a.allow_tight)
    report(R)
    if a.json:
        json.dump(R, open(a.json, "w"), indent=1)
    if a.heat:
        heat_colors(M).export(a.heat)
        print("   heat     ->", a.heat)
    sys.exit(3 if R["verdict"] == "NO-GO" else 0)
