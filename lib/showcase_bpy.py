"""Blender: animate a MechKit/flexify mechanism (mech.json + parts/) or turntable a single STL -> PNG frames.
Run via bin/blender_py. args after '--':
   <mech_dir_or_stl> <frames_dir> [--frames 72] [--w 720] [--h 540] [--motion NAME] [--turntable]
The motion replayed is EXACTLY the one the self-test swept (same Move list), so the video = the verified motion.
Look: warm paper background (neutral studio style), matte PLA, soft key + rim light."""
import bpy, sys, os, json, math, glob
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--") + 1:]
src, outdir = argv[0], argv[1]
def opt(k, d):
    return type(d)(argv[argv.index(k) + 1]) if k in argv else d
FR, W, H = opt("--frames", 72), opt("--w", 720), opt("--h", 540)
MOTION = opt("--motion", "")
TURN = "--turntable" in argv
os.makedirs(outdir, exist_ok=True)

PALETTE = [(0.82, 0.80, 0.76), (0.95, 0.47, 0.12), (0.18, 0.42, 0.85), (0.20, 0.62, 0.32), (0.55, 0.30, 0.75),
           (0.95, 0.78, 0.15), (0.85, 0.20, 0.20), (0.95, 0.55, 0.70), (0.35, 0.75, 0.80)]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = False
world = bpy.data.worlds.new("paper"); sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.93, 0.89, 0.80, 1); bg.inputs[1].default_value = 0.55
try:
    sc.view_settings.view_transform = "Standard"
except Exception:
    pass


def mat(rgb, name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*rgb, 1); p.inputs["Roughness"].default_value = 0.55
    return m


def load(path, rgb, name):
    bpy.ops.wm.stl_import(filepath=path)
    o = bpy.context.selected_objects[0]; o.name = name
    o.data.materials.clear(); o.data.materials.append(mat(rgb, name + "_m"))
    for poly in o.data.polygons:
        poly.use_smooth = False
    return o


objs, spec = {}, None
if os.path.isdir(src):
    spec = json.load(open(os.path.join(src, "mech.json")))
    for i, name in enumerate(spec["parts"]):
        rgb = PALETTE[0] if name in spec.get("fixed", []) else PALETTE[1 + (i % (len(PALETTE) - 1))]
        objs[name] = load(os.path.join(src, "parts", name + ".stl"), rgb, name)
else:
    objs["model"] = load(src, PALETTE[0], "model")
    TURN = True

# ---- floor (shadow catcher look: same paper colour, slightly darker)
allpts = [o.matrix_world @ Vector(c) for o in objs.values() for c in o.bound_box]
mn = Vector((min(p.x for p in allpts), min(p.y for p in allpts), min(p.z for p in allpts)))
mx = Vector((max(p.x for p in allpts), max(p.y for p in allpts), max(p.z for p in allpts)))
ctr = (mn + mx) / 2; size = max((mx - mn).length, 1.0)
bpy.ops.mesh.primitive_plane_add(size=size * 12, location=(ctr.x, ctr.y, mn.z - 0.01))
fl = bpy.context.object; fl.data.materials.append(mat((0.86, 0.82, 0.74), "floor"))

# ---- lights
def light(kind, loc, energy, size_):
    d = bpy.data.lights.new(kind + str(loc), kind); d.energy = energy
    if kind == "AREA":
        d.size = size_
    o = bpy.data.objects.new(d.name, d); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (ctr - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o
light("AREA", ctr + Vector((-size, -size * 1.2, size * 1.6)), 900 * (size / 60) ** 2, size * 1.2)
light("AREA", ctr + Vector((size * 1.3, size * 0.8, size * 0.9)), 350 * (size / 60) ** 2, size)
light("SUN", ctr + Vector((0, 0, size * 3)), 1.2, 0)

# ---- camera
cd = bpy.data.cameras.new("cam"); cd.lens = 55
cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); sc.camera = cam
dist = size * 2.1
def place_cam(az):
    d = Vector((math.cos(az), math.sin(az), 0.75)).normalized()
    cam.location = ctr + d * dist
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()

# ---- motion evaluation (mirrors mechkit.core.apply_move)
base = {k: o.matrix_world.copy() for k, o in objs.items()}

def M_rot(axis, pivot, deg):
    a = Vector(axis).normalized(); p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, a) @ Matrix.Translation(-p)

def pose_mech(t):
    """t in [0,1] -> drive along the motion, there-and-back (ping-pong) so loops are seamless."""
    if spec.get("type") == "chain":
        chain = spec["meta"]["chain"]; parts = spec["parts"]
        mats = {k: Matrix.Identity(4) for k in parts}
        for j in reversed(range(len(chain))):
            th = chain[j]["theta_m"] * math.sin(2 * math.pi * t + j * 0.9)
            R = M_rot((0, 0, 1), chain[j]["pivot"], th)
            for k in parts[j + 1:]:
                mats[k] = R @ mats[k]
        for k in parts:
            objs[k].matrix_world = mats[k] @ base[k]
        return
    mo = next((m for m in spec["motions"] if m["name"] == MOTION), spec["motions"][-1] if spec["motions"] else None)
    if mo is None:
        return
    s = 0.5 - 0.5 * math.cos(2 * math.pi * t)                     # ease 0 -> 1 -> 0
    d = mo["drive"][0] + (mo["drive"][1] - mo["drive"][0]) * s
    mats = {k: Matrix.Identity(4) for k in objs}
    for mv in mo["moves"]:
        v = d * mv.get("ratio", 1.0)
        if mv["type"] == "rot":
            T = M_rot(mv["axis"], mv["pivot"], v)
        elif mv["type"] == "trans":
            T = Matrix.Translation(Vector(mv["axis"]).normalized() * v)
        else:
            T = Matrix.Translation(Vector(mv["axis"]).normalized() * v) @ M_rot(mv["axis"], mv["pivot"], v * mv.get("rate", 0))
        mats[mv["part"]] = T @ mats[mv["part"]]
    for k in objs:
        objs[k].matrix_world = mats[k] @ base[k]

# frame the WHOLE motion (handles swing far outside the closed pose's bbox)
if spec and not TURN:
    pts = []
    for k in range(12):
        pose_mech(k / 12)
        pts += [o.matrix_world @ Vector(c) for o in objs.values() for c in o.bound_box]
    pose_mech(0.0)
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2; size = max((mx - mn).length, 1.0); dist = size * 1.15

for f in range(FR):
    t = f / FR
    if spec and not TURN:
        pose_mech(t); place_cam(math.radians(-55) + 0.35 * math.sin(2 * math.pi * t))
    else:
        place_cam(math.radians(-55) + 2 * math.pi * t)
    sc.render.filepath = os.path.join(outdir, f"f{f:03d}.png")
    bpy.ops.render.render(write_still=True)
print("frames ->", outdir)
