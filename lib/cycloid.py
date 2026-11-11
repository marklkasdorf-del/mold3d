"""cycloid.py: exact cycloidal-disc profile for a cycloidal speed reducer (N pins, N-1 lobes, ratio N-1 : 1).

    pts = disc_pts(N=12, R=38, r_p=3, e=1.5, gap=0.3)   # closed loop, centred on the DISC centre (not the axis)
    checks(N, R, r_p, e, gap)                           # dict: valid, lobes, r_max, r_min, rho_min, undercut ... (raises on a bad profile)
    pin_ring_face(N, R, r_p, wall_r)                    # build123d face: housing ring wall with N merged pins

The pin circle has radius R; pins are inflated by `gap` so the clearance to the lobes is uniform along the whole flank.
At drive 0 the disc centre sits at (e, 0) and the valley of the profile faces the pin at angle 0 (+X).
"""
import math
import numpy as np


def _base(N, R, e, n):
    """the epitrochoid that the pin CENTRES trace relative to the disc (Rr = 0)."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return t, R * np.cos(t) - e * np.cos(N * t), -R * np.sin(t) + e * np.sin(N * t)


def disc_pts(N=12, R=38.0, r_p=3.0, e=1.5, gap=0.3, n=1440):
    Rr = r_p + gap
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    psi = np.arctan2(np.sin((1 - N) * t), R / (e * N) - np.cos((1 - N) * t))
    x = R * np.cos(t) - Rr * np.cos(t + psi) - e * np.cos(N * t)
    y = -R * np.sin(t) + Rr * np.sin(t + psi) + e * np.sin(N * t)
    return [(float(a), float(b)) for a, b in zip(x, y)]


def _rho_min_convex(N, R, e):
    """smallest radius of curvature over the CONVEX parts of the pin-centre epitrochoid (those are what an inflated pin can undercut)."""
    t = np.linspace(0, 2 * math.pi, 20000, endpoint=False)
    dx = -R * np.sin(t) + e * N * np.sin(N * t);  dy = -R * np.cos(t) + e * N * np.cos(N * t)
    ddx = -R * np.cos(t) + e * N * N * np.cos(N * t); ddy = R * np.sin(t) - e * N * N * np.sin(N * t)
    k = (dx * ddy - dy * ddx) / (dx * dx + dy * dy) ** 1.5      # signed curvature
    x = R * np.cos(t) - e * np.cos(N * t); y = -R * np.sin(t) + e * np.sin(N * t)
    area = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
    if area < 0:
        k = -k                                                  # make CCW positive: positive k = convex
    conv = k > 1e-9
    return float((1.0 / k[conv]).min()) if conv.any() else float("inf")


def checks(N=12, R=38.0, r_p=3.0, e=1.5, gap=0.3, strict=True):
    """verify the profile; raises ValueError when strict and anything is wrong. Returns the numbers."""
    from shapely.geometry import Polygon
    pts = disc_pts(N, R, r_p, e, gap)
    Rr = r_p + gap
    P = Polygon(pts)
    r = np.hypot(*np.array(pts).T)
    # lobe count = number of local maxima of |r| (cyclic)
    lobes = int(np.sum((r > np.roll(r, 1)) & (r >= np.roll(r, -1)) & (r > r.mean())))
    rho = _rho_min_convex(N, R, e)
    out = {"valid": bool(P.is_valid and P.is_simple if hasattr(P, "is_simple") else P.is_valid), "lobes": lobes,
           "r_max": round(float(r.max()), 3), "r_min": round(float(r.min()), 3),
           "r_max_expected": round(R - Rr + e, 3), "r_min_expected": round(R - Rr - e, 3),
           "rho_min": round(rho, 3), "pin_radius_inflated": round(Rr, 3), "undercut": bool(rho <= Rr),
           "e_over_pitch": round(e / (R / N), 3), "area_mm2": round(P.area, 2)}
    errs = []
    if not out["valid"]: errs.append("profile polygon is not simple/valid")
    if lobes != N - 1: errs.append(f"{lobes} lobes, expected {N - 1}")
    if abs(out["r_max"] - out["r_max_expected"]) > 0.05: errs.append(f"r_max {out['r_max']} != {out['r_max_expected']} +-0.05")
    if out["r_min"] < out["r_min_expected"] - 0.05: errs.append(f"r_min {out['r_min']} < {out['r_min_expected']}")
    if out["undercut"]: errs.append(f"undercut: min radius of curvature {rho:.2f} <= inflated pin radius {Rr:.2f} (shrink the pin or the eccentricity)")
    if 2 * R * math.sin(math.pi / N) <= 2 * Rr: errs.append(f"neighbouring pins overlap: spacing {2 * R * math.sin(math.pi / N):.2f} <= 2 x {Rr:.2f}")
    if e >= R / N: errs.append(f"eccentricity {e} must be < R/N = {R / N:.2f}")
    out["errors"] = errs
    if strict and errs:
        raise ValueError("cycloid profile: " + "; ".join(errs))
    return out


def pin_ring_face(N=12, R=38.0, r_p=3.0, wall_r=37.5, outer_r=43.0):
    """housing ring (inner wall radius wall_r, outer outer_r) with N pins of radius r_p on circle R, first pin at +X, merged into the wall."""
    from build123d import Circle, Pos
    f = Circle(outer_r) - Circle(wall_r)
    for k in range(N):
        a = 2 * math.pi * k / N
        f = f + Pos(R * math.cos(a), R * math.sin(a)) * Circle(r_p)
    return f
