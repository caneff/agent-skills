---
name: visual-teach
description: "`visual-teach` is the styling + behavior floor under every teaching lesson — link its Base first, then use ready-made `vt-*` blocks for the standard parts. The floor goes under any lesson HTML (especially `/teach`), including heavily custom or interactive ones: use the blocks for the commodity parts and build your bespoke exercise on top, never instead of it."
---

# visual-teach

**Seeding — first action:** copy all assets into the workspace in one shot:

```sh
cp -R "<this skill's assets dir>"/* ./assets/
```

Use the skill base directory announced when this skill loads; do **not** hardcode a developer checkout path. Then open **`assets/visual-teach.md`** — the catalog lists every block with a "reach for when…" trigger, the page shell for new lessons, and linking instructions.

**Floor, not a ceiling:** `vt-*` covers commodity parts. When the lesson's win is to _produce or manipulate_ something live (write a regex, flex a layout), build a bespoke exercise in `./assets/` alongside the `vt-*` blocks — don't settle for a quiz that only tests recognition.
