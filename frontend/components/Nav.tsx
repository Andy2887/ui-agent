"use client";
// Top bar navigation; marks the current section. The root layout wraps <Nav> in Suspense and falls back to
// <NavLinks path="" /> (no section marked), since reading the path would otherwise block prerendering.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./Icon";

const LINKS = [{ href: "/runs", label: "Runs" }, { href: "/settings", label: "Memory" }];

export function Nav() {
  return <NavLinks path={usePathname()} />;
}

export function NavLinks({ path }: { path: string }) {
  return (
    <nav className="topbar__nav" aria-label="Main">
      {LINKS.map((l) => {
        const on = path === l.href || path.startsWith(`${l.href}/`);
        return <Link key={l.href} href={l.href} className="topbar__link" aria-current={on ? "page" : undefined}>{l.label}</Link>;
      })}
      <Link href="/" className="btn btn--primary btn--sm" aria-current={path === "/" ? "page" : undefined}><Icon name="plus" size={14} />New brief</Link>
    </nav>
  );
}
