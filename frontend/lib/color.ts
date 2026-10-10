// OKLCH palette generation + WCAG contrast, mirrored from src/ui_agent/color.py.
import type { Palette } from "./types";

type RGB = [number, number, number];

const hexToRgb = (hex: string): RGB => {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as RGB;
};
const toLin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const fromLin = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const rgbToHex = (rgb: RGB) =>
  "#" + rgb.map((c) => Math.round(Math.min(1, Math.max(0, c)) * 255).toString(16).padStart(2, "0")).join("").toUpperCase();

export const isHex = (s: string) => /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s.trim());
export const normHex = (s: string) => {
  const h = s.trim().replace("#", "");
  return "#" + (h.length === 3 ? h.split("").map((c) => c + c).join("") : h).toUpperCase();
};

export function luminance(hex: string) {
  const [r, g, b] = hexToRgb(hex).map(toLin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a: string, b: string) {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export function hexToOklch(hex: string): [number, number, number] {
  const [r, g, b] = hexToRgb(hex).map(toLin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [L, Math.hypot(A, B), ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360];
}

export function oklchToHex(L: number, C: number, H: number): string {
  let c = C;
  let rgb: RGB = [0, 0, 0];
  for (let i = 0; i < 40; i++) {
    const a = c * Math.cos((H * Math.PI) / 180), b = c * Math.sin((H * Math.PI) / 180);
    const l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s_ = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    rgb = [
      4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
      -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
      -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
    ];
    if (rgb.every((v) => v >= -1e-4 && v <= 1 + 1e-4)) break;
    c *= 0.92;
  }
  return rgbToHex(rgb.map((v) => fromLin(Math.min(1, Math.max(0, v)))) as RGB);
}

/** A 10-step tint/shade scale for display. */
export function scale(hex: string): string[] {
  const [, C, H] = hexToOklch(hex);
  return [0.97, 0.93, 0.86, 0.77, 0.67, 0.57, 0.48, 0.39, 0.3, 0.22].map((L) => oklchToHex(L, C * (L > 0.9 ? 0.35 : 1), H));
}

function shiftUntil(color: string, against: string, required: number) {
  let [L, C, H] = hexToOklch(color);
  const step = luminance(against) < 0.18 ? 0.01 : -0.01;
  let out = color;
  for (let i = 0; i < 100 && contrast(out, against) < required; i++) {
    L = Math.min(1, Math.max(0, L + step));
    out = oklchToHex(L, C, H);
  }
  return out;
}

export type Adjustment = { role: string; from: string; to: string; reason: string };

/** Build a whole palette around one brand color; adjust within the hue if contrast fails. */
export function paletteFromBrand(hex: string, theme: "light" | "dark"): { palette: Palette; adjustments: Adjustment[] } {
  const brand = normHex(hex);
  const [L, C, H] = hexToOklch(brand);
  const nc = Math.min(C * 0.12, 0.015);
  const adjustments: Adjustment[] = [];
  let p: Palette;
  if (theme === "dark") {
    p = {
      bg: oklchToHex(0.17, nc, H), surface: oklchToHex(0.22, nc, H), text: oklchToHex(0.95, nc * 0.6, H),
      muted: oklchToHex(0.75, nc, H), primary: oklchToHex(Math.max(L, 0.68), C, H), on_primary: oklchToHex(0.18, nc, H),
      accent: oklchToHex(0.78, C * 0.8, (H + 40) % 360), border: oklchToHex(0.32, nc, H),
    };
  } else {
    p = {
      bg: oklchToHex(0.985, nc * 0.5, H), surface: "#FFFFFF", text: oklchToHex(0.22, nc, H), muted: oklchToHex(0.46, nc, H),
      primary: brand, on_primary: "#FFFFFF", accent: oklchToHex(0.55, C * 0.9, (H + 40) % 360), border: oklchToHex(0.9, nc, H),
    };
    const dark = oklchToHex(0.2, nc, H);
    if (contrast("#FFFFFF", p.primary) < 4.5 && contrast(dark, p.primary) >= 4.5) p.on_primary = dark;
  }
  const fix = (role: keyof Palette, against: string, req: number, reason: string) => {
    if (contrast(p[role], against) >= req) return;
    const to = shiftUntil(p[role], against, req);
    adjustments.push({ role, from: p[role], to, reason });
    p[role] = to;
  };
  fix("primary", p.on_primary, 4.5, "button text needs 4.5:1 on the button");
  fix("primary", p.bg, 3, "buttons need 3:1 against the page");
  fix("accent", p.bg, 3, "accents need 3:1 against the page");
  return { palette: p, adjustments };
}

export const PAIRS: [keyof Palette, keyof Palette, number, string][] = [
  ["text", "bg", 4.5, "Body text"],
  ["muted", "bg", 4.5, "Secondary text"],
  ["on_primary", "primary", 4.5, "Button label"],
  ["primary", "bg", 3, "Button vs page"],
  ["accent", "bg", 3, "Accent vs page"],
];
