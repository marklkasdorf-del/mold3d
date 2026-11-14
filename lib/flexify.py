#!/usr/bin/env python3
"""flexify: turn ANY creature/object mesh lying on the bed into a print-in-place articulated "flexi" print.

    forge flexify model.stl [--spacing 13] [--theta 25] [--joints-x x1,x2,..] [--out DIR] [--no-align]

Why this exists (bench 2026-10-17): humans out-sculpt the model, the model out-engineers them. Flexify = take a human sculpt (or a
text->3D figure) and add a verified mechanism: hinge joints that print in place, flex, and never fuse.

Joint = "lap joint around a cone pin" (the proven balisong pivot + the gyro trick in 2D):
  * The back segment owns a DISC (radius Ra) in the LOWER layer; the front segment owns a CAP over it (upper layer),
    with a vertical gap vg between them and a cone pin from the cap down through the disc (wide at the bed = captured).
  * Every cut that rotates is an arc centred on the pin, so the gap stays exactly g through the whole swing.
  * Outside the core, a V-notch (front wedge narrowed by theta each side) gives the swing room: +-(theta-3) deg.
Self-test per joint: swing everything behind it +-theta_m (must be clear), lift the back segment 1.5 mm (must jam),
exact min gaps via manifold3d. Output: parts/segNN.stl, flexi.stl, mech.json (chain spec for the web animation).
"""
import argparse, json, math, os, sys
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forge_env
import meshkit as mk
import fit
from manifold3d import Manifold

BIG = 3000.0


def align_to_x(t: trimesh.Trimesh):
    """rotate about Z so the longest horizontal direction is +X; bottom on z=0; centred in XY."""
    xy = t.vertices[:, :2] - t.vertices[:, :2].mean(0)
    w, v = np.linalg.eigh(np.cov(xy.T))
    d = v[:, np.argmax(w)]
    if d[0] < 0:                      # PCA sign is arbitrary: pick the direction that rotates least (no 180 flips)
        d = -d
    ang = -math.atan2(d[1], d[0])
    R = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
    t = t.copy(); t.apply_transform(R)
    t.apply_translation([-t.bounds.mean(0)[0], -t.bounds.mean(0)[1], -t.bounds[0][2]])
    return t


def flat_bottom(M: Manifold, t: trimesh.Trimesh, min_contact_frac=0.25):
    """organic bottoms touch the bed at a point: trim a sliver so there is a real first layer."""
    zmin = t.bounds[0][2]
    for cut in (0.0, 0.4, 0.8, 1.2, 1.6, 2.0):
        sec = M.trim_by_plane([0, 0, 1], zmin + cut + 0.01).slice(zmin + cut + 0.02)
        if sec.area() >= min_contact_frac * (t.extents[0] * t.extents[1]) * 0.25:
            break
    if cut > 0:
        M = M.trim_by_plane([0, 0, 1], zmin + cut)
    return M.translate([0, 0, -(zmin + cut)]), cut


def spine(M: Manifold, n=160):
    """cross-sections perpendicular to X -> centre y, width, top height per x."""
    R = M.rotate([0, -90, 0])                 # world x -> local z (slice axis); local x = -world z, local y = world y
    lo, hi = M.bounding_box()[0], M.bounding_box()[3]
    xs = np.linspace(lo + 0.5, hi - 0.5, n)
    rows = []
    for x in xs:
        cs = R.slice(float(x))
        a = cs.area()
        if a < 0.5:
            rows.append((x, np.nan, 0.0, 0.0, 0.0, 0)); continue
        isl = len([c for c in cs.decompose() if c.area() > 0.8])
        pts = np.concatenate([np.asarray(p) for p in cs.to_polygons()])
        ys, zs = pts[:, 1], -pts[:, 0]
        cy = 0.0; A = 0.0
        for poly in cs.to_polygons():
            p = np.asarray(poly); yy, xx = p[:, 1], p[:, 0]
            cr = xx * np.roll(yy, -1) - np.roll(xx, -1) * yy
            A += cr.sum() / 2; cy += ((yy + np.roll(yy, -1)) * cr).sum() / 6
        cy = cy / A if abs(A) > 1e-9 else ys.mean()
        rows.append((x, cy, ys.max() - ys.min(), zs.max(), a, isl))
    S = np.array(rows)
    ok = ~np.isnan(S[:, 1])
    S[~ok, 1] = np.interp(S[~ok, 0], S[ok, 0], S[ok, 1])
    k = 7
    S[:, 1] = np.convolve(np.pad(S[:, 1], k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    return S


def joint_regions(Ra, g, vg, zs, theta, r0, r1, ztop):
    """front/back regions of one joint in its LOCAL frame (pin at origin, +X = toward the head)."""
    cylIn = mk.cyl(Ra, -1, ztop)
    cylG = mk.cyl(Ra + g, -1, ztop)
    ringG = cylG - cylIn
    back = mk.box(-BIG, -BIG, -1, 0, BIG, ztop)
    a = math.radians(90 - theta)
    wedgeF = mk.prism([(0, 0), (BIG * math.cos(a), BIG * math.sin(a)), (BIG, BIG * math.sin(a)),
                       (BIG, -BIG * math.sin(a)), (BIG * math.cos(a), -BIG * math.sin(a))], -1, ztop)
    lower = mk.box(-BIG, -BIG, -1, BIG, BIG, zs)
    upper = mk.box(-BIG, -BIG, zs + vg, BIG, BIG, ztop)
    pin = mk.cyl(r0, 0, zs, r_top=r1, seg=64) + mk.cyl(r1, zs - 0.01, zs + vg + 1.0, seg=64)
    gn = g / math.cos(math.atan((r0 - r1) / zs))
    # cutters OVERLAP by 0.05 mm: coplanar faces (hole top flush with the disc top) leave a zero-thickness skin that
    # welds the pin (measured: gap 0.0 instead of 0.3). Extend the cone slightly past both faces, slope preserved.
    e = 0.05; sl = (r0 - r1) / zs
    hole = mk.cyl(r0 + gn + sl * e, -e, zs + e, r_top=r1 + gn - sl * e, seg=64) + mk.cyl(r0 + gn + sl * e, -1, 0.0, seg=64)
    F = (wedgeF - cylG) + (upper ^ cylIn) + (upper ^ wedgeF ^ ringG) + pin
    B = ((back - cylG) + (lower ^ cylIn) + (lower ^ back ^ ringG)) - hole
    return F, B


def plan_joints(t, S, spacing, theta, g, vg, joints_x=None, margin_frac=0.10, min_h=3.5, min_w=6.0):
    xs, cy, wd, ht, isl = S[:, 0], S[:, 1], S[:, 2], S[:, 3], S[:, 5]
    L0, L1 = xs.min(), xs.max()
    if joints_x:
        cand = sorted(joints_x, reverse=True)
    else:
        m = max(0.6 * spacing, margin_frac * (L1 - L0))
        n = max(1, int(round((L1 - L0 - 2 * m) / spacing)))
        cand = list(np.linspace(L1 - m, L0 + m, n + 1))
    plans = []
    for x0 in cand:
        # leg-aware: slide the joint (<= spacing/2) to the nearest x whose section is ONE island (no legs/fins)
        order = sorted(np.linspace(x0 - spacing / 2, x0 + spacing / 2, 25), key=lambda v: abs(v - x0))
        x = next((v for v in order if np.interp(v, xs, isl) <= 1.01 and np.interp(v, xs, wd) >= min_w), None)
        if x is None or (plans and abs(plans[-1]["x"] - x) < 0.7 * spacing):
            continue
        p = _joint_at(t, xs, cy, wd, x, spacing, g, vg, min_h, min_w)
        if p:
            plans.append(p)
    return plans


def _joint_at(t, xs, cy, wd, x, spacing, g, vg, min_h=3.5, min_w=6.0):
    """size a joint at x. Only the CORE (pin + hole + 1 mm wall) must be full height; the outer disc may be trimmed by
    the body's own outline (thin tails), it still turns on arcs centred on the pin."""
    y = float(np.interp(x, xs, cy)); w = float(np.interp(x, xs, wd))
    if w < min_w:
        return None
    dy = float(np.interp(x + 2, xs, cy) - np.interp(x - 2, xs, cy)) / 4.0
    Ra = float(np.clip(0.36 * w, 2.8, min(7.5, 0.36 * spacing)))
    for r0 in (float(max(1.6, min(2.4, 0.42 * Ra))), 1.6, 1.45):
        r1 = max(0.95, r0 - 0.7)
        r_core = r0 + g / math.cos(math.atan(0.7 / 2.0)) + 1.0
        if 2 * r_core > w:
            continue
        hh = mk.heights_on_disc(t, x, y, r_core)
        if hh and hh[0] >= min_h:
            break
    else:
        return None
    hmin = hh[0]
    zs = float(np.clip(0.45 * hmin, 1.6, hmin - vg - 1.6))
    return {"x": round(float(x), 2), "y": round(y, 2), "dir": [1.0, dy], "Ra": round(Ra, 2), "zs": round(zs, 2),
            "r0": round(r0, 2), "r1": round(r1, 2), "hmin": round(hmin, 2), "width": round(w, 2)}


def floating(segs):
    bad = []
    for i, s in enumerate(segs):
        big = [q for q in s.decompose() if q.volume() > 2.0]
        if s.is_empty() or len(big) != 1:
            bad.append(i)
    return bad


def joint_check(segs, plans, j, theta_m, g, vg, min_seg=120.0):
    """THE per-joint test (used by heal AND the final selftest, so they can never disagree)."""
    from manifold3d import OpType
    p = plans[j]
    front = Manifold.batch_boolean(segs[: j + 1], OpType.Add)
    back = Manifold.batch_boolean(segs[j + 1:], OpType.Add)
    worst = 0.0
    for ang in np.linspace(-theta_m, theta_m, 9):
        worst = max(worst, mk.inter_vol(mk.rot_z(back, float(ang), p["x"], p["y"]), front))
    lift = mk.inter_vol(segs[j + 1].translate([0, 0, 1.5]), segs[j])
    gp = mk.gap(segs[j], segs[j + 1], 2.0)
    small = min(segs[j].volume(), segs[j + 1].volume()) < min_seg
    ok = worst < 0.05 and lift > 1.0 and gp >= min(g, vg) * 0.85 and not small
    return ok, {"joint": j, "x": p["x"], "swing_worst_mm3": round(worst, 3), "lift_jams": lift > 1.0,
                "lift_overlap_mm3": round(lift, 2), "min_gap": round(gp, 3), "tiny_segment": small, "ok": ok}


def heal(M, t, S, plans, g, vg, theta, ztop, spacing):
    """a segment with a loose piece (leg cut off by a V-notch): nudge the joints next to it along the spine."""
    xs, cy, wd = S[:, 0], S[:, 1], S[:, 2]
    segs = segment(M, plans, g, vg, theta, ztop)
    for _ in range(12):
        bad = floating(segs)
        if not bad:
            break                                     # (was `return`: skipped the joint checks below entirely)
        i = bad[0]
        moved = False
        for j in (i - 1, i):                         # joint j sits between segment j and j+1
            if j < 0 or j >= len(plans):
                continue
            for dx in (3, -3, 6, -6, 9, -9):
                cand = _joint_at(t, xs, cy, wd, plans[j]["x"] + dx, spacing, g, vg)
                if not cand:
                    continue
                trial = plans[:j] + [cand] + plans[j + 1:]
                xs_sorted = [p["x"] for p in trial]
                if xs_sorted != sorted(xs_sorted, reverse=True):
                    continue
                tsegs = segment(M, trial, g, vg, theta, ztop)
                if i not in floating(tsegs) and len(floating(tsegs)) < len(bad) + 0:
                    plans, segs, moved = trial, tsegs, True
                    break
            if moved:
                break
        if not moved:                                 # last resort: drop the offending joint
            j = min(i, len(plans) - 1) if i < len(plans) else len(plans) - 1
            plans = plans[:j] + plans[j + 1:]
            segs = segment(M, plans, g, vg, theta, ztop)
    # every joint must pass the SAME test as the final verdict: nudge it, else drop it (fewer joints that all work)
    xs, cy, wd = S[:, 0], S[:, 1], S[:, 2]
    theta_m = theta - 3.0
    for _ in range(4 * max(1, len(plans))):
        bad = [j for j in range(len(plans)) if not joint_check(segs, plans, j, theta_m, g, vg)[0]]
        if not bad:
            break
        j = bad[0]; fixed = False
        for dx in (3, -3, 6, -6):
            cand = _joint_at(t, xs, cy, wd, plans[j]["x"] + dx, spacing, g, vg)
            if not cand:
                continue
            trial = plans[:j] + [cand] + plans[j + 1:]
            xx = [q["x"] for q in trial]
            if xx != sorted(xx, reverse=True) or (len(xx) > 1 and min(abs(np.diff(xx))) < 0.6 * spacing):
                continue
            tsegs = segment(M, trial, g, vg, theta, ztop)
            if not floating(tsegs) and joint_check(tsegs, trial, j, theta_m, g, vg)[0]:
                plans, segs, fixed = trial, tsegs, True
                break
        if not fixed:
            plans = plans[:j] + plans[j + 1:]
            if not plans:
                break
            segs = segment(M, plans, g, vg, theta, ztop)
    return plans, segs, not floating(segs)


def segment(M, plans, g, vg, theta, ztop):
    remaining = M
    segs = []
    for p in plans:                                   # head -> tail
        F, B = joint_regions(p["Ra"], g, vg, p["zs"], theta, p["r0"], p["r1"], ztop)
        T = mk.frame_matrix((p["x"], p["y"], 0.0), p["dir"])
        F, B = F.transform(T), B.transform(T)
        segs.append(remaining ^ F)
        remaining = remaining ^ B
    segs.append(remaining)
    return [despeckle(s) for s in segs]


def despeckle(s, min_frac=0.03, min_mm3=2.0):
    """drop slivers a V-notch cut off (toe tips etc.): they'd print as loose flakes. Big loose pieces are NOT dropped
    here -- floating() flags them and heal() moves the joint instead."""
    pcs = s.decompose()
    if len(pcs) <= 1:
        return s
    vmax = max(q.volume() for q in pcs)
    keep = [q for q in pcs if q.volume() >= max(min_mm3, min_frac * vmax)]
    despeckle.dropped += sum(q.volume() for q in pcs if q.volume() < max(min_mm3, min_frac * vmax))
    return Manifold.batch_boolean(keep, __import__("manifold3d").OpType.Add) if len(keep) > 1 else keep[0]


despeckle.dropped = 0.0


def selftest(segs, plans, theta_m, g, vg):
    rep = {"joints": [], "ok": True, "floating_bits": floating(segs)}
    if rep["floating_bits"] or not plans:
        rep["ok"] = False
    for j in range(len(plans)):
        ok, r = joint_check(segs, plans, j, theta_m, g, vg)
        rep["joints"].append(r); rep["ok"] &= ok
    return rep


def run(src, out, spacing=13.0, theta=25.0, joints_x=None, align=True, g=None, vg=None, name="flexi"):
    g = fit.get("pip_gap") if g is None else g
    vg = fit.get("pip_vgap") if vg is None else vg
    t = trimesh.load(src, force="mesh")
    t = mk.repair(t) if not t.is_watertight else t
    if align:
        t = align_to_x(t)
    M = mk.tm2mf(t)
    M = Manifold.compose([q for q in M.decompose() if q.volume() > 1.0])   # fill sculpt bubbles, drop micro-islands
    M, cut = flat_bottom(M, t)
    t = mk.mf2tm(M)
    S = spine(M)
    plans = plan_joints(t, S, spacing, theta, g, vg, joints_x)
    if not plans:
        raise SystemExit("no place thick enough for a joint (need ~3.6 mm tall, 7 mm wide); scale the model up")
    ztop = float(t.bounds[1][2] + 5)
    plans, segs, healed = heal(M, t, S, plans, g, vg, theta, ztop, spacing)
    theta_m = theta - 3.0
    rep = selftest(segs, plans, theta_m, g, vg)
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    for i, s in enumerate(segs):
        mk.save(s, os.path.join(out, "parts", f"seg{i:02d}.stl"))
    allm = Manifold.batch_boolean(segs, __import__("manifold3d").OpType.Add)
    allm = Manifold.compose([q for q in allm.decompose() if q.volume() > 0.01])   # drop zero-volume boolean ghosts
    mk.save(allm, os.path.join(out, f"{name}.stl"))
    spec = {"name": name, "type": "chain", "parts": [f"seg{i:02d}" for i in range(len(segs))],
            "fixed": ["seg00"], "meta": {"chain": [{"pivot": [p["x"], p["y"], 0], "theta_m": theta_m} for p in plans],
                                          "gap": g, "vgap": vg, "bottom_trim_mm": cut, "plans": plans},
            "motions": [{"name": "wiggle", "drive": [-theta_m, theta_m], "note": "each joint swings +-theta_m; chain wave"}]}
    json.dump(spec, open(os.path.join(out, "mech.json"), "w"), indent=1)
    rep.update({"segments": len(segs), "joints_n": len(plans), "theta_m": theta_m, "bottom_trim_mm": cut,
                "slivers_dropped_mm3": round(despeckle.dropped, 2),
                "bbox": [round(float(v), 1) for v in t.extents]})
    json.dump(rep, open(os.path.join(out, "selftest.json"), "w"), indent=1)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("--out"); ap.add_argument("--spacing", type=float, default=13.0)
    ap.add_argument("--theta", type=float, default=25.0); ap.add_argument("--joints-x")
    ap.add_argument("--no-align", action="store_true"); ap.add_argument("--name", default=None)
    a = ap.parse_args()
    name = a.name or os.path.splitext(os.path.basename(a.model))[0] + "_flexi"
    out = a.out or os.path.join(forge_env.OUT, name)
    jx = [float(v) for v in a.joints_x.split(",")] if a.joints_x else None
    rep = run(a.model, out, a.spacing, a.theta, jx, not a.no_align, name=name)
    print(f"[{'PASS' if rep['ok'] else 'FAIL'}] {name}: {rep['segments']} segments, {rep['joints_n']} joints, "
          f"swing +-{rep['theta_m']} deg, bbox {rep['bbox']}, bottom trimmed {rep['bottom_trim_mm']} mm, "
          f"slivers dropped {rep['slivers_dropped_mm3']} mm3")
    for j in rep["joints"]:
        print(f"   joint {j['joint']} x={j['x']}: swing worst {j['swing_worst_mm3']} mm3, lift jams {j['lift_jams']} "
              f"({j['lift_overlap_mm3']} mm3), min gap {j['min_gap']}  {'ok' if j['ok'] else 'FAIL'}")
    if rep["floating_bits"]:
        print("   FLOATING PIECES:", rep["floating_bits"])
    print("->", out)
