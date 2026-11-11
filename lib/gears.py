"""gears.py: involute spur + herringbone gears for build123d (no bd_warehouse needed). Proven in bench 2026-10-17:
herringbone planetary Zs15/Zp15x3/Zr45, m1.6, C=0.2/flank -> 0.36 mm min gap, sweep CLEAR, prints as one plate.
    from gears import gear_face, herringbone, set_params
    sun = herringbone(offset(gear_face(15), -0.2, kind=Kind.INTERSECTION), 15*1.6/2, +1)
    ring cutter: offset(gear_face(45, internal=True), +0.2, kind=Kind.ARC)   # INTERSECTION offset fails outward
Planet phasing: planet at angle phi rotates phi*(1+Zs/Zp). Planetary needs Zr=Zs+2Zp and (Zs+Zr)/N integer.
Helix hands: sun +1, planets -1, ring -1 (external pair opposite, internal pair same).
"""
from build123d import *
import math
M = 1.6
H = 14.0
BETA = math.radians(25)
PA = math.radians(20)

def set_params(module=None, height=None, helix_deg=None):
    global M, H, BETA
    if module: M = module
    if height: H = height
    if helix_deg is not None: BETA = math.radians(helix_deg)

def involute_gear_pts(z, m, ha, hf, steps=8):
    r = z * m / 2; rb = r * math.cos(PA); ra = r + ha; rf = r - hf
    inv = lambda a: math.tan(a) - a
    half = math.pi / (2 * z) + inv(PA)          # half tooth angle at the base circle
    tmax = math.sqrt((ra / rb) ** 2 - 1)
    t0 = math.sqrt(max((max(rf, rb) / rb) ** 2 - 1, 0))
    flank = []
    for i in range(steps + 1):
        t = t0 + (tmax - t0) * i / steps
        x, y = rb * (math.cos(t) + t * math.sin(t)), rb * (math.sin(t) - t * math.cos(t))
        rr, ang = math.hypot(x, y), math.atan2(y, x)
        flank.append((rr, half - ang))           # angle measured from tooth centre
    pts = []
    for k in range(z):
        c = 2 * math.pi * k / z
        tooth = []
        if rf < rb: tooth.append((rf, flank[0][1]))
        tooth += flank
        side = [(rr, c - a) for rr, a in tooth] + [(rr, c + a) for rr, a in reversed(tooth)]
        pts += [(rr * math.cos(a), rr * math.sin(a)) for rr, a in side]
    return pts

def gear_face(z, internal=False):
    if internal:   # cutter for ring: external gear with long addendum (tip room for planets)
        return Polygon(*involute_gear_pts(z, M, 1.25 * M, 1.0 * M), align=None)
    return Polygon(*involute_gear_pts(z, M, 1.0 * M, 1.25 * M), align=None)

def herringbone(face, r_pitch, sign, z0=0):
    """face at z=0 -> twisted up H/2 then back. sign = helix hand."""
    face = face.faces()[0] if not isinstance(face, Face) else face
    tw = math.degrees(sign * (H / 2) * math.tan(BETA) / r_pitch)
    low = Solid.extrude_linear_with_rotation(face, (0, 0, 0), (0, 0, H / 2), tw)
    up_face = face.rotate(Axis.Z, tw).moved(Location((0, 0, H / 2)))
    up = Solid.extrude_linear_with_rotation(up_face, (0, 0, H / 2), (0, 0, H / 2), -tw)
    return low.fuse(up).clean()

