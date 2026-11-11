"""topo: give every solid/face/edge of a STEP file an addressable id + a plain-English feature list.

Idea adapted from earthtojake/text-to-cad (MIT, see THIRD_PARTY_NOTICES.md): "reference specific faces and edges" so a revision
request can say "the hole at f12" instead of "that hole over there". Our version is a small
build123d-only re-implementation (no cadgen/uv/telemetry).  Run with the CAD venv:

  python topo.py part.step                 # writes part.topology.json + part.features.md, prints the features
  python topo.py part.step --face s1.f7    # details of one face (+ its edges)
  python topo.py part.step --near=5,0,15  # the 3 faces closest to a point (mm) = "pointing" at the part
  python topo.py part.step --edges         # also list edges (ids sN.eM)
Usually called as `forge/bin/forge topo part.step`.

IDs: sN = solid, sN.fM = face, sN.eM = edge. Solids are sorted by bbox centre (z,y,x), faces/edges by
their bbox centre (z,y,x) rounded to 0.01 mm. IDs are REVISION-SCOPED (a geometry change can renumber
them): always re-run topo after a rebuild and re-resolve; never carry an id across iterations.
Units mm. Axes as in the part file (bed = Z=0)."""
import json, math, os, sys
from build123d import import_step, GeomType, Vector

def r2(x): return round(float(x), 2)
def v3(v): return [r2(v.X), r2(v.Y), r2(v.Z)]
def key(shape):
    c = shape.bounding_box().center()
    return (r2(c.Z), r2(c.Y), r2(c.X))

DIRS = {(0, 0, 1): "top (+Z)", (0, 0, -1): "bottom (-Z, bed side)", (0, -1, 0): "front (-Y)", (0, 1, 0): "back (+Y)",
        (1, 0, 0): "right (+X)", (-1, 0, 0): "left (-X)"}

def dir_name(n):
    for d, name in DIRS.items():
        if n.X * d[0] + n.Y * d[1] + n.Z * d[2] > 0.995: return name
    return f"oblique n=({n.X:.2f},{n.Y:.2f},{n.Z:.2f})"

def describe_face(f, solid):
    t = f.geom_type
    bb = f.bounding_box()
    d = {"type": str(t).split(".")[-1].lower(), "area": r2(f.area), "center": v3(f.center()),
         "bbox_min": v3(bb.min), "bbox_max": v3(bb.max)}
    if t == GeomType.PLANE:
        n = f.normal_at(f.center())          # plane: constant, outward from the solid
        d["normal"] = v3(n); d["facing"] = dir_name(n)
    elif t == GeomType.CYLINDER:
        ax = f.axis_of_rotation; r = f.radius; dr = ax.direction.normalized()
        corners = [Vector(x, y, z) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
        ts = [(c - ax.position).dot(dr) for c in corners]
        lo, hi = min(ts), max(ts)
        # tighten along-axis extent using the face's own edges
        es = [(e.center() - ax.position).dot(dr) for e in f.edges()]
        if es: lo, hi = min(es + [hi]), max(es + [lo])
        L = max(abs(hi - lo), 1e-6)
        cov = f.area / (2 * math.pi * r * L)
        p = f.position_at(0.5, 0.5) if hasattr(f, "position_at") else f.center()
        n = f.normal_at(p)
        radial = (p - ax.position) - dr * ((p - ax.position).dot(dr))
        concave = n.dot(radial) < 0
        mid = ax.position + dr * ((lo + hi) / 2)
        d.update(radius=r2(r), diameter=r2(2 * r), axis_dir=v3(dr), axis_point=v3(mid), length=r2(L), coverage=r2(min(cov, 1.0)),
                 role=("hole" if concave else "boss/pin") if cov > 0.9 else ("fillet/arc concave" if concave else "fillet/arc convex"))
    elif t == GeomType.CONE:
        pass   # cone: type + area + bbox is enough (chamfers, countersinks)
    return d

def describe_edge(e):
    d = {"type": str(e.geom_type).split(".")[-1].lower(), "length": r2(e.length), "center": v3(e.center())}
    if e.geom_type == GeomType.CIRCLE:
        d["radius"] = r2(e.radius); d["arc_center"] = v3(e.arc_center)
    return d

def analyse(path, want_edges=False):
    shape = import_step(path)
    solids = sorted(shape.solids(), key=key)
    out = {"file": os.path.abspath(path), "units": "mm", "solids": []}
    shapes = {}
    for si, s in enumerate(solids, 1):
        bb = s.bounding_box()
        rec = {"id": f"s{si}", "volume": r2(s.volume), "valid": bool(s.is_valid), "bbox_min": v3(bb.min), "bbox_max": v3(bb.max),
               "size": v3(bb.size), "faces": {}, "edges": {}}
        for fi, f in enumerate(sorted(s.faces(), key=key), 1):
            fid = f"s{si}.f{fi}"; rec["faces"][fid] = describe_face(f, s); shapes[fid] = f
        for ei, e in enumerate(sorted(s.edges(), key=key), 1):
            eid = f"s{si}.e{ei}"; rec["edges"][eid] = describe_edge(e); shapes[eid] = e
        out["solids"].append(rec)
    return out, shapes

def features_md(topo):
    L = [f"# Features of {os.path.basename(topo['file'])}", "(ids are revision-scoped: re-run `forge topo` after every rebuild)", ""]
    for s in topo["solids"]:
        L.append(f"## {s['id']}: {s['size'][0]} x {s['size'][1]} x {s['size'][2]} mm, volume {s['volume']} mm3, {'valid' if s['valid'] else 'INVALID B-rep'}, bbox z {s['bbox_min'][2]}..{s['bbox_max'][2]}")
        holes = [(i, f) for i, f in s["faces"].items() if f.get("role") == "hole"]
        bosses = [(i, f) for i, f in s["faces"].items() if f.get("role") == "boss/pin"]
        arcs = [(i, f) for i, f in s["faces"].items() if str(f.get("role", "")).startswith("fillet")]
        planes = [(i, f) for i, f in s["faces"].items() if f["type"] == "plane"]
        if holes:
            L.append("Holes (full cylinders cut into the part):")
            for i, f in holes:
                ax = f["axis_dir"]; kind = "vertical" if abs(ax[2]) > .99 else ("horizontal" if abs(ax[2]) < .01 else "angled")
                L.append(f"- {i}: dia {f['diameter']} mm, depth/length {f['length']} mm, {kind} axis at {f['axis_point']}")
        if bosses:
            L.append("Bosses / pins (full outward cylinders):")
            for i, f in bosses: L.append(f"- {i}: dia {f['diameter']} mm, length {f['length']} mm at {f['axis_point']}")
        if arcs:
            rs = {}
            for i, f in arcs: rs.setdefault((f['role'], f['radius']), []).append(i)
            L.append("Rounded edges / arcs: " + "; ".join(f"R{r} {role} x{len(ids)} ({ids[0]}..)" for (role, r), ids in sorted(rs.items())))
        if planes:
            L.append("Planar faces (largest first):")
            for i, f in sorted(planes, key=lambda kv: -kv[1]["area"])[:14]:
                L.append(f"- {i}: {f['facing']}, {f['area']} mm2, center {f['center']}")
        other = [(i, f["type"]) for i, f in s["faces"].items() if f["type"] not in ("plane", "cylinder")]
        if other:
            L.append(f"Other surfaces ({len(other)}): " + ", ".join(f"{i}={t}" for i, t in other[:12]) + (" ..." if len(other) > 12 else ""))
        L.append("")
    return "\n".join(L)

def near(topo, shapes, pt, k=3):
    p = Vector(*pt)
    from build123d import Vertex
    v = Vertex(*pt)
    res = []
    for fid, rec in ((fid, rec) for s in topo["solids"] for fid, rec in s["faces"].items()):
        res.append((shapes[fid].distance_to(v), fid, rec))
    res.sort(key=lambda t: t[0])
    return res[:k]

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step"); ap.add_argument("--face"); ap.add_argument("--near"); ap.add_argument("--edges", action="store_true")
    ap.add_argument("--k", type=int, default=3); ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    topo, shapes = analyse(a.step, a.edges)
    stem = os.path.splitext(a.step)[0]
    if not a.edges:
        for s in topo["solids"]: s["edges_count"] = len(s["edges"])
    if not a.no_write:
        json.dump(topo, open(stem + ".topology.json", "w"), indent=1)
        open(stem + ".features.md", "w").write(features_md(topo))
    if a.face:
        for s in topo["solids"]:
            if a.face in s["faces"]:
                print(json.dumps({a.face: s["faces"][a.face]}, indent=1)); break
        else: sys.exit(f"topo: no face {a.face} (ids are revision-scoped; re-run topo)")
    elif a.near:
        pt = [float(x) for x in a.near.split(",")]
        for d, fid, rec in near(topo, shapes, pt, a.k):
            extra = rec.get("facing") or rec.get("role") or rec["type"]
            print(f"{fid}  {d:7.2f} mm away  {rec['type']}  {extra}  area {rec['area']}  center {rec['center']}")
    else:
        print(features_md(topo))
        if a.edges:
            for s in topo["solids"]:
                for eid, e in s["edges"].items(): print(f"{eid}: {e}")
