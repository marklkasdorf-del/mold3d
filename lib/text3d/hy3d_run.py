"""hy3d_run.py out.glb front.png [left.png back.png]  (RGBA, bg removed). Hunyuan3D-2mv (multi-view) or 2mini/2 single view if only front.
env: HY_STEPS=50 HY_RES=256 HY_DTYPE=float16|float32 HY_DEVICE=cuda|mps|cpu"""
import sys, os, time, torch
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Hunyuan3D-2"))
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
out = sys.argv[1]; files = sys.argv[2:]
dev = os.environ.get("HY_DEVICE", "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
dt = getattr(torch, os.environ.get("HY_DTYPE", "float16"))
steps = int(os.environ.get("HY_STEPS", 50)); res = int(os.environ.get("HY_RES", 256))
names = ["front", "left", "back"]  # also accepts name=path args, e.g. front=a.png back=b.png
imgs = {}
for i, f in enumerate(files):
    n, _, path = f.partition("=") if "=" in f else (names[i], "", f)
    imgs[n] = Image.open(path).convert("RGBA")
t = time.time()
if len(imgs) > 1:
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2mv", subfolder="hunyuan3d-dit-v2-mv", variant="fp16", device=dev, dtype=dt)
    image = imgs
else:
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2mini", subfolder="hunyuan3d-dit-v2-mini", variant="fp16", device=dev, dtype=dt)
    image = imgs["front"]
print("loaded %.0fs" % (time.time() - t), flush=True)
t = time.time()
mesh = pipe(image=image, num_inference_steps=steps, octree_resolution=res, num_chunks=8000, generator=torch.manual_seed(7), output_type="trimesh")[0]
print("gen %.0fs" % (time.time() - t), len(mesh.vertices), flush=True)
mesh.export(out)
