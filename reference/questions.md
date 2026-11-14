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
Proceed with the defaults and record each one as ASSUMED. Put them in the design's `spec.json`:

```json
{ "assumed": { "tube diameter": "25 mm", "screw": "M3" } }
```

`forge report <dir>` reads `spec.json` in the design folder (`forge run --spec spec.json` copies it there; otherwise save it next to the STL) and adds an **Assumed** row to the Print Report:

`| Assumed | tube diameter 25 mm; screw M3 (not confirmed, check before you print) |`

No `assumed` key (or an empty one) means no row. Never list a number as assumed if the user or a datasheet gave it. After the report, offer: "Tell me the real tube diameter and I'll rebuild."
