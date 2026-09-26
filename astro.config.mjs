import { defineConfig } from 'astro/config';

// Served from GitHub Pages at https://romanprigodskii.github.io/indelible/.
// The built site goes to docs/, which Pages serves from the gh-pages branch.
export default defineConfig({
  site: 'https://romanprigodskii.github.io',
  base: '/indelible',
  outDir: './docs',
});
