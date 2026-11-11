# bench/

Reproduce Round A of `knowledge/benchmark-2026-10-17.md` (accuracy vs real STEP files).

1. `python attempts/parts.py` writes the blind attempts (STLs) next to the script. They were written from the part name/standard only, before the ground truth was opened.
2. Fetch the ground truth yourself (not redistributed here): `forge parts-find "608 bearing" --download`, then `forge step2stl <file>.step truth.stl`.
3. Score: `forge grade attempts/bearing_608zz.stl truth.stl` -> voxel IoU, chamfer and 95th-percentile error in mm.

Round B (moving parts) uses `forge movecheck` plus the motion sweeps in `lib/motion.py`; the community models it compared against are on Printables and are not included.
