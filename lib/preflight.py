#!/usr/bin/env python3
"""preflight: predict print failures BEFORE plastic (mini layer slicer on manifold3d). Model must be in PRINT pose.

    forge preflight model.stl [--slice] [--json out.json] [--heat]       (--heat needs Blender)

Checks (each one is a real failure seen while building and benchmarking this skill):
  contact    bed contact area + shape; knife-edge patch = peels (a helmet print once died on a 9x1 mm sliver)
  tip        centre of mass vs contact hull; tall + narrow = wobble/knock-over
  islands    a region that STARTS IN MID-AIR (no layer under it) = spaghetti unless supported
  overhang   area past 45 deg per layer; unsupported spans anchored on 2+ sides and < 18 mm = OK bridge
  walls      walls < 1.2 mm (won't print) and < 2.0 mm; per layer, opening by offset
  pip        print-in-place: separate bodies closer than fit.pip_gap; first-layer gaps < 0.35 mm fuse (elephant foot)
  bed        fits the printer bed (knowledge/printer.json)
Verdict: GO / CAUTION / GO+SUPPORTS (prints fine with the supports box ticked) / NO-GO (no checkbox saves it),
with plain-English reasons + fixes (geometry, orientation, supports on/off; never slicer tuning).
"""
import argparse, json, math, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import meshkit as mk
import fit
from manifold3d import CrossSection, JoinType

LAYER = 0.2
import printer
BED = printer.bed()


def _polys(cs):
    return [np.asarray(p) for p in cs.to_polygons()]


def _shapely(cs):
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
    polys = []
    for p in cs.to_polygons():
        p = np.asarray(p)
        if len(p) >= 3:
            polys.append(Polygon(p).buffer(0))
    return unary_union(polys) if polys else Polygon()


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


def analyse(path, do_slice=False, allow_tight=False):
    M = mk.load_manifold(path)
    lo = M.bounding_box()
    x0, y0, z0, x1, y1, z1 = lo
    if abs(z0) > 0.05:
        M = M.translate([0, 0, -z0]); z1 -= z0; z0 = 0.0
    t = mk.mf2tm(M)
    R = {"file": os.path.basename(path), "bbox_mm": [round(x1 - x0, 1), round(y1 - y0, 1), round(z1, 1)],
         "volume_cm3": round(M.volume() / 1000, 2), "issues": [], "notes": []}

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
    allow = LAYER * math.tan(math.radians(45))
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
                if len(anchors) >= 2 and span < 18:
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
    if over_area > 120:
        worst.sort(reverse=True)
        issue("SUPPORTS", "overhang", f"{over_area:.0f} mm2 of overhang past 45 deg that isn't a short bridge "
              f"(worst layer z={worst[0][1]:.1f}) -> droops/fails without supports",
              "tick supports (--supports auto), or chamfer the underside to 45 deg")
    elif over_area > 30:
        R["notes"].append(f"{over_area:.0f} mm2 of mild overhang (droopy underside, usually fine)")

    # ---- thin walls (every 4th layer)
    thin12, thin20 = [], []
    for k in range(0, len(layers), 4):
        cs = layers[k]
        if cs.is_empty():
            continue
        for r, bucket in ((0.6, thin12), (1.0, thin20)):
            opened = cs.offset(-r, JoinType.Round).offset(r, JoinType.Round)
            thin = cs - opened
            big = [q for q in thin.decompose() if q.area() > 1.2]
            if big:
                bucket.append((float(zs[k]), round(sum(q.area() for q in big), 1)))
    R["walls_under_1p2"] = thin12[:15]
    R["walls_under_2p0_layers"] = len(thin20)
    tot12 = sum(a for _, a in thin12)
    if thin12 and (len(thin12) >= 3 or tot12 > 10):
        issue("CAUTION", "walls", f"walls thinner than 1.2 mm on {len(thin12)} sampled layers (from z={thin12[0][0]:.1f}) "
              f"-> gaps or missing walls", "thicken to >= 2.0 (house minimum) or accept for text/labels")
    elif thin12:
        R["notes"].append(f"tiny thin spots (<1.2 mm) on {len(thin12)} layer(s), {tot12:.1f} mm2: edges/text, usually fine")
    elif len(thin20) > max(3, 0.2 * (len(layers) / 4)):
        issue("CAUTION", "walls", f"walls under 2.0 mm on {len(thin20)} sampled layers",
              "thicken to 2.0-2.4 mm")

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
                if (isl0[i].offset(0.175, JoinType.Round) ^ isl0[j].offset(0.175, JoinType.Round)).area() > 0.01:
                    fuse += 1
        if fuse and fit.tag("pip_gap") == "[R]" and not allow_tight:
            issue("CAUTION", "pip", f"{fuse} first-layer gap(s) under 0.35 mm: elephant foot may weld them "
                  f"(pip_gap {g} is still a research default)",
                  "print the Fit Card once (forge mech build fitcard) -> forge fit set pip_gap <smallest free>")
        elif fuse and allow_tight:
            R["notes"].append(f"{fuse} first-layer gaps under 0.35 mm: intended (calibration print)")
        elif fuse:
            R["notes"].append(f"{fuse} first-layer gaps at the calibrated pip_gap {g} [V] (Fit Card proved they break free)")

    # ---- slice (real time / grams via the slicer hook)
    if do_slice:
        t, g = printer.slice_stats(path, "on" if (floating or over_area > 120) else "off", timeout=1800)
        if t: R["print_time"] = t
        if g: R["grams"] = g
        if not t and not g:
            R["notes"].append("no slicer hook configured (printer.json slicer_cmd / FORGE_SLICER_CMD): slice the STL in your own slicer")

    lv = [i["level"] for i in R["issues"]]
    R["verdict"] = ("NO-GO" if "NO-GO" in lv else "GO+SUPPORTS" if "SUPPORTS" in lv else
                    "CAUTION" if "CAUTION" in lv else "GO")
    R["supports"] = "on" if "SUPPORTS" in lv else "off"
    return R, M


def orient_search(path, step=15, top=3):
    """try tilts about X and Y (step deg) + the 6 axis lays; score = contact (big good) - overhang (bad) - height.
    Organic parts often want an odd tilt (a helmet printed best tilted 20 deg on the back of the head)."""
    import trimesh
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
    ap.add_argument("--orient", action="store_true", help="search tilts for the best print pose (organic parts)")
    a = ap.parse_args()
    if a.orient:
        for c in orient_search(a.model):
            print(f"   pose rot_x={c['rot_x']:4d} rot_y={c['rot_y']:4d}: contact {c['contact_mm2']:6.0f} mm2, overhang "
                  f"{c['overhang_mm2']:6.0f} mm2, height {c['height']:5.1f}, fits {c['fits']}  score {c['score']}")
        sys.exit(0)
    R, M = analyse(a.model, a.slice, a.allow_tight)
    report(R)
    if a.json:
        json.dump(R, open(a.json, "w"), indent=1)
    if a.heat:
        heat_colors(M).export(a.heat)
        print("   heat     ->", a.heat)
    sys.exit(3 if R["verdict"] == "NO-GO" else 0)
