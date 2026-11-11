"""Print-in-place cycloidal speed reducer (default CYCLO-11: 12 pins, 11 lobes, 11:1, four bodies, one plate, no supports).

Layout (Z up, bed at Z = 0, main axis = Z): every body grows from the bed, every overhang is a 45-degree cone.
  housing (fixed): ring wall with N merged pins, 45-deg ceiling cone, top ring with a scale.
  disc          : the exact cycloid profile (lib/cycloid.py), eccentric by e, with 6 output holes and a bore round the cam.
  carrier (out) : 6 pins through the disc holes (flared at the bed), plate over the stack, pointer turret.
  shaft (input) : cam under the carrier bore, shaft up through it, knob on top.
Motions: `reduce` (one full input turn), `mesh` (one pin pitch, fine), `engage` (carrier-only control).
Everything is parametric: `forge mech build cycloidal N=16 R=45` makes a 15:1.
"""
import math, os, sys
import numpy as np
from build123d import *
from .core import Mech, Motion, Move, CEN, zcyl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fit
import cycloid

SQ2 = math.sqrt(2)


def _cone(r0, r1, h, z=0.0, x=0.0, y=0.0):
    return Pos(x, y, z) * Cone(r0, r1, h, align=CEN)


def build(N=12, R=38.0, r_p=3.0, e=1.5, R_o=17.0, N_o=6, H=10.0, gap=None, r_c=8.0, r_s=6.0, r_o=3.0, vgap=None, n=1440, label=None):
    g = fit.get("pip_gap") if gap is None else gap
    gv = fit.get("pip_vgap") if vgap is None else vgap
    w = fit.get("min_wall")
    NL = N - 1
    chk = cycloid.checks(N, R, r_p, e, g)              # raises on an undercut / bad profile
    assert r_c >= r_s + e + 0.5, "cam must be wide enough to stay trapped under the carrier bore"
    # housing wall must clear the farthest lobe tip over the whole cycle (a tip reaches ~R - r_p + e + ... into the pin gaps)
    P = np.array(cycloid.disc_pts(N, R, r_p, e, g, 720))
    reach = 0.0
    for d in np.arange(0.0, 360.0, 1.0):
        a_ = math.radians(-d / NL); c, s_ = math.cos(a_), math.sin(a_)
        q = np.stack([c * P[:, 0] - s_ * P[:, 1], s_ * P[:, 0] + c * P[:, 1]], 1) + e * np.array([math.cos(math.radians(d)), math.sin(math.radians(d))])
        reach = max(reach, float(np.hypot(q[:, 0], q[:, 1]).max()))
    wall_r = math.ceil((reach + g) * 10) / 10          # 37.9 for the default (the tips reach 37.55 from the axis)
    zp = H + gv                                         # housing pin / carrier pin top = disc top + vertical gap (10.3)
    out_r = R + 5.0                                     # 43
    # ------------------------------------------------------------ housing
    hz_top = 20.0
    bore_top = wall_r - 7.5
    cone_h = wall_r - bore_top                          # 45-degree ceiling: 7.5 for the default
    cut = zcyl(wall_r, zp) + _cone(wall_r, bore_top, cone_h, zp) + zcyl(bore_top, hz_top, z=zp + cone_h - 0.001)
    housing = zcyl(out_r, hz_top) - cut
    for k in range(N):
        a = 2 * math.pi * k / N
        housing += zcyl(r_p, zp, R * math.cos(a), R * math.sin(a))
    # scale on the top ring: NL ticks every 360/NL deg, the "0" tick doubled
    tick_r0, tick_r1 = bore_top + 1.0, bore_top + 5.0
    for k in range(NL):
        for off in ((0.0,) if k else (-1.8, 1.8)):
            housing += Rot(0, 0, 360.0 * k / NL) * (Pos((tick_r0 + tick_r1) / 2, off, hz_top) * Box(tick_r1 - tick_r0, w + 0.4, 0.6, align=CEN))
    # engraved text round the outer wall: one glyph at a time, each a flat cutter 0.6 deep
    txt = label if label is not None else f"CYCLO-{NL}  {NL}:1"
    step = 6.4 / out_r                                  # rad per glyph
    a0 = math.radians(35.0) - step * (len(txt) - 1) / 2     # centred on the 35-deg side (where the product camera looks), reads left to right
    for i, ch in enumerate(txt):
        if ch == " ":
            continue
        a = a0 + step * i
        try:
            sk = Text(ch, font_size=6.0, font="Arial", align=(Align.CENTER, Align.CENTER))
        except Exception:
            sk = Text(ch, font_size=6.0, align=(Align.CENTER, Align.CENTER))
        pl = Plane(origin=(out_r - 0.6, 0, 6.0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
        housing -= Rot(0, 0, math.degrees(a)) * (pl.location * extrude(sk, 2.0))
    # ------------------------------------------------------------ disc (built about its own centre, then moved to (e, 0))
    pts = cycloid.disc_pts(N, R, r_p, e, g, n)
    prof = Polygon(*pts[::-1])   # CCW so the extrusion goes up (+Z)
    disc = extrude(prof, H)
    disc -= zcyl(r_c + g, H + 1, z=-0.5)
    flare_r0, flare_h = r_o + 1.3, 1.3
    for k in range(N_o):
        a = 2 * math.pi * k / N_o
        x, y = R_o * math.cos(a), R_o * math.sin(a)
        r_h = r_o + e + g
        disc -= zcyl(r_h, H + 1, x, y, z=-0.5)
        rc0 = flare_r0 + e + g + gv * SQ2                # counter-cone: flare offset by the rolling clearance + gv*sqrt(2)
        disc -= _cone(rc0, r_h, rc0 - r_h, 0.0, x, y)
    disc = Pos(e, 0, 0) * disc
    # ------------------------------------------------------------ carrier
    carrier = zcyl(22.0, 14.0 - zp, z=zp) - zcyl(r_s + g, 20, z=zp - 1)
    for k in range(N_o):
        a = 2 * math.pi * k / N_o
        x, y = R_o * math.cos(a), R_o * math.sin(a)
        carrier += zcyl(r_o, zp + 0.1, x, y) + _cone(flare_r0, r_o, flare_h, 0.0, x, y)
    ring = zcyl(22.0, 21.0 - 14.0, z=14.0) - zcyl(19.0, 8.0, z=13.9)
    carrier += ring
    # pointer tab (4 wide), 45-degree gusset underneath so nothing overhangs flat
    tab = Pos(0, 2.0, 0) * Rot(90, 0, 0) * extrude(Polygon((21.5, 17.0), (24.0, 19.0), (24.0, 21.0), (21.5, 21.0), align=None), 4.0)
    carrier += tab
    # ------------------------------------------------------------ shaft
    cam = zcyl(r_c, H, x=e)
    sh = zcyl(r_s, 14.3 - H + 0.1, z=H - 0.1)
    kz0, kh = 14.3, 6.0
    knob = _cone(r_s, r_s + kh, kh, kz0) + zcyl(r_s + kh, 24.0 - (kz0 + kh), z=kz0 + kh)
    knob -= Pos(0, 0, 24.0 - 4.0) * extrude(RegularPolygon(3.0, 6, major_radius=False), 4.5)
    knob -= Pos(r_s + kh - 1.0, 0, 24.0 - 1.5) * Box(3.0, 2.0, 3.2, align=CEN)
    shaft = cam + sh + knob
    parts = {"housing": housing, "disc": disc, "carrier": carrier, "shaft": shaft}
    # ------------------------------------------------------------ motions
    pit = (e, 0, 0)
    common = [Move("shaft", "rot"),
              Move("disc", "rot", pivot=pit, ratio=-(N / NL)), Move("disc", "rot", ratio=1.0),
              Move("carrier", "rot", ratio=-1.0 / NL)]
    reduce_ = Motion("reduce", (0, 360), list(common),
                     control=[Move("disc", "rot", pivot=pit, amount=360.0 / NL / 2)], steps=37,
                     note=f"one full input turn: output turns {NL}:1 slower, opposite way")
    mesh = Motion("mesh", (0, 360.0 / N), list(common),
                  control=[Move("shaft", "rot", amount=180.0)], steps=13,
                  note="one pin pitch, fine sweep (2.5 deg); the cam alone must jam in the disc bore")
    engage = Motion("engage", (0, 0), [], control=[Move("carrier", "rot", amount=20.0)], steps=1,
                    note="carrier alone: its pins must hit the disc hole walls")
    name = f"cyclo{NL}" if (N, R) == (12, 38.0) else f"cycloidal{NL}"
    meta = {"N": N, "lobes": NL, "ratio": NL, "output_sign": -1, "input": "shaft", "output": "carrier", "R": R, "r_p": r_p, "e": e, "gap": g, "vgap": gv,
            "gap_pose": ("reduce", 0), "explode": {"shaft": (0, 0, 70), "carrier": (0, 0, 45), "disc": (0, 0, 20), "housing": (0, 0, 0)},
            "diameter": round(2 * out_r, 1), "height": 24.0, "profile": chk, "wall_r": wall_r, "tip_reach": round(reach, 3),
            "accent": {"disc": "orange"},      # studio render: this part orange, the rest graphite
            "ice": [{"part": "carrier", "box": [22.05, -2.05, 16.9, 24.1, 2.05, 21.05]},                       # pointer tab
                    {"part": "shaft", "box": [r_s + 6.0 - 2.6, -1.05, 20.8, r_s + 6.0 + 0.1, 1.05, 24.05]}]}      # knob notch
    return Mech(name, parts, ["housing"], [reduce_, mesh, engage], meta=meta)
