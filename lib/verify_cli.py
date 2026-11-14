#!/usr/bin/env python3
"""verify <stl> [--spec spec.json] [--json] [--raw]  |  verify --orient <stl> [--angle 45]  |  verify --assembly a.stl b.stl [--clearance 0.2] [--move-a x,y,z] [--move-b x,y,z] [--no-contact]
Exit 0 = PASS/WARN, 1 = FAIL, 2 = usage/load error."""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import verify_lib as V


def vec(s):
    return tuple(float(x) for x in s.split(","))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stl", nargs="?")
    ap.add_argument("--spec")
    ap.add_argument("--orient", metavar="STL", help="rank the 6 axis-aligned print orientations (support area, bed contact, height)")
    ap.add_argument("--angle", type=float, default=None, help="overhang limit used by --orient (default: the printer profile's overhang_deg)")
    ap.add_argument("--assembly", nargs=2, metavar=("A", "B"))
    ap.add_argument("--clearance", type=float, default=0.2)
    ap.add_argument("--move-a", type=vec, default=(0, 0, 0), help="translate A (mm) into assembled pose, e.g. 0,0,0")
    ap.add_argument("--move-b", type=vec, default=(0, 0, 0), help="translate B (mm) into assembled pose, e.g. -70,0,22")
    ap.add_argument("--no-contact", action="store_true", help="treat touching surfaces as gap=0 (fail clearance)")
    ap.add_argument("--json", action="store_true", help="print only JSON")
    ap.add_argument("--raw", action="store_true", help="the engineering table (name / value / detail) instead of plain words")
    ap.add_argument("--out", help="also write JSON here")
    a = ap.parse_args()
    try:
        if a.orient:
            res = V.orientations(a.orient, angle=a.angle)
            print(json.dumps(res, indent=1) if a.json else V.format_orient(res)); sys.exit(0)
        if a.assembly:
            res = V.assembly(a.assembly[0], a.assembly[1], a.clearance, a.move_a, a.move_b, allow_contact=not a.no_contact)
        elif a.stl:
            spec = json.load(open(a.spec)) if a.spec else {}
            res = V.verify(a.stl, spec, spec_dir=os.path.dirname(os.path.abspath(a.spec)) if a.spec else None)
        else:
            ap.error("need an STL or --assembly A B")
    except Exception as e:  # never silently pass
        print(f"VERIFY ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str) if a.json else (V.format_text(res) if a.raw or "summary" not in res else V.format_plain(res)))
    sys.exit(1 if res["status"] == "FAIL" else 0)


main()
