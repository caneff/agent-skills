# LMD page template

One shared skeleton, four values that differ by `layout` (`"two"` vs `"one"`,
picked in SKILL.md). Everything else — epigraph, `#ddf` rules bar, rule block
markup — is identical in both.

| Placeholder | `layout == "two"` | `layout == "one"` |
|---|---|---|
| `{{SECTION_MAX_WIDTH}}` | `820px` | `840px` |
| `{{IMAGE_WIDTH}}` | `420` | `600` |
| `{{IMAGE_FLEX}}` | `flex: 3 1 320px;` | `flex: 1 1 100%;` |
| `{{ASIDE_FLEX}}` | `flex: 2 1 280px;` | `flex: 1 1 100%; max-width: 780px; margin: 0 auto;` |

Two-column keeps the image and Rules card side by side (`~3:2` split) for
shorter rulesets. One-column stacks a large centered image above a wide,
full-width Rules card for long rulesets — the card is wide *and*
gutter-free because its `<ul>`/`<li>` carry `max-width: none` (see the
gutter gotcha in SKILL.md), so the text fills the card instead of wrapping
short. `flex-wrap` stacks both variants vertically on narrow screens.

```html
<section style="max-width: {{SECTION_MAX_WIDTH}}; margin: 20px auto; background: #fafaff; border: 1px solid #ddf; border-radius: 8px; padding: 26px 30px;">
  <!-- Intro: only when notes given. Omit this whole <p> (no header, no placeholder) if there are none.
       Author's-note epigraph — italic, centered, muted, hairline divider beneath.
       Text is capped at 620px and centered; the divider rule spans the full column. -->
  <p style="margin: 0 auto 20px; padding-bottom: 15px; border-bottom: 1px solid #ccd; font-style: italic; text-align: center; color: #555; line-height: 1.6;">
    <span style="display: block; max-width: 620px; margin: 0 auto;">{{NOTES}}</span>
  </p>

  <!-- Image left, Rules card right (or stacked, one-column). flex-wrap stacks them on narrow screens. -->
  <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: stretch;">
    <div style="{{IMAGE_FLEX}} text-align: center;">
      <a href="{{SUDOKUPAD_LINK}}"><img:{{IMAGE_ID}} width="{{IMAGE_WIDTH}}" style="max-width: 100%; display: block; margin: 0 auto;"></a>
      <div style="margin-top: 8px;"><a href="{{SUDOKUPAD_LINK}}" style="color: #557; font-weight: bold; text-decoration: none;">Play Now! &rarr;</a></div>
    </div>
    <aside style="{{ASIDE_FLEX}} background: #eef; border: 1px solid #ddf; border-radius: 5px; overflow: hidden;">
      <div style="background: #ddf; padding: 8px 18px; font-weight: bold;">Rules</div>
      <div style="padding: 16px 18px;">
        <div style="margin-bottom: 14px; line-height: 1.5;"><strong style="display: block;">{{RULE_NAME}}</strong><ul style="color: #444; margin: 4px 0 0; padding-left: 18px; max-width: none;"><li style="max-width: none;">{{RULE_POINT}}</li></ul></div>
        <!-- one block per rule (last uses margin-bottom: 0). One <li> per bullet point.
             A single-statement rule is still a <ul> with one <li> — always bullet. -->
      </div>
    </aside>
  </div>
</section>
```
