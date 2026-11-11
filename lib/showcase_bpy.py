"""Blender: animate a MechKit/flexify mechanism (mech.json + parts/) or turntable a single STL -> PNG frames.
Run via bin/blender_py. args after '--':
   <mech_dir_or_stl> <frames_dir> [--frames 72] [--w 720] [--h 540] [--motion NAME] [--turntable]
   studio mode: [--style studio] [--accent PART[,PART]] [--ghost PART] [--section x|y|z=VAL] [--explode]
                [--still hero|cutaway|exploded --out-file FILE] [--samples 256] [--elev DEG] [--az DEG]
The motion replayed is EXACTLY the one the self-test swept (same Move list), so the video = the verified motion.
Look (paper, default): warm paper background, matte PLA, soft key + rim light, Eevee.
Look (studio): Cycles + OIDN, AgX, dark field #15181d with a shadow-catcher floor, graphite PLA, orange accent part, 3-light rig
(key / fill / cool rim), 85 mm camera that fits the part to 70 % of the short side. Same look for every still of one piece."""
import bpy, sys, os, json, math, glob
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index("--") + 1:]
src, outdir = argv[0], argv[1]
def opt(k, d):
    return type(d)(argv[argv.index(k) + 1]) if k in argv else d
FR, W, H = opt("--frames", 72), opt("--w", 720), opt("--h", 540)
MOTION = opt("--motion", "")
TURN = "--turntable" in argv
STYLE = opt("--style", "paper")
STUDIO = STYLE == "studio"
ACCENT = [x for x in opt("--accent", "").split(",") if x]
GHOST = opt("--ghost", "")
SECTION = opt("--section", "")
EXPLODE = "--explode" in argv
STILL = opt("--still", "")
OUTFILE = opt("--out-file", "")
SAMPLES = opt("--samples", 256)
ELEV = opt("--elev", 28.0)
AZ = opt("--az", 35.0)
FILL = opt("--fill", 0.70)         # fraction of the short side the part fills
YSHIFT = opt("--yshift", 0.0)      # ndc: >0 moves the part up the frame, <0 down (room for the GIF overlay)
os.makedirs(outdir, exist_ok=True)

PALETTE = [(0.82, 0.80, 0.76), (0.95, 0.47, 0.12), (0.18, 0.42, 0.85), (0.20, 0.62, 0.32), (0.55, 0.30, 0.75),
           (0.95, 0.78, 0.15), (0.85, 0.20, 0.20), (0.95, 0.55, 0.70), (0.35, 0.75, 0.80)]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = False
world = bpy.data.worlds.new("paper"); sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")

# ------------------------------------------------------------------ engine / world
if STUDIO:
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = SAMPLES; cy.use_denoising = True
    try: cy.denoiser = "OPENIMAGEDENOISE"
    except Exception: pass
    cy.transparent_max_bounces = 24
    try:
        pr = bpy.context.preferences.addons["cycles"].preferences
        pr.compute_device_type = "METAL"; pr.get_devices()
        for d in pr.devices: d.use = d.type == "METAL"
        cy.device = "GPU"
    except Exception:
        pass                                  # no GPU: Cycles falls back to the CPU
    try:
        sc.view_settings.view_transform = "AgX"
        for lk in ("AgX - Medium High Contrast", "Medium High Contrast"):
            try: sc.view_settings.look = lk; break
            except Exception: continue
    except Exception:
        pass
    bg.inputs[0].default_value = (0.0066, 0.0082, 0.011, 1); bg.inputs[1].default_value = 1.0   # #15181d
else:
    sc.render.engine = "BLENDER_EEVEE"
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


def dirv(az, el):
    a, e_ = math.radians(az), math.radians(el)
    return Vector((math.cos(a) * math.cos(e_), math.sin(a) * math.cos(e_), math.sin(e_)))


def lin(h):
    """#rrggbb -> linear rgb"""
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c)


def studio_mat(kind, name, tint=0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    if kind == "graphite":
        p.inputs["Base Color"].default_value = (*lin("#2b2e33"), 1)
        p.inputs["Roughness"].default_value = 0.42; p.inputs["Specular IOR Level"].default_value = 0.5
        p.inputs["Coat Weight"].default_value = 0.15; p.inputs["Coat Roughness"].default_value = 0.25
    elif kind == "cap":                                    # cut faces: matte so the section reads flat
        g = "#%02x%02x%02x" % (0x38 + 0x0f * tint, 0x3c + 0x0f * tint, 0x43 + 0x0f * tint)      # each part's cut face a touch lighter than the last
        p.inputs["Base Color"].default_value = (*lin(g), 1); p.inputs["Roughness"].default_value = 0.8
    elif kind == "orange":
        p.inputs["Base Color"].default_value = (1.0, 0.16, 0.0, 1); p.inputs["Roughness"].default_value = 0.5
        p.inputs["Coat Weight"].default_value = 0.1; p.inputs["Coat Roughness"].default_value = 0.3
    elif kind == "orange_cap":
        p.inputs["Base Color"].default_value = (1.0, 0.16, 0.0, 1); p.inputs["Roughness"].default_value = 0.85
    elif kind == "ice":
        p.inputs["Base Color"].default_value = (*lin("#cfe6ff"), 1); p.inputs["Roughness"].default_value = 0.4
        p.inputs["Emission Color"].default_value = (*lin("#cfe6ff"), 1); p.inputs["Emission Strength"].default_value = 0.1
    elif kind == "ghost":
        p.inputs["Base Color"].default_value = (*lin("#4a5058"), 1); p.inputs["Roughness"].default_value = 0.7
        p.inputs["Alpha"].default_value = 0.12
        for attr, val in (("blend_method", "HASHED"), ("surface_render_method", "DITHERED")):
            try: setattr(m, attr, val)
            except Exception: pass
    elif kind == "axis":
        p.inputs["Base Color"].default_value = (0.8, 0.82, 0.85, 1); p.inputs["Roughness"].default_value = 0.5
        p.inputs["Emission Color"].default_value = (0.8, 0.82, 0.85, 1); p.inputs["Emission Strength"].default_value = 0.6
    return m


def load(path, rgb, name):
    bpy.ops.wm.stl_import(filepath=path)
    o = bpy.context.selected_objects[0]; o.name = name
    o.data.materials.clear()
    if STUDIO:
        for poly in o.data.polygons:
            poly.use_smooth = False
        try:
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32))
        except Exception:
            pass
    else:
        o.data.materials.append(mat(rgb, name + "_m"))
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

# ------------------------------------------------------------------ studio: materials, ice regions, section, ghost
def bbox_pts():
    return [o.matrix_world @ Vector(c) for o in objs.values() for c in o.bound_box]


def cut_part(o, ax, val, keep_low, cap_idx):
    """boolean-cut one part at axis=val; faces lying in the plane get material slot cap_idx. Same idea as render_views.py."""
    axi = "xyz".index(ax)
    big = 10000.0
    bpy.ops.mesh.primitive_cube_add(size=1)
    cut = bpy.context.object
    cut.scale = (big, big, big)
    loc = [0, 0, 0]; loc[axi] = val + (big / 2 if keep_low else -big / 2)
    cut.location = loc
    bpy.ops.object.transform_apply(location=True, scale=True)
    bpy.context.view_layer.objects.active = o
    for solver in ("MANIFOLD", "EXACT"):
        mod = o.modifiers.new("cut", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.object = cut; mod.solver = solver
        bpy.ops.object.modifier_apply(modifier="cut")
        if len(o.data.polygons) > 0:
            break
    bpy.data.objects.remove(cut, do_unlink=True)
    me = o.data
    n = 0
    for p in me.polygons:
        if all(abs(me.vertices[v].co[axi] - val) < 1e-3 for v in p.vertices):
            p.material_index = cap_idx; n += 1
    return n


if STUDIO:
    meta_ = (spec or {}).get("meta", {})
    accent = ACCENT or ([k for k, v in meta_.get("accent", {}).items() if v == "orange"] if spec else [])
    ices = [r for r in meta_.get("ice", [])] if spec else []
    for ti, (name, o) in enumerate(objs.items()):
        is_orange = name in accent
        o.data.materials.clear()
        o.data.materials.append(studio_mat("orange" if is_orange else "graphite", name + "_body"))   # slot 0
        o.data.materials.append(studio_mat("orange_cap" if is_orange else "cap", name + "_cap", ti))     # slot 1
        o.data.materials.append(studio_mat("ice", name + "_ice"))                                   # slot 2
        for r in ices:
            if r["part"] != name:
                continue
            x0, y0, z0, x1, y1, z1 = r["box"]
            for p in o.data.polygons:
                c = p.center
                if x0 <= c.x <= x1 and y0 <= c.y <= y1 and z0 <= c.z <= z1:
                    p.material_index = 2
    if SECTION:
        sa, sv = SECTION.lower().split("="); sv = float(sv)
        keep_low = dirv(AZ, ELEV)["xyz".index(sa)] > 0     # keep the half on the far side of the plane, so the cut face looks at the camera
        ncap = {n: cut_part(o, sa, sv, keep_low, 1) for n, o in objs.items()}
        print("section", SECTION, "cap faces", ncap)
    if GHOST:
        for g in GHOST.split(","):
            if g in objs:
                o = objs[g]; o.data.materials.clear()
                gm = studio_mat("ghost", g + "_ghost")
                for _ in range(3): o.data.materials.append(gm)
                o.visible_shadow = False
    if EXPLODE and spec:
        ex = spec.get("meta", {}).get("explode")
        order = list(spec["parts"])
        zspan = max(p.z for p in bbox_pts()) - min(p.z for p in bbox_pts())
        for i, name in enumerate(order):
            off = ex.get(name) if ex else (0, 0, i * 1.2 * zspan)
            if off:
                objs[name].location = Vector(off)
        bpy.context.view_layer.update()

# ------------------------------------------------------------------ floor + lights
allpts = bbox_pts()
mn = Vector((min(p.x for p in allpts), min(p.y for p in allpts), min(p.z for p in allpts)))
mx = Vector((max(p.x for p in allpts), max(p.y for p in allpts), max(p.z for p in allpts)))
ctr = (mn + mx) / 2; size = max((mx - mn).length, 1.0)
if STUDIO:
    bpy.ops.mesh.primitive_plane_add(size=size * 14, location=(ctr.x, ctr.y, mn.z - 0.01))
    fl = bpy.context.object; fl.is_shadow_catcher = True
    if EXPLODE and spec:                       # thin light-grey axis line through the exploded stack
        zlo, zhi = mn.z, mx.z
        bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=zhi - zlo + 12, vertices=16, location=(0, 0, (zlo + zhi) / 2 + 3))
        ax_o = bpy.context.object; ax_o.data.materials.append(studio_mat("axis", "axis")); ax_o.visible_shadow = False
        mx.z = max(mx.z, zhi + 9)
        ctr = (mn + mx) / 2; size = max((mx - mn).length, 1.0)
else:
    bpy.ops.mesh.primitive_plane_add(size=size * 12, location=(ctr.x, ctr.y, mn.z - 0.01))
    fl = bpy.context.object; fl.data.materials.append(mat((0.86, 0.82, 0.74), "floor"))


def light(kind, loc, energy, size_, name=None, shape="SQUARE", size_y=None, color=None, target=None):
    d = bpy.data.lights.new(name or (kind + str(loc)), kind); d.energy = energy
    if kind == "AREA":
        d.shape = shape; d.size = size_
        if size_y: d.size_y = size_y
    if color: d.color = color
    o = bpy.data.objects.new(d.name, d); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = ((target or ctr) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


UNIT_GAIN = 3.0e2        # 1 BU = 1 mm: Blender lamp watts assume 1 BU ~ 1 m (inverse-square), so the rig's watts carry this gain


def studio_lights(c, sz):
    k = (sz / 60.0) ** 2 * UNIT_GAIN
    light("AREA", c + dirv(-40, 50) * 2.2 * sz, 1400 * k * EXPO, 60, "key", "SQUARE")
    light("AREA", c + dirv(70, 20) * 2.2 * sz, 300 * k * EXPO, 120, "fill", "SQUARE")
    light("AREA", c + dirv(160, 35) * 2.2 * sz, 900 * k * EXPO, 20, "rim", "RECTANGLE", size_y=120, color=lin("#dfe8ff"))


EXPO = float(opt("--expo", 1.0))
if STUDIO:
    studio_lights(ctr, size)
else:
    light("AREA", ctr + Vector((-size, -size * 1.2, size * 1.6)), 900 * (size / 60) ** 2, size * 1.2)
    light("AREA", ctr + Vector((size * 1.3, size * 0.8, size * 0.9)), 350 * (size / 60) ** 2, size)
    light("SUN", ctr + Vector((0, 0, size * 3)), 1.2, 0)

# ------------------------------------------------------------------ camera
cd = bpy.data.cameras.new("cam"); cd.lens = 85 if STUDIO else 55
if STUDIO:
    cd.sensor_width = 36
cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); sc.camera = cam
dist = size * 2.1


def place_cam(az):
    d = Vector((math.cos(az), math.sin(az), 0.75)).normalized()
    cam.location = ctr + d * dist
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()


def world_verts(step=7):
    """numpy (n,3) world-space vertices of every object (subsampled) in the CURRENT pose: the tight fit for the camera."""
    import numpy as np
    out = []
    for o in objs.values():
        n = len(o.data.vertices)
        v = np.empty(n * 3); o.data.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3)[::step]
        M = np.array(o.matrix_world)
        out.append(v @ M[:3, :3].T + M[:3, 3])
    return np.concatenate(out)


def fit_cam(points, az_deg, el_deg, fill=0.70, width_fill=0.82, yshift=0.0):
    """studio camera: aim at the bbox centre and back off until the part fills `fill` of the short side (and <= width_fill of the long one).
    points = numpy (n,3) world points (every pose that will be rendered)."""
    import numpy as np
    global dist, ctr
    d = dirv(az_deg, el_deg)
    dd = size * 2.0
    for it in range(24):
        cam.location = ctr + d * dd
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        inv = np.array(cam.matrix_world.inverted())
        q = points @ inv[:3, :3].T + inv[:3, 3]
        z = np.maximum(-q[:, 2], 1e-3)
        k = cd.lens / (cd.sensor_width / 2)
        xn = q[:, 0] / z * k; yn = q[:, 1] / z * k * (W / H)
        mx_x = float((xn.max() - xn.min()) / 2); mx_y = float((yn.max() - yn.min()) / 2)
        cx, cy = float(xn.max() + xn.min()) / 2, float(yn.max() + yn.min()) / 2 - yshift           # re-aim so the part sits mid-frame
        scale = max(mx_y / fill, mx_x / width_fill) if H <= W else max(mx_x / fill, mx_y / width_fill)
        if abs(scale - 1) < 0.004 and abs(cx) < 0.004 and abs(cy) < 0.004:
            break
        right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0)); up = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
        ctr = ctr + right * (cx * dd / k) + up * (cy * dd / (k * (W / H)))
        dd *= scale
    dist = dd
    return d


# ------------------------------------------------------------------ motion evaluation (mirrors mechkit.core.apply_move)
base = {k: o.matrix_world.copy() for k, o in objs.items()}

def M_rot(axis, pivot, deg):
    a = Vector(axis).normalized(); p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, a) @ Matrix.Translation(-p)

LINEAR = STUDIO          # studio: one-way ramp 0 -> drive end (frame 0 = start, last frame = end); paper: eased there-and-back loop

def pose_mech(t):
    """t in [0,1] -> drive along the motion (paper: there-and-back ease so loops are seamless; studio: linear one-way)."""
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
    s = t if LINEAR else 0.5 - 0.5 * math.cos(2 * math.pi * t)    # ease 0 -> 1 -> 0
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
pts = None
if spec and not TURN and not STILL:
    pts = []
    for k in range(12):
        pose_mech(k / 12)
        pts += [o.matrix_world @ Vector(c) for o in objs.values() for c in o.bound_box]
    pose_mech(0.0)
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2; size = max((mx - mn).length, 1.0); dist = size * 1.15

if STUDIO:
    import numpy as np
    if spec and not TURN and not STILL:
        fit_pts = []
        for k in range(12):
            pose_mech(k / 12); fit_pts.append(world_verts(11))
        pose_mech(0.0)
        fit_pts = np.concatenate(fit_pts)
    else:
        fit_pts = world_verts(5)
    if EXPLODE and spec:
        fit_pts = np.concatenate([fit_pts, np.array([[0, 0, mx.z], [0, 0, mn.z]])])
    fit_cam(fit_pts, AZ, ELEV, fill=FILL, yshift=YSHIFT)
    bpy.context.view_layer.update()
    for ob in list(bpy.data.objects):          # lights were placed around the pre-motion centre; re-aim them at the final centre
        if ob.type == "LIGHT":
            ob.rotation_euler = (ctr - ob.location).to_track_quat("-Z", "Y").to_euler()

if STILL:
    if spec and not TURN:
        pose_mech(0.0)
    sc.render.filepath = OUTFILE or os.path.join(outdir, f"{STILL}.png")
    bpy.ops.render.render(write_still=True)
    print("still ->", sc.render.filepath)
    raise SystemExit(0)

for f in range(FR):
    t = f / (FR - 1) if (LINEAR and FR > 1) else f / FR
    if STUDIO:
        if spec and not TURN:
            pose_mech(t)
        else:
            objs_rot = math.radians(360) * t
            for o in objs.values(): o.rotation_euler[2] = objs_rot
    elif spec and not TURN:
        pose_mech(t); place_cam(math.radians(-55) + 0.35 * math.sin(2 * math.pi * t))
    else:
        place_cam(math.radians(-55) + 2 * math.pi * t)
    sc.render.filepath = os.path.join(outdir, f"f{f:03d}.png")
    bpy.ops.render.render(write_still=True)
print("frames ->", outdir)
