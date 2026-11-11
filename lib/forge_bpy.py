"""Helpers for forge bpy-lane part scripts (import inside Blender:  sys.path.insert(0, FORGE_LIB); import forge_bpy as fb).
1 Blender unit = 1 mm. Booleans ASSERT they did something (silent drops are the #1 bpy failure).
  fb.reset()                          clean scene
  o = fb.box('name', sx, sy, sz, z0=0, x=0, y=0)    box centred on x,y, spanning z0..z0+sz
  fb.cyl('name', r, h, z0=0, x=0, y=0, seg=64)
  fb.boolean(target, tool, 'DIFFERENCE'|'UNION'|'INTERSECT', solver='MANIFOLD')   consumes tool; asserts volume changed
  t = fb.text('HELLO', size=9, extrude=0.4, x=0, y=0, z=2)    watertight text mesh (fixes non-manifold)
  fb.export(objs_or_None, path)        STL export (selected objects) -> use os.environ['FORGE_OUT_STL']
  fb.out_stl() / fb.parts_dir()        paths forge run provides (FORGE_OUT_STL, FORGE_PARTS_DIR)"""
import bpy, bmesh, os
from mathutils import Vector


def out_stl():
    return os.environ.get("FORGE_OUT_STL", "forge_out.stl")


def parts_dir():
    d = os.environ.get("FORGE_PARTS_DIR", os.path.dirname(os.path.abspath(out_stl())) + "/parts")
    os.makedirs(d, exist_ok=True)
    return d


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.scale_length = 0.001
    bpy.context.scene.unit_settings.length_unit = "MILLIMETERS"


def _bm_volume(o):
    bm = bmesh.new(); bm.from_mesh(o.data); v = bm.calc_volume(); bm.free(); return abs(v)


def box(name, sx, sy, sz, z0=0, x=0, y=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z0 + sz / 2))
    o = bpy.context.object; o.name = name; o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o


def cyl(name, r, h, z0=0, x=0, y=0, seg=64):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=seg, location=(x, y, z0 + h / 2))
    o = bpy.context.object; o.name = name
    return o


def boolean(target, tool, op="DIFFERENCE", solver="MANIFOLD"):
    v0 = _bm_volume(target)
    m = target.modifiers.new("b", "BOOLEAN"); m.operation = op; m.object = tool; m.solver = solver
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier="b")
    bpy.data.objects.remove(tool, do_unlink=True)
    v1 = _bm_volume(target)
    if abs(v1 - v0) < 1e-6 * max(v0, 1):
        raise RuntimeError(f"boolean {op} on '{target.name}' changed nothing (volume {v0:.1f}); operands in different frames or non-manifold tool?")
    return target


def text(body, size=9, extrude=0.4, x=0, y=0, z=0, font=None):
    bpy.ops.object.text_add(location=(x, y, z))
    t = bpy.context.object
    t.data.body = body; t.data.align_x = "CENTER"; t.data.align_y = "CENTER"; t.data.size = size; t.data.extrude = extrude
    if font: t.data.font = bpy.data.fonts.load(font)
    bpy.ops.object.convert(target="MESH"); t = bpy.context.object
    bm = bmesh.new(); bm.from_mesh(t.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(t.data); bm.free()
    return t


def export(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    objs = objs if objs is not None else list(bpy.data.objects)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True)
    print("EXPORTED", path)
