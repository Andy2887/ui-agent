You write HANDOFF.md: the integration spec a coding agent (e.g. Claude Code) will use to rebuild this page in a new project. The HTML is the visual source of truth; your document makes its structure and intent explicit.

Write Markdown with these sections:
1. **Overview**: what the page is, the design character in 2–3 sentences.
2. **How to build from this**: set up tokens as the theme first, build components top-down, then compare against `screenshots/` at 375, 768 and 1440px.
3. **Component inventory**: one subsection per `data-component`: purpose, structure (key elements and BEM classes), variants, interaction states, responsive behavior.
4. **Tokens**: a table of the `:root` custom properties grouped by kind, with the role of each.
5. **Placeholders and assets**: every `data-placeholder`, with what to supply.
6. **Accessibility notes**: landmarks, heading outline, focus handling, contrast, motion.
7. **Known limitations**: remaining low-severity issues and anything the HTML only approximates.

Be specific and concise. Do not repeat the CSS verbatim.
