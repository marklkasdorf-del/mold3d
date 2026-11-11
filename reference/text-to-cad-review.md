# text-to-cad review (2026-10-15) — earthtojake/text-to-cad v0.7.21 + Miguel Torrez "This Free AI Skill Lets You 3D Print Anything" (https://youtu.be/NDCzv3XIIFY, 2026-07-29, 5 min)

What it is: an MIT agent plugin ("CAD Skills") = skills `cad`, `step-parts`, `dfam-check`, `dfm`, `gcode`, `bambu-labs`, `dxf`, `urdf/srdf/sdf`, `engineering-drawing`, `sendcutsend` on top of a Python runtime `cadgen` (build123d + warm build daemon + CAD Viewer web app + MCP server), installed with `claude plugin install` / `npx skills add`. The video builds a Stream Deck+ clamp in Codex: install, look up the official product dimensions, split into separate printable parts, open the model in the viewer. Transcript: YouTube returned HTTP 429 for captions on every retry (even yt-dlp 2026.08.19), so the video is reviewed from its description/chapters + the repo, which is the thing it demonstrates.

| text-to-cad idea | Verdict | Reasoning | Where it landed |
|---|---|---|---|
| Per-model Python script, named params, one factory per feature | ours equal | Phase 2/3 + templates already do this | - |
| Face/edge refs (`#o1.2.f7`) + selection from viewer | **theirs better -> adopted (lite)** | lets "that left hole" become an id with numbers | `lib/topo.py`, `forge topo`, `--near=x,y,z` |
| Plain-English part notes (README catalog, cad-brief) | **theirs better -> adopted** | auto-written `.features.md` (hole dias, planes) beats hand notes | `forge topo` output |
| Product-dimension lookup (step.parts, STEP of real screws/boards) | **theirs new -> adopted** | exact dummies for fit checks; verified M3x12 head 5.5 x 2.8 | `lib/step_parts.py`, `forge parts-find`, `forge step2stl` |
| DfAM orientation candidates (6 axis lays) | **theirs new -> adopted** | answers "which face down" with numbers | `verify --orient` |
| Wall thickness per connected body, p05 stat | **theirs better -> adopted** | stops a fit gap reading as a wall in assembled-pose STLs | `verify_lib.wall_thickness` |
| Units-suspect flag (bbox diag < 1 mm) | theirs new -> adopted | metres/inch exports pass silently | `verify` `units` row |
| `overlap_volume` / `closest_points` / signed volume per solid / `BRepAlgoAPI_Check` | **theirs better -> adopted** | `a & b` returns None/empty; sum of volumes hides an inverted solid | `lib/b123d_checks.py`; template uses `assert_solid` |
| "Turn visual doubt into a geometry check" table | ours equal | verification-playbook already says numbers first | - |
| Snapshot presets (xray, hidden-line, display JSON, 10 size profiles) | ours better for us | our 6-view sheet + rulers + section is enough; their renderer needs Playwright/Chromium | trashed |
| CAD Viewer web app + MCP cards (orbit, click-select, Quick Edit notes) | theirs better, not adopted | needs a daemon, localhost server, MCP tunnel; the loop is terminal/phone friendly with sheet.png. Revisit as a static three.js Artifact if wanted | - |
| STEP as primary output, STL/3MF/GLB mesh exports | ours equal | we already write STEP beside STL; 3MF/GLB not needed | - |
| Separate parts for print (one file per part + assembly) | ours equal | `$FORGE_PARTS_DIR`, assembly template, `verify --assembly` | - |
| Store/daemon/freshness cache (`cadgen store why`) | trashed | `forge run` is a 4 s one-shot; a cache adds a daemon | - |
| OrcaSlicer headless (`gcode`), Bambu Connect | ours better / n/a | this skill stops at a verified STL; slicing is the user's choice | trashed |
| DFM (CNC, sheet metal, molding), DXF, drawings, SendCutSend, URDF/SRDF/SDF, kinematics | n/a | not 3D-print or not the target hardware | trashed |
| dfam-check process limits (FDM wall 1.2/1.6, hole 2.0, feature 0.8, bridge 10) | ours equal | matches print-tolerances.md [R]; their bridge 10 is stricter than our 20 - coupon it | - |
| Our verify/render/coupon/fit-log loop, Blender lane, photo->head, scad lane | **ours better** | they have no printed-fit feedback, no cavity-safe section render, no organic lane | kept untouched |

## License and security
- License: MIT (c) 2026 Thompson Labs LLC, every skill and `cadgen` carry the file. Code copied: `step_parts.py` (from skills/step-parts, credited in header + sources.md). `topo.py`, `b123d_checks.py`, orientation code are our own re-implementations of the ideas.
- Telemetry ON by default: `cadgen` sends usage stats + crash reports (random install id, country from IP) to `api.texttocad.dev` -> PostHog; `uvx cadgen telemetry off`. Daily update check to the same host (`CADGEN_UPDATE_CHECK=0`).
- Installers: plugin marketplace `#latest` branch, `npx skills add` and `uvx --from cadgen==0.7.21` pull code from GitHub/PyPI on every update ("Update text-to-cad to X" message tells the agent to re-run them) = supply-chain surface; first snapshot downloads Playwright Chromium; a warm daemon and an MCP server with a tunnel module run locally; the viewer is unauthenticated on 127.0.0.1 (their SECURITY.md).
- Decision: nothing installed, hooks/installers not run, plugin not added. Only `api.step.parts` (read-only, sha256-verified downloads from GitHub media) is called, and only when `forge parts-find` is run by hand. Catalog text is treated as data.
