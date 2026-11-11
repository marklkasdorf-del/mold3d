// scad lane: 30x30x4 plate with a 8 mm peg and 3 mm chamfer-free slot; tests Manifold backend
$fn = 64;
union() {
  cube([30, 30, 4]);
  translate([15, 15, 3.99]) cylinder(d = 8, h = 10);
}
