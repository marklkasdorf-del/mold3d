# gotchas-bpy.md — Blender 5.2.1 LTS bpy (bundled Python 3.13, numpy 2.3)

Binary: `/Applications/Blender.app/Contents/MacOS/Blender`. Headless: `Blender -b --factory-startup --python script.py` (args after `--` go to your script via `sys.argv`).
**Inside an agent sandbox Blender can SEGFAULT at startup (exit 139, `gpu::supports_barycentric_whitelist` / `MTLBackend::metal_is_supported`). Run Blender outside such sandboxes.** Outside: ~1 s startup. The harmless `ArchWarn: ARCH_CACHE_LINE_SIZE` line can be ignored.
Everything marked (verified) was run in Blender 5.2.1 on 2026-10-14. Training data is dominated by Blender 2.8-4.x (strayspark): **say "Blender 5.2" in every plan and introspect before guessing an API.**

## Introspect first, never guess (strayspark: the "cheapest win")
```python
import bpy
print(bpy.app.version_string)                                                   # 5.2.1 LTS
print([i.identifier for i in bpy.types.Modifier.bl_rna.properties['type'].enum_items])   # valid modifier types
print([i.identifier for i in bpy.context.scene.display.shading.bl_rna.properties['light'].enum_items])  # ['STUDIO','MATCAP','FLAT'] (verified)
print(dir(bpy.ops.wm)[:50])        # find the real operator name before calling it
```
A wrong enum raises a message that lists the valid ones — read it, don't retry blindly ("enum case is the single most common wasted turn").

## Render engine ids and case (verified)
| Value | Result in 5.2 |
|---|---|
| `'BLENDER_WORKBENCH'` | OK (fast, 1.2 s for 640x480, the forge verification renderer) |
| `'BLENDER_EEVEE'` | OK (4 s, real shadows; **not** `BLENDER_EEVEE_NEXT`, that raises) |
| `'CYCLES'` | OK, **UPPERCASE**. `'cycles'` raises. `'EEVEE'` raises. |
Valid set printed by Blender itself: `('BLENDER_EEVEE', 'BLENDER_WORKBENCH', 'CYCLES')`.
Workbench top-down ortho is flat (no depth cue): use oblique views or EEVEE for top/inside views (audit gotcha #4). Wall/cavity facts come from numbers + section views, not shading.

## Removed / renamed APIs hit in 5.x
- `scene.node_tree` is gone (`hasattr(scene,'node_tree')` -> False, verified). Use `scene.compositing_node_group` where needed or avoid compositing.
- STL: `bpy.ops.export_mesh.stl` does not exist (verified). Use **`bpy.ops.wm.stl_export(filepath=..., export_selected_objects=True, apply_modifiers=True, global_scale=1.0)`** and `bpy.ops.wm.stl_import(filepath=...)`.
- Action/animation API changed in 5.0 (strayspark). We don't animate; if you must, introspect.

## Units: 1 Blender unit = 1 mm
```python
s = bpy.context.scene
s.unit_settings.system = 'METRIC'; s.unit_settings.scale_length = 0.001; s.unit_settings.length_unit = 'MILLIMETERS'
```
With export_scale/global_scale 1.0 the STL bbox is mm-correct (60 x 40 x 25 verified). Scale bugs ("trees as big as mountains", "3x too big") come from forgetting this: **assert the bbox against spec numbers after every build.**

## Silent-boolean traps (audit gotchas #2, #3)
1. **Non-manifold operand + `solver='MANIFOLD'` = the operand is silently dropped** (union returns the lid with no text, no error). Text converted to mesh is non-manifold. Fix: `bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)` + `bmesh.ops.recalc_face_normals`, then use `solver='EXACT'`. Always compare volume before/after (templates/part_bpy.py does).
2. **Operands must share one coordinate frame.** Subtracting a cavity at x=0 from an object at x=70 = silent no-op. Build everything at the origin; translate/instance last. Apply transforms (`bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)`) before booleans.
3. Cutter must overshoot by 0.01-0.1 mm like any CSG.
4. Boolean unions of threads "almost always produce non-manifold edges" (3d-agent.com via research): use OpenSCAD/BOSL2 or build123d for threads, not Blender.
5. After a boolean the result object can end up with an **empty material slot 0** so faces render with the wrong/missing material (Codex Poke Ball, TojQChim9mM). Irrelevant for STL, matters for presentation renders: rebuild slot assignments after booleans.
6. `bpy.ops.object.modifier_apply` needs the object active+selected (the `select_only()` helper in the template) — otherwise "Context is incorrect".

## Checks you can trust (bmesh)
```python
bm = bmesh.new(); bm.from_mesh(obj.data)
nm  = sum(1 for e in bm.edges if not e.is_manifold)   # 0 required
vol = abs(bm.calc_volume(signed=True))                 # mm3
bm.free()
```
(verified, used by the template.) No 3D-Print Toolbox is installed — do not call it. Independent audit = `forge/bin/verify <stl>` (trimesh).

## Voxel remesh = watertight by construction (verified)
```python
obj.data.remesh_voxel_size = 0.8        # mm (BU); smaller = more detail + more faces
bpy.context.view_layer.objects.active = obj; obj.select_set(True)
bpy.ops.object.voxel_remesh()           # metaball ball cluster: 0 non-manifold edges afterwards
```
Use it to fuse messy unions, then `DECIMATE` (ratio 0.4 took 3490 -> 2154 faces, still manifold). Voxel size must be <= half the smallest feature you need to keep.

## Text
`bpy.data.curves`/`bpy.ops.object.text_add()`; `t.data.extrude` is HALF the total depth (extrudes both sides); `align_x='CENTER'`. Convert with `bpy.ops.object.convert(target='MESH')` then weld (trap #1). Letters under 0.8 mm stroke won't print. Text bodies in the default font worked in 5.2.

## Safety/process rules from the Blender-MCP world
- Save before risky ops: `bpy.ops.wm.save_as_mainfile(filepath=...)` ("ALWAYS save your work", ahujasid README). In headless runs, write the .blend next to the STL as `iter_NN.blend`.
- Break big operations into small sequential scripts (same README). One feature per script call.
- If a script crashes Blender, stop, revert to the last .blend, rebuild smaller (YouTube YwIGmEs0NdU).
- We use headless `-b --python`, **not** blender-mcp (not installed; maintainer account reportedly compromised Aug 2026, HN 49238028). Deterministic and sandbox-friendly once unsandboxed.

## Scale/placement reality
Vision is "terrible" at re-placing objects from a top view (YwIGmEs0NdU). Place by numbers (coordinates, bbox, raycasts), verify by numbers, use renders only to confirm.
