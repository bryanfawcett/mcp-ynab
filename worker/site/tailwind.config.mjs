// Tailwind v4 CSS-first configuration handles content detection and most
// theme setup on its own, but @bundu/ui ships its theme extension (the
// seven-mineral color scale, the fluid type scale, radius/spacing tokens)
// as a v3-style JS preset (`tailwind-preset.mjs`) rather than CSS `@theme`
// blocks. Tailwind v4 still supports loading a JS config — including its
// `presets` — via the `@config` directive in src/styles/global.css, which
// is what pulls this file (and therefore the preset) in.
import preset from '@bundu/ui/tailwind-preset';

/** @type {import('tailwindcss').Config} */
export default {
  presets: [preset],
};
