"use client";
import type { ReactNode } from "react";

export function OptionCard({ selected, onSelect, title, hint, sample, badge, multi, disabled }: {
  selected: boolean; onSelect: () => void; title: string; hint?: string; sample?: ReactNode;
  badge?: string; multi?: boolean; disabled?: boolean;
}) {
  return (
    <button type="button" className={`option ${selected ? "is-selected" : ""}`} aria-pressed={selected}
      onClick={onSelect} disabled={disabled && !selected}>
      {sample && <div className="option__sample">{sample}</div>}
      <div className="option__label">
        <span className={`option__mark ${multi ? "option__mark--multi" : ""}`} aria-hidden="true" />
        <span className="option__title">{title}</span>
        {badge && <span className="tag tag--rec">{badge}</span>}
      </div>
      {hint && <p className="option__hint">{hint}</p>}
    </button>
  );
}

export function Section({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section className="setup-section" id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <header className="setup-section__head">
        <h2 id={id ? `${id}-h` : undefined}>{title}</h2>
        {hint && <p>{hint}</p>}
      </header>
      {children}
    </section>
  );
}
