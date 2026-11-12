# CYCLO-11: PRINT NOTE

Print `cyclo11_SUPPORTS-OFF.3mf` (not the STL): supports OFF, no brim, stock profile, nothing else changed.
Why: the 0.30 mm gaps are print-in-place clearances; a slicer's "auto supports" puts supports under the flat carrier underside
(z = 10.3, 0.3 mm over the disc) and they fill the gap and weld the parts. `forge preflight` reports this as "SUPPORTS: OFF (required)",
and `forge export examples/cyclo11/cyclo11.stl` wrote the 3MF that carries that into the slicer. After opening it, check the Support box is UNTICKED.
