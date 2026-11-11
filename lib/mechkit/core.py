"""MechKit core: a mechanism = named parts + declared motions. One self-test for all of them.

    m = Mech("hinge", parts={"leafA": a, "leafB": b}, fixed=["leafA"],
             motions=[Motion("open", (0, 180), [Move("leafB", "rot", axis=(1,0,0), pivot=(0,0,3))],
                             control=[Move("leafB", "trans", axis=(0,0,1), amount=2.0)])])
    rep = selftest(m)          # static overlaps, sweep worst mm3, control jams?, min gaps, range of motion
    export(m, outdir)          # parts/*.stl, assembled.stl, mech.json (motions -> web animation + docs)

Move types:
  rot    axis, pivot, ratio      angle = drive * ratio (deg)
  trans  axis(dir), ratio        offset = drive * ratio (mm)
  helix  axis(z dir), pivot, rate(deg/mm), ratio   offset = drive*ratio mm along axis, turn = offset*rate deg
A control move is applied at its full `amount` (deg or mm) to prove the parts really engage: it MUST collide.
"""
from __future__ import annotations
import json, math, os, sys
from dataclasses import dataclass, field, asdict
from build123d import Axis, Location, Pos, Compound, Solid, export_stl
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


@dataclass
class Move:
    part: str
    type: str                       # rot | trans | helix
    axis: tuple = (0, 0, 1)
    pivot: tuple = (0, 0, 0)
    ratio: float = 1.0
    rate: float = 0.0               # helix deg per mm
    amount: float = 0.0             # control moves only


@dataclass
class Motion:
    name: str
    drive: tuple                    # (start, end) in deg (rot) or mm (trans/helix)
    moves: list
    control: list = field(default_factory=list)
    steps: int = 13
    note: str = ""


@dataclass
class Mech:
    name: str
    parts: dict
    fixed: list
    motions: list
    meta: dict = field(default_factory=dict)


def ov(a, b):
    try:
        r = a & b
    except Exception:
        return 0.0
    if r is None:
        return 0.0
    try:
        return float(r.volume)
    except Exception:
        return 0.0


def _rot(shape, axis, pivot, deg):
    if abs(deg) < 1e-9:
        return shape
    ax = Axis(tuple(pivot), tuple(axis))
    return shape.rotate(ax, deg)


def apply_move(shape, mv: Move, drive: float):
    v = drive * mv.ratio
    if mv.type == "rot":
        return _rot(shape, mv.axis, mv.pivot, v)
    if mv.type == "trans":
        a = np.array(mv.axis, float); a /= np.linalg.norm(a)
        return Pos(*(a * v)) * shape
    if mv.type == "helix":
        a = np.array(mv.axis, float); a /= np.linalg.norm(a)
        s = _rot(shape, mv.axis, mv.pivot, v * mv.rate)
        return Pos(*(a * v)) * s
    raise ValueError(mv.type)


def posed(m: Mech, motion: Motion, drive: float):
    out = dict(m.parts)
    for mv in motion.moves:
        out[mv.part] = apply_move(out[mv.part], mv, drive)
    return out


def _pairs(names):
    return [(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))]


def selftest(m: Mech, tol=0.01, verbose=True, gaps=True):
    rep = {"name": m.name, "static": {}, "motions": [], "ok": True}
    names = list(m.parts)
    for a, b in _pairs(names):
        v = ov(m.parts[a], m.parts[b])
        if v > tol:
            rep["static"][f"{a}&{b}"] = round(v, 3); rep["ok"] = False
    for mo in m.motions:
        worst, where = 0.0, None
        for k in range(mo.steps):
            d = mo.drive[0] + (mo.drive[1] - mo.drive[0]) * k / max(mo.steps - 1, 1)
            P = posed(m, mo, d)
            moving = {mv.part for mv in mo.moves}
            for a, b in _pairs(names):
                if a not in moving and b not in moving:
                    continue
                v = ov(P[a], P[b])
                if v > worst:
                    worst, where = v, f"{a}&{b}@{d:.1f}"
        ctrl = None
        if mo.control:
            # the WRONG motion must be blocked somewhere along its PATH (not just at its end pose: a gimbal ring
            # tilted 25 deg about the wrong axis is clear of the pins, but it jams hard at 10 deg on the way there)
            cv = 0.0
            for k in range(1, 7):
                f = k / 6
                P = dict(m.parts)
                for mv in mo.control:
                    P[mv.part] = apply_move(P[mv.part], Move(mv.part, mv.type, mv.axis, mv.pivot, 1.0, mv.rate), mv.amount * f)
                cv = max([cv] + [ov(P[a], P[b]) for a, b in _pairs(names)])
                if cv > 1.0:
                    break
            ctrl = cv > 1.0
        r = {"motion": mo.name, "drive": list(mo.drive), "sweep_worst_mm3": round(worst, 3), "collide_at": where,
             "control_jams": ctrl}
        if worst > tol or ctrl is False:
            rep["ok"] = False
        rep["motions"].append(r)
    if gaps:
        gp = m.meta.get("gap_pose")          # (motion_name, drive): measure gaps where the parts actually meet
        if gp:
            mo = next(x for x in m.motions if x.name == gp[0])
            rep["gaps"] = min_gaps(Mech(m.name, posed(m, mo, gp[1]), m.fixed, []))
        else:
            rep["gaps"] = min_gaps(m)
    if verbose:
        print_report(rep)
    return rep


def min_gaps(m: Mech, n=6000):
    """surface-to-surface min distance for every touching pair (trimesh, on the exported tessellation)."""
    import trimesh
    meshes = {k: _to_trimesh(v) for k, v in m.parts.items()}
    out = {}
    for a, b in _pairs(list(meshes)):
        A, B = meshes[a], meshes[b]
        if not (np.all(A.bounds[0] - 1.0 < B.bounds[1]) and np.all(B.bounds[0] - 1.0 < A.bounds[1])):
            continue
        pa, _ = trimesh.sample.sample_surface_even(A, n, seed=1)
        pb, _ = trimesh.sample.sample_surface_even(B, n, seed=2)
        from scipy.spatial import cKDTree
        d1, _ = cKDTree(B.vertices).query(pa) if len(B.faces) > 60000 else (trimesh.proximity.closest_point(B, pa)[1], None)
        d2, _ = cKDTree(A.vertices).query(pb) if len(A.faces) > 60000 else (trimesh.proximity.closest_point(A, pb)[1], None)
        g = float(min(d1.min(), d2.min()))
        if g < 3.0:
            out[f"{a}&{b}"] = round(g, 3)
    return out


def _to_trimesh(shape, tol=0.01, ang=0.05):
    import trimesh, tempfile
    fd, p = tempfile.mkstemp(suffix=".stl"); os.close(fd)
    export_stl(shape, p, tolerance=tol, angular_tolerance=ang)
    t = trimesh.load(p, force="mesh"); os.remove(p)
    return t


def range_of_motion(m: Mech, part: str, axis, pivot, lo=-180, hi=180, step=5.0, tol=0.05):
    """sweep one part about an axis from 0 both ways until it collides; returns (min_deg, max_deg)."""
    names = [n for n in m.parts if n != part]
    def hits(deg):
        s = _rot(m.parts[part], axis, pivot, deg)
        return any(ov(s, m.parts[n]) > tol for n in names)
    res = []
    for sgn, lim in ((1, hi), (-1, lo)):
        d = 0.0
        while abs(d + sgn * step) <= abs(lim):
            if hits(d + sgn * step):
                break
            d += sgn * step
        res.append(d)
    return res[1], res[0]


def print_report(rep):
    st = "PASS" if rep["ok"] else "FAIL"
    print(f"[{st}] {rep['name']}")
    if rep["static"]:
        print("   static overlaps:", rep["static"])
    for r in rep["motions"]:
        c = {None: "no control", True: "control jams (good)", False: "CONTROL DID NOT JAM (check proves nothing)"}[r["control_jams"]]
        s = "clear" if r["sweep_worst_mm3"] <= 0.01 else f"COLLIDES {r['sweep_worst_mm3']} mm3 at {r['collide_at']}"
        print(f"   motion {r['motion']} {r['drive']}: {s}; {c}")
    if rep.get("gaps"):
        g = rep["gaps"]; print(f"   min gaps (mm): {g}  -> tightest {min(g.values()):.3f}")


def export(m: Mech, outdir, tol=0.01):
    """angular_tolerance 0.05 rad: coarse facets on big curved parts eat ~0.06 mm of a 0.3 mm print-in-place gap."""
    os.makedirs(os.path.join(outdir, "parts"), exist_ok=True)
    for k, v in m.parts.items():
        export_stl(v, os.path.join(outdir, "parts", f"{k}.stl"), tolerance=tol, angular_tolerance=0.05)
    export_stl(Compound(list(m.parts.values())), os.path.join(outdir, f"{m.name}.stl"), tolerance=tol, angular_tolerance=0.05)
    spec = {"name": m.name, "parts": list(m.parts), "fixed": m.fixed, "meta": m.meta,
            "motions": [{"name": mo.name, "drive": list(mo.drive), "note": mo.note,
                         "moves": [asdict(mv) for mv in mo.moves]} for mo in m.motions]}
    json.dump(spec, open(os.path.join(outdir, "mech.json"), "w"), indent=1)
    return os.path.join(outdir, f"{m.name}.stl")


# ---------- shared geometry helpers ----------
from build123d import Cylinder, Box, Align, Text, extrude, Plane, Rot, Sketch

CEN = (Align.CENTER, Align.CENTER, Align.MIN)


def zcyl(r, h, x=0, y=0, z=0):
    return Pos(x, y, z) * Cylinder(r, h, align=CEN)


def label(txt, size=5.0, height=0.8, font="Arial Black"):
    """raised label, centred on XY origin, bottom at z=0. Strokes stay >= 0.8 mm at size >= 4.5 (Arial Black)."""
    try:
        sk = Text(txt, font_size=size, font=font, align=(Align.CENTER, Align.CENTER))
    except Exception:
        sk = Text(txt, font_size=size, align=(Align.CENTER, Align.CENTER))
    return extrude(sk, height)


# ---------- measured ratio + backlash (forge mech ratio) ----------
def _move_matrix(mv: Move, drive: float):
    """4x4 world transform of one Move at `drive` (mirrors apply_move; used on tessellated parts, no CAD booleans)."""
    v = drive * mv.ratio
    I = np.eye(4)
    if mv.type == "trans":
        a = np.array(mv.axis, float); a /= np.linalg.norm(a); I[:3, 3] = a * v
        return I
    ax = np.array(mv.axis, float); ax /= np.linalg.norm(ax)
    ang = math.radians(v * (mv.rate if mv.type == "helix" else 1.0))
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    Rm = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)
    p = np.array(mv.pivot, float)
    I[:3, :3] = Rm; I[:3, 3] = p - Rm @ p
    if mv.type == "helix":
        T = np.eye(4); T[:3, 3] = ax * v
        I = T @ I
    return I


def _mf(shape):
    from manifold3d import Manifold, Mesh
    t = _to_trimesh(shape)
    mf = Manifold(Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
    return mf.simplify(0.002) if mf.num_tri() > 50000 else mf     # 20x fewer triangles on herringbone gears, same volumes


def _inter(a, b):
    from manifold3d import Manifold, OpType
    return Manifold.batch_boolean([a, b], OpType.Intersect).volume()


def measure_ratio(m: Mech, motion="reduce", driven="carrier", driver="shaft", K=24, window=5.0, bisect=12, tol=0.01):
    """MEASURED reduction ratio and backlash. For K drive values: pose every body per the motion, then free the driven part
    about the main axis (Z) and bisect (on overlap volume against every other posed body) for the interval [lo, hi] of extra
    angle in which nothing touches. theta(d) = predicted + (lo + hi)/2.
    Returns {declared, measured, ..., backlash_deg, backlash_arcmin, samples}; measured = input turns per output turn (signed)."""
    mo = next(x for x in m.motions if x.name == motion)
    base = {k: _mf(v) for k, v in m.parts.items()}

    def zsum(part):
        return sum(mv.ratio for mv in mo.moves if mv.part == part and mv.type == "rot" and abs(mv.axis[2]) > 0.99
                   and all(abs(c) < 1e-9 for c in mv.pivot[:2]))
    pred_ratio, drv_ratio = zsum(driven), zsum(driver)

    def world(d):
        T = {k: np.eye(4) for k in base}
        for mv in mo.moves:
            T[mv.part] = _move_matrix(mv, d) @ T[mv.part]
        return T

    def mf_at(part, T, extra=0.0):
        M = T[part]
        if extra:
            M = _move_matrix(Move(part, "rot", (0, 0, 1), (0, 0, 0), 1.0), extra) @ M
        return base[part].transform(M[:3, :4])

    others = [k for k in base if k != driven]
    ds = np.linspace(mo.drive[0], mo.drive[1], K)
    samples = []
    for d in ds:
        T = world(d)
        fixed = {k: mf_at(k, T) for k in others}
        def hits(delta):
            s = mf_at(driven, T, delta)
            return any(_inter(s, f) > tol for f in fixed.values())
        res = {}
        for side, sgn in (("lo", -1.0), ("hi", 1.0)):
            if hits(0.0):
                res[side] = float("nan"); continue
            if not hits(sgn * window):
                res[side] = sgn * window; continue          # no contact inside the window (capped)
            free, blocked = 0.0, sgn * window
            for _ in range(bisect):
                mid = (free + blocked) / 2
                if hits(mid): blocked = mid
                else: free = mid
            res[side] = free
        samples.append({"drive": round(float(d), 4), "pred_deg": round(float(d) * pred_ratio, 4), "lo": round(res["lo"], 4),
                        "hi": round(res["hi"], 4), "theta": round(float(d) * pred_ratio + (res["lo"] + res["hi"]) / 2, 4),
                        "play_deg": round(res["hi"] - res["lo"], 4)})
    good = [s for s in samples if not math.isnan(s["theta"])]
    d0, d1 = samples[0], samples[-1]
    dth = d1["theta"] - d0["theta"]
    span_in = (mo.drive[1] - mo.drive[0]) * drv_ratio
    measured = span_in / dth if abs(dth) > 1e-9 else float("inf")
    fit_slope = float(np.polyfit([s["drive"] * drv_ratio for s in good], [s["theta"] for s in good], 1)[0])
    plays = sorted(s["play_deg"] for s in good)
    back = plays[len(plays) // 2]
    declared_out_per_in = pred_ratio / drv_ratio if drv_ratio else float("nan")
    decl = m.meta.get("ratio")
    declared = (decl * m.meta.get("output_sign", 1)) if decl else 1.0 / declared_out_per_in
    return {"declared": declared, "declared_from": "meta.ratio" if decl else "motion moves",
            "declared_out_per_in": 1.0 / declared, "measured": round(measured, 4), "measured_fit": round(1.0 / fit_slope, 4) if fit_slope else None,
            "measured_out_per_in": round(1.0 / measured, 5), "backlash_deg": round(back, 3), "backlash_arcmin": round(back * 60, 1),
            "backlash_min_deg": round(plays[0], 3), "backlash_max_deg": round(plays[-1], 3),
            "motion": motion, "driven": driven, "driver": driver, "window_deg": window, "capped_samples": sum(1 for s in good if abs(s["lo"]) >= window or abs(s["hi"]) >= window),
            "samples": samples}
