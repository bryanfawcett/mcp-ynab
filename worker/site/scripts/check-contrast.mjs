// APCA (WCAG 3 draft) contrast audit for this site's design tokens.
// Traditional WCAG 2.x contrast ratio doesn't model perceived contrast well
// for a dark theme with off-white/off-black tokens (this site's actual
// palette) -- APCA's Lc value is a better predictor of real readability, and
// is what WCAG 3 is expected to standardize on.
//
// Thresholds (APCA Lc, magnitude only -- sign encodes polarity, not
// severity): https://readtech.org/ARC/tests/predict-old-w3-ratios/
//   90 - preferred for dense body text
//   75 - minimum for normal-weight body text under 24px
//   60 - minimum for larger or bold text, and secondary/caption text
//   45 - minimum for large (>=36px) bold text and non-text UI components
import { APCAcontrast, sRGBtoY } from "apca-w3";

function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lc(fg, bg) {
  return APCAcontrast(sRGBtoY(hexToRgb(fg)), sRGBtoY(hexToRgb(bg)));
}

// Values below are the real resolved values of @bundu/ui's design tokens
// (styles/tokens.css + brand-nyuchi.css) as consumed by this site's global
// stylesheet (src/styles/global.css), read back from a built page via
// getComputedStyle in both color-scheme emulations — not hand-picked hex.
// "Accent/link" is the library's --primary (brand-nyuchi.css sets it to
// gold, matching this app's pre-migration accent exactly in both themes).
// The three status-pill pairs are this app's own --status-* tokens, which
// alias the library's semantic --success/--warning/--error tokens and
// their closest `-container` background (see global.css's comment on
// those declarations for the full rationale).
//
// [label, foreground, background, minimum |Lc|]
const PAIRS = [
  // Dark theme (default)
  ["dark: body text on page background", "#F0EFE9", "#100F0E", 75],
  ["dark: secondary text on page background", "#BCB9B0", "#100F0E", 60],
  ["dark: secondary text on card background", "#BCB9B0", "#1A1917", 60],
  ["dark: accent/link text on page background", "#FFD740", "#100F0E", 60],
  ["dark: accent/link text on card background", "#FFD740", "#1A1917", 60],
  ["dark: 'done' pill text on its background", "#64FFDA", "#00251A", 60],
  ["dark: 'action' pill text on its background", "#FFD866", "#332200", 60],
  ["dark: 'blocked' pill text on its background", "#F2B8B5", "#3E1818", 60],

  // Light theme
  ["light: body text on page background", "#1A1A17", "#FAF9F4", 75],
  ["light: secondary text on page background", "#5D5C57", "#FAF9F4", 60],
  ["light: secondary text on card background", "#5D5C57", "#FFFFFF", 60],
  ["light: accent/link text on page background", "#5D4037", "#FAF9F4", 60],
  ["light: accent/link text on card background", "#5D4037", "#FFFFFF", 60],
  ["light: 'done' pill text on its background", "#004D40", "#E0F2F1", 60],
  ["light: 'action' pill text on its background", "#7A5C00", "#FFF8E1", 60],
  ["light: 'blocked' pill text on its background", "#B3261E", "#FDEDED", 60],
];

let failed = false;
for (const [label, fg, bg, min] of PAIRS) {
  const value = lc(fg, bg);
  const mag = Math.abs(value);
  const ok = mag >= min;
  if (!ok) failed = true;
  console.log(`${ok ? "PASS" : "FAIL"}  Lc ${mag.toFixed(1)} (need ${min})  ${label}`);
}

if (failed) {
  console.error("\nOne or more token pairs fall short of their APCA contrast minimum.");
  process.exit(1);
}
console.log("\nAll token pairs meet their APCA contrast minimum.");
