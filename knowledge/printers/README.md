# Printer profiles

One JSON file per printer. `install.sh` copies the one you pick to `knowledge/printer.json` (your copy, git-ignored);
`forge printer use <name>` does the same later, `forge printer` shows the active one with every number's source.
`FORGE_PRINTER=/path/to/profile.json` points forge at another file. Missing file = the generic 220 x 220 x 250 mm, 0.4 nozzle profile.

## Keys
| key | what | used by |
|---|---|---|
| `bed` | build volume X, Y, Z in mm (the maker's nominal; shrink a few mm if your usable area is smaller) | bed-fit check, split, plate |
| `nozzle`, `layer`, `material` | your stock profile | preflight layer slicing, wall minimums |
| `slicer_cmd` | optional shell template with `{stl}` and `{supports}` whose output has `printing time: ...` and `total filament used [g]: ...` lines | print time and grams in reports |
| `support_angle` | slope from horizontal below which your slicer auto-supports a face (deg) | auto-support trap check |
| `support_trap_gap` | the biggest gap (mm) an auto support would fill between two bodies | auto-support trap check |
| `bridge_mm` | longest unsupported span anchored on two sides that still prints (mm) | preflight bridges vs overhangs |
| `overhang_deg` | steepest overhang from horizontal that prints without support (deg) | preflight + verify overhang checks |
| `min_wall_mm` | thinnest wall that prints at all (mm) | preflight thin-wall check, verify default |
| `first_layer_fuse_mm` | first-layer gap below which elephant foot welds two bodies (mm) | preflight print-in-place check |
| `overhang_area_mm2` | unsupported overhang area (not bridges) a part may carry before supports are demanded | preflight overhang check |
| `sources` | one line per key saying where the number came from; `UNVERIFIED` when nobody has checked it | `forge printer`, humans |

Every threshold preflight uses is one of these keys, so "why 18 mm?" has an answer in the file. Measured print-in-place gaps
are a different thing: they are per user (`knowledge/fit.json`, `forge fit set`) and the shared record is `knowledge/fit-table.md`.

## Adding a printer
Copy `anycubic-kobra-x.json`, change the numbers you can back up, and write a source line for each one
(a spec-page URL for the bed, the slicer's documented default for `support_angle`). Leave a value at the generic default and say
`UNVERIFIED` in `sources` rather than inventing a number. The installer's printer menu lists every file in this folder by its `name`.
