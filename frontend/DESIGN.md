# Studio: the UI Agent design system

The app chrome around the designs UI Agent generates. It stays neutral so the generated designs, each with its own palette and fonts, are the only color on the page.

Tokens live in `app/tokens.css`; component styles in `app/globals.css`; icons in `components/Icon.tsx`.

## Principles

1. **The work is the color.** Chrome is zinc greys. Generated sketches, tiles and frames carry all the hue.
2. **Magenta means "this one".** `--accent` marks what is selected, active or current: the picked card, the working agent, the current step, the focused field. Never decoration, never a primary button.
3. **One ink action per panel.** `.btn--primary` (ink: near-black in light, near-white in dark) is the next step. Everything else is a plain `.btn` or a `.link`.
4. **Mono for machine facts.** Geist Mono for run IDs, versions, scores, file names and small uppercase labels (`.eyebrow`, table heads, `dt`). Geist for everything people read.

## Token layers

```
primitives   --zinc-500, --magenta-600, --fs-14, --sp-4, --r-6     raw values; never used in components
     │
     ▼
semantic     --text-muted, --accent, --surface, --bad              what a value is for; light + dark
     │
     ▼
component    --control-h, --card-pad, --card-r, --chip-h           knobs for one component
```

Components use semantic and component tokens only. To retheme, change the semantic layer; to retune a component everywhere, change its component token.

### Color (semantic)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | zinc-50 | zinc-950 | page canvas |
| `--surface` | white | zinc-925 | cards, inputs, top bar |
| `--surface-sunken` | zinc-100 | zinc-900 | wells, tracks, segmented controls, table heads |
| `--text` / `--text-muted` / `--text-faint` | 950 / 600 / 500 | 50 / 400 / #8a8a94 | body / secondary / captions only |
| `--border` / `--border-strong` | 200 / 300 | 800 / 700 | dividers / controls |
| `--primary` / `--on-primary` | zinc-900 / white | zinc-50 / zinc-950 | the one main action |
| `--accent` / `--accent-text` / `--accent-soft` | magenta 500 / 600 / 50 | 400 / 300 / 950 | selection fill-ring / as text / selected background |
| `--ok` `--warn` `--bad` (+ `-soft`) | green / amber / red-orange | lighter on dark | status, always with an icon or label |

All text pairs pass WCAG AA (4.5:1). `--text-faint` is the floor: at least 4.5:1 on every surface, so use it for captions and hints, not for body copy.

### Type

Geist (UI) and Geist Mono (data). Scale: `--fs-12 13 14 15 16 18 22 28 36`. Body is 15px/1.55. **No chrome text below 12px.**

| Role | Style |
|---|---|
| Page title `h1` | 28px (36 on the brief), 600, -0.025em |
| Section `.h2` | 18px, 600 |
| Card title `h3` | 16px, 600 |
| Eyebrow / label | `.eyebrow`: 12px mono, uppercase, +0.08em, `--text-faint` |
| Number | `.num` or `.score`: mono, tabular figures |

### Space, shape, motion

- Spacing on a 4px grid: `--sp-1` (4) … `--sp-16` (64).
- Radii are small: controls `--r-6`, cards `--r-8`, the floating decision bar `--r-12`, chips `--r-full`.
- Durations: `--dur-1` 120ms (hover), `--dur-2` 180ms (state), `--dur-3` 320ms (agent graph). Ease: `--ease-out`.
- `prefers-reduced-motion` turns off all animation.

## Components

| Class | Notes |
|---|---|
| `.btn` `.btn--primary` `.btn--selected` `.btn--sm` `.btn--block` `.btn--danger` `.btn--file` | 40px tall (44 for `--block`). `--selected` is the magenta "picked" state for toggles like "Use this layout". |
| `.link` `.link--muted` | Text actions; underline turns magenta on hover. |
| `.field` (+ `--lead`, `--grow`), `.field-row`, `.field__hint` | Visible label above every input; magenta focus ring. |
| `.chip` `.chip.is-on` | Suggested answers. |
| `.segmented` | Radio group of view options. |
| `.stepper` | − count + with icon buttons. |
| `.tag` (+ `--dot`, `--<status>`) | Run, gate and lesson statuses. `--running` pulses. |
| `.badge--ok/warn/bad` | Audit results, with an icon. |
| `.sev--high/medium/low` | Issue severity. |
| `.callout` (+ `--warn`, `--error`) | Icon + message. Errors use `role="alert"`. |
| `.card` / `.aside-card`, `.card__head` | Bordered surface. |
| `.cand` (+ `.is-picked`) | Direction card: media, body, actions. |
| `.empty`, `.skeleton`, `.spinner` | Empty, loading and working states. |
| `.table` in `.table-wrap` | Mono uppercase head, `.num` right-aligned cells. |
| `.steps` | Run progress: done = ink rule + check, current = magenta rule. |
| `.agent-graph` | Live pipeline; the working agent is magenta. |
| `.tile` | A direction's own look. Its colors and fonts come from `--t-*` set inline; only its sizes follow this system. |

## Icons

`<Icon name="check" />` from `components/Icon.tsx`: 24px grid, 1.75 stroke, `currentColor`, hidden from screen readers unless given a `label`. Don't use emoji or text glyphs (✓ ↗ →) as icons. The one exception is the CSS check in `.steps`.

## Checklist for new UI

- [ ] Only semantic or component tokens; no hex values, no primitives.
- [ ] At most one `.btn--primary` per panel; selection uses `--accent`.
- [ ] Every input has a visible label; every icon-only button has an `aria-label`.
- [ ] Loading, empty and error states exist.
- [ ] Works at 375, 768 and 1440px, in light and dark.
