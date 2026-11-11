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
            d = mo.drive[0] + (mo.drive[1] - mo.drive[0]) * k / (mo.steps - 1)
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


def _to_trimesh(shape, tol=0.01):
    import trimesh, tempfile
    fd, p = tempfile.mkstemp(suffix=".stl"); os.close(fd)
    export_stl(shape, p, tolerance=tol, angular_tolerance=0.05)
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
