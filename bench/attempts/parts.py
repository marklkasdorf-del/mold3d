# Blind benchmark attempt (2026-10-17). Input = part name/standard only; dims from the model's own knowledge.
# Ground truth (STEP from step.parts, not included) was not opened. One function per part; exports bench/attempts/<id>.stl
from build123d import *
import math, pathlib
OUT = pathlib.Path(__file__).parent

def nut_m8():  # ISO 4032 M8: s=13 AF, m=6.8, 30deg chamfer both faces, bore = thread minor 6.647
    s, m = 13.0, 6.8
    body = extrude(RegularPolygon(s / 2, 6, major_radius=False), m)
    e = s / math.cos(math.radians(30))
    # 30deg chamfer: intersect with double cone, chamfer starts at dw ~ 0.95*s
    dw = 0.95 * s; h = (e - dw) / 2 * math.tan(math.radians(30))
    cone = Solid.make_cone(dw / 2, dw / 2 + (m / 2) / math.tan(math.radians(30)), m / 2) \
         + Solid.make_cone(dw / 2 + (m / 2) / math.tan(math.radians(30)), dw / 2, m / 2, Plane.XY.offset(m / 2))
    body = body & cone
    return body - Cylinder(6.647 / 2, m, align=(Align.CENTER, Align.CENTER, Align.MIN))

def bearing_608zz():  # 8 x 22 x 7, shields recessed 0.3 between ring lands
    d, D, B = 8, 22, 7
    a = (Cylinder(D / 2, B) - Cylinder(d / 2, B)).moved(Location((0, 0, B / 2)))
    for z in (B - 0.3, 0):  # shield recess annulus 12.2..19.2
        a -= Pos(0, 0, z) * (Cylinder(19.2 / 2, 0.3, align=(Align.CENTER, Align.CENTER, Align.MIN))
                             - Cylinder(12.2 / 2, 0.3, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    return a

def shcs_m5x16():  # ISO 4762 M5x16: dk=8.5 k=5, hex s=4 depth 2.5 (+cone), shank 5 x 16
    head = Cylinder(8.5 / 2, 5, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((0, 0, 16)))
    head = chamfer(head.edges().group_by(Axis.Z)[-1], 0.4)
    sock = Pos(0, 0, 21 - 2.5) * extrude(RegularPolygon(4 / 2, 6, major_radius=False), 2.5)
    cone = Solid.make_cone(0.01, 4 / 2 / math.cos(math.radians(30)), 4 * 0.29 / 2 * 1.15, Plane.XY.offset(21 - 2.5 - 0.66))
    shank = Cylinder(2.5, 16, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shank = chamfer(shank.edges().group_by(Axis.Z)[0], 0.5)
    return head + shank - sock - cone

def nema17_40():  # 42.3 sq x 40 body, corner chamfer 4.5, 22x2 pilot, 5x24 shaft w/ D-flat, M3 holes @31 x4.5 deep
    W, L = 42.3, 40
    body = Box(W, W, L, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = chamfer(body.edges().filter_by(Axis.Z), 4.5)
    body += Pos(0, 0, L) * Cylinder(11, 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shaft = Pos(0, 0, L) * Cylinder(2.5, 24, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shaft -= Pos(2.5 - 0.5 + 5, 0, L + 24 - 7.5) * Box(10, 10, 15)  # D-flat 0.5 deep, 15 long
    body += shaft
    for x in (-15.5, 15.5):
        for y in (-15.5, 15.5):
            body -= Pos(x, y, L - 4.5) * Cylinder(1.25, 4.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return body

def profile_2020_l50():  # B-type slot 6: opening 6.2, lip 1.8, T cavity 11 wide to depth 6.1 w/ 45deg floor, core bore 4.2
    sk = Rectangle(20, 20)
    slot = Polygon((-3.1, 10.1), (3.1, 10.1), (3.1, 8.2), (5.5, 8.2), (5.5, 6.4), (2.9, 3.9),
                   (-2.9, 3.9), (-5.5, 6.4), (-5.5, 8.2), (-3.1, 8.2), align=None)
    for k in range(4):
        sk -= Rot(0, 0, 90 * k) * slot
    sk -= Circle(2.1)
    return extrude(sk, 50)

def gt2_20t_b5_w6():  # PD 12.73, OD 12.22, groove r~0.555; hub 16x7 + flanges 18x1, teeth 7, bore 5, 2x M3 set
    OD = 12.22; n = 20
    teeth = Cylinder(OD / 2, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))
    rc = OD / 2 - 0.75 + 0.555
    for k in range(n):
        a = 2 * math.pi * k / n
        teeth -= Pos(rc * math.cos(a), rc * math.sin(a), 0) * Cylinder(0.555, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))
    p = Cylinder(8, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))
    p += Pos(0, 0, 7) * Cylinder(9, 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    p += Pos(0, 0, 8) * teeth
    p += Pos(0, 0, 15) * Cylinder(9, 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    p -= Cylinder(2.5, 16, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for ang in (0, 90):
        p -= Pos(0, 0, 3.5) * Rot(0, 0, ang) * Rot(0, 90, 0) * Cylinder(1.25, 9, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return p

PARTS = {"iso4032_hex_nut_m8": nut_m8, "bearing_608zz": bearing_608zz,
         "iso4762_socket_head_cap_screw_m5x16": shcs_m5x16,
         "stepper_motor_nema17_l0040_single_shaft": nema17_40,
         "profile_2020_b_slot6_a_l50": profile_2020_l50, "gt2_pulley_20t_bore5_w6": gt2_20t_b5_w6}
for k, f in PARTS.items():
    s = f()
    export_stl(s, str(OUT / f"{k}.stl"))
    print(f"{k:42s} vol={s.volume:9.1f} valid={s.is_valid} solids={len(s.solids())} bbox={[round(v,2) for v in s.bounding_box().size]}")
