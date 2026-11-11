#!/usr/bin/env python3
"""showcase: video + GIF + listing kit for any model or mechanism (needs Blender).

    forge showcase out/gyro            # mechanism folder (mech.json + parts/): plays the VERIFIED motion
    forge showcase model.stl           # single model: turntable
    options: --frames 72 --w 720 --h 540 --motion NAME --turntable --price-per-kg 20
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--w", type=int, default=720); ap.add_argument("--h", type=int, default=540)
    ap.add_argument("--motion", default=""); ap.add_argument("--turntable", action="store_true")
    ap.add_argument("--price-per-kg", type=float, default=20.0); ap.add_argument("--no-slice", action="store_true")
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
    r = run(cmd, timeout=7200)
    pngs = sorted(glob.glob(os.path.join(frames, "f*.png")))
    if not pngs:
        sys.exit("render failed:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    mp4 = os.path.join(outdir, f"{name}_showcase.mp4"); gif = os.path.join(outdir, f"{name}_showcase.gif")
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", os.path.join(frames, "f%03d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", mp4])
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", os.path.join(frames, "f%03d.png"),
         "-vf", "fps=16,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer",
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
