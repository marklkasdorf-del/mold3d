#!/usr/bin/env python3
"""export: write a 3MF that CARRIES the supports decision into the slicer (the STL can't: a ticked "auto supports" box once
welded CYCLO-11's 0.30 mm gaps and tore the print into 3 pieces).

    forge export model.stl [--supports on|off|auto] [--out file.3mf]
    forge export --piece plug=body.stl@1,button.stl@2,text.stl@2 --piece socket=socket.stl@1 [--supports ...] --out set.3mf

--piece (repeatable) = one object on the plate made of colour parts, each part STL @ its filament slot (all parts of a piece in
the same coordinates; pieces are laid out side by side). Written as a Bambu/Orca project 3MF (parts + filament slots +
per-object supports). Every export ends with `forge contents` on the written file: what is in it, read back.

auto (default) = the preflight verdict (traps or no overhang -> off, mid-air islands / steep overhang -> on, NO-GO -> refuses).
Output <stem>_SUPPORTS-OFF.3mf / _SUPPORTS-ON.3mf. Contents: core 3MF model (mm, centred on the bed) plus ONLY the supports setting:
  Metadata/project_settings.config   Orca / Bambu Studio / AnkerMake Studio (JSON): enable_support, support_type
  Metadata/Slic3r_PE.config          PrusaSlicer / SuperSlicer:  ; support_material = 0|1, ; support_material_auto = 0|1
Nothing else is set: stock profile, one checkbox. Open the 3MF (not the STL) in the slicer and CHECK the Support box matches the filename.
"""
import argparse, json, os, sys, zipfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import printer

CT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
      '<Default Extension="config" ContentType="text/plain"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def model_xml(V, F, title, center):
    tx, ty = center
    vs = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in V)
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in F)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
            f'<metadata name="Title">{title}</metadata><metadata name="Application">Mold3D forge export</metadata>'
            f'<resources><object id="1" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object></resources>'
            f'<build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 {tx:.3f} {ty:.3f} 0"/></build></model>')


def settings(on):
    orca = {"enable_support": "1" if on else "0", "support_type": "normal(auto)"}
    prusa = f"; support_material = {int(on)}\n; support_material_auto = {int(on)}\n"
    return json.dumps(orca, indent=2), prusa


def write_3mf(stl, out, on):
    import trimesh
    m = trimesh.load(stl, force="mesh")
    m.merge_vertices()
    V = m.vertices - np.array([(m.bounds[0][0] + m.bounds[1][0]) / 2, (m.bounds[0][1] + m.bounds[1][1]) / 2, m.bounds[0][2]])
    bed = printer.bed()
    oj, pc = settings(on)
    title = os.path.splitext(os.path.basename(stl))[0]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model_xml(V, m.faces, title, (bed[0] / 2, bed[1] / 2)))
        z.writestr("Metadata/project_settings.config", oj)
        z.writestr("Metadata/Slic3r_PE.config", pc)
    return out


NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')


def parse_piece(arg):
    """'plug=body.stl@1,button.stl@2' -> ('plug', [('body', 'body.stl', 1), ('button', 'button.stl', 2)])"""
    name, _, rest = arg.partition("=")
    if not rest:
        raise SystemExit(f"forge export: --piece wants NAME=part.stl@slot[,part.stl@slot...], got {arg!r}")
    parts = []
    for tok in rest.split(","):
        f, _, slot = tok.partition("@")
        if not os.path.exists(f):
            raise SystemExit(f"forge export: no such file {f}")
        parts.append((os.path.splitext(os.path.basename(f))[0], f, int(slot or 1)))
    return name, parts


def write_pieces(pieces, out, sup_by_piece, title):
    """pieces: [(name, [(part_name, stl, slot)])] -> one project 3MF, every piece on the plate, parts on their filament slots."""
    import trimesh
    bed = printer.bed()
    loaded = [(n, [(pn, trimesh.load(f, force="mesh"), s) for pn, f, s in ps]) for n, ps in pieces]
    for _, ps in loaded:
        for _, m, _ in ps:
            m.merge_vertices()
    widths = [float(np.ptp(np.vstack([m.vertices for _, m, _ in ps])[:, 0])) for _, ps in loaded]
    gap = 10.0; x = bed[0] / 2 - (sum(widths) + gap * (len(widths) - 1)) / 2
    sub, top, build, cfg = [], [], [], ['<?xml version="1.0" encoding="UTF-8"?>\n<config>']
    oid, topid = 1, 100
    for gi, ((name, ps), wdt) in enumerate(zip(loaded, widths)):
        allv = np.vstack([m.vertices for _, m, _ in ps]); lo, hi = allv.min(0), allv.max(0)
        off = -np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        path = f"/3D/Objects/object_{gi + 1}.model"; objs, comps = [], []
        on = sup_by_piece[name]
        cfg.append(f'  <object id="{topid}">\n    <metadata key="name" value="{name}"/>\n    <metadata key="extruder" value="{ps[0][2]}"/>\n'
                   f'    <metadata key="enable_support" value="{int(on)}"/>')
        for pn, m, slot in ps:
            V = m.vertices + off
            vs = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in V)
            ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
            objs.append(f'<object id="{oid}" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')
            comps.append(f'<component p:path="{path}" objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
            cfg.append(f'    <part id="{oid}" subtype="normal_part">\n      <metadata key="name" value="{pn if pn.startswith(name) else name + '_' + pn}"/>\n      <metadata key="extruder" value="{slot}"/>\n    </part>')
            oid += 1
        cfg.append("  </object>")
        sub.append((path, f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}><metadata name="BambuStudio:3mfVersion">1</metadata><resources>{"".join(objs)}</resources><build/></model>'))
        top.append(f'<object id="{topid}" type="model"><components>{"".join(comps)}</components></object>')
        build.append(f'<item objectid="{topid}" transform="1 0 0 0 1 0 0 0 1 {x + wdt / 2:.3f} {bed[1] / 2:.3f} 0" printable="1"/>')
        x += wdt + gap; topid += 1
    cfg.append("</config>")
    main = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}><metadata name="Application">BambuStudio-01.10.00.00</metadata>'
            f'<metadata name="BambuStudio:3mfVersion">1</metadata><metadata name="Title">{title}</metadata><resources>{"".join(top)}</resources><build>{"".join(build)}</build></model>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            "".join(f'<Relationship Target="{p}" Id="rel-{i + 1}" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>' for i, (p, _) in enumerate(sub)) + "</Relationships>")
    any_on = any(sup_by_piece.values())
    oj, pc = settings(any_on)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", main); z.writestr("3D/_rels/3dmodel.model.rels", rels)
        for p, xml in sub:
            z.writestr(p.lstrip("/"), xml)
        z.writestr("Metadata/model_settings.config", "\n".join(cfg))
        z.writestr("Metadata/project_settings.config", oj)
        z.writestr("Metadata/Slic3r_PE.config", pc)
    return out


def show_contents(path, expect=None):
    """the delivery list: read the written file back and print what is in it; mismatch vs --expect -> exit 1."""
    import contents3mf
    r = contents3mf.inspect(path)
    print(contents3mf.format_plain(r))
    if expect:
        want = json.load(open(expect)) if os.path.exists(expect) else json.loads(expect)
        bad = contents3mf.compare(r, want)
        print("MATCHES THE ASK" if not bad else "DOES NOT MATCH THE ASK (do not send it):\n" + "\n".join("  - " + b for b in bad))
        return not bad
    return True


def check_3mf(path):
    """read it back: -> (triangles, bbox_mm, orca_enable_support, prusa_support_material). Raises if invalid."""
    import trimesh
    with zipfile.ZipFile(path) as z:
        cfg = json.loads(z.read("Metadata/project_settings.config"))
        pe = z.read("Metadata/Slic3r_PE.config").decode()
    m = trimesh.load(path, force="mesh")
    pm = [l for l in pe.splitlines() if l.startswith("; support_material =")][0].split("=")[1].strip()
    return len(m.faces), [round(float(v), 1) for v in m.extents], cfg["enable_support"], pm


def orca_sanity(path, want_off):
    """best effort: let OrcaSlicer's CLI slice the 3MF and read the support setting back from the gcode config block."""
    import shutil, subprocess, tempfile
    exe = "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
    if not os.path.exists(exe):
        return None, "NOT SLICER-CHECKED: OrcaSlicer not installed; say so in the hand-off"
    d = tempfile.mkdtemp()
    try:
        p = subprocess.run([exe, "--slice", "0", "--outputdir", d, os.path.abspath(path)], capture_output=True, text=True, timeout=45, cwd=d)
        gc = [os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.endswith((".gcode", ".json")) or "plate" in f]
        sup = None
        for g in gc:
            if g.endswith(".gcode"):
                for l in open(g, errors="ignore"):
                    if l.startswith("; enable_support ="):
                        sup = l.split("=")[1].strip()
        if sup is not None:
            return sup == ("0" if want_off else "1"), f"OrcaSlicer sliced it; gcode says enable_support = {sup}"
        return None, f"NOT SLICER-CHECKED: OrcaSlicer rc={p.returncode}, no gcode came back ({(p.stdout + p.stderr).strip()[-200:] or 'it printed nothing'}); say so in the hand-off"
    except Exception as e:
        return None, f"NOT SLICER-CHECKED: OrcaSlicer CLI failed ({type(e).__name__}); say so in the hand-off"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="?"); ap.add_argument("--supports", choices=["on", "off", "auto"], default="auto"); ap.add_argument("--out")
    ap.add_argument("--piece", action="append", help="NAME=part.stl@slot[,part.stl@slot...]: one multi-colour piece (repeat per piece)")
    ap.add_argument("--expect", help="JSON (or file) of what was asked for: pieces, filaments, supports, visible_from_top (see forge contents)")
    ap.add_argument("--no-orca", action="store_true", help="skip the OrcaSlicer CLI load check")
    a = ap.parse_args(argv)
    if a.piece:
        sys.exit(export_pieces(a))
    if not a.model:
        ap.error("need a model STL or --piece")
    if not os.path.exists(a.model):
        sys.exit(f"forge export: no such file {a.model}")
    import preflight
    R, _ = preflight.analyse(a.model)
    preflight.report(R)
    sup = a.supports
    if sup == "auto":
        if R["verdict"] == "NO-GO":
            sys.exit("forge export: preflight says NO-GO, so there is no safe supports setting. Fix the geometry (or pass --supports on|off to force it).")
        sup = R["supports"]
    elif sup == "on" and R["support_traps"]:
        print("   WARNING: supports ON but preflight found auto-support traps: they WILL weld the print-in-place gaps")
    elif sup == "off" and R["supports"] == "on":
        print("   WARNING: supports OFF but preflight says this part needs them (mid-air islands / steep overhangs)")
    on = sup == "on"
    out = a.out or os.path.splitext(a.model)[0] + ("_SUPPORTS-ON.3mf" if on else "_SUPPORTS-OFF.3mf")
    write_3mf(a.model, out, on)
    tris, ext, ce, pm = check_3mf(out)
    print(f"forge export: wrote {out}  ({tris} triangles, {ext} mm)  supports {'ON' if on else 'OFF'} "
          f"[orca enable_support={ce}, prusa support_material={pm}]")
    print("   open THIS 3MF in the slicer (not the STL) and confirm the Support box reads " + ("ticked" if on else "UNTICKED") + "; change nothing else.")
    if not a.no_orca:
        ok, msg = orca_sanity(out, not on)
        print("   orca check:", msg, "" if ok is None else ("-> OK" if ok else "-> MISMATCH"))
    sys.exit(0 if show_contents(out, a.expect) else 1)


def export_pieces(a):
    import preflight, tempfile, trimesh
    pieces = [parse_piece(p) for p in a.piece]
    sup = {}
    for name, ps in pieces:
        if a.supports != "auto":
            sup[name] = a.supports == "on"; continue
        tmp = os.path.join(tempfile.mkdtemp(), f"{name}.stl")
        trimesh.util.concatenate([trimesh.load(f, force="mesh") for _, f, _ in ps]).export(tmp)
        R, _ = preflight.analyse(tmp)
        if R["verdict"] == "NO-GO":
            return f"forge export: preflight says NO-GO for piece {name!r}; fix it (or pass --supports on|off to force)."
        sup[name] = R["supports"] == "on"
    out = a.out or (pieces[0][0] + "_set" + ("_SUPPORTS-ON.3mf" if any(sup.values()) else "_SUPPORTS-OFF.3mf"))
    write_pieces(pieces, out, sup, os.path.splitext(os.path.basename(out))[0])
    print(f"forge export: wrote {out}")
    if not a.no_orca:
        ok, msg = orca_sanity(out, not any(sup.values()))
        print("   orca check:", msg, "" if ok is None else ("-> OK" if ok else "-> MISMATCH"))
    return 0 if show_contents(out, a.expect) else 1


if __name__ == "__main__":
    main()
