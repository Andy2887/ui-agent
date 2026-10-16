# HTML contract

The page you produce is the source of truth that another coding agent will rebuild in a real codebase. Every design decision must be visible and named.

- One complete HTML document per page. All CSS in a single `<style>` block in `<head>`. No JavaScript unless the design genuinely needs it (e.g. a mobile nav toggle); if so, small vanilla JS in one `<script>` at the end of `<body>`.
- Plain, hand-written CSS only. No Tailwind, Bootstrap, CDN resets or utility-class systems. Use modern CSS freely: grid, `clamp()`, custom properties, `:has()`, `@keyframes`, `prefers-reduced-motion`.
- Code puts a base layer first in `<head>` (`<style data-base-layer>`, rules inside `@layer base`): box-sizing, zero margins on `body`, `figure` and `blockquote`, inherited fonts on form controls, 1.5em checkboxes and radios, images that shrink to fit, a default `:focus-visible` ring in `--color-primary`, a `.visually-hidden` class and reduced motion. Don't repeat or edit it. Any rule you write outside a layer overrides it.
- All design tokens are CSS custom properties on `:root`: semantic colors (`--color-bg`, `--color-surface`, `--color-text`, `--color-muted`, `--color-primary`, `--color-on-primary`, `--color-accent`, `--color-border`, plus any extra roles you need), font families, a type scale, a spacing scale, radii, shadows, motion durations/easing. Document breakpoints in a comment.
- Component CSS references tokens (`var(--…)`) for colors, fonts, font sizes and spacing. Literal values are acceptable only for hairlines (1px), 0, percentages and layout fractions.
- No inline `style=""` attributes.
- Semantic landmarks: `header`, `nav`, `main`, `section`, `footer`. Exactly one `h1`. Logical heading order.
- Every top-level block (each child of `main`, plus the header and footer) has `data-component="<kebab-name>"` (e.g. `hero`, `feature-grid`, `pricing-table`). Use BEM-style class names.
- Mobile-first media queries at 768 / 1024 / 1280px. No horizontal scrolling at 375px.
- **Balance side-by-side columns.** At 768px and up, columns in the same row must carry comparable weight. When one side is much shorter, make a deliberate choice: give it real content these users need, centre the row vertically, make the short side sticky, or collapse the row to one column. Never leave a large empty area beside or under content, and never push a block to one side with nothing balancing it.
- Icons as inline SVG. Images are CSS/SVG placeholders annotated with `data-placeholder="<name> <WxH>, <what it shows>"`. No external images.
- Fonts: system stacks or Google Fonts only (one `<link>` to fonts.googleapis.com). No other network requests.
- Interaction states for every interactive element: hover, `:focus-visible` (clearly visible), active, and disabled where relevant.
- Accessibility floor: WCAG AA contrast, body text ≥ 16px on mobile, nothing under 12px, tap targets ≥ 44×44px on mobile, `lang` on `<html>`, `<meta name="viewport">`, labels on form fields, `alt`/`aria-label` on meaningful visuals. Respect `prefers-reduced-motion`.
- Realistic, specific copy derived from the prompt. Never lorem ipsum.

## Before you finish, check the page against the audit

Code renders the page at 375, 768 and 1440px and measures it. Each of these fails the audit:
- Any `style=""` attribute, even for a one-off margin or a hidden label. Add a class; use `.visually-hidden` for screen-reader-only text.
- Under 90% of color, background, border, font-family, font-size, margin, padding and gap declarations using `var(--…)`. Hex, `rgb()` and `oklch()` values belong only on `:root`.
- At 375px, a `<p>` or `<li>` inside `<main>` with more than about 60 characters set below 16px (smaller sizes are for short labels only), or any visible text below 12px.
- At 375px, a link, button, input, select or summary smaller than 24×24px, except links inside a sentence. Aim for 44×44px.
- Horizontal scrolling at any viewport: fixed widths, wide tables, nowrap rows or long strings that don't shrink at 375 or 768px.
- A focusable element that looks the same focused and unfocused, e.g. `outline: none` with no replacement.
- Text below WCAG AA contrast (4.5:1, or 3:1 for large text), including muted text on tinted surfaces.
- Not exactly one `<h1>`, a top-level block without `data-component`, a missing doctype, `lang` or viewport meta, or a console error.
- In a multi-page site: no real link to a page this page must reach (`links_to`), or a link to an `.html` file that isn't in the site map.
