#!/usr/bin/env python3
"""showcase: video + GIF + listing kit for any model or mechanism (needs Blender).

    forge showcase out/gyro            # mechanism folder (mech.json + parts/): plays the VERIFIED motion
    forge showcase model.stl           # single model: turntable
    options: --frames 72 --w 720 --h 540 --motion NAME --turntable --price-per-kg 20
    studio look (Cycles, needs Blender): --style studio|paper  --accent PART[,PART]  --ghost PART  --section x|y|z=VAL  --explode
             --still hero|cutaway|exploded  (one product still -> <name>_<still>.png instead of a video)  --samples 256  --elev 28  --az 35
    --annotate : burn INPUT / OUTPUT angle, ratio and (if ratio.json exists) measured ratio + backlash into every frame of the video/GIF
Writes <name>_showcase.mp4 (phone/Instagram), <name>_showcase.gif (web/Discord), poster.png and listing.md:
title, 3-line description, print recipe, time/grams from your slicer hook (if configured), filament cost, and a suggested price
(shop brain: covers filament + machine time + failures, rounded to a .99 ending) + license reminder.
"""
import argparse, glob, json, math, os, subprocess, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import printer

HERE = os.path.dirname(os.path.abspath(__file__))
FORGE = os.path.dirname(HERE)


def _fit_tag():
    sys.path.insert(0, HERE)
    import fit
    return fit.tag("pip_gap")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def slice_stats(stl, supports="auto"):
    return printer.slice_stats(stl, supports)


def hours(tstr):
    h = 0.0
    for part in (tstr or "").replace("d", "d ").split():
        if part.endswith("d"): h += 24 * float(part[:-1])
        elif part.endswith("h"): h += float(part[:-1])
        elif part.endswith("m"): h += float(part[:-1]) / 60
        elif part.endswith("s"): h += float(part[:-1]) / 3600
    return h


def price(grams, hrs, per_kg=20.0):
    filament = grams / 1000 * per_kg
    machine = hrs * 0.35                       # electricity + wear, $/h (~0.1 kWh/h + nozzle/bed wear)
    cost = (filament + machine) * 1.25         # 25% failure/waste buffer
    suggested = max(3.99, math.ceil(cost * 3.0) - 0.01)   # 3x cost is the usual small-shop floor
    return round(filament, 2), round(cost, 2), suggested


def annotate_frames(frames_dir, pngs, spec, a, outdir):
    """--annotate: burn INPUT / OUTPUT angle + ratio (+ measured ratio and backlash from ratio.json) into every frame, top-left.
    Values come from mech.json (the same Moves the render replays) so frame 0 reads INPUT 0 and the last INPUT = the drive end."""
    from PIL import Image, ImageDraw
    import annotate as ann
    if not spec:
        sys.exit("--annotate needs a mechanism folder (mech.json)")
    mo = next((m for m in spec["motions"] if m["name"] == a.motion), spec["motions"][-1])
    drv = next((mv for mv in mo["moves"] if mv["type"] == "rot" and abs(mv.get("ratio", 1.0) - 1.0) < 1e-9), mo["moves"][0])
    out_mv = [mv for mv in mo["moves"] if mv["part"] == (spec["meta"].get("output") or "carrier") and mv["type"] == "rot"] or \
             [mv for mv in mo["moves"] if mv["type"] == "rot" and mv is not drv][-1:]
    out_ratio = sum(mv.get("ratio", 1.0) for mv in out_mv)
    meta = spec.get("meta", {})
    declared = meta.get("ratio")
    rj = os.path.join(outdir, "ratio.json")
    rat = json.load(open(rj)) if os.path.exists(rj) else None
    n = len(pngs); log = []
    for f, p in enumerate(pngs):
        t = f / (n - 1) if (a.style == "studio" and n > 1) else (0.5 - 0.5 * math.cos(2 * math.pi * f / n))
        d = mo["drive"][0] + (mo["drive"][1] - mo["drive"][0]) * t
        lines = [f"INPUT {d:.0f} deg", f"OUTPUT {d * out_ratio + 0.0:+.1f} deg"]
        if declared: lines.append(f"RATIO {declared}:1" + (f"  measured {abs(rat['measured']):.2f}:1" if rat else ""))
        if rat: lines.append(f"BACKLASH {rat['backlash_deg']:.1f} deg")
        img = Image.open(p).convert("RGBA")
        sz = max(14, round(30 * img.width / 720))
        fnt = ann.font(sz, True)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
        wmax = max(dr.textlength(l, font=fnt) for l in lines); lh = int(sz * 1.25); pad = int(sz * 0.4)
        box = (pad, pad, pad + wmax + 2 * pad, pad + lh * len(lines) + pad)
        dr.rounded_rectangle(box, radius=int(sz * 0.35), fill=(0, 0, 0, 153))
        for i, l in enumerate(lines):
            dr.text((box[0] + pad, box[1] + pad // 2 + i * lh), l, font=fnt, fill=(255, 255, 255, 217))
        Image.alpha_composite(img, lay).convert("RGB").save(p)
        log.append({"frame": f, "lines": lines, "input_deg": round(d, 3), "output_deg": round(d * out_ratio, 3)})
    json.dump(log, open(os.path.join(outdir, "annotate.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--w", type=int, default=720); ap.add_argument("--h", type=int, default=540)
    ap.add_argument("--motion", default=""); ap.add_argument("--turntable", action="store_true")
    ap.add_argument("--price-per-kg", type=float, default=20.0); ap.add_argument("--no-slice", action="store_true")
    ap.add_argument("--style", default="paper", choices=["paper", "studio"]); ap.add_argument("--accent", default="")
    ap.add_argument("--ghost", default=""); ap.add_argument("--section", default=""); ap.add_argument("--explode", action="store_true")
    ap.add_argument("--still", default="", choices=["", "hero", "cutaway", "exploded"]); ap.add_argument("--samples", type=int, default=0)
    ap.add_argument("--elev", type=float, default=0.0); ap.add_argument("--az", type=float, default=0.0)
    ap.add_argument("--expo", type=float, default=1.0); ap.add_argument("--annotate", action="store_true")
    ap.add_argument("--gif-width", type=int, default=480)
    ap.add_argument("--fill", type=float, default=0.0); ap.add_argument("--yshift", type=float, default=0.0)
    a = ap.parse_args()
    src = os.path.abspath(a.src)
    if os.path.isdir(src):
        spec = json.load(open(os.path.join(src, "mech.json")))
        name = spec["name"]; outdir = src
        stl = os.path.join(src, f"{name}.stl")
    else:
        spec = None; name = os.path.splitext(os.path.basename(src))[0]; outdir = os.path.dirname(src); stl = src
    frames = os.path.join(outdir, "showcase_frames")
    shutil.rmtree(frames, ignore_errors=True)
    cmd = [os.path.join(FORGE, "bin", "blender_py"), os.path.join(HERE, "showcase_bpy.py"), src, frames,
           "--frames", str(a.frames), "--w", str(a.w), "--h", str(a.h)]
    if a.motion: cmd += ["--motion", a.motion]
    if a.turntable: cmd += ["--turntable"]
    if a.style == "studio":
        cmd += ["--style", "studio", "--samples", str(a.samples or (256 if a.still else 48)), "--expo", str(a.expo)]
        if a.accent: cmd += ["--accent", a.accent]
        if a.ghost: cmd += ["--ghost", a.ghost]
        if a.explode: cmd += ["--explode"]
        if a.elev: cmd += ["--elev", str(a.elev)]
        if a.az: cmd += ["--az", str(a.az)]
        fill, ysh = a.fill, a.yshift
        if a.annotate and not a.still and not fill:
            fill, ysh = 0.56, -0.10                        # leave the top-left of the frame to the overlay
        if fill: cmd += ["--fill", str(fill)]
        if ysh: cmd += ["--yshift", str(ysh)]
    if a.still:
        sec = a.section or ("y=0" if a.still == "cutaway" else "")   # y=0 passes through housing pins, carrier pins and the cam offset
        out_png = os.path.join(outdir, f"{name}_{a.still}.png")
        if a.style != "studio": sys.exit("--still needs --style studio")
        if sec: cmd += ["--section", sec]
        if a.still == "exploded" and "--explode" not in cmd: cmd += ["--explode"]
        if a.still == "cutaway" and not a.az and sec.startswith("y"): cmd += ["--az", "68"]    # look square at a y-cut face
        cmd += ["--still", a.still, "--out-file", out_png]
        if a.w == 720 and a.h == 540:      # default frame is the video size; stills are product-sheet size
            i = cmd.index("--w"); cmd[i + 1] = "2000" if a.still == "hero" else "1600"
            i = cmd.index("--h"); cmd[i + 1] = "1500" if a.still == "hero" else "1200"
        r = run(cmd, timeout=7200)
        if not os.path.exists(out_png):
            sys.exit("render failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
        print(json.dumps({"still": out_png, "style": "studio", "section": sec or None}))
        return
    if a.section: cmd += ["--section", a.section]
    r = run(cmd, timeout=7200)
    pngs = sorted(glob.glob(os.path.join(frames, "f*.png")))
    if not pngs:
        sys.exit("render failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    if a.annotate:
        annotate_frames(frames, pngs, spec, a, outdir)
    mp4 = os.path.join(outdir, f"{name}_showcase.mp4"); gif = os.path.join(outdir, f"{name}_showcase.gif")
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", os.path.join(frames, "f%03d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4])
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", os.path.join(frames, "f%03d.png"),
         "-vf", f"fps=16,scale={a.gif_width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer",
         gif])
    shutil.copy(pngs[len(pngs) // 4], os.path.join(outdir, "poster.png"))
    t, g = (None, None) if a.no_slice else slice_stats(stl, "off" if spec else "auto")
    lines = [f"# {name} — listing kit", ""]
    if spec:
        meta = spec.get("meta", {})
        lines += [f"**What it does:** {'; '.join(m.get('note', m['name']) for m in spec.get('motions', []))}",
                  f"**Print-in-place:** comes off the bed moving. Gap {meta.get('gap', '?')} mm "
                  + ("(calibrated on this printer by the Fit Card)." if _fit_tag() == "[V]"
                     else "(research default: print the Fit Card to calibrate before selling).")]
    if t:
        hrs = hours(t); fil, cost, sug = price(g, hrs, a.price_per_kg)
        lines += ["", f"**Print:** {t}, {g} g PLA (your slicer profile, no tuning)",
                  f"**Cost:** filament ${fil} · all-in ~${cost} (filament + machine time + 25% fail buffer)",
                  f"**Suggested price:** ${sug}  (3x cost small-shop floor; fidgets at fairs often go $5-12)"]
    lines += ["", "**License check before selling:** your own MechKit/sculpt designs are yours. Printables downloads: "
              "check the license (CC BY-NC = no selling). Text->3D figures: Hunyuan3D community license (personal use OK).",
              "", f"Video: {os.path.basename(mp4)} · GIF: {os.path.basename(gif)} · poster.png"]
    open(os.path.join(outdir, "listing.md"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"mp4": mp4, "gif": gif, "poster": os.path.join(outdir, "poster.png"),
                      "listing": os.path.join(outdir, "listing.md"), "frames": len(pngs), "print": t, "grams": g}))


if __name__ == "__main__":
    main()
