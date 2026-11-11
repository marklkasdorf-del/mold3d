// forge starter: OpenSCAD part (lane scad).  forge/bin/forge run part_scad.scad --name mypart
// forge calls:  openscad --backend=Manifold -o $FORGE_OUT_STL part_scad.scad
// Units mm. Origin: part sits on Z=0 (bed), centred in X/Y. Parameter block -> one module per feature -> assemble.
// Example: tray with chamfered bottom edge, corner screw holes, optional # debug on cutters.
include <BOSL2/std.scad>

$fn = 64;            // set it or curves are blocky ($fn on EVERY curved thing via this global)

// ---------------- PARAMETERS (mm) ----------------
LENGTH = 80;  WIDTH = 50;  HEIGHT = 20;
WALL = 2.4;   FLOOR = 2.4;           // >=1.2 min, 2.0+ recommended
CORNER_R = 4; BOTTOM_CH = 1.0;       // chamfer (not round) on the bed-side edge
HOLE_D = 3.4; HOLE_INSET = 8;        // M3 clearance
EPS = 0.01;                          // cutters overshoot by EPS -> no coplanar faces / z-fighting

// ---------------- FEATURES ----------------
module body() {
    // BOSL2 cuboid() cannot take rounding AND chamfer together (assertion), so hull a chamfer ring under the full slab.
    hull() {
        translate([0, 0, BOTTOM_CH])
            linear_extrude(HEIGHT - BOTTOM_CH) rect([LENGTH, WIDTH], rounding=CORNER_R);
        linear_extrude(EPS)
            rect([LENGTH - 2*BOTTOM_CH, WIDTH - 2*BOTTOM_CH], rounding=max(CORNER_R - BOTTOM_CH, 0.5));
    }
}
module cavity() {
    translate([0, 0, FLOOR])
        cuboid([LENGTH - 2*WALL, WIDTH - 2*WALL, HEIGHT], rounding=max(CORNER_R - WALL, 0.5), edges="Z", anchor=BOTTOM);
}
module screw_holes() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx*(LENGTH/2 - HOLE_INSET), sy*(WIDTH/2 - HOLE_INSET), -EPS])
            cylinder(d=HOLE_D, h=FLOOR + 2*EPS);          // prefix with # to see the cutter in preview
}

// ---------------- ASSEMBLE ----------------
difference() {
    body();
    cavity();
    screw_holes();
}
// forge/bin/verify asserts volume + bbox after export: SCAD cannot check itself (silent boolean drops).
