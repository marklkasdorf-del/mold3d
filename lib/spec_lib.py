"""spec_lib: the spec.json schema that verify and the Print Report share.

Two things live here:

1. The "no guessed numbers" gate (fit numbers and their sources).
   Every number that decides whether the part FITS something lives in spec.json under "fit", each with a source:

       "fit": {
         "pod diameter":   {"mm": 38.2, "source": "measured", "note": "calipers"},
         "screw clearance": {"mm": 3.4, "source": "parts-find", "ref": "ISO 4762 M3"},
         "tube diameter":  {"mm": 25,   "source": "ASSUMED"}
       }

   Allowed sources: measured | datasheet | parts-find | photofit | user | library | ASSUMED.
   Anything else (or a missing source) counts as ASSUMED: the gate cannot be dodged by typing "guess".
   The older shorthand  "assumed": {"screw size": "M4"}  still works and counts as ASSUMED fit numbers.
   Only entries under "fit" are judged: wall thickness, colours, fillets never nag.

   An ASSUMED fit number stamps the Print Report NOT FIT-CHECKED and names the cheapest fix
   (a datasheet, `forge parts-find`, `forge photofit`, or one question with a default).

2. Named requirements ("checks") that `forge verify` runs and prints as PASS/FAIL in plain words.
   See verify_lib.named_checks for the check types; this module only reads/normalises them.
"""
import json, os, re

SOURCES = ("measured", "datasheet", "parts-find", "photofit", "user", "library")
ASSUMED = "ASSUMED"


def load(path):
    try:
        return json.load(open(path)) or {}
    except Exception:
        return {}


def find_spec(*dirs):
    """first spec.json found in the given folders, or None."""
    for d in dirs:
        if not d:
            continue
        p = os.path.join(d, "spec.json")
        if os.path.exists(p):
            return p
    return None


def fmt(v):
    """38.2 -> '38.2 mm'; strings pass through ('M4', '72 mm')."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:g} mm"
    return str(v)


_fmt = fmt


def fit_numbers(spec):
    """Normalise the fit block + legacy "assumed" into a list of
    {name, value, source, ok, fix}. ok = the source is a real one."""
    out = []
    fit = spec.get("fit") or {}
    if isinstance(fit, dict):
        for name, e in fit.items():
            if not isinstance(e, dict):
                e = {"mm": e}
            src = str(e.get("source", ASSUMED)).strip()
            ok = src.lower() in SOURCES
            val = e.get("mm", e.get("value"))
            out.append({"name": str(name), "value": val, "source": src if ok else ASSUMED,
                        "ok": ok, "fix": e.get("fix") or cheapest_fix(name, e), "ref": e.get("ref") or e.get("note")})
    legacy = spec.get("assumed") or {}
    if isinstance(legacy, list):
        legacy = {str(k): "" for k in legacy}
    if isinstance(legacy, dict):
        names = {o["name"] for o in out}
        for name, v in legacy.items():
            if str(name) in names:
                continue
            out.append({"name": str(name), "value": v, "source": ASSUMED, "ok": False,
                        "fix": cheapest_fix(name, {"mm": v}), "ref": None})
    return out


def assumed_fit(spec):
    return [f for f in fit_numbers(spec) if not f["ok"]]


_PARTS = re.compile(r"\b(m\d(\.\d)?|screw|bolt|nut|washer|insert|bearing|motor|nema|servo|shaft|magnet|pulley|rod)\b", re.I)
_DEVICES = re.compile(r"\b(phone|iphone|pixel|galaxy|ipad|tablet|pi\b|raspberry|arduino|esp32|esp8266|controller|camera|gopro|battery|18650|aa\b|aaa\b|watch|airpods|switch|deck|laptop|macbook|remote|board)\b", re.I)
_OUTLINE = re.compile(r"\b(outline|footprint|shape|pocket|insert for|profile|irregular)\b", re.I)


def cheapest_fix(name, entry=None):
    """The cheapest way to turn an ASSUMED fit number into a sourced one, in plain words."""
    n = str(name)
    default = _fmt(entry.get("mm", entry.get("value"))) if isinstance(entry, dict) and entry.get("mm", entry.get("value")) not in (None, "") else None
    if _PARTS.search(n):
        return f'`forge parts-find "{n}"` gives the real dimensions'
    if _DEVICES.search(n):
        return f"look up the maker's spec sheet for the {n} (knowledge/devices.json first, then the official page)"
    if _OUTLINE.search(n):
        return "`forge photofit mat`, photograph the object on it, and the outline is exact"
    q = f"ask one question: what is the {n}?"
    return q + (f" (default {default})" if default else "")


def fit_summary(spec):
    """One plain line for the Print Report's Fit row, or None when the spec has no fit numbers.
    Returns (stamped: bool, text)."""
    fits = fit_numbers(spec)
    if not fits:
        return None
    bad = [f for f in fits if not f["ok"]]
    if not bad:
        by = {}
        for f in fits:
            by[f["source"]] = by.get(f["source"], 0) + 1
        srcs = ", ".join(f"{v} {k}" for k, v in sorted(by.items(), key=lambda kv: -kv[1]))
        return False, f"fit-checked: {len(fits)} fit number{'s' if len(fits) != 1 else ''} sourced ({srcs})"
    items = [f"{f['name']}" + (f" {_fmt(f['value'])}" if f["value"] not in (None, "") else "") for f in bad[:3]]
    what = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    more = f" and {len(bad) - 3} more" if len(bad) > 3 else ""
    fix = bad[0]["fix"]
    return True, (f"NOT FIT-CHECKED: {what}{more} {'was' if len(bad) == 1 else 'were'} assumed, so the part may not fit. "
                  f"Cheapest fix: {fix}")


def fit_row(spec):
    """verify row for the gate: PASS when every fit number has a source, WARN when any is ASSUMED, None without a fit block."""
    fits = fit_numbers(spec)
    if not fits:
        return None
    bad = [f for f in fits if not f["ok"]]
    if not bad:
        return {"name": "fit_sources", "status": "PASS", "value": len(fits),
                "detail": f"every fit number has a source ({', '.join(sorted({f['source'] for f in fits}))})",
                "plain": f"All {len(fits)} fit number{'s have' if len(fits) != 1 else ' has'} a real source"}
    names = ", ".join(f["name"] for f in bad[:3]) + (f" and {len(bad) - 3} more" if len(bad) > 3 else "")
    return {"name": "fit_sources", "status": "WARN", "value": len(bad),
            "detail": f"ASSUMED fit numbers: {names} -> NOT FIT-CHECKED; fix: {bad[0]['fix']}",
            "plain": f"NOT FIT-CHECKED: {names} {'is' if len(bad) == 1 else 'are'} assumed. Fix: {bad[0]['fix']}"}


if __name__ == "__main__":
    import sys
    s = load(sys.argv[1]) if len(sys.argv) > 1 else {}
    for f in fit_numbers(s):
        print(("ok      " if f["ok"] else "ASSUMED ") + f"{f['name']}: {_fmt(f['value'])} [{f['source']}]" + ("" if f["ok"] else f"  fix: {f['fix']}"))
    r = fit_summary(s)
    print(r[1] if r else "no fit numbers in spec")
