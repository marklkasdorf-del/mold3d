"""concept.py: words -> best 3D-friendly concept image (RGBA, background removed). 100% local, free.

    venv/bin/python concept.py "<subject>" OUTDIR [--n 4] [--view front|top] [--seed 1] [--steps 6]

LCM-Dreamshaper-v7 (MIT, 4-8 steps, ~2-4 s/image on Apple MPS) draws n candidates with a prompt engineered for
image->3D: ONE object, whole thing in frame, plain white background, soft even light, clay-toy render (no textures to
confuse the 3D model). Each candidate is cut out (rembg isnet-general-use) and scored:
   CLIP(text, image)  - does it look like what was asked?
   cut-out quality    - one clean blob, not touching the border, sensible fill.
Best one -> OUTDIR/concept.png (RGBA, square, padded). All candidates + scores kept in OUTDIR/candidates/.
"""
import argparse, json, os, sys, time
import numpy as np
import torch
from PIL import Image

STYLE = ("a single {s}, cute 3D printable figurine, full body, entire object in frame, centered, isolated on a plain "
         "white background, smooth matte clay render, soft even studio lighting, no shadow, simple solid shapes, "
         "toy design, high detail")
STYLE_TOP = ("top-down view of a single {s} lying flat, seen from directly above, full body, entire object in frame, "
             "centered, isolated on a plain white background, smooth matte clay render, soft even light, no shadow, toy design")


def dev():
    return "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"


def gen_images(prompt, n, seed, steps, size=768):
    from diffusers import DiffusionPipeline
    pipe = DiffusionPipeline.from_pretrained("SimianLuo/LCM_Dreamshaper_v7", safety_checker=None,
                                             requires_safety_checker=False, torch_dtype=torch.float32)
    pipe = pipe.to(dev())
    pipe.set_progress_bar_config(disable=True)
    ims = []
    for i in range(n):
        g = torch.Generator("cpu").manual_seed(seed + i)
        im = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=8.0, height=size, width=size,
                  generator=g, output_type="pil").images[0]
        ims.append(im)
    del pipe
    return ims


def cutout(im):
    from rembg import remove, new_session
    if not hasattr(cutout, "sess"):
        cutout.sess = new_session("isnet-general-use")
    return remove(im, session=cutout.sess)


def blob_score(rgba):
    a = np.array(rgba)[..., 3] > 128
    h, w = a.shape
    fill = a.mean()
    if fill < 0.02:
        return 0.0, {"fill": float(fill)}
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).mean()
    from scipy import ndimage
    lab, n = ndimage.label(a)
    sizes = ndimage.sum(a, lab, range(1, n + 1)) if n else [0]
    main = max(sizes) / max(1, a.sum())
    s = 1.0
    s *= 1.0 if 0.08 < fill < 0.55 else 0.5            # not a speck, not a wall
    s *= max(0.0, 1.0 - 6 * border)                    # touching the frame = cropped object
    s *= main ** 2                                      # one main blob
    return float(s), {"fill": round(float(fill), 3), "border": round(float(border), 3), "main_blob": round(float(main), 3)}


def clip_scores(text, ims):
    from transformers import CLIPModel, CLIPProcessor
    m = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    p = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    with torch.no_grad():
        inp = p(text=[text], images=ims, return_tensors="pt", padding=True)
        out = m(**inp)
        sims = (out.image_embeds @ out.text_embeds.T).squeeze(1)
    return [float(v) for v in sims]


def pad_square(rgba, pad=1.25):
    a = np.array(rgba); ys, xs = np.where(a[..., 3] > 128)
    if len(xs) == 0:
        return rgba
    rgba = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    w, h = rgba.size; s = int(max(w, h) * pad)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0)); out.paste(rgba, ((s - w) // 2, (s - h) // 2))
    return out.resize((768, 768), Image.LANCZOS) if s > 768 else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject"); ap.add_argument("out")
    ap.add_argument("--n", type=int, default=4); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=6); ap.add_argument("--view", default="front", choices=["front", "top"])
    ap.add_argument("--raw-prompt", action="store_true", help="use the subject text as the full prompt")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "candidates"), exist_ok=True)
    prompt = a.subject if a.raw_prompt else (STYLE_TOP if a.view == "top" else STYLE).format(s=a.subject)
    t = time.time()
    ims = gen_images(prompt, a.n, a.seed, a.steps)
    t_gen = time.time() - t
    cuts = [cutout(im) for im in ims]
    cl = clip_scores(f"a 3D figurine of a {a.subject}", ims)
    rows = []
    for i, (im, cu, c) in enumerate(zip(ims, cuts, cl)):
        b, info = blob_score(cu)
        score = c * (0.35 + 0.65 * b)
        im.save(os.path.join(a.out, "candidates", f"c{i}.png")); cu.save(os.path.join(a.out, "candidates", f"c{i}_cut.png"))
        rows.append({"i": i, "clip": round(c, 4), "blob": round(b, 3), **info, "score": round(score, 4)})
    best = max(rows, key=lambda r: r["score"])
    pad_square(cuts[best["i"]]).save(os.path.join(a.out, "concept.png"))
    ims[best["i"]].save(os.path.join(a.out, "concept_raw.png"))
    meta = {"subject": a.subject, "prompt": prompt, "view": a.view, "seed": a.seed, "steps": a.steps,
            "gen_seconds": round(t_gen, 1), "candidates": rows, "best": best["i"]}
    json.dump(meta, open(os.path.join(a.out, "concept.json"), "w"), indent=1)
    # contact sheet of candidates (best boxed) so a human can overrule the pick
    W = 256; sheet = Image.new("RGB", (W * len(ims), W + 26), (240, 236, 226))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        sheet.paste(im.resize((W, W)), (i * W, 26))
        d.text((i * W + 6, 6), f"#{i} clip {rows[i]['clip']:.3f} blob {rows[i]['blob']:.2f}" + ("  <- BEST" if i == best["i"] else ""),
               fill=(160, 30, 30) if i == best["i"] else (0, 0, 0))
    sheet.save(os.path.join(a.out, "candidates_sheet.png"))
    print(json.dumps({"best": best, "gen_seconds": round(t_gen, 1), "concept": os.path.join(a.out, "concept.png")}))


if __name__ == "__main__":
    main()
