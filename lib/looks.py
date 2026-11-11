#!/usr/bin/env python3
"""looks: does it LOOK like the thing? Automatic recognizability score (CLIP zero-shot on renders). venv: .venv-ai

    forge looks <render_dir_or_png...> --target "butterfly knife" [--refs ref1.png ref2.png] [--extra "a comb,a ruler"]
<render_dir> = a folder with views/*.png from `forge render` (iso, front, side, oblique...).
Score = mean probability (over views) that CLIP picks the TARGET out of a line-up of decoys (puck, box, egg, rock,
stick, blob, plate, bar...). It's "would a stranger name this object at a glance?" as a number:
   >= 60%  reads clearly     30-60%  so-so     < 30%  doesn't read (iterate the FORM: proportions, signature features)
--refs: also report CLIP image similarity to reference images (e.g. tiles from a model-site contact sheet).
Validated on the 2026-10-17 bench pairs (human > v2 > v1 balisong; real helmet >> egg helmet): see the skill.
"""
import argparse, glob, json, os, sys
import torch
from PIL import Image

DECOYS = ["a hockey puck", "a plain box", "an egg", "a rock", "a stick", "a blob of clay", "a flat plate", "a metal bar",
          "a cylinder", "a brick", "a bowl", "a vase", "a pebble", "a lump", "a block of wood"]
PROMPT = "a 3D printed {}, grey plastic render"


def clean_renders(stl, n=6):
    """photo-like turntable frames (matte PLA on warm paper) -- CLIP reads these far better than annotated CAD views."""
    import subprocess, tempfile
    forge = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(tempfile.gettempdir(), "looks_" + os.path.splitext(os.path.basename(stl))[0])
    subprocess.run([os.path.join(forge, "bin", "blender_py"), os.path.join(forge, "lib", "showcase_bpy.py"), os.path.abspath(stl),
                    out, "--frames", str(n), "--w", "512", "--h", "512", "--turntable"], capture_output=True, timeout=1800)
    return sorted(glob.glob(os.path.join(out, "f*.png")))


def load_views(paths):
    files = []
    for p in paths:
        if p.lower().endswith((".stl", ".3mf", ".obj")):
            files += clean_renders(p)
            continue
        if os.path.isdir(p):
            v = os.path.join(p, "views")
            files += sorted(glob.glob(os.path.join(v if os.path.isdir(v) else p, "*.png")))
        else:
            files.append(p)
    files = [f for f in files if not os.path.basename(f).startswith(("raw_", "sec"))]
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+"); ap.add_argument("--target", required=True)
    ap.add_argument("--refs", nargs="*", default=[]); ap.add_argument("--extra", default="")
    ap.add_argument("--json")
    a = ap.parse_args()
    from transformers import CLIPModel, CLIPProcessor
    m = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    files = load_views(a.inputs)
    if not files:
        sys.exit("no images found")
    ims = [Image.open(f).convert("RGB") for f in files]
    labels = [a.target] + DECOYS + [e.strip() for e in a.extra.split(",") if e.strip()]
    texts = [PROMPT.format(l) for l in labels]
    with torch.no_grad():
        inp = proc(text=texts, images=ims, return_tensors="pt", padding=True)
        out = m(**inp)
        probs = out.logits_per_image.softmax(-1)          # (views, labels)
        img_emb = out.image_embeds
    per_view = probs[:, 0].tolist()
    score = float(sum(per_view) / len(per_view))
    top = [labels[int(i)] for i in probs.argmax(-1)]
    res = {"target": a.target, "recognizability": round(100 * score, 1), "views": len(files),
           "per_view": {os.path.basename(f): round(100 * p, 1) for f, p in zip(files, per_view)},
           "clip_thinks_it_is": {os.path.basename(f): t for f, t in zip(files, top)}}
    if a.refs:
        rims = [Image.open(r).convert("RGB") for r in a.refs]
        with torch.no_grad():
            r_emb = m.get_image_features(**proc(images=rims, return_tensors="pt"))
            r_emb = r_emb / r_emb.norm(dim=-1, keepdim=True)
        sim = (img_emb @ r_emb.T)                          # image_embeds are already normalised
        res["ref_similarity"] = round(float(sim.max(dim=1).values.mean()), 3)
    v = res["recognizability"]
    res["verdict"] = "reads clearly" if v >= 60 else ("so-so" if v >= 30 else "doesn't read -> iterate the FORM")
    print(json.dumps(res, indent=1))
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
