# The simple questionnaire (vague requests) and the ASSUMED convention

Goal: never guess a number that decides whether the part FITS or WORKS, and never nag about anything else.

## Ask only about these
Fit interfaces and function: what it attaches to or holds (device model, object size), a screw or bolt size, a slot or hole the part must match, a load or span, which side an opening faces when it matters.

## Never ask about (use a safe default, state it)
Color, fillet radius, wall thickness above the minimum, text font, logo placement, anything the user can change in one re-run.

## Step 1: look it up first
If a number can be found (`forge parts-find`, `knowledge/devices.json`, a datasheet via web search, `forge photofit`), find it instead of asking. Ask only about what is left.

## Step 2: ask 1-3 questions, multiple choice
Each question has 2-4 options with smart defaults, and the user can always type their own:
- common sizes ("M3", "M4", "M5")
- "standard <device> size (I'll look it up)"
- "I'll measure it" (then offer `forge photofit mat` or calipers)

In Claude Code use the AskUserQuestion tool (one call, up to 3 questions). In Codex or any agent without that tool, send a short numbered list, each item with its default marked:

```
Two quick questions so it fits:
1. What does it clamp onto?  (a) 25 mm tube  (b) 32 mm tube  (c) other: tell me the diameter   [default a]
2. Screw size?  (a) M3  (b) M4  (c) I'll measure   [default a]
Reply "go" to use the defaults.
```

## Step 3: "just make it" / no answer
Proceed with the defaults and record each one as ASSUMED in the design's `spec.json`.

## The fit block: every fit number carries its source
Numbers that decide whether the part FITS something go under `fit`, each with where it came from:

```json
{
  "fit": {
    "pod diameter":         {"mm": 38.2, "source": "measured", "note": "calipers"},
    "screw clearance hole": {"mm": 3.4,  "source": "parts-find", "ref": "ISO 4762 M3"},
    "tube diameter":        {"mm": 25,   "source": "ASSUMED", "fix": "ask: what tube diameter? (default 25)"}
  }
}
```

Sources: `measured` (calipers, ruler), `datasheet` (maker's spec page, cite it in spec.md), `parts-find` (`forge parts-find`), `photofit` (`forge photofit`), `user` (the user typed the number), `library` (`knowledge/devices.json` or `knowledge/objects.json`, which carry their own sources), `ASSUMED` (a default nobody confirmed). A missing or made-up source counts as ASSUMED. Only `fit` entries are judged: walls, fillets, colours never nag.

The older shorthand still works and means the same thing: `{ "assumed": { "tube diameter": "25 mm", "screw": "M3" } }`.

What happens next:
- `forge verify <stl> --spec spec.json` adds a line: `WARN  NOT FIT-CHECKED: tube diameter is assumed. Fix: ...` (a warning, not a failure: the build can finish, but it is not green).
- `forge report <dir>` stamps the header **NOT FIT-CHECKED** and adds a `Fit` row naming the assumed numbers and the cheapest fix; the `Assumed` row lists them all. With every fit number sourced the row reads `fit-checked: 3 fit numbers sourced (2 measured, 1 parts-find)`. No fit block, no row.
- The cheapest fix is picked from the name (screw/bearing/motor -> `forge parts-find`; phone/board/device -> the maker's spec sheet; outline/pocket -> `forge photofit`; anything else -> one question with the default). Set `"fix"` on the entry to override it.

Never list a number as assumed if the user or a datasheet gave it. After a stamped report, offer the fix in one line: "Tell me the real tube diameter and I'll rebuild."
