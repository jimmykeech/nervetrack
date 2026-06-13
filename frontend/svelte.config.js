import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // `<label>` is used as a field caption above steppers/toggles and native
    // inputs throughout; suppress the "must wrap a control" a11y warning.
    warningFilter: (w) => w.code !== 'a11y_label_has_associated_control'
  },
  kit: {
    adapter: adapter()
  }
};

export default config;
