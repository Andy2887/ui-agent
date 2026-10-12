# HTML contract

The page you produce is the source of truth that another coding agent will rebuild in a real codebase. Every design decision must be visible and named.

- One complete `index.html`. All CSS in a single `<style>` block in `<head>`. No JavaScript unless the design genuinely needs it (e.g. a mobile nav toggle); if so, small vanilla JS in one `<script>` at the end of `<body>`.
- Plain, hand-written CSS only. No Tailwind, Bootstrap, CDN resets or utility-class systems. Use modern CSS freely: grid, `clamp()`, custom properties, `:has()`, `@keyframes`, `prefers-reduced-motion`.
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
