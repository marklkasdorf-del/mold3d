# Gotchas learned building Mold3D

Each one cost real time once. The three that matter every time are in SKILL.md (cutter overlap 0.05 mm, angular_tolerance 0.05, must-jam controls checked along the path).

- manifold3d: a CLOCKWISE outline extrudes to an EMPTY solid (meshkit.prism fixes winding). `min_gap` is exact; use it.
- Cutters that share a face with the target leave a zero-thickness skin (pin welded, gap 0.0): extend cutters 0.05 mm past both faces, slope preserved.
- build123d `Polygon(*pts)` needs TUPLES; JSON lists became a zero-area sliver.
- Must-jam controls must be checked along the PATH: a gimbal ring tilted 25 deg about the wrong axis is clear of its pins, but jams at 10 deg.
- Export with angular_tolerance 0.05: coarse facets on big curves ate 0.06 mm of a 0.3 mm gap (the printer gets the facets).
- 45-deg cone pins/sockets must stay true 45 deg (rb > L): a clamped tip made pin and socket non-parallel (gap 0.21 instead of 0.30). Non-45 cones: offset radially by gap/cos(angle).
- Twisted (helical) surfaces: an in-plane offset g gives only g*cos(helix angle) of real gap.
- PCA axis sign is arbitrary: never flip a model 180 deg just because eigh said so.
- Taubin-smooth ONLY uniform voxel meshes; it melted a plinth cylinder into a splash.
- Image->3D from a TOP view is read as a front view (blob). Flat things (flexis, reliefs) come from the outline (`text3d/relief.py`), not Hunyuan.
- CLIP judges annotated CAD views badly (grid/text confuse it); always score clean renders.
- AI helmets are solid heads on a skinny neck stump: the hollowed cavity is SEALED above the neck -> punch the cavity outline down through the bottom (helmet_post does). Figure prompts say "full body" -> helmets need their own helmet-only prompt.
- Big hollow shells: slice in the pose preflight --orient picks (seam on the bed), never in the assembled pose (faceplate slice FAILED floating there; rim-down shell = 540 g of support).
- Artifacts don't serve .bin: ship geometry as base64 JSON.
- Head fit is a 3D question: the widest inner slice of a full helmet is the roomy jaw (v1 said 87% when 106% fit). Use the padded head proxy + interference search.
- Thin-wall fixing by "opening" treats surface roughness as thin and grows lumps each pass; thicken around the MEDIAL surface instead (distance-transform ridge), one pass, target min + 0.4.
- Flat-face analysis must sample the face AREA: a big flat face can be 2 triangles (magnet placement saw nothing).
- Auto-placing text: the bbox centre of a boomerang is empty air; ray-cast a grid and use the deepest point of the footprint.

