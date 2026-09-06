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

// [label, foreground, background, minimum |Lc|]
const PAIRS = [
  // Dark theme (default)
  ["dark: body text on page background", "#F3F3F1", "#0E0D0C", 75],
  ["dark: secondary text on page background", "#B8B3A8", "#0E0D0C", 60],
  ["dark: secondary text on card background", "#B8B3A8", "#131211", 60],
  ["dark: accent/link text on page background", "#FFD740", "#0E0D0C", 60],
  ["dark: accent/link text on card background", "#FFD740", "#131211", 60],
  ["dark: 'done' pill text on its background", "#7CD992", "#17301F", 60],
  ["dark: 'action' pill text on its background", "#FFD740", "#35301A", 60],
  ["dark: 'blocked' pill text on its background", "#F2B8B5", "#3A211F", 60],

  // Light theme
  ["light: body text on page background", "#1A1918", "#F3F3F1", 75],
  ["light: secondary text on page background", "#55514B", "#F3F3F1", 60],
  ["light: secondary text on card background", "#55514B", "#EEEEEC", 60],
  ["light: accent/link text on page background", "#5D4037", "#F3F3F1", 60],
  ["light: accent/link text on card background", "#5D4037", "#EEEEEC", 60],
  ["light: 'done' pill text on its background", "#166B3A", "#E4F3E9", 60],
  ["light: 'action' pill text on its background", "#8A5A00", "#FBEFD8", 60],
  ["light: 'blocked' pill text on its background", "#B3261E", "#FBE4E2", 60],
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
