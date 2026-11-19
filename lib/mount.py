#!/usr/bin/env python3
"""forge mount <init|product|card|measure-card|numbers|comb|result|build> ...   photo of the spot -> a part that fits it

  init <name> <photo...> [--ask "..."] [--add]   copy photos (EXIF-rotated), write grid_N.jpg + the analysis.json skeleton
  product "<query>"                              look a branded payload up in knowledge/objects.json (never measure it)
  card <name>                                    Mount Card (mount_card.png, 1080x1350)
  measure-card <name>                            Measuring Card (measure_card.png, 1080x1350)
  numbers <name> "<reply>" [--profile f.json] [--confirm]   parse "A 32 B 18", typo-check against the photo
  comb <name> [--center A=31]                    fit comb: 3 teeth at centre -1/0/+1 (short print)
  result <name> "<reply>"                        "-1 clicked" / "all loose ~2" -> the measured number (or a new comb)
  build <name>                                   the part: pieces, <name>.stl, spec.json, mount.json, verify.json

Exit codes: 0 ok, 1 build/verify FAIL, 2 needs the user or the agent (bad input, a flag, a missing field). The last stdout line
is always one JSON object. Designs live in <MOLD3D_OUT>/<name>/. Spec: docs/specs/photo-to-fit.md in the repo history.
"""
import datetime, json, math, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forge_env

FORGE = os.path.dirname(HERE)
OBJECTS = os.path.join(FORGE, "knowledge", "objects.json")
SECTIONS = ("round", "edge", "flat", "irregular")
STYLES = {"round": ("clamp-round", "strap"), "edge": ("hookover",), "flat": ("screw",), "irregular": ("strap",)}
STYLE_NAME = {"clamp-round": "Bolt clamp", "hookover": "Hook-over clip", "strap": "Strap saddle", "screw": "Screw plate"}
GREEN, RED, ORANGE, BLUE = (30, 158, 80), (214, 40, 40), (235, 130, 0), (40, 90, 220)


class Stop(Exception):
    def __init__(self, msg, code=2, **extra):
        super().__init__(msg); self.msg, self.code, self.extra = msg, code, extra


def emit(ok, code=0, **kw):
    print(json.dumps(dict({"ok": ok}, **kw), default=str))
    sys.exit(code)


def ddir(name):
    d = os.path.join(forge_env.OUT, name)
    if not os.path.isdir(d):
        raise Stop(f"no design called '{name}' in {forge_env.OUT}: run `forge mount init {name} <photo>` first")
    return d


def load(name):
    p = os.path.join(ddir(name), "analysis.json")
    if not os.path.exists(p):
        raise Stop(f"{name} has no analysis.json yet: run `forge mount init {name} <photo>` and fill it in")
    try:
        return json.load(open(p))
    except Exception as e:
        raise Stop(f"analysis.json is not valid JSON ({e})")


def save(name, a):
    json.dump(a, open(os.path.join(ddir(name), "analysis.json"), "w"), indent=1)


# ------------------------------------------------------------------ validation
def _coords(a):
    """every normalized coordinate in the analysis as (where, x, y)."""
    out = []
    it = a.get("interface") or {}
    for i, pt in enumerate(it.get("spot") or []):
        out.append((f"interface.spot[{i}]", pt))
    ld = a.get("load") or {}
    for k in ("from", "to"):
        if ld.get(k):
            out.append((f"load.{k}", ld[k]))
    for i, o in enumerate(a.get("obstacles") or []):
        if o.get("at"):
            out.append((f"obstacles[{i}].at", o["at"]))
    for m in a.get("measure") or []:
        for k in ("p0", "p1"):
            if m.get(k):
                out.append((f"measure {m.get('label')}.{k}", m[k]))
    sr = a.get("scale_ref")
    if sr:
        for k in ("p0", "p1"):
            if sr.get(k):
                out.append((f"scale_ref.{k}", sr[k]))
    return out


def validate(a, need=("payload", "interface.section", "style", "measure")):
    miss = []
    if "payload" in need and not isinstance(a.get("payload"), dict):
        miss.append("payload")
    it = a.get("interface") or {}
    if "interface.section" in need and it.get("section") not in SECTIONS:
        miss.append(f"interface.section (one of {', '.join(SECTIONS)})")
    if "style" in need and not a.get("style"):
        miss.append("style")
    if "measure" in need:
        ms = a.get("measure") or []
        if not ms:
            miss.append("measure (at least one entry)")
        elif len(ms) > 3:
            miss.append("measure (at most 3 entries)")
        for i, m in enumerate(ms):
            for k in ("label", "what", "photo", "p0", "p1"):
                if m.get(k) is None:
                    miss.append(f"measure[{i}].{k}")
    for where, pt in _coords(a):
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in pt)):
            miss.append(f"{where} must be [x, y] inside 0..1")
    if miss:
        raise Stop("analysis.json is missing or wrong: " + "; ".join(miss), missing=miss)
    sec, sty = it.get("section"), a.get("style")
    if "style" in need and sty not in STYLE_NAME:
        raise Stop(f"unknown style '{sty}': use one of {', '.join(STYLE_NAME)}")
    if "style" in need and "interface.section" in need and sty not in STYLES[sec]:
        raise Stop(f"style '{sty}' does not suit a {sec} section: use {' or '.join(STYLES[sec])}")


# ------------------------------------------------------------------ pure functions
_VAL = re.compile(r"(?<![A-Za-z])([A-Ca-c])\s*[=:]?\s*(c)?\s*(\d+(?:\.\d+)?|\.\d+)\s*(mm|cm|in|\")?(?![A-Za-z])")


def parse_numbers(text, labels):
    """"A 32 B 18" -> {A: {mm, note}}. Raises ValueError("Reply like: A 32 B 18") for anything it cannot read."""
    labels = [l.upper() for l in labels]
    hint = "Reply like: " + " ".join(f"{l} {'32' if i == 0 else '18'}" for i, l in enumerate(labels))
    t = (text or "").strip()
    out = {}
    if len(labels) == 1 and re.fullmatch(r"\s*(\d+(?:\.\d+)?|\.\d+)\s*(mm|cm|in|\")?\s*", t):
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?|\.\d+)\s*(mm|cm|in|\")?\s*", t)
        v, unit = float(m.group(1)), m.group(2)
        mm = v * 10 if unit == "cm" else v * 25.4 if unit in ("in", '"') else v
        return {labels[0]: {"mm": round(mm, 3), "note": ""}}
    for m in _VAL.finditer(t):
        lab = m.group(1).upper()
        if lab not in labels:
            raise ValueError(f"I only need {', '.join(labels)}, not {lab}. {hint}")
        v, unit = float(m.group(3)), m.group(4)
        if m.group(2):
            out[lab] = {"mm": round(v / math.pi, 2), "note": f"paper strip, circumference {m.group(3)}"}
        else:
            mm = v * 10 if unit == "cm" else v * 25.4 if unit in ("in", '"') else v
            out[lab] = {"mm": round(mm, 3), "note": f"typed {m.group(3)}{unit or ''}" if unit else ""}
    missing = [l for l in labels if l not in out]
    if not out or missing:
        raise ValueError(hint if not out else f"I still need {', '.join(missing)}. {hint}")
    return out


def _dist(p, q, size):
    return math.hypot((p[0] - q[0]) * size[0], (p[1] - q[1]) * size[1])


def _close(x, est, tol=0.20):
    return est > 0 and abs(x - est) / est <= tol


def _hint(u, est, tol):
    if _close(u * 10, est, tol):
        return "looks like cm"
    if _close(u * 25.4, est, tol):
        return "looks like inches"
    if _close(u / 10, est, tol):
        return "an extra digit?"
    s = f"{u:g}"
    if s.isdigit() and len(s) > 1 and _close(float(s[::-1]), est, tol):
        return "digits swapped?"
    return "that's far from what the photo shows"


def typo_check(analysis, numbers, design_dir=None, sizes=None):
    """flag lines for numbers far from what the photo (scale_ref) or the prior says. sizes: {photo_index: (w, h)} in pixels."""
    flags = []
    sr = analysis.get("scale_ref")
    prior = (analysis.get("interface") or {}).get("prior_mm") or {}

    def size_of(i):
        if sizes and i in sizes:
            return sizes[i]
        from PIL import Image
        f = analysis["photos"][i]["file"]
        with Image.open(os.path.join(design_dir, f)) as im:
            return im.size

    for m in analysis.get("measure") or []:
        lab = m["label"]
        if lab not in numbers:
            continue
        n = numbers[lab]
        u = float(n["mm"] if isinstance(n, dict) else n)
        what = re.sub(r"\s*diameter\s*$", "", m.get("what", "size")).strip() or "size"
        if sr and sr.get("photo") == m.get("photo") and sr.get("p0") and sr.get("p1"):
            sz = size_of(m["photo"])
            ref_px = _dist(sr["p0"], sr["p1"], sz)
            if ref_px <= 0:
                continue
            est = float(sr["mm"]) * _dist(m["p0"], m["p1"], sz) / ref_px
            if _close(u, est, 0.20):
                continue
            refw = sr.get("what", "the reference").split(",")[0]
            flags.append(f"{lab} {u:g}? Next to the {refw} the {what} looks like about {est:.0f} ({_hint(u, est, 0.20)}). Typo, or is it really {u:g}?")
        elif lab in prior:
            est = float(prior[lab])
            if _close(u, est, 0.35):
                continue
            flags.append(f"{lab} {u:g}? I expected about {est:.0f} for the {what} ({_hint(u, est, 0.35)}). Typo, or is it really {u:g}?")
    return flags


_CL = re.compile(r"^\s*(-1|minus one|0|zero|\+?1|plus one)\s*(clicked|click|fits|fit|good|snug)\b", re.I)
_ALL = re.compile(r"^\s*all\s+(loose|tight)\s*(?:~|about|around)?\s*(\d+(?:\.\d+)?)?\s*$", re.I)


def parse_result(text):
    t = (text or "").strip()
    m = _CL.match(t)
    if m:
        k = m.group(1).lower()
        return ("click", -1 if k in ("-1", "minus one") else 0 if k in ("0", "zero") else 1)
    m = _ALL.match(t)
    if m:
        return (m.group(1).lower(), float(m.group(2)) if m.group(2) else 1.0)
    return None


RESULT_HELP = 'Tell me which tooth clicked: "-1 clicked", "0 fits" or "+1 snug", or "all loose ~2" / "all tight ~2" (the ~number is about how many mm off).'


def apply_result(centre, text):
    """-> ("measured", mm) | ("redo", new_centre)"""
    r = parse_result(text)
    if r is None:
        raise ValueError(RESULT_HELP)
    kind, v = r
    if kind == "click":
        return "measured", centre + v
    return "redo", (centre - 1 - v) if kind == "loose" else (centre + 1 + v)


# ------------------------------------------------------------------ images
def _tf():
    from PIL import ImageOps
    return ImageOps


def photo_path(d, a, i):
    return os.path.join(d, a["photos"][i]["file"])


def next_index(d):
    n = [int(m.group(1)) for f in os.listdir(d) for m in [re.fullmatch(r"photo_(\d+)\.jpg", f)] if m]
    return (max(n) + 1) if n else 1


def make_grid(src, dst):
    from PIL import Image, ImageDraw
    import annotate
    im = Image.open(src).convert("RGB")
    W, H = im.size
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    f = annotate.font(28, True)
    for k in range(11):
        v = k / 10.0
        x, y = round(v * (W - 1)), round(v * (H - 1))
        dr.line([(x, 0), (x, H)], fill=(255, 0, 200, 150), width=2)
        dr.line([(0, y), (W, y)], fill=(0, 220, 255, 150), width=2)
    for k in range(11):
        v = k / 10.0
        x, y = round(v * (W - 1)), round(v * (H - 1))
        s = f"{v:.1f}"
        for (xx, yy, anc) in ((min(max(x, 22), W - 22), 14, "mm"), (22, min(max(y, 14), H - 14), "mm")):
            bb = dr.textbbox((xx, yy), s, font=f, anchor=anc)
            dr.rectangle((bb[0] - 3, bb[1] - 2, bb[2] + 3, bb[3] + 2), fill=(20, 20, 20, 200))
            dr.text((xx, yy), s, font=f, fill=(255, 255, 255, 255), anchor=anc)
    Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(dst, quality=88)


def to_jpeg(src, dst):
    from PIL import Image, ImageOps
    ext = os.path.splitext(src)[1].lower()
    tmp = None
    if ext in (".heic", ".heif"):
        if not shutil.which("sips"):
            raise Stop("I can't read HEIC photos here: send it as a JPEG, please")
        tmp = dst + ".tmp.jpg"
        r = subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", tmp], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tmp):
            raise Stop("I couldn't convert that HEIC photo: send it as a JPEG, please")
        src = tmp
    try:
        im = Image.open(src); im.load()
    except Exception:
        raise Stop(f"I can't read {os.path.basename(src)} as a photo: send it as a JPEG, please")
    im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > 2000:
        s = 2000.0 / max(im.size)
        im = im.resize((round(im.size[0] * s), round(im.size[1] * s)), Image.LANCZOS)
    im.save(dst, quality=92)
    if tmp and os.path.exists(tmp):
        os.remove(tmp)


# ------------------------------------------------------------------ subcommands
def sub_init(args):
    flags = {"--ask": None}
    add = "--add" in args
    pos, i = [], 0
    while i < len(args):
        if args[i] == "--ask":
            flags["--ask"] = args[i + 1] if i + 1 < len(args) else ""; i += 2; continue
        if args[i] == "--add":
            i += 1; continue
        pos.append(args[i]); i += 1
    if not pos or (not add and len(pos) < 2) or (add and len(pos) < 2):
        raise Stop("usage: forge mount init <name> <photo...> [--ask \"...\"]   |   forge mount init <name> --add <photo...>")
    name, photos = pos[0], pos[1:]
    for p in photos:
        if not os.path.exists(p):
            raise Stop(f"no such photo: {p}")
    d = os.path.join(forge_env.OUT, name)
    if add and not os.path.isdir(d):
        raise Stop(f"no design called '{name}' yet: run `forge mount init {name} <photo>` first")
    os.makedirs(d, exist_ok=True)
    ap = os.path.join(d, "analysis.json")
    a = json.load(open(ap)) if os.path.exists(ap) else {"name": name, "ask": flags["--ask"] or "", "photos": [], "payload": None,
                                                         "interface": {"section": None}, "style": None, "measure": [], "missing_views": [],
                                                         "numbers": {}, "flags": [], "mode": None, "comb": None}
    if flags["--ask"] is not None and not add:
        a["ask"] = flags["--ask"]
    made = []
    for p in photos:
        n = next_index(d)
        dst = os.path.join(d, f"photo_{n}.jpg")
        to_jpeg(p, dst)
        make_grid(dst, os.path.join(d, f"grid_{n}.jpg"))
        a["photos"].append({"file": f"photo_{n}.jpg", "view": None})
        made.append(f"grid_{n}.jpg")
    save(name, a)
    emit(True, 0, design=d, photos=[x["file"] for x in a["photos"]], grids=[os.path.join(d, g) for g in made],
         next="Read the grid_N.jpg images, then fill analysis.json (coordinates are 0..1 on the photo)")


def load_objects():
    try:
        return json.load(open(OBJECTS)).get("objects", [])
    except Exception:
        return []


def sub_product(args):
    q = " ".join(args).strip().lower()
    if not q:
        raise Stop('usage: forge mount product "<payload words>"')
    toks = [t for t in re.split(r"[^a-z0-9.]+", q) if t]
    out = []
    for o in load_objects():
        hay = " ".join([o["name"]] + o.get("aliases", [])).lower()
        words = set(re.split(r"[^a-z0-9.]+", hay))
        if all(t in words or t in hay for t in toks):
            out.append({k: o.get(k) for k in ("id", "name", "kind", "capacity_ml", "empty_g", "body_d", "base_d", "height", "handle_w", "source", "read")})
    emit(True, 0, query=q, matches=out, count=len(out))


def _wrap(dr, txt, f, maxw):
    lines, cur = [], ""
    for w in txt.split(" "):
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _arrow(dr, p0, p1, color, width, head, both=False):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    head = min(head, L / 2.5)
    dr.line([(p0[0] + (ux * head * 0.7 if both else 0), p0[1] + (uy * head * 0.7 if both else 0)), (p1[0] - ux * head * 0.7, p1[1] - uy * head * 0.7)], fill=color, width=width)

    def tri(tip, sgn):
        bx, by = tip[0] - sgn * ux * head, tip[1] - sgn * uy * head
        px, py = -uy * head * 0.5, ux * head * 0.5
        dr.polygon([tip, (bx + px, by + py), (bx - px, by - py)], fill=color)
    tri(p1, 1)
    if both:
        tri(p0, -1)


def _tag(dr, xy, s, f, fg, bg=(255, 255, 255), pad=8, anchor="lt"):
    bb = dr.textbbox(xy, s, font=f, anchor=anchor)
    dr.rectangle((bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad), fill=bg)
    dr.text(xy, s, font=f, fill=fg, anchor=anchor)
    return (bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad)


def _disk(dr, c, r, label, color, f):
    dr.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=color, outline=(255, 255, 255), width=4)
    dr.text(c, label, font=f, fill=(255, 255, 255), anchor="mm")


def range_preview(a):
    """the 'Fits: ...' line, from the numbers (or the prior), or None."""
    try:
        import mountgen as M
        A = ((a.get("numbers") or {}).get("A") or {}).get("mm")
        if A is None:
            return None
        if a.get("style") == "clamp-round":
            return M.clamp_params(float(A))["range_text"].replace("Grips", "Grips", 1)
        if a.get("style") == "hookover":
            return f"Grips desks {A - 2:g}–{A + 1:g} mm thick"
        if a.get("style") == "strap":
            return f"Grips {A - 5:g}–{A + 40:g} mm tube with a 20 mm strap"
    except Exception:
        return None
    return None


def sub_card(args):
    from PIL import Image, ImageDraw
    import annotate
    if not args:
        raise Stop("usage: forge mount card <name>")
    name = args[0]; a = load(name); d = ddir(name)
    validate(a, ("payload", "interface.section", "style"))
    it = a["interface"]
    pi = int(it.get("photo", 0))
    src = Image.open(photo_path(d, a, pi)).convert("RGB")
    W, H = 1080, 1350
    card = Image.new("RGB", (W, H), annotate.PAPER)
    s = min(W / src.size[0], 900 / src.size[1])
    iw, ih = round(src.size[0] * s), round(src.size[1] * s)
    ox, oy = (W - iw) // 2, (900 - ih) // 2
    card.paste(src.resize((iw, ih), Image.LANCZOS), (ox, oy))
    dr = ImageDraw.Draw(card)
    px = lambda p: (ox + p[0] * iw, oy + p[1] * ih)
    fb56, fb48, f40, f36 = annotate.font(56, True), annotate.font(48, True), annotate.font(40), annotate.font(36, True)
    spot = it.get("spot") or []
    if len(spot) >= 3:
        pts = [px(p) for p in spot]
        dr.line(pts + [pts[0]], fill=GREEN, width=8, joint="curve")
        _tag(dr, (min(p[0] for p in pts), min(p[1] for p in pts) - 6), "HERE", fb56, GREEN, anchor="lb")
    ld = a.get("load") or {}
    if ld.get("from") and ld.get("to") and ld.get("photo", pi) == pi:
        p0, p1 = px(ld["from"]), px(ld["to"])
        _arrow(dr, p0, p1, RED, 10, 40)
        mass = (a.get("payload") or {}).get("mass_full_g")
        if mass:
            right = p0[0] + 14 + 260 <= W
            _tag(dr, (p0[0] + 14, p0[1] + 30) if right else (p0[0] - 14, p0[1] + 30), f"≈ {mass / 1000:.1f} kg", fb48, RED, anchor="lm" if right else "rm")
    for k, o in enumerate(a.get("obstacles") or [], 1):
        if o.get("photo", pi) != pi or not o.get("at"):
            continue
        c = px(o["at"]); r = float(o.get("r", 0.05)) * iw
        dr.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), outline=ORANGE, width=8)
        _disk(dr, (c[0] - r * 0.7, c[1] - r * 0.7), 36, str(k), ORANGE, fb48)
        lab = f"{k}: {o.get('what', 'obstacle')}, keep {o.get('keep_out_mm', 10):g} mm"
        wlab = dr.textlength(lab, font=f36) + 24
        right = c[0] + r + 8 + wlab <= W
        _tag(dr, (c[0] + r + 8, c[1]) if right else (c[0] - r - 8, c[1]), lab, f36, ORANGE, anchor="lm" if right else "rm")
    # bottom panel
    y = 920
    letters = "ABC"
    ok_styles = a.get("styles") or [{"id": a["style"], "why": ""}]
    for i, sdef in enumerate(ok_styles[:3]):
        pick = sdef["id"] == a["style"]
        txt = f"{letters[i]}  {STYLE_NAME.get(sdef['id'], sdef['id'])}" + (" (my pick)" if pick else "") + (f": {sdef.get('why', '')}" if sdef.get("why") else "")
        f = fb48 if False else f40
        for line in _wrap(dr, txt, f, W - 60):
            dr.text((30, y), line, font=f, fill=GREEN if pick else annotate.INK); y += 50
        y += 8
    fits = range_preview(a)
    if fits:
        for line in _wrap(dr, "Fits: " + fits.replace("Grips ", "grips ", 1), f40, W - 60):
            dr.text((30, y), line, font=f40, fill=annotate.INK); y += 50
    if y > H:
        raise Stop("the Mount Card text does not fit: shorten the style reasons in analysis.json")
    out = os.path.join(d, "mount_card.png")
    card.save(out)
    emit(True, 0, file=out, size=list(card.size), style=a["style"])


def sub_measure_card(args):
    from PIL import Image, ImageDraw
    import annotate
    if not args:
        raise Stop("usage: forge mount measure-card <name>")
    name = args[0]; a = load(name); d = ddir(name)
    validate(a, ("measure",))
    ms = a["measure"]
    pi = int(ms[0]["photo"])
    on = [m for m in ms if int(m["photo"]) == pi]
    src = Image.open(photo_path(d, a, pi)).convert("RGB")
    sw, sh = src.size
    xs = [m[k][0] for m in on for k in ("p0", "p1")]
    ys = [m[k][1] for m in on for k in ("p0", "p1")]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    mx, my = max(0.15 * bw, 0.06), max(0.15 * bh, 0.10)
    x0, x1 = max(0.0, min(xs) - mx), min(1.0, max(xs) + mx)
    y0, y1 = max(0.0, min(ys) - my), min(1.0, max(ys) + my)
    cw, ch = (x1 - x0) * sw, (y1 - y0) * sh
    for _ in range(2):                                     # a thin strip tells nobody anything: widen the short side to >= 70 % of the long one
        if cw < 0.7 * ch:
            grow = (0.7 * ch - cw) / sw / 2; x0, x1 = max(0.0, x0 - grow), min(1.0, x1 + grow)
        elif ch < 0.7 * cw:
            grow = (0.7 * cw - ch) / sh / 2; y0, y1 = max(0.0, y0 - grow), min(1.0, y1 + grow)
        cw, ch = (x1 - x0) * sw, (y1 - y0) * sh
    crop = src.crop((round(x0 * sw), round(y0 * sh), round(x1 * sw), round(y1 * sh)))
    s = min(1080 / cw, 900 / ch)
    ci = crop.resize((max(1, round(cw * s)), max(1, round(ch * s))), Image.LANCZOS)
    W, H = 1080, 1350
    card = Image.new("RGB", (W, H), annotate.PAPER)
    ox, oy = (W - ci.size[0]) // 2, (900 - ci.size[1]) // 2
    card.paste(ci, (ox, oy))
    dr = ImageDraw.Draw(card)
    to = lambda p: (ox + (p[0] - x0) * sw * s, oy + (p[1] - y0) * sh * s)
    fb56, fb64, f40 = annotate.font(56, True), annotate.font(64, True), annotate.font(40)
    for m in on:
        p0, p1 = to(m["p0"]), to(m["p1"])
        _arrow(dr, p0, p1, BLUE, 10, 44, both=True)
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        _disk(dr, mid, 40, m["label"], BLUE, fb56)
    y = 920
    for m in ms:
        tool = m.get("tool", "calipers"); pr = m.get("precision_mm", 0.5)
        for line in _wrap(dr, f"{m['label']}  {m['what']} · {tool} · ±{pr:g} mm", f40, W - 60):
            dr.text((30, y), line, font=f40, fill=annotate.INK); y += 48
        nc = m.get("no_calipers")
        if nc == "strip":
            t = f"no calipers: wrap a paper strip, reply {m['label']} c<length>"
        elif nc == "profile":
            t = "no calipers: press foil or cardboard on it, cut the outline, photograph it on the photofit mat"
        else:
            t = None
        if t:
            for line in _wrap(dr, t, f40, W - 60):
                dr.text((30, y), line, font=f40, fill=(90, 90, 100)); y += 48
        y += 8
    prior = (a.get("interface") or {}).get("prior_mm") or {}
    reply = "Reply: " + " ".join(f"{m['label']} {prior.get(m['label'], '<mm>'):g}" if isinstance(prior.get(m["label"]), (int, float)) else f"{m['label']} <mm>" for m in ms)
    for line in _wrap(dr, reply, fb56, W - 60):
        dr.text((30, y + 4), line, font=fb56, fill=BLUE); y += 66
    if y > H:
        raise Stop("the Measuring Card text does not fit: shorten the measure entries in analysis.json")
    out = os.path.join(d, "measure_card.png")
    card.save(out)
    emit(True, 0, file=out, size=list(card.size), labels=[m["label"] for m in ms])


def sub_numbers(args):
    pos, confirm, prof = [], False, None
    i = 0
    while i < len(args):
        if args[i] == "--confirm":
            confirm = True
        elif args[i] == "--profile":
            prof = args[i + 1] if i + 1 < len(args) else None; i += 1
        else:
            pos.append(args[i])
        i += 1
    if not pos or (len(pos) < 2 and not prof):
        raise Stop('usage: forge mount numbers <name> "<reply>" [--profile outline.json] [--confirm]')
    name = pos[0]; a = load(name); d = ddir(name)
    validate(a, ("measure",))
    labels = [m["label"] for m in a["measure"]]
    nums = {}
    if prof:
        try:
            size = json.load(open(prof))["size_mm"]
        except Exception:
            raise Stop("that outline file has no size_mm: run `forge photofit <photo> --no-bin` first")
        for lab, v in zip(labels, size):
            nums[lab] = {"mm": round(float(v), 2), "note": "photofit outline", "source": "photofit"}
    else:
        try:
            parsed = parse_numbers(pos[1], labels)
        except ValueError as e:
            raise Stop(str(e))
        nums = {k: dict(v, source="user") for k, v in parsed.items()}
    flags = [] if confirm else typo_check(a, nums, design_dir=d)
    if flags:
        a["flags"] = flags; save(name, a)
        raise Stop(flags[0], flags=flags)
    a.setdefault("numbers", {}).update({k: {kk: vv for kk, vv in v.items() if vv != ""} for k, v in nums.items()})
    a["flags"] = []
    save(name, a)
    emit(True, 0, numbers=a["numbers"])


def _out_comb(d):
    c = os.path.join(d, "comb"); os.makedirs(c, exist_ok=True)
    return c


def do_comb(name, a, label, centre):
    import mountgen as M, verify_lib as V, spec_lib
    d = ddir(name)
    if a.get("style") == "strap" or a.get("style") == "screw":
        raise Stop("nothing to test, a strap adjusts" if a.get("style") == "strap" else "nothing to test: a screw plate has no size to fit")
    c = _out_comb(d)
    shape, checks, teeth = M.comb(a, label, centre)
    stl = os.path.join(c, "comb.stl")
    M.export(shape, stl)
    spec = {"components": 1, "min_wall_mm": 0.55, "volume_mm3": [0, 6000 * max(1.0, (centre / 32.0) ** 2)], "height_mm": [7.5, 9.0],
            "fit": {f"{label} centre of the comb": {"mm": centre, "source": ((a.get("numbers") or {}).get(label) or {}).get("source", "ASSUMED")}},
            "checks": {n: {k: p} for (n, k, p) in checks}}
    json.dump(spec, open(os.path.join(c, "spec.json"), "w"), indent=1)
    res = V.verify(stl, spec, spec_dir=c)
    res["name"] = "comb"
    json.dump(res, open(os.path.join(c, "verify.json"), "w"), indent=1, default=str)
    mt = {"style": "fit comb", "range_text": "Fit comb: teeth " + " / ".join(f"{v:g}" for _, v in teeth) + " mm", "range_mm": [teeth[0][1], teeth[-1][1]],
          "hardware": "", "pieces": [{"name": "comb", "role": "test"}], "print_pose": "Flat, supports off."}
    json.dump(mt, open(os.path.join(c, "mount.json"), "w"), indent=1)
    a["comb"] = {"label": label, "center": centre, "teeth": [{"tooth": t, "mm": v} for t, v in teeth], "date": str(datetime.date.today())}
    a["mode"] = "test"
    save(name, a)
    return res, c


def sub_comb(args):
    if not args:
        raise Stop("usage: forge mount comb <name> [--center A=31]")
    name = args[0]; a = load(name)
    validate(a, ("payload", "interface.section", "style", "measure"))
    label = a["measure"][0]["label"]; centre = None
    for j, x in enumerate(args):
        if x == "--center" and j + 1 < len(args):
            m = re.fullmatch(r"([A-Ca-c])=(\d+(?:\.\d+)?)", args[j + 1])
            if not m:
                raise Stop("--center needs a value like A=31")
            label, centre = m.group(1).upper(), float(m.group(2))
    if centre is None:
        n = (a.get("numbers") or {}).get(label)
        centre = float(n["mm"]) if n else (a["interface"].get("prior_mm") or {}).get(label)
        if centre is None:
            raise Stop(f"I need a number for {label} first (`forge mount numbers`) or --center {label}=<mm>")
    res, c = do_comb(name, a, label, float(centre))
    emit(res["status"] != "FAIL", 1 if res["status"] == "FAIL" else 0, dir=c, stl=os.path.join(c, "comb.stl"), teeth=a["comb"]["teeth"],
         checks=f"{res['summary']['green']} of {res['summary']['total']} green",
         tell="Print it with supports OFF. Push each tooth onto the part and tell me which one clicks.")


def sub_result(args):
    if len(args) < 2:
        raise Stop('usage: forge mount result <name> "<reply>"')
    name, text = args[0], " ".join(args[1:])
    a = load(name)
    cb = a.get("comb")
    if not cb:
        raise Stop("there is no comb for this design yet: run `forge mount comb` first")
    try:
        kind, v = apply_result(float(cb["center"]), text)
    except ValueError as e:
        raise Stop(str(e))
    lab = cb["label"]
    if kind == "measured":
        a.setdefault("numbers", {})[lab] = {"mm": round(v, 3), "source": "measured", "note": f"fit comb {datetime.date.today()}"}
        a["flags"] = []
        save(name, a)
        emit(True, 0, label=lab, mm=round(v, 3), source="measured", say=f"{v:g} mm it is, measured.")
    a.setdefault("numbers", {})[lab] = {"mm": round(v, 3), "source": "user", "note": "re-centred after the comb"}
    save(name, a)
    res, c = do_comb(name, a, lab, float(v))
    emit(True, 0, label=lab, new_center=round(v, 3), dir=c, stl=os.path.join(c, "comb.stl"), say=f"New comb centred on {v:g} mm: print it and tell me which tooth clicks.")


def plate_stl(pieces, path):
    import mountgen as M
    from build123d import Compound
    M.export(Compound([p["plate"] for p in pieces]), path)


def sub_build(args):
    if not args:
        raise Stop("usage: forge mount build <name>")
    name = args[0]; a = load(name); d = ddir(name)
    validate(a, ("payload", "interface.section", "style", "measure"))
    import mountgen as M, verify_lib as V, spec_lib, printer
    try:
        r = M.build(a, bed_x=float(printer.bed()[0]))
    except ValueError as e:
        raise Stop(str(e))
    pieces, mount = r["pieces"], r["mount"]
    pd = os.path.join(d, "pieces"); os.makedirs(pd, exist_ok=True)
    for f in os.listdir(pd):
        os.remove(os.path.join(pd, f))
    for p in pieces:
        M.export(p["plate"], os.path.join(pd, p["name"] + ".stl"))
    from build123d import Compound, Pos, Cylinder, Rot
    asm = [p["solid"] if p["asm"] is None else p["asm"] * p["solid"] for p in pieces]
    M.export(Compound(asm), os.path.join(d, "assembled.stl"))
    stl = os.path.join(d, name + ".stl")
    plate_stl(pieces, stl)
    # ---- spec.json
    fit = {}
    srcs = {"A": ((a.get("numbers") or {}).get("A") or {}).get("source")}
    meas = {m["label"]: m for m in a["measure"]}
    for k, v in r["fit"].items():
        e = {"mm": round(v["mm"], 3), "source": v["source"]}
        if v["source"] == "ASSUMED":
            lab = k[-1] if k[-1] in "ABC" else "A"
            e["fix"] = f"ask one question: {meas.get(lab, {}).get('what', 'the size')}? (reply like {lab} {v['mm']:g})"
        fit[k] = e
    pay = a["payload"]
    for key, label in (("body_d", "payload body diameter"), ("base_d", "payload base diameter"), ("height", "payload height")):
        if pay.get(key):
            fit[label] = {"mm": pay[key], "source": "datasheet" if pay.get("source", "datasheet") not in spec_lib.SOURCES else pay.get("source"),
                          "ref": pay.get("ref") or pay.get("object_id")}
    checks = {}
    for p in pieces:
        for (cn, kind, pt) in p["checks"]:
            q = [round(pt[0] + p["offset"][0], 3), round(pt[1] + p["offset"][1], 3), round(pt[2] + p["offset"][2], 3)]
            checks[cn if cn not in checks else f"{cn} ({p['name']})"] = {kind: q}
    if r["dummy"]:
        from build123d import Cylinder
        dm = r["dummy"]
        lower = next(p for p in pieces if p["name"] == "clamp_lower")
        dummy = Rot(90, 0, 0) * Cylinder(dm["d"] / 2.0, dm["length"])
        M.export(dummy, os.path.join(d, "dummy_dlo.stl"))
        checks["a D_lo tube fits the lower half"] = {"fits": "dummy_dlo.stl", "clearance": 0.0, "touch_ok": True,
                                                    "move": [round(lower["offset"][0], 3), round(lower["offset"][1], 3), round(lower["offset"][2], 3)]}
    spec = {"components": len(pieces), "min_wall_mm": mount.get("min_wall_mm", 2.0), "fit": fit, "checks": checks}
    mount.pop("min_wall_mm", None)
    json.dump(spec, open(os.path.join(d, "spec.json"), "w"), indent=1)
    json.dump(mount, open(os.path.join(d, "mount.json"), "w"), indent=1)
    res = V.verify(stl, spec, spec_dir=d)
    V.plain_rows(res["checks"], spec)
    res["name"] = name
    res["summary"] = {"green": sum(1 for x in res["checks"] if x["status"] == "PASS"), "total": len(res["checks"]),
                      "not_green": [x["plain"] for x in res["checks"] if x["status"] != "PASS"]}
    json.dump(res, open(os.path.join(d, "verify.json"), "w"), indent=1, default=str)
    bad = res["status"] == "FAIL" or not mount["load"]["ok"]
    why = [x["plain"] for x in res["checks"] if x["status"] == "FAIL"] + ([] if mount["load"]["ok"] else
          [f"the arm is overloaded: {mount['load']['sigma_mpa']} MPa against {mount['load']['allow_mpa']} allowed"])
    emit(not bad, 1 if bad else 0, stl=stl, status=res["status"], checks=f"{res['summary']['green']} of {res['summary']['total']} green",
         range=mount["range_text"], hardware=mount["hardware"], load=mount["load"], failing=why,
         assumed=[k for k, v in fit.items() if v["source"] == "ASSUMED"])


SUBS = {"init": sub_init, "product": sub_product, "card": sub_card, "measure-card": sub_measure_card, "numbers": sub_numbers,
        "comb": sub_comb, "result": sub_result, "build": sub_build}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); sys.exit(0)
    if argv[0] not in SUBS:
        print(f"forge mount: unknown step '{argv[0]}'. Steps: {', '.join(SUBS)}")
        emit(False, 2, error="unknown step")
    try:
        SUBS[argv[0]](argv[1:])
    except Stop as e:
        print(e.msg)
        emit(False, e.code, error=e.msg, **e.extra)


if __name__ == "__main__":
    main()
