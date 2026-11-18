# lessons.md — one line per lesson, newest last. Format: `date · project · lesson (number if any) · phase`
2026-10-14 · face-relief charm · Local Depth-Anything-V2-Small works (10 s CPU) and gives silhouette/nose but NOT eyes/brows/mouth: fuse with CLAHE-darkness features + hand-placed mouth groove; marching-cubes on an analytic field replaces boolean engines for reliefs (watertight, exact flat bed) · phase 3
2026-10-14 · face-relief charm · A relief printed face-down is all overhang: print face UP, make the peg a separate insert printed standing in a back socket; `( cmd ) &` subshell + background pip silently died, use nohup · phase 2/5
2026-10-14 · face-relief charm · verify min_wall flags thin rounded peaks (0.75) and random hair-strand grooves (0.49); drop texture, relax to 0.7 for reliefs · phase 3
2026-10-14 · forge tools · added bin/relook + lib/relief_closeup.py (EEVEE raking-light closeup vs photo) because sheet.png is too flat to judge likeness · phase 3
2026-10-17 · benchmark · standard parts from full spec = 0.96 IoU vs real STEP; recalled dims miss (pulley 0.41): always parts-find/datasheet · phase 1
2026-10-17 · benchmark · 3/3 print-in-place mechanisms passed sweeps first build; looks lost on every iconic object -> mandatory REFERENCE PASS (forge refs) before modeling named things · phase 1b
2026-10-17 · benchmark · motion sweep needs a negative control; a 3-lobe part offset 120 deg is a no-op control (symmetry) · phase 3
2026-10-17 · benchmark · balisong: keep each handle's swept volume on its own side of y=0 => pivot PY >= (bar_inner+bar_w)/2; widening bars without moving pivots crashed at 180 deg (sweep caught it) · phase 3
2026-10-17 · Mold3D 2.0 · control tests must check the PATH not the end pose (gimbal ring clear at 25 deg, jams at 10) · phase 3
2026-10-17 · Mold3D 2.0 · coplanar cutter faces leave zero-thickness skins that weld pins (gap 0.0): extend cutters 0.05 mm · phase 3
2026-10-17 · Mold3D 2.0 · manifold3d CW outline = empty solid; build123d Polygon needs tuples (JSON lists -> zero-area sliver) · phase 3
2026-10-17 · Mold3D 2.0 · export angular_tolerance 0.05: coarse facets on big spheres ate 0.06 of a 0.3 mm gap · phase 3
2026-10-17 · Mold3D 2.0 · Taubin smoothing only on uniform voxel meshes (melted a plinth); smooth before adding sharp parts · phase 3
2026-10-17 · Mold3D 2.0 · CLIP looks-score only on clean photo-like renders; annotated CAD views mislead it · phase 3
2026-10-17 · Mold3D 2.0 · image->3D reads a top view as a front view; flat flexis come from the outline (relief.py) · phase 0
2026-11-09 · bridge turbine · accessory keyed into an existing part's own holes (triangle key + split-prong barbs out the far face) = positive lock with zero changes to the host; barb flex via manifold sweep of the prong against the tunnel (1.04 mm, 0.66% strain) · phase 3
2026-11-09 · bridge turbine · looks: pointed spinner reads "airplane propeller"; tower height was the real lever (hub 110->128 mm: 38->48%, 4/6 views) · phase 3
2026-11-09 · bridge turbine · horizontal axle printed as part of the upright tower beats a separate 5x25 pin (preflight NO-GO knife edge); 45-deg conical seat replaces a drooping flat flange and self-centres · phase 2/5
2026-11-09 · bridge v2 · split a span with a flat-bottom bow-tie key slid in along the extrusion axis: locks tension + sag (controls jam at 0.5 mm), glue makes it permanent; host it in a solid node and fuse the accessory mount onto the key · phase 2
2026-11-09 · bridge v2 · a dovetail notch cut through a part printed deck-down is a one-sided cantilever ceiling (preflight GO+SUPPORTS); profile-extruded parts print on their side = zero overhangs · phase 5
2026-11-09 · bridge v2 · ducted ("box fan") turbine scores 19% "wind turbine" in CLIP because it reads as a box fan -- that IS the requested look; score the target the user asked for, not the generic noun · phase 3
2026-11-10 · clickfidget · first independent blind STL review caught 3 real issues my selftest passed (button had 0.15 mm left after release, bridge right over the 0.25 gap, sharp arm root). Add a 'button still proud after release >= 1 mm' check to any push-release design · phase 3
2026-11-10 · clickfidget v3-v5 · beam math must use the REAL cross-section (shapely I and c from a mesh section); a 2x2 side flange on a 2 mm arm doubled force and strain · phase 3
2026-11-17 · clickfidget v6 · arm modelled flush (0.00 mm) to the socket on 3 faces passed every check because they measured OVERLAP, not GAP: touching = 0 overlap = "pass". Now `gap_min` per mover (touching is its own FAIL) · phase 3
2026-11-17 · clickfidget v7 · gap_min on v7 still finds the arm's +Y face 0.05 mm from the socket wall (x 27-34, z -5.7..-0.5, model frame) over ~19 mm2: fixing the 3 named faces did not fix every sliding face; check them all, not the ones you noticed · phase 3
2026-11-17 · clickfidget v7 · a "two-colour 3MF" held the plug only, one colour, text on the bed face; then the fixed one still had the text on the bed face. `forge contents --expect` reads the file back vs the ask before anything is sent · phase 5
