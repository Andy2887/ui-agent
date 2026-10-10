import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "UI Agent",
  description: "Explore design directions, pick one, and get a refined, handoff-ready page.",
};

// Fonts used by the option samples (every preset pairing + style sample), loaded once.
const SAMPLE_FONTS =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700&family=DM+Sans:wght@400;500" +
  "&family=Nunito:wght@700;800&family=Nunito+Sans:wght@400;600&family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@400;600" +
  "&family=JetBrains+Mono:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;700" +
  "&family=Cormorant+Garamond:wght@500;600&family=Jost:wght@400;500&display=swap";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href={SAMPLE_FONTS} />
      </head>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header className="topbar">
          <Link href="/" className="brandmark"><span aria-hidden="true">◧</span> UI Agent</Link>
          <nav aria-label="Main">
            <Link href="/">New design</Link>
            <Link href="/runs">Runs</Link>
            <Link href="/settings">Memory</Link>
          </nav>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
