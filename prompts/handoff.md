You write HANDOFF.md: the integration spec a coding agent (e.g. Claude Code) will use to rebuild this small multi-page site in a new project. Each `<page>` is that page's HTML and its visual source of truth; the page marked `key="true"` was designed first and set the shared design system. Your document makes the site's structure and intent explicit.

Write Markdown with these sections:
1. **Overview**: what the site is, its pages in one line each, and the design character in 2–3 sentences.
2. **How to build from this**: set up tokens as the theme first, build the shared shell and components next, then each page top-down, wiring links as in FLOWS.md. Compare each page against `screenshots/<page>/` at 375, 768 and 1440px.
3. **Routes and flows**: one route per page file, and each flow as the sequence of routes it walks, with the element the user clicks at each step.
4. **Shared components**: the header, footer and every component used on more than one page: purpose, structure (key elements and BEM classes), variants, interaction states, responsive behavior. Note where pages use a component differently.
5. **Page-specific components**: per page, each `data-component` that appears only there, described the same way.
6. **Tokens**: a table of the `:root` custom properties grouped by kind, with the role of each. They are shared by every page.
7. **Placeholders and assets**: every `data-placeholder`, per page, with what to supply.
8. **Accessibility notes**: landmarks, heading outline per page, `aria-current` in the nav, focus handling, contrast, motion.
9. **Known limitations**: remaining issues (per page) and anything the HTML only approximates.

Be specific and concise. Do not repeat the CSS verbatim.
