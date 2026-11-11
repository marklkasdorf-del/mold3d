"""b123d_checks: tiny, None-safe geometry checks for part scripts (lane b123d). Import inside a part file:
    from b123d_checks import overlap_volume, min_distance, signed_volumes, is_sound, assert_solid
(forge run puts forge/lib on PYTHONPATH.)  Ideas adapted from earthtojake/text-to-cad cadgen.geometry (MIT):
exact overlap volume that returns 0 for contact/disjoint, minimum distance, per-solid SIGNED volume
(aggregate volume can hide an inverted member), and BRepAlgoAPI_Check soundness (the verdict a boolean demands of
an operand; stricter than shape.is_valid). All lengths mm."""
from build123d import Shape


def overlap_volume(a, b) -> float:
    """Exact intersection volume of two shapes. 0.0 when disjoint or only touching (build123d's `a & b` can
    return None or an empty Compound, which is how `(a & b).volume` crashes); never raises on non-overlap."""
    x = a & b
    if x is None: return 0.0
    try: return float(sum(s.volume for s in x.solids()))
    except Exception: return 0.0


def min_distance(a, b) -> float:
    """Minimum distance between two shapes (0 if they touch or overlap). Use for 'gap >= CLEAR' asserts."""
    return float(a.distance_to(b))


def signed_volumes(shape):
    """[(solid_index, volume)] per solid. A negative volume = inside-out solid; check each, not the sum."""
    return [(i, float(s.volume)) for i, s in enumerate(shape.solids(), 1)]


def is_sound(shape) -> bool:
    """True if OCCT's BRepAlgoAPI_Check (valid, no self-intersection, no tiny edges) passes. Expensive; gate
    where a failure is plausible (after fillets on odd edges, before a big boolean), not after every op."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
    try: return bool(BRepAlgoAPI_Check(shape.wrapped).IsValid())
    except Exception: return False


def assert_solid(shape, name="part", solids=1):
    """One-call sanity gate for the end of a part script: valid B-rep, sound, N solids, all volumes > 0."""
    assert shape is not None, f"{name}: shape is None"
    assert shape.is_valid, f"{name}: invalid B-rep"
    n = len(shape.solids())
    assert n == solids, f"{name}: expected {solids} solid(s), got {n}"
    neg = [(i, v) for i, v in signed_volumes(shape) if v <= 0]
    assert not neg, f"{name}: non-positive solid volume(s) {neg} (inside-out?)"
    assert is_sound(shape), f"{name}: BRepAlgoAPI_Check failed (self-intersection / tiny edges)"
    return shape
