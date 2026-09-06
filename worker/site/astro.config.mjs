import { defineConfig } from 'astro/config';

// Static output only — this builds to worker/site/dist, which the Worker
// (../wrangler.jsonc's `assets.directory`) serves directly for every path
// that isn't /mcp or /health. Cloudflare serves a matching static file
// before ever invoking the Worker's own fetch handler, so this landing/
// privacy-policy content never wakes the container.
export default defineConfig({
  site: 'https://ynab.nyuchi.com',
  output: 'static',
});
