import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import react from '@astrojs/react';

// Static output only — this builds to worker/site/dist, which the Worker
// (../wrangler.jsonc's `assets.directory`) serves directly for every path
// that isn't /mcp or /health. Cloudflare serves a matching static file
// before ever invoking the Worker's own fetch handler, so this landing/
// privacy-policy content never wakes the container.
//
// Tailwind is wired in via the official `@tailwindcss/vite` Vite plugin
// (Tailwind v4's supported integration path — the older `@astrojs/tailwind`
// package targets Tailwind v3's PostCSS-based setup and doesn't apply here).
// `@astrojs/react` renders @bundu/ui's React primitives (Button, used by
// its Hero.astro) to static HTML at build time; nothing here needs client-
// side hydration, so no `client:*` directives are used anywhere.
export default defineConfig({
  site: 'https://ynab.nyuchi.com',
  output: 'static',
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
});
