"""motion.py: kinematic checks for moving / print-in-place parts (build123d). Proven in bench 2026-10-17.

    from motion import sweep, control, ov
    # each mover: (shape, transform_fn(shape, t) -> moved shape), t in [0,1]
    worst = sweep(movers=[(handleA, lambda s, t: rot_about(s, (0, 8.5, 0), 180 * t))], fixed=[blade], steps=13)
    control(...)  # NEGATIVE CONTROL: a motion that SHOULD jam must jam, else the check proves nothing

Rules learned:
- Always run a negative control; a 'CLEAR' with no control can mean parts don't even engage (gears not meshing,
  hole bigger than the part). Avoid control offsets that hit a symmetry (3-lobe part: 120 deg = no-op!).
- Static overlap == 0 is necessary, not sufficient: pair with movecheck.py gaps (target 0.25-0.4 mm on a 0.4 mm nozzle).
"""
from build123d import Axis, Pos, Rot


def ov(a, b):
    r = a & b
    return r.volume if r is not None else 0.0


def rot_about(shape, centre, deg, axis="Z"):
    cx, cy, cz = centre
    r = {"X": Rot(deg, 0, 0), "Y": Rot(0, deg, 0), "Z": Rot(0, 0, deg)}[axis]
    return Pos(cx, cy, cz) * r * Pos(-cx, -cy, -cz) * shape


def helix_move(shape, dz, deg_per_mm, centre=(0, 0)):
    """ride a helix: translate dz along Z while turning dz*rate about the Z axis through centre."""
    return Pos(0, 0, dz) * rot_about(shape, (*centre, 0), dz * deg_per_mm)


def sweep(movers, fixed=(), steps=13, tol=0.01, verbose=True):
    """movers: [(shape, fn(shape, t))]; checks every moved pair + moved-vs-fixed at each t. Returns worst mm3."""
    worst = 0.0
    for k in range(steps):
        t = k / (steps - 1)
        moved = [fn(s, t) for s, fn in movers]
        pairs = [(i, j) for i in range(len(moved)) for j in range(i + 1, len(moved))]
        for i, j in pairs:
            v = ov(moved[i], moved[j])
            if v > tol and verbose: print(f"  COLLIDE mover{i}-mover{j} @t={t:.2f}: {v:.2f} mm3")
            worst = max(worst, v)
        for i, m in enumerate(moved):
            for f in fixed:
                v = ov(m, f)
                if v > tol and verbose: print(f"  COLLIDE mover{i}-fixed @t={t:.2f}: {v:.2f} mm3")
                worst = max(worst, v)
    return worst


def control(moved_wrong, fixed, min_mm3=1.0):
    """True if a deliberately wrong motion collides (it should)."""
    return ov(moved_wrong, fixed) > min_mm3
