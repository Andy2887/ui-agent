import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Mark } from "@/components/Icon";
import { Nav, NavLinks } from "@/components/Nav";
import "./tokens.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "UI Agent",
  description: "Brief a designer agent on the problem and users, pick a sketch, and get a refined, handoff-ready page.",
};

// App chrome fonts. Each direction's own fonts load on demand next to its sketch.
const APP_FONTS = "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap";

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
          <Link href="/" className="brandmark"><Mark />UI Agent</Link>
          <Suspense fallback={<NavLinks path="" />}><Nav /></Suspense>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
