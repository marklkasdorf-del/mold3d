#!/usr/bin/env python3
"""report: the Mold3D Print Report. One command at the end of every finished design.

    forge report <out_dir | model.stl> [--json] [--fresh] [--no-export] [--no-preview] [--allow-tight]

Gathers what exists (never guesses; anything missing is omitted):
  bbox, printer, preflight verdict + supports decision + top issues (cached preflight.json if newer than the STL, else runs it),
  moving parts + min gap + whether gaps are calibrated [V] or research default [R] (mech.json + selftest.json + fit.json),
  slice time / grams (only if a slicer hook is configured), and the print-ready files.
Collects the deliverables next to the STL: <name>.3mf (via the same writer as `forge export`, supports decision baked in),
preview.png (copied from an existing render; rendered with Blender only if Blender is installed), report.json.
Prints the chat-ready markdown table (the one the agent shows the user); --json prints report.json instead.
Exit 0 = print-ready, 3 = preflight NO-GO (no 3MF written), 4 = a spec check failed (the part is not what was asked for).
"""
import argparse, datetime, glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forge_env
import fit
import printer

SEV = {"NO-GO": 0, "CAUTION": 1, "SUPPORTS": 2, "TRAP": 3}


# ---------------------------------------------------------------- plain English
def plain(i):
    """translate one preflight issue into a short plain-English sentence (no numbers except tool-reported ones)."""
    c, lv, m = i.get("code"), i.get("level"), i.get("msg", "")
    if c == "bed":
        return "too big for your print bed; split it or scale it down"
    if c == "contact":
        return ("the part touches the bed on a tiny sliver and will peel off; re-orient it" if lv == "NO-GO"
                else "small footprint for its height; add a brim")
    if c == "tip":
        return ("it will tip or peel off the bed; re-orient it or add a brim" if lv == "NO-GO"
                else "tall and narrow, so it may wobble; add a brim")
    if c == "islands":
        return "some parts start in mid-air and need supports"
    if c == "overhang":
        return "steep overhangs need supports"
    if c == "walls":
        return ("walls too thin to print reliably in places" if "1.2" in m else "some walls are thin and may feel fragile")
    if c == "pip":
        return ("moving parts are too close together and will fuse" if lv == "NO-GO"
                else "tight gap near the bed may fuse")
    if c == "traps":
        return ("it needs supports, but supports would glue the moving parts together; the shape needs changing" if lv == "NO-GO"
                else "supports would glue the moving parts together, so keep them OFF")
    return m.split(" -> ")[0][:90]


def top_issues(issues, n=2):
    seen, out = set(), []
    for i in sorted(issues, key=lambda i: SEV.get(i.get("level"), 9)):
        text = plain(i)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out[:n]


# ---------------------------------------------------------------- gathering
def read_spec(out_dir, stl):
    """the design's spec.json: next to the report, else next to the STL, else {}."""
    import spec_lib
    p = spec_lib.find_spec(out_dir, os.path.dirname(stl))
    return spec_lib.load(p) if p else {}


def read_assumed(spec):
    """Fit numbers nobody confirmed (spec_lib: "fit" entries with source ASSUMED plus the older "assumed" shorthand)."""
    import spec_lib
    return {f["name"]: spec_lib.fmt(f["value"]) if f["value"] not in (None, "") else "" for f in spec_lib.assumed_fit(spec)}


def resolve(arg):
    p = os.path.abspath(arg)
    if os.path.isdir(p):
        name = os.path.basename(p.rstrip("/"))
        stl = os.path.join(p, name + ".stl")
        if not os.path.exists(stl):
            cands = [f for f in glob.glob(os.path.join(p, "*.stl")) if not f.endswith("_heat.stl")]
            if len(cands) != 1:
                sys.exit(f"forge report: no <name>.stl in {p}" if not cands else
                         f"forge report: {len(cands)} STLs in {p}; pass the one you want: {', '.join(os.path.basename(c) for c in cands)}")
            stl = cands[0]
        return p, stl
    if not os.path.exists(p):
        sys.exit(f"forge report: no such file or folder {p}")
    return os.path.dirname(p), p


def _suffix(out_dir, stl):
    """report.json / preflight.json for the design's primary STL, <stem>.* when several STLs share a folder."""
    stem = os.path.splitext(os.path.basename(stl))[0]
    others = [f for f in glob.glob(os.path.join(out_dir, "*.stl")) if os.path.abspath(f) != os.path.abspath(stl)]
    return "" if (not others or stem == os.path.basename(out_dir.rstrip("/"))) else stem + "."


def _jload(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def get_checks(out_dir, stl, spec, fresh):
    """verify's 'N of M green': a verify.json next to the STL that is newer than it (forge run wrote it), else run verify now."""
    pre = _suffix(out_dir, stl)
    cache = os.path.join(out_dir, pre + "verify.json")
    res = None
    if not fresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(stl):
        res = _jload(cache)
        if not (res and res.get("summary")):
            res = None
    if res is None:
        try:
            import verify_lib
            res = verify_lib.verify(stl, spec, spec_dir=out_dir)
            json.dump(res, open(cache, "w"), indent=1, default=str)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
    s = res["summary"]
    return {"green": s["green"], "total": s["total"], "not_green": s.get("not_green", []), "status": res.get("status")}


def get_preflight(out_dir, stl, fresh, allow_tight):
    pre = _suffix(out_dir, stl)
    cache = os.path.join(out_dir, pre + "preflight.json")
    if not fresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(stl):
        R = _jload(cache)
        if R and "verdict" in R:
            return R, "cached " + os.path.basename(cache)
    import preflight
    hook = bool(os.environ.get("FORGE_SLICER_CMD") or printer.load().get("slicer_cmd"))
    R, _ = preflight.analyse(stl, do_slice=hook, allow_tight=allow_tight)
    json.dump(R, open(cache, "w"), indent=1, default=str)
    return R, "ran preflight"


def mech_info(out_dir):
    mech = _jload(os.path.join(out_dir, "mech.json"))
    if not mech:
        return None
    st = _jload(os.path.join(out_dir, "selftest.json"))
    parts, fixed = mech.get("parts", []), mech.get("fixed", [])
    info = {"count": max(len(parts) - len(fixed), 0), "motions": len(mech.get("motions", []))}
    if st:
        info["selftest_ok"] = bool(st.get("ok"))
        bad = [m for m in st.get("motions", []) if m.get("collide_at") or (m.get("sweep_worst_mm3") or 0) > 0]
        jam_ok = all(m.get("control_jams") for m in st.get("motions", []))
        info["clear_through_motion"] = bool(st.get("ok")) and not bad and not st.get("static")
        info["must_jam_controls_pass"] = jam_ok
        if bad:
            info["collisions"] = [{"motion": m["motion"], "at": m.get("collide_at")} for m in bad]
        g = st.get("gaps") or {}
        if g:
            info["min_gap_mm"] = round(min(g.values()), 3)
            info["max_gap_mm"] = round(max(g.values()), 3)
    meta = mech.get("meta") or {}
    if isinstance(meta.get("gaps"), list):           # the Fit Card: gaps are the experiment, not the design
        info["calibration_print"] = True
        info["gap_range_mm"] = [min(meta["gaps"]), max(meta["gaps"])]
    return info


def find_preview(out_dir, stl, allow_render):
    dst = os.path.join(out_dir, "preview.png")
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(stl):
        return dst, None
    stem = os.path.splitext(os.path.basename(stl))[0]
    for pat in (f"{stem}_hero.png", "poster.png", "sheet.png"):
        c = os.path.join(out_dir, pat)
        if os.path.exists(c):
            shutil.copy(c, dst)
            return dst, None
    if not allow_render:
        return None, "preview skipped (--no-preview)"
    if not forge_env.find_blender():
        return None, "preview.png is off (Blender isn't installed). Everything else works."
    tmp = os.path.join(out_dir, "_preview_tmp")
    try:
        r = subprocess.run([os.path.join(forge_env.ROOT, "bin", "render"), stl, tmp], capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.exists(os.path.join(tmp, "sheet.png")):
            shutil.copy(os.path.join(tmp, "sheet.png"), dst)
            return dst, None
        return None, "preview.png is off (Blender didn't start here; inside an agent sandbox re-run outside it). Everything else works."
    except Exception as e:
        return None, f"preview.png is off ({type(e).__name__}). Everything else works."
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def make_3mf(out_dir, stl, R):
    """<name>_SUPPORTS-OFF|ON.3mf next to the STL, supports decision = preflight's. NO-GO writes nothing (no safe setting)."""
    if R.get("verdict") == "NO-GO":
        return None
    on = R.get("supports") == "on"
    out = os.path.splitext(stl)[0] + ("_SUPPORTS-ON.3mf" if on else "_SUPPORTS-OFF.3mf")
    other = os.path.splitext(stl)[0] + ("_SUPPORTS-OFF.3mf" if on else "_SUPPORTS-ON.3mf")
    if os.path.exists(other):
        os.remove(other)                              # a stale opposite file would be a loaded gun
    if not (os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(stl)):
        import export3mf
        export3mf.write_3mf(stl, out, on)
    return out


def gather(a):
    out_dir, stl = resolve(a.target)
    name = os.path.splitext(os.path.basename(stl))[0]
    mech = mech_info(out_dir)
    cal = bool(mech and mech.get("calibration_print"))
    R, how = get_preflight(out_dir, stl, a.fresh, a.allow_tight or cal)
    pr = printer.load()
    rep = {"name": name, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "printer": pr.get("name"), "bbox_mm": R.get("bbox_mm"), "volume_cm3": R.get("volume_cm3"),
           "preflight": {"verdict": R["verdict"], "supports": R["supports"], "supports_text": R.get("supports_text"),
                         "issues": [{k: i.get(k) for k in ("level", "code", "msg", "fix")} for i in R.get("issues", [])],
                         "notes": R.get("notes", []), "source": how}}
    rep["watch_for"] = top_issues(R.get("issues", []))
    spec = read_spec(out_dir, stl)
    rep["assumed"] = read_assumed(spec)
    import spec_lib
    fs = spec_lib.fit_summary(spec)
    if fs:
        rep["fit"] = {"stamped": fs[0], "text": fs[1], "numbers": spec_lib.fit_numbers(spec)}
    rep["checks"] = get_checks(out_dir, stl, spec, a.fresh)
    if mech:
        rep["moving_parts"] = mech
        tag = fit.tag("pip_gap")
        mech["gaps_basis"] = ("calibration_print" if cal else "calibrated" if tag == "[V]" else "research_default")
        mech["pip_gap_tag"] = tag
    if R.get("print_time") or R.get("grams"):
        rep["slice"] = {k: R[k] for k in ("print_time", "grams") if R.get(k)}
    files = {"stl": stl}
    notes = []
    if not a.no_export:
        f3 = make_3mf(out_dir, stl, R)
        if f3:
            files["3mf"] = f3
        else:
            notes.append("no 3MF written: preflight says NO-GO, so there is no safe supports setting. Fix the geometry first.")
    pv, why = find_preview(out_dir, stl, not a.no_preview)
    if pv:
        files["preview"] = pv
    elif why:
        notes.append(why)
    rep["files"] = files
    if notes:
        rep["notes"] = notes
    pre = _suffix(out_dir, stl)
    rpath = os.path.join(out_dir, pre + "report.json")
    files["report"] = rpath
    json.dump(rep, open(rpath, "w"), indent=1, default=str)
    return rep


# ---------------------------------------------------------------- rendering
def _dims(b):
    return " x ".join(f"{v:g}" for v in b) + " mm"


def _home(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p.startswith(h + os.sep) else p


def verdict_text(pf):
    v, s = pf["verdict"], pf["supports"]
    if v == "NO-GO":
        return "❌ NO-GO, fix the shape before printing"
    if v == "GO+SUPPORTS":
        return "⚠️ GO + supports, supports ON"
    req = " (required)" if any(i["code"] == "traps" and i["level"] == "TRAP" for i in pf["issues"]) else ""
    if v == "CAUTION":
        return f"⚠️ GO with cautions, supports OFF{req}"
    return f"✅ GO, supports OFF{req}"


def markdown(rep):
    head = ["**MOLD3D PRINT REPORT**", rep["name"]]
    if rep.get("bbox_mm"):
        head.append(_dims(rep["bbox_mm"]))
    if rep.get("printer"):
        head.append(rep["printer"])
    fitinfo = rep.get("fit")
    if fitinfo and fitinfo.get("stamped"):
        head.append("**NOT FIT-CHECKED**")
    rows = [("Verdict", verdict_text(rep["preflight"]))]
    ck = rep.get("checks") or {}
    if "total" in ck:
        rest = [t for t in ck["not_green"] if not t.startswith("NOT FIT-CHECKED")]     # the Fit row already says that one
        txt = f"{ck['green']} of {ck['total']} green"
        if rest:
            txt += ": " + "; ".join(rest[:2]) + (f"; and {len(rest) - 2} more" if len(rest) > 2 else "")
        rows.append(("Checks", ("✅ " if ck["green"] == ck["total"] else "❌ " if ck.get("status") == "FAIL" else "⚠️ ") + txt))
    if fitinfo:
        rows.append(("Fit", ("⚠️ " if fitinfo["stamped"] else "✅ ") + fitinfo["text"]))
    mp = rep.get("moving_parts")
    if mp:
        if mp.get("selftest_ok") is None:
            rows.append(("Moving parts", f"{mp['count']}"))
        elif mp.get("clear_through_motion"):
            rows.append(("Moving parts", f"{mp['count']}, all clear through full motion"))
        else:
            c = mp.get("collisions") or []
            rows.append(("Moving parts", f"{mp['count']}, COLLISION in " + (", ".join(x["motion"] for x in c[:2]) or "self-test") + ", do not print"))
        if "min_gap_mm" in mp:
            if mp["gaps_basis"] == "calibration_print":
                lo, hi = mp["gap_range_mm"]
                rows.append(("Gaps", f"{lo:.2f} to {hi:.2f} mm test range (this print calibrates your printer)"))
            elif mp["gaps_basis"] == "calibrated":
                rows.append(("Gaps", f"{mp['min_gap_mm']:.2f} mm (calibrated on your printer)"))
            else:
                rows.append(("Gaps", f"{mp['min_gap_mm']:.2f} mm (default, print the Fit Card to calibrate)"))
    sl = rep.get("slice")
    if sl:
        rows.append(("Print", " · ".join(x for x in ((f"~{sl['print_time']}" if sl.get("print_time") else None),
                                                      (f"{sl['grams']:g} g" if sl.get("grams") else None)) if x)))
    if rep.get("assumed"):
        rows.append(("Assumed", "; ".join(f"{k} {v}".strip() for k, v in rep["assumed"].items()) + " (not confirmed, check before you print)"))
    rows.append(("Watch for", "; ".join(rep["watch_for"]) if rep["watch_for"] else "nothing flagged by preflight"))
    f = rep["files"]
    if "3mf" in f:
        rows.append(("Files", f"`{_home(f['3mf'])}` (print this)"))
    else:
        rows.append(("Files", f"`{_home(f['stl'])}` (not print-ready)"))
    lines = [" · ".join(head), "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target"); ap.add_argument("--json", action="store_true", help="print report.json instead of the markdown table")
    ap.add_argument("--fresh", action="store_true", help="re-run preflight even if a cached preflight.json is newer than the STL")
    ap.add_argument("--no-export", action="store_true", help="don't write the 3MF")
    ap.add_argument("--no-preview", action="store_true", help="don't render a preview (an existing render is still copied)")
    ap.add_argument("--allow-tight", action="store_true", help="calibration print: tight gaps are intended (set automatically for the Fit Card)")
    a = ap.parse_args(argv)
    rep = gather(a)
    print(json.dumps(rep, indent=1, default=str) if a.json else markdown(rep))
    for n in rep.get("notes", []):
        print(f"\nnote: {n}", file=sys.stderr)
    sys.exit(3 if rep["preflight"]["verdict"] == "NO-GO" else 4 if (rep.get("checks") or {}).get("status") == "FAIL" else 0)


if __name__ == "__main__":
    main()
