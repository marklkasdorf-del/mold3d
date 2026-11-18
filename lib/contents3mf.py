#!/usr/bin/env python3
"""contents: what is actually IN a 3MF, read back from the file, before anyone is told "here it is".

    forge contents file.3mf [--expect '{"pieces": 2, "filaments": 2, "visible_from_top": ["text"]}'] [--json]

Lists every piece on the plate, its parts, the filament slot each part prints in, the supports setting, the size, and
WHERE each part shows: from the top (what the slicer opens on), only on the bed face (the underside: hidden until the
print is flipped), or buried inside another part. --expect compares that to the ask and exits 1 on any mismatch:
  pieces            number of pieces on the plate
  filaments         number of different filament slots used
  supports          "on" | "off"
  visible_from_top  part names (substring match) that must show from above, e.g. ["text", "button"]
Reads plain single-mesh 3MFs (forge export) and Bambu/Orca project 3MFs (components + Metadata/model_settings.config).
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"


def _mat(s):
    v = [float(x) for x in (s or "1 0 0 0 1 0 0 0 1 0 0 0").split()]
    M = np.eye(4); M[:3, :3] = np.array(v[:9]).reshape(3, 3).T; M[:3, 3] = v[9:12]
    return M


def _meshes(z, path):
    root = ET.fromstring(z.read(path.lstrip("/")))
    objs = {}
    for o in root.iter(CORE + "object"):
        mesh = o.find(CORE + "mesh")
        if mesh is not None:
            V = np.array([[float(v.get(k)) for k in "xyz"] for v in mesh.iter(CORE + "vertex")])
            F = np.array([[int(t.get(k)) for k in ("v1", "v2", "v3")] for t in mesh.iter(CORE + "triangle")])
            objs[o.get("id")] = ("mesh", V, F, o.get("name"))
        else:
            comps = [(c.get(PROD + "path") or path, c.get("objectid"), _mat(c.get("transform"))) for c in o.iter(CORE + "component")]
            objs[o.get("id")] = ("comp", comps, None, o.get("name"))
    return root, objs


def _settings(z):
    """Bambu/Orca model_settings.config -> {object_id: {name, extruder, enable_support, parts: {part_id: {name, extruder}}}}"""
    if "Metadata/model_settings.config" not in z.namelist():
        return {}
    root = ET.fromstring(z.read("Metadata/model_settings.config"))
    md = lambda el: {m.get("key"): m.get("value") for m in el.findall("metadata")}
    out = {}
    for o in root.findall("object"):
        d = md(o); d["parts"] = {p.get("id"): md(p) for p in o.findall("part")}
        out[o.get("id")] = d
    return out


def _global_supports(z):
    n = z.namelist()
    if "Metadata/project_settings.config" in n:
        try:
            v = json.loads(z.read("Metadata/project_settings.config")).get("enable_support")
            if v is not None:
                return "on" if str(v) in ("1", "true") else "off"
        except ValueError:
            pass
    if "Metadata/Slic3r_PE.config" in n:
        m = re.search(r"support_material = (\d)", z.read("Metadata/Slic3r_PE.config").decode(errors="ignore"))
        if m:
            return "on" if m.group(1) == "1" else "off"
    return None


def read(path):
    """-> {"pieces": [{name, supports, size_mm, parts: [{name, filament, mesh}]}], "supports": global}"""
    import trimesh
    with zipfile.ZipFile(path) as z:
        root, top = _meshes(z, "3D/3dmodel.model")
        cache = {"/3D/3dmodel.model": top}
        cfg = _settings(z); gsup = _global_supports(z)
        pieces = []
        for item in root.iter(CORE + "item"):
            oid = item.get("objectid"); M = _mat(item.get("transform"))
            kind, a, b, oname = top[oid]
            oc = cfg.get(oid, {})
            parts = []
            if kind == "mesh":
                parts.append((oname or oc.get("name") or f"object {oid}", a, b, M, oc.get("extruder")))
            else:
                for sub, cid, CM in a:
                    sp = "/" + sub.lstrip("/")
                    if sp not in cache:
                        cache[sp] = _meshes(z, sp)[1]
                    k2, V, F, pname = cache[sp][cid]
                    pc = oc.get("parts", {}).get(cid, {})
                    parts.append((pc.get("name") or pname or f"part {cid}", V, F, M @ CM, pc.get("extruder") or oc.get("extruder")))
            ps = []
            for name, V, F, T, ext in parts:
                Vh = np.c_[V, np.ones(len(V))] @ T.T
                ps.append({"name": name, "filament": int(ext) if ext else 1, "mesh": trimesh.Trimesh(Vh[:, :3], F, process=False)})
            allv = np.vstack([p["mesh"].vertices for p in ps])
            sup = oc.get("enable_support")
            pieces.append({"name": oc.get("name") or oname or f"piece {oid}",
                           "supports": ("on" if sup == "1" else "off") if sup is not None else gsup,
                           "size_mm": [round(float(x), 1) for x in allv.max(0) - allv.min(0)], "z0": float(allv[:, 2].min()), "parts": ps})
    return {"file": os.path.basename(path), "pieces": pieces, "supports": gsup}


def where(part, others, z0, n=3000):
    """where this part can be SEEN: 'top' (upward faces not covered by another part of the piece),
    'bed face' (only its faces on the build plate show), or 'buried'. Visible area per view in mm2."""
    import trimesh
    m = part["mesh"]
    if len(m.faces) == 0:
        return "empty", 0.0, 0.0
    pts, fi = trimesh.sample.sample_surface(m, n, seed=2)
    nz = m.face_normals[fi][:, 2]; w = m.area / n
    blockers = [o["mesh"].triangles for o in others if len(o["mesh"].faces)]
    up = nz > 0.5
    top_mm2 = 0.0
    if up.any():
        o = pts[up] + np.array([0, 0, 1e-3]); clear = np.ones(len(o), bool)
        from verify_lib import tri_ray_first_hit
        for T in blockers:
            clear &= ~np.isfinite(tri_ray_first_hit(o, np.tile([0, 0, 1.0], (len(o), 1)), T))
        top_mm2 = float(clear.sum() * w)
    bed_mm2 = float(((nz < -0.9) & (pts[:, 2] < z0 + 0.05)).sum() * w)
    if top_mm2 >= 1.0:
        return "top", round(top_mm2, 1), round(bed_mm2, 1)
    if bed_mm2 >= 1.0:
        return "bed face", round(top_mm2, 1), round(bed_mm2, 1)
    return "buried", round(top_mm2, 1), round(bed_mm2, 1)


def inspect(path):
    r = read(path)
    for pc in r["pieces"]:
        for p in pc["parts"]:
            others = [o for o in pc["parts"] if o is not p]
            p["shows"], p["top_mm2"], p["bed_mm2"] = where(p, others, pc["z0"]) if others else ("top", None, None)
            p["triangles"] = len(p["mesh"].faces)
    r["filaments"] = sorted({p["filament"] for pc in r["pieces"] for p in pc["parts"]})
    return r


def compare(r, want):
    bad = []
    if "pieces" in want and len(r["pieces"]) != int(want["pieces"]):
        bad.append(f"{len(r['pieces'])} piece(s) on the plate, asked for {want['pieces']}")
    if "filaments" in want and len(r["filaments"]) != int(want["filaments"]):
        bad.append(f"{len(r['filaments'])} filament slot(s) used, asked for {want['filaments']}")
    if "supports" in want:
        for pc in r["pieces"]:
            if pc["supports"] != want["supports"]:
                bad.append(f"{pc['name']}: supports {pc['supports'] or 'not set'}, asked for {want['supports']}")
    for name in want.get("visible_from_top", []):
        hits = [p for pc in r["pieces"] for p in pc["parts"] if name.lower() in p["name"].lower()]
        if not hits:
            bad.append(f"no part named like '{name}' in the file")
        for p in hits:
            if p["shows"] != "top":
                bad.append(f"'{p['name']}' is not visible from the top: it shows {'only on the bed face (underside)' if p['shows'] == 'bed face' else 'nowhere (' + p['shows'] + ')'}")
    return bad


def format_plain(r):
    out = [f"CONTENTS of {r['file']}: {len(r['pieces'])} piece(s), filament slot(s) {', '.join(map(str, r['filaments']))}"]
    for pc in r["pieces"]:
        out.append(f"  {pc['name']}: {' x '.join(f'{x:g}' for x in pc['size_mm'])} mm, supports {pc['supports'] or 'NOT SET'}")
        for p in pc["parts"]:
            shows = {"top": "seen from the top", "bed face": "ONLY ON THE BED FACE (underside, hidden in the slicer's top view)",
                     "buried": "BURIED (not visible anywhere)", "empty": "EMPTY"}[p["shows"]]
            out.append(f"    - {p['name']}: filament {p['filament']}, {p['triangles']} triangles, {shows}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file"); ap.add_argument("--expect", help="JSON (or a path to one) describing what was asked for")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = inspect(a.file)
    except Exception as e:
        print(f"CONTENTS ERROR: cannot read {a.file}: {type(e).__name__}: {e}", file=sys.stderr); sys.exit(2)
    want = {}
    if a.expect:
        want = json.load(open(a.expect)) if os.path.exists(a.expect) else json.loads(a.expect)
    bad = compare(r, want)
    if a.json:
        print(json.dumps({**r, "pieces": [{**pc, "parts": [{k: v for k, v in p.items() if k != "mesh"} for p in pc["parts"]]} for pc in r["pieces"]],
                          "mismatch": bad}, indent=1, default=str))
    else:
        print(format_plain(r))
        if want:
            print("MATCHES THE ASK" if not bad else "DOES NOT MATCH THE ASK (do not send it):\n" + "\n".join("  - " + b for b in bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
