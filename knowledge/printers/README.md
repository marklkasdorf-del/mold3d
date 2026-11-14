# Printer profiles
Copy one over `knowledge/printer.json` (or point `FORGE_PRINTER` at it) and edit bed / nozzle / layer.
`slicer_cmd` is optional: a shell template with `{stl}` and `{supports}` whose output contains
`printing time: ...` and `total filament used [g]: ...` lines (see `lib/printer.py`). Left empty, forge never slices.
Bed sizes here are the manufacturers' nominal build volumes; shrink them a few mm if your real usable area is smaller.
`knowledge/printer.json` is your own copy (git-ignored; `install.sh` creates it). If it is missing, forge uses a generic 220 x 220 x 250 mm, 0.4 nozzle profile.
