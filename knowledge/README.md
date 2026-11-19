# knowledge/

Small, curated, human-and-agent-readable notes the skill reads at session start.

| file | what |
|---|---|
| `printer.json`, `printers/` | active printer profile (bed, nozzle, layer, optional slicer hook) + examples |
| `fit.json` (created by `forge fit set`) | YOUR measured clearances; overrides the research defaults in `lib/fit.py` |
| `moldy-taste.md` (created lazily by Moldy, git-ignored) | what you picked, printed, liked and rejected; shape in `moldy-taste.example.md` |
| `fit-log.md` | one row per real fit print; the audit trail behind `fit.json` |
| `lessons.md` | dated one-line lessons learned while building (read before modeling) |
| `benchmark-2026-10-17.md` | the benchmark write-up (accuracy vs real STEP, movers vs community champions) |
| `mechkit.md`, `mechkit-tests.json` | MechKit catalogue and the latest self-test scoreboard |
| `devices.json` | phone/device dimensions for `forge make stand` (add your own: `forge make devices add NAME WxHxT`) |

Convention: new technique -> `knowledge/<topic>.md` (40 lines max, with a runnable snippet). Never store personal data here.
