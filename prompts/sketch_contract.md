# Sketch contract

A sketch is a plain-text wireframe in three parts, in this order, each under its own heading line:

```
DESKTOP 1440px
<the page as an ASCII box chart, at most 96 characters wide>

MOBILE 375px
<one line per section: how it reflows, what moves or is dropped>

NOTES
<2–4 numbered notes explaining why a part is shaped this way for these users>
```

## Notation

| Mark | Means |
| --- | --- |
| `+-- hero ----...+` | A page section. The top border names its section id. One box per section, in the direction's order. |
| `\|` and `+---+` inside a section | Columns, cards and panels. Their widths show their relative size at 1440px. |
| `# Text` | Page headline (h1). Only one. |
| `## Text` / `### Text` | Section heading / card or item heading. |
| `[[ Label ]]` | Primary button. |
| `[ Label ]` | Secondary button or link-button. |
| `[[ Label ]] -> post` | The button or link goes to another page of the site (its id from the site map). |
| `Label*` in the nav | The page the visitor is on. |
| `[img: what it shows]` | Image, illustration or product visual, described in words. |
| `[____ Label ____]` | Form field. |
| `~~~~~~~~~~` | One line of running body text (placeholder). |
| `(1)` | Marker for note 1 under NOTES. |

## Rules

- Plain ASCII only for the drawing: `+ - | [ ] ( ) # ~ _ : > *`. Every line of the desktop chart is at most 96 characters; keep box edges aligned.
- Show hierarchy through notation, position and space: bigger things get more lines and wider boxes.
- No eyebrow or kicker labels above headings, and no numbered section labels: a heading carries its own weight.
- Write real copy for everything that carries the concept (headlines, sub-heads, CTAs, key labels and numbers). Use `~~~` lines only for running body text.
- Balance side-by-side columns: both sides of a row carry comparable weight. If one side has little to say, give the section one column instead. Notes do not count as content; the full design drops them.
- No colors, fonts, shadows or radii. The direction's mood is shown to the PM next to the sketch.
- Keep it short: roughly 40–90 lines in all.

## Example (two sections)

```
DESKTOP 1440px
+-- hero --------------------------------------------------------------------------------------+
|  # See today's open slots, book in two taps  |  +--------------------------------------+     |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~      |  | [img: today's slots, one row per     |     |
|  ~~~~~~~~~~~~~~~~~~~~~~~~~~                  |  |  physio, next free time marked]      |     |
|  [[ Book a slot ]] -> book  [ Our team ] (1) |  +--------------------------------------+     |
|                                              |                                               |
+----------------------------------------------------------------------------------------------+
+-- how-it-works ------------------------------------------------------------------------------+
|  ## Three steps, no phone call                                                               |
|  +------------------------+  +------------------------+  +------------------------+          |
|  | ### 1 Pick a physio    |  | ### 2 Pick a time      |  | ### 3 Get a reminder   |          |
|  | ~~~~~~~~~~~~~~~~~~~~   |  | ~~~~~~~~~~~~~~~~~~~~   |  | ~~~~~~~~~~~~~~~~~~~~   |  (2)     |
|  +------------------------+  +------------------------+  +------------------------+          |
+----------------------------------------------------------------------------------------------+

MOBILE 375px
hero: copy first, buttons full width; slot visual moves below them
how-it-works: three steps stack, numbers stay as the anchor

NOTES
(1) Booking is the one job; the secondary link is for first-time visitors who need reassurance.
(2) Numbered steps answer "is this harder than calling?" before anyone asks.
```
