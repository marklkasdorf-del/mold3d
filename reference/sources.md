# sources.md — research index (2026-10-14 sweeps) and quotes worth keeping
Raw research notes are not included in this repo.
Citation style in forge docs: `(HN <id>)` = https://news.ycombinator.com/item?id=<id>; `(YT <id>)` = https://youtu.be/<id>.

## Hacker News threads
| ID | Topic | Keep |
|---|---|---|
| 47183039 | SynapsCAD / vibe-code 3D models | arjie: "letting the machine just spend its time iterating on the design with PNGs that it rotates and renders before it actually gives me an STL works quite well." contingencies' failure list + rails A-E: subtract must lower volume; no zero-volume result; no shared faces; orthographic elevation to know up/down; semantic names. nszceta: "stay away from mesh based CAD like OpenSCAD and go straight for build123d." |
| 47970497 | text-to-cad | garfij: better results once "told it how to produce rendered PNGs ... and to inspect it from several angles." david_mchale: caliper numbers + reference photos; "still needs heavy manual checking." Eisenstein: "the trick... is to be an expert in the field already." |
| 47913203 | CAD in Codex / softservo recipe | "1. Generate a python script for every STEP file... Use build123d > cadquery. 2. Reference specific faces and edges... 3. Maintain markdown explaining important part features... 4. Verify results with screenshots and geometry. Models don't have great spatial awareness, but they can interpret images and verify constraints very well." Burns tokens. |
| 48173429 | GenCAD | pdntspa: parameterize so you can print a small prototype first, then the full-size model. |
| 49676577 | CadQuery vs OpenSCAD benchmark | dofm: OpenSCAD "absolutely not the right tool for functional parts"; common objects "already exist". evilduck: edit an existing STL by Python mesh code, "went perfectly." |
| 45140921 | CADAM | gerdesj: hallucinated BOSL functions; missing epsilon in closing geometry. |
| 47365299 | Claude tips for 3D work | willis936: complex enclosures fail unless broken into one function per feature. bambax: FreeCAD Python for lofts "run, check, delete, repeat". |
| 47894977 / 48572553 | "Is text-to-CAD BS?" / Launch Adam | calibrate: good for simple printable functional parts, poor for engineering assemblies; many demos are cherry-picked. |
| 44622374 | Blender MCP Show HN | triangle-only topology is a showstopper for UV/sculpt, fine for printing. |
| 43774990 | Teaching LLMs solid modeling | pasting an error screenshot to a vision model helped. |
| 47772725 | build123d + Claude -> CNC | real STEP parts shipped to a shop. |
| 47475417 | OpenSCAD live reload | VS Code + OpenSCAD auto-reload loop. |
| 49238028 | blender-mcp maintainer hacked (Aug 2026) | treat community Blender MCP supply chain with care; we use headless `-b --python`. |

## Blogs / repos
- flowful-ai/cad-skill (SKILL.md, preview.py, design-review.md) https://github.com/flowful-ai/cad-skill — research real dims first and cite them ("Even 1-2mm off can make a part unusable"); interview first; 3 phases with preview after each ("Do NOT disappear and come back with a finished model"); PARAMETERS/MODEL/EXPORT template; bottom at Z=0; 3-line print recipe; tolerance table (wall 1.2/2.0, hole clearance 0.2/0.3, press-fit 0.1-0.15, min feature 0.4/0.8, bridges <20, overhang <45, TPU ~0.5, PETG +0.1, ABS shrink 0.5-0.7%).
- ModelRift https://modelrift.com/blog/cadquery-vs-openscad/ and https://modelrift.com/blog/openscad-llm-benchmark — silent boolean failures; "Only volume measurement caught it"; "Preview and export are not the same thing... the exported mesh needs its own inspection pass."; mandatory STL audit fields (triangles, bbox, volume, watertight, non-manifold, boundary edges, flipped faces, components).
- Dave Snider https://www.davesnider.com/posts/claude-3d — "Natively, Claude can't read an STL"; "I almost always build tooling first to give us a shared language"; capture-view CLI with angle/zoom/look-at; debug markers.
- Will Patrick https://willpatrick.xyz/technology/2025/04/23/teaching-llms-how-to-solid-model.html — spatial reasoning collapses on 5+ operation sequences; build incrementally; libraries reduce complexity.
- Lindsay https://lindsay.codes/posts/claude-code-for-3d-printing/ — needed "a lot of trial and error and coaching"; orthogonal views; check against measurements.
- strayspark https://www.strayspark.studio/blog/ai-hallucinating-blender-python-api-bpy-fix — state the Blender version; introspect enums; `CYCLES` casing "single most common wasted turn".
- MindStudio https://www.mindstudio.ai/blog/claude-blender-mcp-real-world-performance — Blender MCP fine for hard-surface/architecture; fails on organics, clean topology, exact placement.
- ahujasid/blender-mcp README https://github.com/ahujasid/blender-mcp — save first; small sequential steps. Official Blender Lab MCP: https://projects.blender.org/lab/blender_mcp. hydroxide.dev https://hydroxide.dev/articles/blender-mcp-claude-code/.
- earthtojake/text-to-cad (MIT, Thompson Labs LLC) — fully reviewed 2026-10-15, see `reference/text-to-cad-review.md`. Adopted: `lib/step_parts.py` (code adapted from skills/step-parts/scripts/download_step_part.py), ideas for `lib/topo.py` (topology refs + feature notes), `lib/b123d_checks.py` (cadgen.geometry overlap/closest/signed-volume/is_sound), `verify --orient` + per-body wall + units flag (skills/dfam-check). Video: Miguel Torrez NDCzv3XIIFY (Stream Deck+ clamp; captions 429, reviewed via description).
- jmwright/cadquery-llm-skill; gmoddev/Blender_mcp (BVH gap/interpenetration checks); seehiong/blender-mcp-bridge (`check_mesh_for_printing`, `apply_voxel_remesh`); nurb.dev (nine printability checks); marknefedov codex-blender-bench ("view fusion is the main bottleneck").
- Not yet read (leads): BenchCAD arXiv 2605.10865, cadbench.ai, Zoo.dev blog.

## YouTube (transcripts read)
- YwIGmEs0NdU Claude Code + official Blender MCP (Blender 5.1): wrong scale, false assumptions in your own prompt cost an hour ("wait, the rest pose is not as you said"), Claude vision "terrible" at placement, crash -> revert.
- r7H60u0kHRA ahujasid MCP: primitive-only modeling "not really work"; rename pass first; metadata per part.
- 0PSOCFHBAfw assistant-mode vs MCP: be exact ("use Blender's rigid body physics"); start Blender+server before Claude; usage limits burn fast.
- TojQChim9mM MCP showdown: boolean leaves empty material slot 0; art-direction passes; meshes from generators then deform.
- VfdEz-My_D0 photos -> Fusion 360 MCP -> print: scale reference in photos; dimensions directly "likely beats photos"; AI asks fit-type before modeling.
- npWO0JIsJ48 "Text-to-CAD is missing the point": make the LLM write a parametric program with named parameters; edits then cost no tokens.
- wRllLcHbh64, HLbMCvdClrM, KrFttd5D1cw (OpenSCAD idioms: variables first, centre shapes, mm, `$fn`, `#` and `!`), GVXL7hIOJro (build123d), NjybDaUOKEg (image-to-3D contrast).
- Unread YouTube leads (rate-limited, 429): 6trAkQY5_kc, DxCLJvpKKlo, tpjJeH1pPws, FGc4-TSZYKA, 3m1aG6nqmNU, Ci9Xc-VPc04, ACal_vkrc9Q, vg0qrfVdTg4, 6rDDWx1hXH8. (NDCzv3XIIFY reviewed 2026-10-15 via description + repo.) Use `forge learn <url>` on them when a topic needs it.

## Local audit (this Mac)
audit REPORT.md (2026-10-14): Blender 5.2.1 sandbox segfault; engine ids; stl_export; text non-manifold + MANIFOLD silent drop; shared coordinate frame; Workbench top-down flat; trimesh needs shapely/rtree for section (absent) so v2 sections.py loop-count idea; v2 REPORT.md (2026-09-09): render-critique loop works (4 parts ~9-10/10) but was never automated, fit numbers never test-printed, CPU rasterizer faked a dome on flat caps.
