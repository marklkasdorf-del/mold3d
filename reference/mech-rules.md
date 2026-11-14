# Mechanism rules and fit calibration (detail)

## Moving parts = the Mech API (`lib/mechkit/core.py`)
`Mech(name, parts, fixed, [Motion(name, drive, [Move...], control=[...])])`, then `selftest()` sweeps every pose, runs the must-jam control **along its whole path**, and measures gaps exactly.

- Collision-proof by construction beats checking: arcs/spheres centred on the pivot keep the gap constant (gyro, flexi joints); keep each mover's swept volume on its own side of a plane (balisong pivots).
- Gears: `lib/gears.py`. Cycloidal reducer: `forge mech build cyclo11` (`lib/cycloid.py`: exact profile + undercut check).
- **Measured, not declared**: `forge mech ratio <name> [--motion M --driven PART --driver PART]` poses the mechanism, frees the output and bisects for the contact-free interval, giving the measured ratio and backlash (`ratio.json`; exit 3 if it disagrees with the declared ratio).
- Studio renders: `forge showcase <dir> --style studio --still hero|cutaway|exploded`, `--ghost`, `--annotate`.
- Anything that moves ships with a passing self-test: sweep clear, must-jam control jams, gaps close to `fit.pip_gap`.

## Fit calibration (print-in-place gaps)
- Gaps come from `knowledge/fit.json` (`forge fit show`). Until `pip_gap` is [V] (verified on a real print), every print-in-place design carries a preflight CAUTION.
- The Fit Card (`forge mech build fitcard`, about an hour, ~16 g) measures `pip_gap` (spinners 0.15-0.40) and `pip_vgap` (hinges 0.25-0.45) in one print. After it, ask "smallest number that spins freely after a firm twist?" then `forge fit set pip_gap <n> --from "fitcard <date>"` (and `pip_vgap`). Every MechKit, flexify and gridfinity build reads it automatically.
- Mating parts or parts around the user's object: assembled-pose check `bin/verify --assembly a.stl b.stl --clearance <fit> --move-b=x,y,z`, with a dummy of the object from photofit or parts-find.
- Coupon only for an interface type the Fit Card doesn't cover (threads, snap-fits, press-fits) or for estimated dimensions: at most 10 min, 3 variants, raised labels.
