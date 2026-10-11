import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "UI Agent",
  description: "Brief a designer agent on the problem and users, pick a sketch, and get a refined, handoff-ready page.",
};

// App chrome fonts. Each direction's own fonts load on demand next to its sketch.
const APP_FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@600;700&display=swap";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href={APP_FONTS} />
      </head>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header className="topbar">
          <Link href="/" className="brandmark"><span aria-hidden="true">◧</span> UI Agent</Link>
          <nav aria-label="Main">
            <Link href="/">New brief</Link>
            <Link href="/runs">Runs</Link>
            <Link href="/settings">Memory</Link>
          </nav>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
